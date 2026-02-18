"""
事件模式定义模块

本模块定义了 Agent 事件到 SSE (Server-Sent Events) 事件的映射和转换逻辑。
主要用于将后端领域模型中的 AgentEvent 转换为前端可以通过 SSE 流式接收的事件格式。

主要功能：
1. 定义各种事件的数据模型（MessageEventData, ToolEventData 等）
2. 定义对应的 SSE 事件类（MessageSSEEvent, ToolSSEEvent 等）
3. 提供事件映射器（EventMapper）用于动态转换事件类型
4. 处理特殊转换逻辑（如浏览器工具截图文件 ID 转签名 URL）
"""
from pydantic import BaseModel, Field, TypeAdapter
from typing import Any, Union, Literal, Dict, Optional, List, Self, Type
from datetime import datetime
from dataclasses import dataclass
from app.domain.models.plan import ExecutionStatus, Step
from app.interfaces.schemas.file import FileInfoResponse
from app.domain.models.event import ToolStatus, ToolContent, BrowserToolContent
from app.domain.models.event import (
    AgentEvent,
    ErrorEvent,
    PlanEvent,
    MessageEvent,
    TitleEvent,
    ToolEvent,
    StepEvent,
)

class BaseEventData(BaseModel):
    """基础事件数据模型
    
    所有事件数据模型的基类，包含所有事件共有的字段：
    - event_id: 事件的唯一标识符，用于前端追踪和关联事件
    - timestamp: 事件发生的时间戳，序列化为 Unix 时间戳（整数）
    
    用途：
    - 作为其他事件数据模型的基类
    - 提供统一的事件基础数据提取和转换方法
    """
    event_id: Optional[str]  # 事件唯一标识符，可能为空（新创建的事件）
    timestamp: datetime = Field(default_factory=lambda: datetime.now())  # 事件时间戳，默认当前时间

    class Config:
        """Pydantic 配置类
        
        配置 JSON 序列化行为：
        - datetime 类型转换为 Unix 时间戳（整数），便于前端处理
        """
        json_encoders = {
            datetime: lambda v: int(v.timestamp())  # 将 datetime 转换为 Unix 时间戳
        }

    @classmethod
    def base_event_data(cls, event: AgentEvent) -> dict:
        """从 AgentEvent 提取基础事件数据（事件 ID 和时间戳）
        
        这是一个类方法，用于从领域模型的 AgentEvent 中提取基础字段。
        这些字段是所有事件类型共有的，用于标识和追踪事件。
        
        Args:
            event: 领域模型中的 AgentEvent 实例
            
        Returns:
            包含 event_id 和 timestamp 的字典
            - event_id: 从 event.id 获取
            - timestamp: 从 event.timestamp 转换为 Unix 时间戳（整数）
        """
        return {
            "event_id": event.id,
            "timestamp": int(event.timestamp.timestamp())  # 转换为 Unix 时间戳
        }
    
    @classmethod
    def from_event(cls, event: AgentEvent) -> Self:
        """从 AgentEvent 创建 BaseEventData 实例
        
        这是一个通用的转换方法，将领域模型事件转换为 API 层的数据模型。
        它会：
        1. 提取基础事件数据（ID 和时间戳）
        2. 提取事件的其他字段（排除 type, id, timestamp，因为这些已处理）
        3. 创建并返回新的 BaseEventData 实例
        
        Args:
            event: 领域模型中的 AgentEvent 实例
            
        Returns:
            BaseEventData 实例，包含从 event 提取的所有相关数据
        """
        return cls(
            **cls.base_event_data(event),  # 先添加基础字段
            **event.model_dump(exclude={"type", "id", "timestamp"})  # 再添加其他字段，排除已处理的
        )

class CommonEventData(BaseEventData):
    """通用事件数据模型
    
    用于处理未匹配到特定事件类型的事件，或者需要额外字段的事件。
    允许接收任意额外字段（extra = "allow"），提供灵活性。
    
    使用场景：
    - 当 EventMapper 无法找到匹配的事件类型时，使用此类型作为兜底
    - 需要动态扩展字段的事件
    """
    class Config:
        json_encoders = {
            datetime: lambda v: int(v.timestamp())
        }
        extra = "allow"  # 允许接收未定义的额外字段

