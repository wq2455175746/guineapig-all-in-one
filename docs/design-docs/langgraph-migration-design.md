# LangGraph 重构方案：Agent 编排引擎

> 基于方案 B（彻底重构）+ 方案 1（interrupt/resume 映射）

## 用户确认的决策

面试时间 2026-07-26，经过方案评审后确认以下决策：

| 决策点 | 确认结果 |
|--------|---------|
| 迁移策略 | **增量迁移** — 新增 `/agent/chat/langgraph` 端点与现有 `/agent/chat/stream` 共存，逐步切换流量 |
| Python 3.13 兼容预验证 | 不需要，实施阶段遇到问题再解决 |
| 并行执行 | **当前串行** — 所有 Node 按 plan 顺序串行执行，不引入 fan-out 并行。等 Client 端支持多节点后再考虑 |

---

## 1. 现状与目标

### 现状痛点

| 问题 | 表现 |
|------|------|
| 自定义 DAG 引擎冗余 | `DAGExecutionEngine` 本质是顺序执行器，和 LangGraph 功能重叠 |
| 状态传递脆弱 | Pipeline 结果通过无类型 dict 在各函数间手递 |
| 同步 LLM 调用 | `DeepAnalyzer.analyze()` 和 `DAGGenerator.generate()` 使用同步 OpenAI SDK |
| 自定义 HITL 管理 | `AgentEventManager` 240 行 asyncio.Event 管理确认/取消/delegate |
| Pipeline 和 Execution 两层分离 | 意图识别管线 + DAG 执行引擎是两个独立的系统，耦合在 `agent.py` 路由中 |

### 目标架构

```
一条 LangGraph 图，所有逻辑都是 Node：
┌─────────────────────────────────────────────────────┐
│                  Agent StateGraph                      │
│                                                        │
│  Phase0 ─→ Phase1 ─→ Phase2 ─→ Route ─→ Capability    │
│    │           │         │         │        Nodes      │
│    │           │         │         │         │         │
│    └───→ fallback_json ──┘──→ direct_llm ──┘         │
│                   │         │         │               │
│               (Conditional Edges)       │             │
│                                        └──→ Client    │
│                                             Delegate   │
│                                                        │
│  interrupt() 用于: HITL 确认 + Client delegate 等待   │
└─────────────────────────────────────────────────────────┘
```

---

## 2. State Schema 设计

这是最核心的变更 — 用类型化的 State 替代当前的 dict 传递。

```python
from typing import Annotated, Any, Literal, Optional
from typing_extensions import TypedDict
from langgraph.graph import add_messages

class AgentState(TypedDict):
    """整个 Agent 图的全局状态"""

    # ── 输入 ──
    message: str                                         # 用户消息
    user_id: int
    session_id: str
    conversation_history: list[dict]                     # 过去的对话
    scene_memory: list[dict]                             # 摘要记忆
    mcp_servers: list[dict]
    skills: list[dict]
    rag_context: Optional[dict]

    # ── Capability 清单（扫描一次，全局复用）──
    capabilities_formatted: str                          # LLM 可读格式
    mcp_tool_infos: list                                 # MCP 工具列表

    # ── Phase 0-3 结果 ──
    quick_result: Optional[str]                          # trivial/simple/complex
    candidates: list                                     # Phase 1 结果
    deep_analysis: Optional[dict]                        # Phase 2 LLM 分析结果
    decision_action: Optional[str]                       # fallback/proceed/reject/clarify
    decision_reason: str

    # ── 能力执行结果（可被条件边读取）──
    step_results: Annotated[list[dict], add_messages]    # 执行历史
    current_capability: Optional[str]                    # 当前正在执行的 capability (用于路由)

    # ── SSE 事件队列（双任务架构的桥梁）──
    sse_events: list[dict]                               # 待推送的 SSE 事件

    # ── Token 统计 ──
    pipeline_input_tokens: int
    pipeline_output_tokens: int

    # ── 最终结果 ──
    final_content: str                                   # LLM 生成的回复内容
    execution_status: str                                # completed / failed / rejected
```

**关键设计说明：**

