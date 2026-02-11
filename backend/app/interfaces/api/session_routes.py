from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, Query
from sse_starlette.sse import EventSourceResponse
from typing import AsyncGenerator, List, Optional
from sse_starlette.event import ServerSentEvent
from datetime import datetime
import asyncio
import websockets
import logging
from app.interfaces.dependencies import get_file_service

from app.application.services.agent_service import AgentService
from app.application.services.token_service import TokenService
from app.application.errors.exceptions import NotFoundError, UnauthorizedError
from app.interfaces.dependencies import get_agent_service, get_current_user, get_optional_current_user, get_token_service, verify_signature_websocket
from app.interfaces.schemas.base import APIResponse
from app.interfaces.schemas.session import (
    ChatRequest, ShellViewRequest, CreateSessionResponse, GetSessionResponse,
    ListSessionItem, ListSessionResponse, ShellViewResponse,
    ShareSessionResponse, SharedSessionResponse
)
from app.interfaces.schemas.file import FileViewRequest, FileViewResponse
from app.interfaces.schemas.resource import AccessTokenRequest, SignedUrlResponse
from app.interfaces.schemas.event import EventMapper
from app.domain.models.file import FileInfo
from app.domain.models.user import User

logger = logging.getLogger(__name__)
SESSION_POLL_INTERVAL = 5

router = APIRouter(prefix="/sessions", tags=["sessions"])

# 前端在“新建会话/新任务”时通常先调用 PUT /sessions 获取一个新的 session_id，然后再进入聊天并发送消息
@router.put("", response_model=APIResponse[CreateSessionResponse])
async def create_session(
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service)
) -> APIResponse[CreateSessionResponse]:
    session = await agent_service.create_session(current_user.id)
    return APIResponse.success(
        CreateSessionResponse(
            session_id=session.id,
        )
    )

@router.get("/{session_id}", response_model=APIResponse[GetSessionResponse])
async def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service)
) -> APIResponse[GetSessionResponse]:
    session = await agent_service.get_session(session_id, current_user.id)
    if not session:
        raise NotFoundError("Session not found")
    return APIResponse.success(GetSessionResponse(
        session_id=session.id,
        title=session.title,
        status=session.status,
        events=await EventMapper.events_to_sse_events(session.events),
        is_shared=session.is_shared
    ))

@router.delete("/{session_id}", response_model=APIResponse[None])
async def delete_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service)
) -> APIResponse[None]:
    await agent_service.delete_session(session_id, current_user.id)
    return APIResponse.success()

@router.post("/{session_id}/stop", response_model=APIResponse[None])
async def stop_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service)
) -> APIResponse[None]:
    await agent_service.stop_session(session_id, current_user.id)
    return APIResponse.success()

@router.post("/{session_id}/clear_unread_message_count", response_model=APIResponse[None])
async def clear_unread_message_count(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service)
) -> APIResponse[None]:
    await agent_service.clear_unread_message_count(session_id, current_user.id)
    return APIResponse.success()

@router.get("", response_model=APIResponse[ListSessionResponse])
async def get_all_sessions(
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service)
) -> APIResponse[ListSessionResponse]:
    sessions = await agent_service.get_all_sessions(current_user.id)
    session_items = [
        ListSessionItem(
            session_id=session.id,
            title=session.title,
            status=session.status,
            unread_message_count=session.unread_message_count,
            latest_message=session.latest_message,
            latest_message_at=int(session.latest_message_at.timestamp()) if session.latest_message_at else None,
            is_shared=session.is_shared
        ) for session in sessions
    ]
    return APIResponse.success(ListSessionResponse(sessions=session_items))

@router.post("")
async def stream_sessions(
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service)
) -> EventSourceResponse:
    async def event_generator() -> AsyncGenerator[ServerSentEvent, None]:
        while True:
            sessions = await agent_service.get_all_sessions(current_user.id)
            session_items = [
                ListSessionItem(
                    session_id=session.id,
                    title=session.title,
                    status=session.status,
                    unread_message_count=session.unread_message_count,
                    latest_message=session.latest_message,
                    latest_message_at=int(session.latest_message_at.timestamp()) if session.latest_message_at else None,
                    is_shared=session.is_shared
                ) for session in sessions
            ]
            yield ServerSentEvent(
                event="sessions",
                data=ListSessionResponse(sessions=session_items).model_dump_json()
            )
            await asyncio.sleep(SESSION_POLL_INTERVAL)
    return EventSourceResponse(event_generator())

