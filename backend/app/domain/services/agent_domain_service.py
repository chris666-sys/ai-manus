from typing import Optional, AsyncGenerator, List
import logging
import time
from datetime import datetime
from app.domain.models.session import Session, SessionStatus
from app.domain.external.llm import LLM
from app.domain.external.sandbox import Sandbox
from app.domain.external.search import SearchEngine
from app.domain.models.event import BaseEvent, ErrorEvent, DoneEvent, MessageEvent, WaitEvent, AgentEvent
from pydantic import TypeAdapter
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.repositories.session_repository import SessionRepository
from app.domain.services.agent_task_runner import AgentTaskRunner
from app.domain.external.task import Task
from app.domain.utils.json_parser import JsonParser
from typing import Type
from app.domain.external.file import FileStorage
from app.domain.models.file import FileInfo
from app.domain.repositories.mcp_repository import MCPRepository

# Setup logging
logger = logging.getLogger(__name__)

class AgentDomainService:
    """
    Agent domain service, responsible for coordinating the work of planning agent and execution agent
    """
    
    def __init__(
        self,
        agent_repository: AgentRepository,
        session_repository: SessionRepository,
        llm: LLM,
        sandbox_cls: Type[Sandbox],
        task_cls: Type[Task],
        json_parser: JsonParser,
        file_storage: FileStorage,
        mcp_repository: MCPRepository,
        search_engine: Optional[SearchEngine] = None,
    ):
        self._repository = agent_repository
        self._session_repository =session_repository
        self._llm = llm
        self._sandbox_cls = sandbox_cls
        self._search_engine = search_engine
        self._task_cls = task_cls
        self._json_parser = json_parser
        self._file_storage = file_storage
        self._mcp_repository = mcp_repository
        logger.info("AgentDomainService initialization completed")
            
    async def shutdown(self) -> None:
        """Clean up all Agent's resources"""
        logger.info(f"Starting to close all Agents")
        await self._task_cls.destroy()
        logger.info("All agents closed successfully")

    async def _create_task(self, session: Session) -> Task:
        """Create a new agent task"""
        sandbox = None
        sandbox_id = session.sandbox_id
        if sandbox_id:
            sandbox = await self._sandbox_cls.get(sandbox_id)
        if not sandbox:
            sandbox = await self._sandbox_cls.create()
            session.sandbox_id = sandbox.id
            await self._session_repository.save(session)
        browser = await sandbox.get_browser()
        if not browser:
            logger.error(f"Failed to get browser for Sandbox {sandbox_id}")
            raise RuntimeError(f"Failed to get browser for Sandbox {sandbox_id}")
        
        await self._session_repository.save(session)

        task_runner = AgentTaskRunner(
            session_id=session.id,
            agent_id=session.agent_id,
            user_id=session.user_id,
            llm=self._llm,
            sandbox=sandbox,
            browser=browser,
            file_storage=self._file_storage,
            search_engine=self._search_engine,
            session_repository=self._session_repository,
            json_parser=self._json_parser,
            agent_repository=self._repository,
            mcp_repository=self._mcp_repository,
        )

        task = self._task_cls.create(task_runner)
        session.task_id = task.id
        await self._session_repository.save(session)

        return task
        
    async def _get_task(self, session: Session) -> Optional[Task]:
        """Get a task for the given session"""

        task_id = session.task_id
        if not task_id:
            return None
        
        return self._task_cls.get(task_id)

    async def stop_session(self, session_id: str) -> None:
        """Stop a session"""
        session = await self._session_repository.find_by_id(session_id)
        if not session:
            logger.error(f"Attempted to stop non-existent Session {session_id}")
            raise RuntimeError("Session not found")
        task = await self._get_task(session)
        if task:
            task.cancel()
        await self._session_repository.update_status(session_id, SessionStatus.COMPLETED)

    async def chat(
        self,
        session_id: str,
        user_id: str,
        message: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        latest_event_id: Optional[str] = None,
        attachments: Optional[List[dict]] = None
    ) -> AsyncGenerator[BaseEvent, None]:
        """
        Chat with an agent
        """

        try:
            # 1) 校验会话归属与存在性，避免用户访问他人或不存在的会话
            session = await self._session_repository.find_by_id_and_user_id(session_id, user_id)
            if not session:
                logger.error(f"Attempted to chat with non-existent Session {session_id} for user {user_id}")
                raise RuntimeError("Session not found")

            # 2) 获取当前会话对应的任务（若已存在则复用）
            task = await self._get_task(session)

            # 3) 如果有新消息，确保任务处于可运行状态并写入输入流
            if message:
                # 会话不在运行中则创建新任务，保证后续可消费输入流
                if session.status != SessionStatus.RUNNING:
                    task = await self._create_task(session)
                    if not task:
                        raise RuntimeError("Failed to create task")
                
                # 更新会话的最新消息与时间戳，便于历史记录与列表展示
                await self._session_repository.update_latest_message(session_id, message, timestamp or datetime.now())

                # 组装用户消息事件（包含附件），用于驱动后端流程
                message_event = MessageEvent(
                    message=message, 
                    role="user", 
                    attachments=[FileInfo(file_id=attachment["file_id"], filename=attachment["filename"]) for attachment in attachments] if attachments else None
                )

                # 将消息写入任务输入流，触发 Plan-Act 处理
                event_id = await task.input_stream.put(message_event.model_dump_json())

                # 记录事件 ID 并持久化，保证事件可回放
                message_event.id = event_id
                await self._session_repository.add_event(session_id, message_event)
                
                # 启动或唤醒任务执行（异步流式输出）
                await task.run()
                logger.debug(f"Put message into Session {session_id}'s event queue: {message[:50]}...")
            
            logger.info(f"Session {session_id} started")
            logger.debug(f"Session {session_id} task: {task}")
           
            # 4) 轮询任务输出流，将事件逐条产出（供 SSE 转发）
            while task and not task.done:
                # 使用 start_id 支持断点续读；block_ms=0 表示非阻塞轮询
                event_id, event_str = await task.output_stream.get(start_id=latest_event_id, block_ms=0)
                latest_event_id = event_id
                if event_str is None:
                    logger.debug(f"No event found in Session {session_id}'s event queue")
                    continue
                # 反序列化为领域事件并补齐 ID
                # 用 Pydantic 根据 AgentEvent 的联合类型定义自动识别并反序列化成具体事件类（如 PlanEvent / ToolEvent / MessageEvent 等）
                event = TypeAdapter(AgentEvent).validate_json(event_str)
                event.id = event_id
                logger.debug(f"Got event from Session {session_id}'s event queue: {type(event).__name__}")
                # 读到事件则清零未读计数，避免消息红点累积
                await self._session_repository.update_unread_message_count(session_id, 0)
                # 将事件产出给上层（最终会被 SSE 发送给前端）
                yield event
                # 遇到终止/等待/异常事件则结束本轮流式输出
                if isinstance(event, (DoneEvent, ErrorEvent, WaitEvent)):
                    break
            
            logger.info(f"Session {session_id} completed")

        except Exception as e:
            logger.exception(f"Error in Session {session_id}")
            # 出错时生成 ErrorEvent，保证前端能收到可见错误
            event = ErrorEvent(error=str(e))
            await self._session_repository.add_event(session_id, event)
            yield event # TODO: raise api exception
        finally:
            # 无论成功或异常，都清零未读计数，保持会话状态一致
            await self._session_repository.update_unread_message_count(session_id, 0)