- `step_results` 使用 `add_messages` 归约器 — 每次添加自然追加，保留历史
- `decision_action` 被条件边（ConditionalEdge）读取来决定路由方向
- `current_capability` 用于 next_capability 路由器动态选择能力节点

---

## 3. 节点设计

### 3.1 CapabilityScanner Node

**职责：** 扫描可用能力（合并 MCP/CLI/Skill/Web Search/RAG/Memory/LLM）

```python
class CapabilityScannerNode:
    async def __call__(self, state: AgentState) -> dict:
        mcp_tool_infos = [MCPToolInfo(...) for s in state["mcp_servers"]]
        inventory = await CapabilityRegistry.scan(
            mcp_servers=mcp_tool_infos,
            skills=state["skills"],
            rag_context=state["rag_context"],
        )
        return {
            "capabilities_formatted": CapabilityRegistry.format_for_llm(inventory),
            "mcp_tool_infos": mcp_tool_infos,
        }
```

- 从 `agent.py` `_run_intent_pipeline` 的对应逻辑直接迁移
- 扫描结果注入 State，后续所有 Node 都可读

### 3.2 Phase0QuickFilter Node

```python
class Phase0QuickFilterNode:
    async def __call__(self, state: AgentState) -> dict:
        result = QuickFilter.classify(state["message"], state["conversation_history"])
        return {"quick_result": result.value}
```

- 纯同步，零依赖
- 输出只有 `quick_result`

### 3.3 trivial → 条件边

```python
def route_after_phase0(state: AgentState) -> Literal["trivial", "non_trivial"]:
    if state.get("quick_result") == "trivial":
        return "trivial"  # → 直接 LLM fallback
    return "non_trivial"  # → Phase 1（继续执行 pipeline）
```

### 3.4 Phase1IntentScanner Node

```python
class Phase1IntentScannerNode:
    async def __call__(self, state: AgentState) -> dict:
        if state.get("quick_result") != "simple":
            return {"candidates": []}  # Phase 1 只在 simple 时执行
        candidates = IntentScanner.scan(state["message"])
        return {"candidates": [c.model_dump() for c in candidates]}
```

### 3.5 Phase2DeepAnalyzer Node

**关键变更：** 改为异步 LLM 调用

```python
class Phase2DeepAnalyzerNode:
    async def __call__(self, state: AgentState) -> dict:
        needs_deep = (
            state["quick_result"] == "complex"
            or (state["quick_result"] == "simple" and not state["candidates"])
            or (state["candidates"] and state["candidates"][0]["confidence"] < 0.5)
        )
        if not needs_deep:
            return {}

        result = await DeepAnalyzer.analyze_async(  # 改为异步
            user_message=state["message"],
            capabilities_formatted=state["capabilities_formatted"],
            conversation_history=state["conversation_history"],
        )
        return {
            "deep_analysis": result.model_dump() if result else None,
            # token 统计更新
        }
```

**变更：** `DeepAnalyzer.analyze()` → 改为 `analyze_async()` 使用 `httpx.AsyncClient` 替代 OpenAI 同步 SDK

### 3.6 Phase3IntentDecision Node / ConditionalEdge

可以是简单的纯函数：

```python
def phase3_decision(state: AgentState) -> AgentState:
    decision = IntentDecision.decide(
        QuickFilterResult(state["quick_result"]),
        [ScanResult(**c) for c in state.get("candidates", [])],
        DeepAnalysisResult(**state["deep_analysis"]) if state.get("deep_analysis") else None,
    )
    return {
        "decision_action": decision.action,
        "decision_reason": decision.reason,
        "deep_analysis": decision.primary_intent.model_dump() if decision.primary_intent else None,
    }

def route_by_decision(state: AgentState) -> Literal["proceed", "fallback", "reject", "clarify"]:
    return state["decision_action"]
```

**这是整个图的核心路由器：** 决定走 DAG 执行路径还是直接 LLM fallback。

### 3.7 Capability Nodes （取代 DAGExecutionEngine）

这是去掉 `DAGDefinition` 中间层的核心设计。每个能力是一个独立的 Node：