# 这段是 **聊天接口的 SSE 流式返回**：
# - `@router.post("/{session_id}/chat")`：定义聊天入口，拿到 `session_id`、`ChatRequest`、当前用户和 `AgentService`。
# - `event_generator()`：异步生成器。  
#   - 调用 `agent_service.chat(...)`，它会不断产出领域事件（plan/step/tool/message 等）。
#   - 每个事件先经过 `EventMapper.event_to_sse_event()` 转成 SSE 可发送的结构。
#   - 如果有结果，就 `yield ServerSentEvent(event=..., data=...)`，把事件类型和 JSON 数据推给前端。
# - `return EventSourceResponse(event_generator())`：把这个生成器包装成 SSE 响应流，前端能边执行边收到事件。
# 简而言之：**这是“聊天请求 → 后端流式产出事件 → 通过 SSE 推送给前端”的核心桥梁**。
#
# 这里的 `yield` 是在 **异步生成器** 里“逐条产出”结果。
# 具体作用：
# - `event_generator()` 是 `async def`，返回一个**异步生成器**。
# - `yield ServerSentEvent(...)` 会把**当前这一条 SSE 事件**推送给 `EventSourceResponse`。
# - 函数不会结束，而是等下一次事件再继续 `yield`，所以前端能实时收到一条条事件流。
# 简而言之：`yield` 让 SSE 变成 **边生成边推送** 的流式输出。
@router.post("/{session_id}/chat")
async def chat(
    session_id: str,
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service)
) -> EventSourceResponse:
    async def event_generator() -> AsyncGenerator[ServerSentEvent, None]:
        async for event in agent_service.chat(
            session_id=session_id,
            user_id=current_user.id,
            message=request.message,
            timestamp=datetime.fromtimestamp(request.timestamp) if request.timestamp else None,
            event_id=request.event_id,
            attachments=request.attachments
        ):
            logger.debug(f"Received event from chat: {event}")
            sse_event = await EventMapper.event_to_sse_event(event)
            logger.debug(f"Received event: {sse_event}")
            if sse_event:
                yield ServerSentEvent(
                    event=sse_event.event,
                    data=sse_event.data.model_dump_json() if sse_event.data else None
                )

    return EventSourceResponse(event_generator())

@router.post("/{session_id}/shell")
async def view_shell(
    session_id: str,
    request: ShellViewRequest,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service)
) -> APIResponse[ShellViewResponse]:
    """View shell session output
    
    If the agent does not exist or fails to get shell output, an appropriate exception will be thrown and handled by the global exception handler
    
    Args:
        session_id: Session ID
        request: Shell view request containing session ID
        
    Returns:
        APIResponse with shell output
    """
    result = await agent_service.shell_view(session_id, request.session_id, current_user.id)
    return APIResponse.success(result)

@router.post("/{session_id}/file")
async def view_file(
    session_id: str,
    request: FileViewRequest,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service)
) -> APIResponse[FileViewResponse]:
    """View file content
    
    If the agent does not exist or fails to get file content, an appropriate exception will be thrown and handled by the global exception handler
    
    Args:
        session_id: Session ID
        request: File view request containing file path
        
    Returns:
        APIResponse with file content
    """
    result = await agent_service.file_view(session_id, request.file, current_user.id)
    return APIResponse.success(result)