class BaseSSEEvent(BaseModel):
    """SSE（Server-Sent Events）事件基类
    
    SSE 是一种服务器推送技术，允许服务器向客户端实时推送数据。
    本类定义了 SSE 事件的标准格式：
    - event: 事件类型名称（如 "message", "tool", "plan" 等）
    - data: 事件的具体数据，类型为 BaseEventData 或其子类
    
    所有具体的 SSE 事件类（如 MessageSSEEvent, ToolSSEEvent）都继承自此类。
    """
    event: str  # 事件类型名称，对应 AgentEvent.type
    data: BaseEventData  # 事件数据，具体类型由子类指定

    @classmethod
    def from_event(cls, event: AgentEvent) -> Self:
        """从 AgentEvent 创建 SSE 事件实例
        
        这是一个通用的转换方法，通过反射机制动态确定数据类类型。
        
        流程：
        1. 从类的类型注解中获取 data 字段的类型（数据类）
        2. 使用该数据类的 from_event 方法转换事件数据
        3. 创建 SSE 事件实例，event 字段使用 event.type，data 字段使用转换后的数据
        
        Args:
            event: 领域模型中的 AgentEvent 实例
            
        Returns:
            BaseSSEEvent 实例，包含事件类型和转换后的数据
        """
        # 通过类型注解获取数据类类型，默认为 BaseEventData
        data_class: Type[BaseEventData] = cls.__annotations__.get('data', BaseEventData)
        return cls(
            event=event.type,  # 使用事件的类型名称
            data=data_class.from_event(event)  # 使用数据类的转换方法
        )

class MessageEventData(BaseEventData):
    """消息事件数据模型
    
    用于表示用户或助手发送的消息事件。
    
    字段说明：
    - role: 消息发送者角色，"user" 表示用户消息，"assistant" 表示助手消息
    - content: 消息的文本内容
    - attachments: 消息附件列表（可选），包含文件信息响应对象
    """
    role: Literal["user", "assistant"]  # 消息角色：用户或助手
    content: str  # 消息文本内容
    attachments: Optional[List[FileInfoResponse]] = None  # 附件列表，可能为空

class MessageSSEEvent(BaseSSEEvent):
    """消息 SSE 事件
    
    用于通过 SSE 流式传输消息事件到前端。
    事件类型固定为 "message"，前端可以通过监听此事件类型来接收消息更新。
    """
    event: Literal["message"] = "message"  # 固定事件类型为 "message"
    data: MessageEventData  # 消息事件数据

    @classmethod
    async def from_event_async(cls, event: MessageEvent) -> Self:
        """异步从 MessageEvent 创建 MessageSSEEvent 实例
        
        使用异步方法是因为需要异步转换附件信息（FileInfo 转 FileInfoResponse）。
        如果消息包含附件，需要为每个附件调用异步方法获取完整的文件信息。
        
        转换流程：
        1. 提取基础事件数据（ID 和时间戳）
        2. 提取消息角色和内容
        3. 如果有附件，异步转换每个附件为 FileInfoResponse（包含文件 URL 等信息）
        4. 创建并返回 MessageSSEEvent 实例
        
        Args:
            event: 领域模型中的 MessageEvent 实例
            
        Returns:
            MessageSSEEvent 实例，包含完整的消息数据
        """
        return cls(
            data=MessageEventData(
                **BaseEventData.base_event_data(event),  # 基础字段
                role=event.role,  # 消息角色
                content=event.message,  # 消息内容
                # 如果有附件，异步转换每个附件；否则为 None
                attachments=[await FileInfoResponse.from_file_info(attachment) for attachment in event.attachments] if event.attachments else None
            )
        )

class ToolEventData(BaseEventData):
    """工具事件数据模型
    
    用于表示工具调用相关的事件，包括工具调用的开始和完成。
    
    字段说明：
    - tool_call_id: 工具调用的唯一标识符，用于关联同一次调用的开始和完成事件
    - name: 工具名称（如 "browser", "file", "shell" 等）
    - status: 工具调用状态，ToolStatus.CALLING（调用中）或 ToolStatus.CALLED（已调用）
    - function: 调用的具体函数名称（如 "browser_view", "file_read" 等）
    - args: 函数调用的参数字典
    - content: 工具执行结果的内容（可选），包含工具特定的结果数据
              - BrowserToolContent: 浏览器工具结果（截图 URL）
              - FileToolContent: 文件工具结果（文件内容）
              - ShellToolContent: Shell 工具结果（控制台输出）
              - SearchToolContent: 搜索工具结果（搜索结果列表）
              - McpToolContent: MCP 工具结果（MCP 工具返回的数据）
    """
    tool_call_id: str  # 工具调用唯一标识符
    name: str  # 工具名称（如 "browser", "file"）
    status: ToolStatus  # 调用状态：CALLING（调用中）或 CALLED（已完成）
    function: str  # 具体函数名称（如 "browser_view"）
    args: Dict[str, Any]  # 函数参数字典
    content: Optional[ToolContent] = None  # 工具执行结果内容，可能为空