```python
class WebSearchNode:
    async def __call__(self, state: AgentState) -> dict:
        params = _resolve_params(state, state["current_params"])  # 解析 {{step_id.key}} 引用
        result = await CapabilityHandlers.handle_web_search(params)
        return {"step_results": [{"capability": "web_search", "result": result}]}

class RAGNode:
    async def __call__(self, state: AgentState) -> dict:
        params = _resolve_params(state, state["current_params"])
        result = await CapabilityHandlers.handle_rag(params)
        return {"step_results": [{"capability": "rag", "result": result}]}

class LLMChatNode:
    async def __call__(self, state: AgentState) -> dict:
        params = _resolve_params(state, state["current_params"])
        result = await CapabilityHandlers.handle_llm_chat(params)
        return {"step_results": [{"capability": "llm_chat", "result": result}]}

class MCPCallNode:
    async def __call__(self, state: AgentState) -> dict:
        params = _resolve_params(state, state["current_params"])
        result = await CapabilityHandlers.handle_mcp_call(params)
        return {"step_results": [{"capability": "mcp_call", "result": result}]}
```

**需要新增的组件：** `PlanGeneratorNode` — 替代 `DAGGenerator`，不是生成 `DAGDefinition` json，而是**生成执行计划列表**（plan, 一个有序的步骤列表）：

```python
class PlanGeneratorNode:
    """
    替代 DAGGenerator + DAGValidator。

    输入: deep_analysis + capabilities_formatted
    输出: execution_plan = [
        {"step_id": "s1", "capability": "web_search", "params": {...}},
        {"step_id": "s2", "capability": "llm_chat", "params": {...}},
    ]

    和当前 DAGGenerator 的区别：
    - 输出不再是 DAGDefinition（不再包含 depends_on/execution_location 等）
    - 只需告诉图"下一步执行什么"
    - 依赖解析由图的拓扑结构保证
    """
    async def __call__(self, state: AgentState) -> dict:
        plan = await _generate_plan(
            state["deep_analysis"],
            state["capabilities_formatted"],
        )
        return {"execution_plan": plan, "plan_index": 0}
```

### 3.8 PlanExecutor Router（条件边 + 子图）

核心设计：PlanExecutor 是一个**子图（SubGraph）**，动态执行计划中的每一步。

```
PlanExecutor SubGraph:
┌────────────────────────────────────────────┐
│                                            │
│   ┌──────────────────────┐                │
│   │  PlanEntry Node      │                │
│   │  (进入执行器)         │                │
│   └────────┬─────────────┘                │
│            │ read plan[plan_index]         │
│            ▼                               │
│   ┌──────────────────────┐                │
│   │  next_capability     │                │
│   │  (条件边路由器)       │                │
│   └──┬────┬────┬────┬────┘                │
│      │    │    │    │                      │
│      ▼    ▼    ▼    ▼                      │
│    web   rag  llm  mcp  client_delegate   │
│   search      chat     │                   │
│              │   │  │  │   │               │
│              │   │  │  │   │               │
│              │   │  │  │   │               │
│              ▼   ▼  ▼  ▼   ▼               │
│   ┌──────────────────────────┐             │
│   │  post_step (共享节点)     │             │
│   │  - 下发 SSE 事件         │             │
│   │  - plan_index += 1       │             │
│   │  - 检查 plan 是否完成    │             │
│   └──────────┬───────────────┘             │
│              │ plan_complete?              │
│              ▼     │                       │
│           continue  exit(→ summary)        │
└────────────────────────────────────────────┘
```

核心路由器：

```python
def next_capability(state: AgentState) -> str:
    """动态路由：当前 plan_index 指向哪个 capability 就走哪个 Node"""
    plan = state.get("execution_plan", [])
    idx = state.get("plan_index", 0)
    if idx >= len(plan):
        return "plan_complete"

    step = plan[idx]
    capability = step.get("capability", "llm_chat")

    # 检查是否是 client 端能力
    if capability in ("cli", "skill") or capability.startswith("mcp_stdio"):
        return "client_delegate"

    return capability  # web_search / rag / llm_chat / mcp_call
```