@router.websocket("/{session_id}/vnc")
async def vnc_websocket(
    websocket: WebSocket,
    session_id: str,
    signature: str = Depends(verify_signature_websocket),#signatur没有使用，是为触发FastAPI验证签名
    agent_service: AgentService = Depends(get_agent_service)
) -> None:
    """VNC WebSocket endpoint (binary mode)
    
    Establishes a connection with the VNC WebSocket service in the sandbox environment and forwards data bidirectionally
    Supports authentication via signed URL with signature verification
    
    Args:
        websocket: WebSocket connection
        session_id: Session ID
        signature: Verified signature from dependency injection
    """
    # 这是 WebSocket 握手的服务端接受操作。subprotocol="binary" 指定了子协议为 binary（二进制），告知客户端（前端 noVNC）本连接将以二进制模式传输数据。
    # 这两行的时序关系：
    # 前端发起 WebSocket 连接请求 ws://.../session/xxx/vnc?signature=abc123
    # FastAPI 先执行 Depends(verify_signature_websocket) 验证签名 ← 第 222 行
    # 验证通过后，服务端接受 WebSocket 握手，协商 binary 子协议 ← 第 236 行
    # 之后才开始双向数据转发
    # 如果第 2 步签名验证失败，就不会执行到第 3 步，连接直接被拒绝。
    await websocket.accept(subprotocol="binary")
    logger.info(f"Accepted WebSocket connection for session {session_id}")
    
    try:
        # ======================================================================
        # WebSocket 双向代理：VNC 远程桌面转发
        # 
        # 架构链路（对应架构图中的 "websocket forward" 模块）：
        #
        #   Manus Web (noVNC)  <--WebSocket-->  Manus Server  <--WebSocket-->  Ubuntu Sandbox (websockify)
        #        前端                          本段代码(代理)                       沙箱
        #
        # 沙箱内部链路：websockify -> x11vnc -> xvfb（虚拟帧缓冲）
        # 前端 noVNC 组件通过本代理与沙箱内的 websockify 通信，实现远程桌面访问。
        # ======================================================================

        # 根据 session_id 获取沙箱的 websockify 地址（即 VNC over WebSocket 的 URL）
        sandbox_ws_url = await agent_service.get_vnc_url(session_id)

        logger.info(f"Connecting to VNC WebSocket at {sandbox_ws_url}")
    
        # 与沙箱内的 websockify 建立 WebSocket 连接（Manus Server -> Sandbox 的右半段链路）
        async with websockets.connect(sandbox_ws_url) as sandbox_ws:
            logger.info(f"Connected to VNC WebSocket at {sandbox_ws_url}")

            # --- 上行通道：noVNC(前端) -> Manus Server -> websockify(沙箱) ---
            # 用户在前端 noVNC 上的操作（鼠标移动/点击、键盘输入等）
            # 被编码为 RFB 协议二进制帧，经由本代理转发到沙箱的 websockify
            async def forward_to_sandbox():
                try:    
                    while True:
                        # 接收前端 noVNC 发来的二进制数据（RFB 协议帧）
                        data = await websocket.receive_bytes()
                        # 原样转发给沙箱的 websockify
                        await sandbox_ws.send(data)
                except WebSocketDisconnect:
                    # 前端断开（用户关闭/刷新页面），上行通道正常结束
                    logger.info("Web -> VNC connection closed")
                    pass
                except Exception as e:
                    logger.error(f"Error forwarding data to sandbox: {e}")
            
            # --- 下行通道：websockify(沙箱) -> Manus Server -> noVNC(前端) ---
            # 沙箱桌面的画面变化由 xvfb -> x11vnc -> websockify 产生，
            # 本代理将这些画面更新帧转发给前端 noVNC 进行渲染
            async def forward_from_sandbox():
                try:
                    while True:
                        # 接收沙箱 websockify 发来的二进制数据（屏幕更新帧）
                        data = await sandbox_ws.recv()
                        # 原样转发给前端 noVNC
                        await websocket.send_bytes(data)
                except websockets.exceptions.ConnectionClosed:
                    # 沙箱端连接关闭（沙箱销毁/重启等），下行通道正常结束
                    logger.info("VNC -> Web connection closed")
                    pass
                except Exception as e:
                    logger.error(f"Error forwarding data from sandbox: {e}")
            
            # 将上行和下行两个通道，分别作为异步任务并发运行，形成全双工代理
            forward_task1 = asyncio.create_task(forward_to_sandbox())
            forward_task2 = asyncio.create_task(forward_from_sandbox())
            
            # 等待任一通道关闭——任一方向断开意味着代理链路已失效
            done, pending = await asyncio.wait(
                [forward_task1, forward_task2],
                return_when=asyncio.FIRST_COMPLETED
            )

            logger.info("WebSocket connection closed")
            
            # 取消另一个仍在运行的通道，防止协程泄漏
            for task in pending:
                task.cancel()
    
    except ConnectionError as e:
        logger.error(f"Unable to connect to sandbox environment: {str(e)}")
        await websocket.close(code=1011, reason=f"Unable to connect to sandbox environment: {str(e)}")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        await websocket.close(code=1011, reason=f"WebSocket error: {str(e)}")