class ToolSSEEvent(BaseSSEEvent):
    """工具 SSE 事件
    
    用于通过 SSE 流式传输工具调用事件到前端。
    事件类型固定为 "tool"，前端可以通过监听此事件类型来接收工具调用更新。
    
    特殊处理：
    - 对于浏览器工具，会将截图文件 ID 转换为签名 URL，便于前端直接访问
    """
    event: Literal["tool"] = "tool"  # 固定事件类型为 "tool"
    data: ToolEventData  # 工具事件数据

    @classmethod
    async def from_event_async(cls, event: ToolEvent) -> Self:
        """异步从 ToolEvent 创建 ToolSSEEvent 实例
        
        特殊处理浏览器工具内容：
        - 浏览器工具返回的截图是文件 ID（file_id）
        - 需要转换为签名 URL（signed URL）才能被前端访问
        - 签名 URL 包含访问令牌，有时效性，用于安全访问文件
        
        转换流程：
        1. 获取工具内容（tool_content）
        2. 如果是浏览器工具内容（BrowserToolContent），转换截图文件 ID 为签名 URL
        3. 提取基础事件数据和其他工具字段
        4. 创建并返回 ToolSSEEvent 实例
        
        Args:
            event: 领域模型中的 ToolEvent 实例
            
        Returns:
            ToolSSEEvent 实例，包含完整的工具调用数据
        """
        content = event.tool_content
        # 特殊处理：浏览器工具的截图文件 ID 需要转换为签名 URL
        if isinstance(content, BrowserToolContent):
            from app.interfaces.dependencies import get_file_service
            # 将文件 ID 转换为带签名的访问 URL，前端可以直接使用此 URL 显示截图
            content = BrowserToolContent(screenshot=await get_file_service().create_signed_url(content.screenshot))
        return cls(
            data=ToolEventData(
                **BaseEventData.base_event_data(event),  # 基础字段
                tool_call_id=event.tool_call_id,  # 工具调用 ID
                name=event.tool_name,  # 工具名称
                status=event.status,  # 调用状态
                function=event.function_name,  # 函数名称
                args=event.function_args,  # 函数参数
                content=content  # 工具内容（可能已转换）
            )
        )

class DoneSSEEvent(BaseSSEEvent):
    """完成 SSE 事件
    
    表示任务或对话已完成，前端收到此事件后可以停止监听 SSE 流。
    此事件不包含数据字段，仅作为完成信号。
    """
    event: Literal["done"] = "done"  # 固定事件类型为 "done"

class WaitSSEEvent(BaseSSEEvent):
    """等待 SSE 事件
    
    表示需要等待用户输入（例如 message_ask_user 工具调用后）。
    前端收到此事件后应暂停处理，等待用户响应。
    此事件不包含数据字段，仅作为等待信号。
    """
    event: Literal["wait"] = "wait"  # 固定事件类型为 "wait"

class ErrorEventData(BaseEventData):
    """错误事件数据模型
    
    用于表示执行过程中发生的错误。
    
    字段说明：
    - error: 错误消息字符串，描述错误的具体内容
    """
    error: str  # 错误消息

class ErrorSSEEvent(BaseSSEEvent):
    """错误 SSE 事件
    
    用于通过 SSE 流式传输错误信息到前端。
    事件类型固定为 "error"，前端可以通过监听此事件类型来处理错误。
    """
    event: Literal["error"] = "error"  # 固定事件类型为 "error"
    data: ErrorEventData  # 错误事件数据