### 3.9 ClientDelegateNode（interrupt 映射核心）

```python
class ClientDelegateNode:
    """
    Client delegate 节点 — 使用 LangGraph interrupt() 暂停图执行，
    等待 Client 通过 HTTP 回调恢复。

    双任务架构：
      Task 1: 遍历 graph.astream()，遇到 interrupt 后阻塞等待
      Task 2: HTTP handler 收到回调后调用 Command(resume=...)
    """
    async def __call__(self, state: AgentState) -> AgentState:
        plan = state["execution_plan"]
        idx = state["plan_index"]
        step = plan[idx]

        # 1. 发出 interrupt — 暂停图执行，value 中包含 delegate 上下文
        delegate_result = interrupt({
            "type": "client_delegate",
            "step_id": step["step_id"],
            "capability": step["capability"],
            "params": step["params"],
            "session_id": state["session_id"],
        })

        # 2. 恢复后，delegate_result 就是 Client 的回调结果
        return {
            "step_results": [{"capability": step["capability"], "result": delegate_result}],
        }
```

### 3.10 HITLConfirmNode（interrupt 映射 — 确认/取消）

```python
class HITLConfirmNode:
    """
    执行前等待用户确认 — 使用 LangGraph interrupt() 原生支持。

    替换 AgentEventManager.wait_for_confirmation()。
    """
    async def __call__(self, state: AgentState) -> AgentState:
        plan = state.get("execution_plan", [])

        # 发出 interrupt，暂停图执行等待用户确认
        confirmation = interrupt({
            "type": "confirm_plan",
            "plan": plan,
            "session_id": state["session_id"],
        })

        # confirmation 可以是 {"confirmed": true} 或 {"cancelled": true}
        if not confirmation.get("confirmed", False):
            # 用户取消 → 跳转到 summary 节点
            return {"decision_action": "cancelled"}

        return {"decision_action": "executing"}
```

### 3.11 ExecutionSummaryNode

```python
class ExecutionSummaryNode:
    """
    DAG 执行完成后，用 LLM 生成自然语言总结。

    从当前 _stream_execution_summary() 迁移。
    """
    async def __call__(self, state: AgentState) -> AgentState:
        step_results = state["step_results"]
        if not step_results:
            return {"execution_status": "completed", "final_content": "执行完成。"}

        content = await _generate_summary(
            state["message"],
            step_results,
            state.get("scene_memory"),
        )
        return {"execution_status": "completed", "final_content": content}
```

### 3.12 DirectLLMNode

```python
class DirectLLMNode:
    """
    非 DAG 路径 — 直接 LLM 回复（trivial/fallback/clarify）。

    从当前 _direct_llm_stream() 迁移。

    注意：这是流式节点，需要特殊的 SSE 处理。
    在 SSE 双任务架构中，这个节点的输出需要通过 sse_queue 逐 chunk 发送。
    """
    async def __call__(self, state: AgentState) -> AgentState:
        content = await _direct_llm_call(
            state["message"],
            state.get("scene_memory"),
        )
        return {"execution_status": "completed", "final_content": content}
```

---

## 4. SSE 双任务架构

这是整个方案中最关键的新增设计。

### 4.1 当前问题

LangGraph 的 `astream()` 在遇到 `interrupt()` 时会**暂停迭代**，需要等外部 `Command(resume=...)` 后才继续 yield 事件。但是 SSE 流需要保持 HTTP 连接不断开。

### 4.2 双任务桥接设计