@router.get("/{session_id}/files")
async def get_session_files(
    session_id: str,
    current_user: Optional[User] = Depends(get_optional_current_user),
    agent_service: AgentService = Depends(get_agent_service)
) -> APIResponse[List[FileInfo]]:
    if not current_user and not await agent_service.is_session_shared(session_id):
        raise UnauthorizedError()
    files = await agent_service.get_session_files(session_id, current_user.id if current_user else None)
    return APIResponse.success(files)


@router.post("/{session_id}/vnc/signed-url", response_model=APIResponse[SignedUrlResponse])
async def create_vnc_signed_url(
    session_id: str,
    request_data: AccessTokenRequest,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service),
    token_service: TokenService = Depends(get_token_service)
) -> APIResponse[SignedUrlResponse]:
    """Generate signed URL for VNC WebSocket access
    
    This endpoint creates a signed URL that allows temporary access to the VNC
    WebSocket for a specific session without requiring authentication headers.
    """
    
    # Validate expiration time (max 15 minutes)
    expire_minutes = request_data.expire_minutes
    if expire_minutes > 15:
        expire_minutes = 15
    
    # Check if session exists and belongs to user
    session = await agent_service.get_session(session_id, current_user.id)
    if not session:
        raise NotFoundError("Session not found")
    
    # Create signed URL for VNC WebSocket
    ws_base_url = f"/api/v1/sessions/{session_id}/vnc"
    signed_url = token_service.create_signed_url(
        base_url=ws_base_url,
        expire_minutes=expire_minutes
    )
    
    logger.info(f"Created signed URL for VNC access for user {current_user.id}, session {session_id}")
    
    return APIResponse.success(SignedUrlResponse(
        signed_url=signed_url,
        expires_in=expire_minutes * 60,
    ))


@router.post("/{session_id}/share", response_model=APIResponse[ShareSessionResponse])
async def share_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service)
) -> APIResponse[ShareSessionResponse]:
    """Share a session to make it publicly accessible
    
    This endpoint marks a session as shared, allowing it to be accessed
    without authentication using the shared session endpoint.
    """
    await agent_service.share_session(session_id, current_user.id)
    return APIResponse.success(ShareSessionResponse(
        session_id=session_id,
        is_shared=True
    ))

@router.get("/{session_id}/share/files")
async def get_shared_session_files(
    session_id: str,
    agent_service: AgentService = Depends(get_agent_service)
) -> APIResponse[List[FileInfo]]:
    files = await agent_service.get_shared_session_files(session_id)
    for file in files:
        await get_file_service().enrich_with_file_url(file)
    return APIResponse.success(files)


@router.delete("/{session_id}/share", response_model=APIResponse[ShareSessionResponse])
async def unshare_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    agent_service: AgentService = Depends(get_agent_service)
) -> APIResponse[ShareSessionResponse]:
    """Unshare a session to make it private again
    
    This endpoint marks a session as not shared, removing public access.
    """
    await agent_service.unshare_session(session_id, current_user.id)
    return APIResponse.success(ShareSessionResponse(
        session_id=session_id,
        is_shared=False
    ))


@router.get("/shared/{session_id}", response_model=APIResponse[SharedSessionResponse])
async def get_shared_session(
    session_id: str,
    agent_service: AgentService = Depends(get_agent_service)
) -> APIResponse[SharedSessionResponse]:
    """Get a shared session without authentication
    
    This endpoint allows public access to sessions that have been marked as shared.
    No authentication is required, but the session must be explicitly shared.
    """
    session = await agent_service.get_shared_session(session_id)
    if not session:
        raise NotFoundError("Shared session not found")
    
    return APIResponse.success(SharedSessionResponse(
        session_id=session.id,
        title=session.title,
        status=session.status,
        events=await EventMapper.events_to_sse_events(session.events),
        is_shared=session.is_shared
    ))