class StepEventData(BaseEventData):
    """步骤事件数据模型
    
    用于表示计划执行过程中的单个步骤。
    
    字段说明：
    - status: 步骤的执行状态（ExecutionStatus）
             - CREATED: 已创建
             - STARTED: 已开始执行
             - COMPLETED: 已完成
             - FAILED: 执行失败
    - id: 步骤的唯一标识符
    - description: 步骤的描述信息，说明该步骤要执行的任务
    """
    status: ExecutionStatus  # 步骤执行状态
    id: str  # 步骤唯一标识符
    description: str  # 步骤描述

class StepSSEEvent(BaseSSEEvent):
    """步骤 SSE 事件
    
    用于通过 SSE 流式传输步骤更新到前端。
    事件类型固定为 "step"，前端可以通过监听此事件类型来更新步骤状态。
    """
    event: Literal["step"] = "step"  # 固定事件类型为 "step"
    data: StepEventData  # 步骤事件数据

    @classmethod
    def from_event(cls, event: StepEvent) -> Self:
        """从 StepEvent 创建 StepSSEEvent 实例
        
        转换流程：
        1. 提取基础事件数据（ID 和时间戳）
        2. 从 event.step 中提取步骤的状态、ID 和描述
        3. 创建并返回 StepSSEEvent 实例
        
        Args:
            event: 领域模型中的 StepEvent 实例
            
        Returns:
            StepSSEEvent 实例，包含步骤的完整信息
        """
        return cls(
            data=StepEventData(
                **BaseEventData.base_event_data(event),  # 基础字段
                status=event.step.status,  # 步骤状态
                id=event.step.id,  # 步骤 ID
                description=event.step.description  # 步骤描述
            )
        )

class TitleEventData(BaseEventData):
    """标题事件数据模型
    
    用于表示会话或任务的标题更新。
    
    字段说明：
    - title: 新的标题文本
    """
    title: str  # 标题文本

class TitleSSEEvent(BaseSSEEvent):
    """标题 SSE 事件
    
    用于通过 SSE 流式传输标题更新到前端。
    事件类型固定为 "title"，前端可以通过监听此事件类型来更新会话标题。
    """
    event: Literal["title"] = "title"  # 固定事件类型为 "title"
    data: TitleEventData  # 标题事件数据

class PlanEventData(BaseEventData):
    """计划事件数据模型
    
    用于表示执行计划，包含多个步骤。
    
    字段说明：
    - steps: 计划中的所有步骤列表，每个步骤包含状态、ID 和描述
    """
    steps: List[StepEventData]  # 步骤列表

class PlanSSEEvent(BaseSSEEvent):
    """计划 SSE 事件
    
    用于通过 SSE 流式传输计划更新到前端。
    事件类型固定为 "plan"，前端可以通过监听此事件类型来显示和更新执行计划。
    
    计划事件通常在任务开始时发送，包含完整的步骤列表。
    """
    event: Literal["plan"] = "plan"  # 固定事件类型为 "plan"
    data: PlanEventData  # 计划事件数据

    @classmethod
    def from_event(cls, event: PlanEvent) -> Self:
        """从 PlanEvent 创建 PlanSSEEvent 实例
        
        转换流程：
        1. 提取基础事件数据（ID 和时间戳）
        2. 遍历 event.plan.steps，将每个步骤转换为 StepEventData
        3. 创建 PlanEventData，包含所有转换后的步骤
        4. 创建并返回 PlanSSEEvent 实例
        
        注意：每个步骤都使用相同的基础事件数据（来自 PlanEvent），
        但步骤本身的状态、ID 和描述来自 step 对象。
        
        Args:
            event: 领域模型中的 PlanEvent 实例
            
        Returns:
            PlanSSEEvent 实例，包含完整的计划信息（所有步骤）
        """
        return cls(
            data=PlanEventData(
                **BaseEventData.base_event_data(event),  # 基础字段
                # 将计划中的每个步骤转换为 StepEventData
                steps=[StepEventData(
                    **BaseEventData.base_event_data(event),  # 使用计划的基础字段
                    status=step.status,  # 步骤状态
                    id=step.id,  # 步骤 ID
                    description=step.description  # 步骤描述
                ) for step in event.plan.steps]  # 遍历计划中的所有步骤
            )
        )