```python
# ── agent.py (LangGraph SSE Handler) ──

async def event_stream():  # FastAPI StreamingResponse 的 generator
    # 创建队列用于 interrupt/resume 的异步通信
    interrupt_queue = asyncio.Queue()

    # 将队列注册到全局 registry，供 agent_control HTTP endpoint 读取
    # （不再使用 AgentEventManager，改用 InterruptRegistry）
    InterruptRegistry.register(state["session_id"], interrupt_queue)

    try:
        # Task 1: 运行 LangGraph
        async def run_graph():
            async for event in graph.astream_events(state, version="v2"):
                if event["event"] == "on_chain_start":
                    # → plan_ready / step_started
                    yield _format_sse("step_started", event["data"])
                elif event["event"] == "on_chain_end":
                    # → step_completed / log
                    yield _format_sse("step_completed", ...)
                elif event["event"] == "on_interrupt":
                    # → awaiting_confirmation / step_awaiting_client
                    interrupt_data = event["data"]
                    yield _format_sse(
                        "step_awaiting_client" if "client_delegate" in str(interrupt_data)
                        else "awaiting_confirmation",
                        interrupt_data,
                    )
                    # 等待外部 resume
                    result = await interrupt_queue.get()
                    # 通过 Command(resume=result) 恢复图执行
                    # （这需要 LangGraph 的 astream 支持动态注入 resume — 确认 API）

        # Task 2: 消费 Task 1 的事件，逐条 yield 到 SSE 流
        async for sse_event in run_graph():
            yield sse_event

    finally:
        InterruptRegistry.unregister(state["session_id"])
```

```python
# ── agent_control.py (恢复入口) ──

class InterruptRegistry:
    """全局 interrupt 队列注册表 — 替代 AgentEventManager"""
    _queues: dict[str, asyncio.Queue] = {}

    @classmethod
    def register(cls, session_id: str, queue: asyncio.Queue):
        cls._queues[session_id] = queue

    @classmethod
    async def resume(cls, session_id: str, data: dict) -> bool:
        """为指定 session 投递 resume 数据"""
        queue = cls._queues.get(session_id)
        if not queue:
            return False
        await queue.put(data)
        return True

@router.post("/chat/confirm")
async def agent_confirm(request: AgentSessionRequest):
    """用户确认 → 投递 confirmation data → 恢复 LangGraph"""
    await InterruptRegistry.resume(request.session_id, {"confirmed": True})
    return {"success": True}

@router.post("/chat/delegate-result")
async def agent_delegate_result(request: AgentDelegateResultRequest):
    """Client 回调 → 投递 delegate result → 恢复 LangGraph"""
    await InterruptRegistry.resume(request.session_id, {
        "result": request.result,
        "error": request.error,
    })
    return {"success": True}
```

**需要确认的 LangGraph API：** `astream_events` 在 `on_interrupt` 事件后如何注入 `Command(resume=...)` 值。根据 LangGraph v0.3+ 文档，需要在外部调用 `graph.aresume()` 或创建新的 `Command` 对象。具体实现路径需根据 langgraph 版本确认。

---

## 5. 保留 vs 删除的文件清单

### 删除（不再需要）

| 文件 | 行数 | 原因 |
|------|------|------|
| `app/agent/dag/` (generator.py, validator.py, __init__.py) | ~200 | DAGDefinition 被 PlanGenerator 替代 |
| `app/agent/executor/engine.py` | ~658 | DAGExecutionEngine 被能力节点 + 条件边替代 |
| `app/agent/event_manager.py` | ~264 | 被 InterruptRegistry + interrupt() 替代 |
| `app/agent/models.py` 中 DAG/Timeline 相关模型 | ~80 | 不再需要 DAGDefinition/DAGStep/TimelineEntry |

### 迁移（修改后保留）

| 文件 | 变更 |
|------|------|
| `app/agent/executor/handlers.py` | 保留 CapabilityHandlers，改为 async，接口不变 |
| `app/agent/intent/` (5 个文件) | 保留 Phase 0-3 逻辑，仅去掉和 DAG 相关的引用 |
| `app/agent/capability_registry.py` | 保留，接口不变 |
| `app/agent/models.py` | 精简：删除 DAG/Timeline，新增执行计划相关模型 |

### 新增

| 文件 | 行数估算 |
|------|---------|
| `app/agent/langgraph/state.py` — State 定义 | ~80 |
| `app/agent/langgraph/nodes.py` — 所有节点类 | ~300 |
| `app/agent/langgraph/graph.py` — 图构建 + 条件边 | ~150 |
| `app/agent/langgraph/plan_generator.py` — 替代 DAGGenerator | ~120 |
| `app/agent/langgraph/interrupt_registry.py` — 替代 EventManager | ~60 |
| `app/agent/langgraph/__init__.py` | ~10 |

