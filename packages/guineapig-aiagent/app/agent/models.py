"""
Agent 编排数据模型 — Capability / Intent / DAG / Task / Timeline

所有模型均为 Pydantic BaseModel，与现有 aiagent 代码风格一致。
"""

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field

# ═══════════════════════════════════════════
# Capability 相关
# ═══════════════════════════════════════════


class CapabilityType(str, Enum):
    """能力类型枚举"""

    MCP = "mcp"
    CLI = "cli"
    SKILL = "skill"
    WEB_SEARCH = "web_search"
    RAG = "rag"
    MEMORY = "memory"
    LLM_CHAT = "llm_chat"


class ExecutionLocation(str, Enum):
    """执行位置"""

    SERVER = "server"  # AiAgent 直连执行
    CLIENT = "client"  # 委托到 Electron Client 执行


class MCPToolInfo(BaseModel):
    """MCP 服务及工具信息"""

    server_name: str = Field(..., description="MCP server 名称")
    transport_type: str = Field(
        ..., description="传输协议: stdio | sse | streamable_http"
    )
    mcp_url: str = Field(
        "", description="MCP server URL（仅 sse/streamable_http 使用）"
    )
    headers: dict = Field(
        default_factory=dict,
        description="MCP 请求头（仅 sse/streamable_http 使用）",
    )
    command: str = Field(
        "", description="stdio 启动命令（仅 stdio 使用，client 端执行）"
    )
    args: list[str] = Field(
        default_factory=list,
        description="stdio 启动命令参数（仅 stdio 使用，client 端执行）",
    )
    env: dict = Field(
        default_factory=dict,
        description="stdio 启动环境变量（仅 stdio 使用，client 端执行）",
    )
    tools: list[Any] = Field(
        default_factory=list,
        description="该服务提供的工具列表，每项含 name/description",
    )


class CapabilityInfo(BaseModel):
    """单个能力的描述"""

    type: CapabilityType = Field(..., description="能力类型")
    name: str = Field(..., description="能力名称（唯一标识）")
    description: str = Field("", description="人类可读的描述")
    execution_location: ExecutionLocation = Field(
        ..., description="执行位置: server | client"
    )
    tools: list[Any] = Field(
        default_factory=list, description="子工具列表，每项含 name/description"
    )
    enabled: bool = Field(True, description="当前是否可用")


class CapabilityInventory(BaseModel):
    """当前时刻的完整能力清单"""

    capabilities: list[CapabilityInfo] = Field(default_factory=list)
    scanned_at: str = Field("", description="扫描时间戳 (ISO 格式)")


# ═══════════════════════════════════════════
# Intent 相关
# ═══════════════════════════════════════════


class QuickFilterResult(str, Enum):
    """Phase 0 快速筛选结果"""

    TRIVIAL = "trivial"  # 简单对话/问候 → 直接走普通对话
    TASK = "task"  # 需要分析的任务 → 走一次 LLM 意图识别


class DeepAnalysisResult(BaseModel):
    """Phase 2 LLM 深度意图分析结果"""

    intent_type: str = Field(
        ..., description="意图类型（如 web_search, multi_step_complex）"
    )
    intent_summary: str = Field("", description="意图的自然语言描述")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="置信度 0-1")
    entities: dict = Field(default_factory=dict, description="提取的实体信息")
    required_capabilities: list[str] = Field(
        default_factory=list, description="完成任务需要的能力列表"
    )
    feasible: bool = Field(True, description="当前可用能力是否可行")
    infeasible_reason: str = Field("", description="不可行的具体原因")
    complexity: str = Field("single_step", description="single_step | multi_step")
    estimated_steps: int = Field(1, ge=1, description="预估步骤数")
    source: str = Field("llm", description="分析来源")


# ═══════════════════════════════════════════
# DAG 相关
# ═══════════════════════════════════════════