class CommonSSEEvent(BaseSSEEvent):
    """通用 SSE 事件
    
    用于处理未匹配到特定事件类型的事件。
    使用 CommonEventData 作为数据模型，允许接收任意额外字段。
    
    使用场景：
    - 作为兜底事件类型，当无法匹配到具体事件类型时使用
    - 需要动态扩展字段的事件
    """
    event: str  # 事件类型（动态）
    data: CommonEventData  # 通用事件数据（允许额外字段）

# Agent SSE 事件类型联合，包含所有可能的 SSE 事件类型
# 这个联合类型用于类型提示，表示 event_to_sse_event 方法可能返回的任何 SSE 事件类型
AgentSSEEvent = Union[
    CommonEventData,      # 通用事件（兜底类型）
    PlanSSEEvent,         # 计划事件
    MessageSSEEvent,       # 消息事件
    TitleSSEEvent,        # 标题事件
    ToolSSEEvent,         # 工具事件
    StepSSEEvent,         # 步骤事件
    DoneSSEEvent,         # 完成事件
    ErrorSSEEvent,        # 错误事件
    WaitSSEEvent,         # 等待事件
]

@dataclass
class EventMapping:
    """事件类型映射信息的数据类
    
    用于存储事件类型到 SSE 事件类的映射关系。
    这个映射在 EventMapper._get_event_type_mapping() 中动态生成。
    
    字段说明：
    - sse_event_class: SSE 事件类（如 MessageSSEEvent, ToolSSEEvent）
    - data_class: 对应的数据类（如 MessageEventData, ToolEventData）
    - event_type: 事件类型字符串（如 "message", "tool"）
    """
    sse_event_class: Type[BaseEventData]  # SSE 事件类类型
    data_class: Type[BaseEventData]  # 数据类类型
    event_type: str  # 事件类型字符串