### 修改

| 文件 | 变更 |
|------|------|
| `app/routers/agent.py` | 大改：SSE 流改为双任务架构，LangGraph StateGraph 替换手写 pipeline |
| `app/routers/agent_control.py` | 改为 InterruptRegistry，不再引用 EventManager |

---

## 6. 边界情况处理

| 场景 | LangGraph 方案 |
|------|---------------|
| DeepAnalyzer LLM 调用失败 | Node 内部 try/except，设置 `low_confidence` 标记，条件边路由到 fallback |
| 所有能力节点执行失败 | Capability Node 内部 retry（保留当前重试逻辑），失败后设 `step_error` 标记，条件边可选走到 summary 或重试 |
| Client delegate 超时 | interrupt() 的 timeout 参数（LangGraph 原生支持）或外部超时定时器 |
| SSE 连接断开 | StreamingResponse 的 generator 被 close，asyncio.CancelledError 传播到图执行，InterruptRegistry 清理 |
| 并行步骤 | **本次不做。** 所有能力节点串行执行。LangGraph 的 fan-out 后续 Client 端支持多节点后再引入 |
| 执行计划为空 | PlanGenerator 返回空列表 → 条件边路由到 DirectLLMNode |

---

## 7. 实施步骤与预估工期

| 阶段 | 任务 | 文件 | 预估 |
|------|------|------|------|
| 1 | 添加 langgraph 依赖，验证 Python 3.13 兼容 | pyproject.toml | 0.5d |
| 2 | 创建 `app/agent/langgraph/` 模块：State、InterruptRegistry | 3 个新文件 | 0.5d |
| 3 | 编写所有节点类 + 条件边（从现有代码迁移） | nodes.py, graph.py | 2d |
| 4 | PlanGenerator（替代 DAGGenerator） | plan_generator.py | 0.5d |
| 5 | 重写 SSE 双任务架构（agent.py runtime） | agent.py | 1d |
| 6 | 更新 agent_control.py（改用 InterruptRegistry） | agent_control.py | 0.25d |
| 7 | 删除冗余代码（dag/, engine.py, event_manager.py） | 8 个文件 | 0.25d |
| 8 | 清理 models.py 中已废弃的 DAG/Timeline 模型 | models.py | 0.25d |
| 9 | 回归测试：trivial/simple/complex/proceed/reject/delegate 全路径 | - | 2d |
| 10 | 集成测试：SSE 流 + interrupt/resume 全链路 | - | 1d |
| **合计** | | | **~8.25 天** |

---

## 8. 风险与 Mitigation

| 风险 | 影响 | Mitigation |
|------|------|-----------|
| langgraph 对 Python 3.13 不支持 | 阻断 | 先创建临时测试验证 pyproject.toml 安装，失败则回退方案 C |
| interrupt() + astream_events 的 resume API 不匹配设计 | 中 | 预留 fallback：interrupt 走 LangGraph 原生，delegate 仍用 EventManager |
| Client delegate 跨进程时序问题 | 低 | InterruptRegistry 使用 asyncio.Queue 线程安全，锁设计参考 EventManager |
| SSE 和 LangGraph 的流式事件粒度不匹配 | 中 | 通过双任务架构桥接，LangGraph event → 转换函数 → SSE format |
| 迁移期间新旧代码需要共存 | 低 | 模块化设计，langgraph/ 和 dag/executor/ 可共存，逐个功能切换 |

---

## 9. 迁移策略

采用**增量替换**，新旧端点共存，逐步切换：

```
Step 1: 新增 app/agent/langgraph/ 模块（独立运行，不改变现有逻辑）
Step 2: 在 agent.py 中新增 /agent/chat/langgraph SSE 端点，和现有 /agent/chat/stream 并存
Step 3: 内部测试/灰度验证通过后，将默认路由切到 LangGraph 端点
Step 4: 确认旧路径不再有流量后，删除旧代码（dag/, executor/engine.py, event_manager.py）
```

这样可以在不影响现有环境的情况下逐步验证，随时可以回退。