class DAGStep(BaseModel):
    """DAG 中的单个步骤"""

    step_id: str = Field(..., description="步骤唯一标识 (s1, s2, ...)")
    capability: str = Field(..., description="使用的能力名称")
    action: str = Field(..., description="具体操作")
    params: dict = Field(default_factory=dict, description="操作参数")
    output_key: str = Field("", description="输出字段名，供后续步骤引用")
    depends_on: list[str] = Field(
        default_factory=list, description="依赖的 step_id 列表"
    )
    execution_location: ExecutionLocation = Field(
        ExecutionLocation.SERVER, description="执行位置"
    )
    requires_confirmation: bool = Field(False, description="是否需要用户确认")
    max_retries: int = Field(2, description="最大重试次数")
    timeout_seconds: int = Field(60, description="超时秒数")
    fallback_action: Optional[str] = Field(None, description="失败时的降级操作")


class DAGDefinition(BaseModel):
    """完整的 DAG 定义"""

    steps: list[DAGStep] = Field(default_factory=list)
    original_intent: str = Field("", description="原始意图描述")
    estimated_total_steps: int = Field(0)


# ═══════════════════════════════════════════
# Task 状态
# ═══════════════════════════════════════════


class TaskStatus(str, Enum):
    """任务状态枚举"""

    PENDING = "pending"
    RUNNING = "running"
    AWAITING_CLIENT = "awaiting_client"  # 等待 Client 执行回调
    AWAITING_CONFIRMATION = "awaiting_confirmation"  # 等待用户确认计划
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskState(BaseModel):
    """任务执行状态"""

    task_id: str = Field(..., description="任务唯一 ID")
    user_id: int = Field(0, description="用户 ID")
    session_id: str = Field("", description="会话 ID")
    status: TaskStatus = Field(TaskStatus.PENDING, description="当前状态")
    original_input: str = Field("", description="用户的原始输入")
    dag_definition: list[DAGStep] = Field(
        default_factory=list, description="DAG 步骤定义"
    )
    current_step: str = Field("", description="当前正在执行的 step_id")
    error: str = Field("", description="错误信息")
    created_at: str = Field("", description="创建时间 ISO 格式")
    updated_at: str = Field("", description="最后更新时间 ISO 格式")


# ═══════════════════════════════════════════
# Timeline 记录
# ═══════════════════════════════════════════


class TimelineLog(BaseModel):
    """单条执行日志"""

    ts: str = Field("", description="时间戳")
    level: str = Field("info", description="日志级别")
    msg: str = Field("", description="日志内容")


# ═══════════════════════════════════════════
# SSE Stream 事件
# ═══════════════════════════════════════════


class StreamEventType(str, Enum):
    """SSE 流事件类型"""

    PLAN_READY = "plan_ready"  # 计划就绪，待用户确认
    STEP_STARTED = "step_started"  # 步骤开始执行
    STEP_COMPLETED = "step_completed"  # 步骤执行成功
    STEP_FAILED = "step_failed"  # 步骤执行失败
    STEP_AWAITING_CLIENT = "step_awaiting_client"  # 等待 Client 执行并回调
    AWAITING_CONFIRMATION = "awaiting_confirmation"  # 等待用户确认计划
    EXECUTION_COMPLETE = "execution_complete"  # 全部执行完成
    ERROR = "error"  # 致命错误
    LOG = "log"  # 日志消息


class StreamEvent(BaseModel):
    """SSE 流中的单个事件"""

    event: str = Field(..., description="事件类型")
    data: dict = Field(default_factory=dict, description="事件数据 payload")
    timestamp: str = Field("", description="事件时间戳 ISO 格式")


class TimelineEntry(BaseModel):
    """单个步骤的完整执行记录"""

    step_id: str = Field(..., description="步骤 ID")
    capability: str = Field("", description="使用的能力")
    status: str = Field("running", description="执行状态")
    started_at: str = Field("", description="开始时间")
    completed_at: str = Field("", description="完成时间，空表示未完成")
    duration_ms: int = Field(0, description="耗时毫秒")
    params: dict = Field(default_factory=dict, description="入参")
    result_summary: str = Field("", description="结果摘要")
    error: str = Field("", description="错误信息")
    logs: list[TimelineLog] = Field(default_factory=list, description="执行日志")