class EventMapper:
    """将 AgentEvent 映射为 SSEEvent 的映射器
    
    这个类负责将后端领域模型中的 AgentEvent 转换为前端可以通过 SSE 接收的事件格式。
    
    主要功能：
    1. 动态发现和映射事件类型到 SSE 事件类
    2. 缓存映射关系以提高性能
    3. 处理特殊转换逻辑（如异步转换、文件 ID 转 URL 等）
    
    使用方式：
    - 调用 event_to_sse_event() 转换单个事件
    - 调用 events_to_sse_events() 批量转换事件列表
    """
    
    _cached_mapping: Optional[Dict[str, EventMapping]] = None  # 缓存的映射关系，避免重复计算
    
    @staticmethod
    def _get_event_type_mapping() -> Dict[str, EventMapping]:
        """动态获取事件类型到 SSE 事件类的映射（带缓存）
        
        这个方法通过反射机制自动发现所有 SSE 事件类，并建立事件类型到类的映射。
        映射结果会被缓存，避免重复计算。
        
        工作原理：
        1. 检查缓存，如果已存在则直接返回
        2. 使用 get_args() 获取 AgentSSEEvent Union 类型的所有成员类型
        3. 遍历每个 SSE 事件类：
           - 跳过基类 BaseSSEEvent
           - 通过类型注解获取 event 字段的 Literal 值（事件类型字符串）
           - 通过类型注解获取 data 字段的类型（数据类）
           - 建立映射关系：事件类型 -> EventMapping
        4. 缓存映射结果并返回
        
        Returns:
            事件类型到 EventMapping 的字典
            - key: 事件类型字符串（如 "message", "tool"）
            - value: EventMapping 对象，包含 SSE 事件类和数据类信息
        """
        # 如果已有缓存，直接返回
        if EventMapper._cached_mapping is not None:
            return EventMapper._cached_mapping
            
        from typing import get_args
        
        # 获取 AgentSSEEvent Union 类型的所有成员类型
        # 这会返回一个元组，包含所有可能的 SSE 事件类型
        sse_event_classes = get_args(AgentSSEEvent)
        mapping = {}
        
        # 遍历每个 SSE 事件类，建立映射关系
        for sse_event_class in sse_event_classes:
            # 跳过基类，因为基类不是具体的事件类型
            if sse_event_class == BaseSSEEvent:
                continue
                
            # 检查类是否有 event 字段的类型注解
            if hasattr(sse_event_class, '__annotations__') and 'event' in sse_event_class.__annotations__:
                event_field = sse_event_class.__annotations__['event']
                # 检查是否是 Literal 类型（有 __args__ 属性）
                if hasattr(event_field, '__args__') and len(event_field.__args__) > 0:
                    event_type = event_field.__args__[0]  # 获取 Literal 的第一个值（事件类型字符串）
                    
                    # 从 sse_event_class 获取数据类类型
                    data_class = None
                    if hasattr(sse_event_class, '__annotations__') and 'data' in sse_event_class.__annotations__:
                        data_class = sse_event_class.__annotations__['data']
                    
                    # 建立映射关系
                    mapping[event_type] = EventMapping(
                        sse_event_class=sse_event_class,  # SSE 事件类
                        data_class=data_class,  # 数据类
                        event_type=event_type  # 事件类型字符串
                    )
        
        # 缓存映射结果，避免重复计算
        EventMapper._cached_mapping = mapping
        return mapping
    
    @staticmethod
    async def event_to_sse_event(event: AgentEvent) -> AgentSSEEvent:
        """将 AgentEvent 转换为 SSE 事件
        
        这是核心转换方法，负责将领域模型事件转换为 API 层的事件格式。
        
        转换流程：
        1. 获取事件类型到 SSE 事件类的映射关系（带缓存）
        2. 根据 event.type 查找对应的映射
        3. 如果找到映射：
           - 优先使用 from_event_async 方法（如果存在），用于需要异步操作的事件
           - 否则使用 from_event 方法（同步转换）
        4. 如果未找到映射，使用 CommonEventData 作为兜底类型
        
        特殊处理：
        - MessageSSEEvent 和 ToolSSEEvent 使用异步方法，因为需要：
          * 转换附件信息（MessageSSEEvent）
          * 转换文件 ID 为签名 URL（ToolSSEEvent 中的浏览器工具）
        
        Args:
            event: 领域模型中的 AgentEvent 实例，可能是以下类型之一：
                   - MessageEvent: 消息事件
                   - ToolEvent: 工具事件
                   - PlanEvent: 计划事件
                   - StepEvent: 步骤事件
                   - TitleEvent: 标题事件
                   - ErrorEvent: 错误事件
                   - DoneEvent: 完成事件
                   - WaitEvent: 等待事件
            
        Returns:
            对应的 SSE 事件实例，类型为 AgentSSEEvent 联合类型中的一种
            - 如果找到匹配类型，返回对应的 SSE 事件（如 MessageSSEEvent, ToolSSEEvent）
            - 如果未找到匹配类型，返回 CommonEventData（兜底类型）
        """
        # 动态获取事件类型到 SSE 事件类的映射关系（带缓存）
        event_type_mapping = EventMapper._get_event_type_mapping()
        
        # 根据事件类型查找对应的映射
        event_mapping = event_type_mapping.get(event.type)
        
        if event_mapping:
            # 找到匹配的映射，进行转换
            sse_event_class = event_mapping.sse_event_class
            
            # 优先使用异步方法（如果存在），用于需要异步操作的事件
            # 例如：MessageSSEEvent 需要异步转换附件，ToolSSEEvent 需要异步转换文件 URL
            if hasattr(sse_event_class, 'from_event_async'):
                sse_event = await sse_event_class.from_event_async(event)
            else:
                # 使用同步方法进行转换
                sse_event = sse_event_class.from_event(event)
            return sse_event
        
        # 如果未找到匹配的类型，返回通用事件作为兜底
        # 这通常发生在添加了新的事件类型但忘记添加对应的 SSE 事件类时
        return CommonEventData.from_event(event)
    
    @staticmethod
    async def events_to_sse_events(events: List[AgentEvent]) -> List[AgentSSEEvent]:
        """从事件列表批量创建 SSE 事件列表
        
        这是一个便捷方法，用于批量转换多个事件。
        会过滤掉 None 值和空事件，只返回有效的 SSE 事件。
        
        转换流程：
        1. 遍历事件列表
        2. 跳过空事件（None 或 falsy 值）
        3. 对每个有效事件调用 event_to_sse_event() 进行转换
        4. 过滤掉转换结果为 None 的事件
        5. 返回转换后的 SSE 事件列表
        
        Args:
            events: AgentEvent 实例列表，可能包含 None 值或空事件
            
        Returns:
            SSE 事件列表，已过滤掉 None 值和空事件
        """
        return list(filter(lambda x: x is not None, [
            await EventMapper.event_to_sse_event(event) for event in events if event
        ]))