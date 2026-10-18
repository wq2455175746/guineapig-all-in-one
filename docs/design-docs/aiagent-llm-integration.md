# AIAgent LLM Integration Design

## Metadata
- **Status**: implemented (updated to match current code)
- **Created**: 2026-05-21
- **Updated**: 2026-10-17
- **Package**: guineapig-aiagent
- **Tech**: Python 3.13, FastAPI, openai SDK (OpenAI-compatible), MCP, Milvus, Langfuse

> 说明：本文替换早期"Subagent 多轮循环 + 内嵌 SenseVoice/CosyVoice"的草稿设计，
> 描述**当前代码**的意图识别、DAG 编排与执行器实现。

## Overview

guineapig-aiagent 是系统的 AI 能力核心，负责 ASR 语音识别、LLM 对话、TTS 语音合成与 Agent 编排。
编排采用 **Plan-then-Execute（先规划后执行）**：意图识别后生成 DAG，再由执行器按拓扑序执行。
**未使用 LangGraph/LangChain**。

## Core Loop: 意图识别 → DAG 生成 → 执行

```
┌──────────────────────────────────────────────────────┐
│                    Agent Pipeline                     │
│                                                       │
│  1. QuickFilter (Phase 0)  规则分流 trivial / task    │
│  2. DeepAnalyzer (Phase 1) LLM 分析（结构化 JSON）     │
│  3. DAGGenerator           生成步骤 + DAGValidator 校验│
│  4. DAGExecutionEngine     拓扑序执行                 │
│     - server 能力：直接执行（web/rag/memory/llm/mcp）  │
│     - client 能力：下发 delegate，等待客户端回调       │
│  5. ExecutionSummary       LLM 生成自然语言总结        │
│                                                       │
│  SSE 流式推送执行事件；HITL 支持执行前确认/取消        │
└──────────────────────────────────────────────────────┘
```

关键组件（`app/agent/`）：
- `intent/quick_filter.py` — Phase 0，纯正则零 LLM，输出 `TRIVIAL` / `TASK`
- `intent/deep_analyzer.py` — Phase 1，一次非流式 LLM 调用（`response_format=json_object`）
- `dag/generator.py` + `dag/validator.py` — DAG 生成与校验（步骤唯一性、环检测、占位符引用）
- `executor/engine.py` — `DAGExecutionEngine`，拓扑排序 + 重试 + 有界自纠错（replan）
- `executor/handlers.py` — `CapabilityHandlers`（web_search / rag / llm_chat / memory / mcp_*）
- `executor/middleware.py` — 参数解析、MCP 连接、未解析引用守卫、输出截断
- `capability_registry.py` — 能力扫描与 LLM 可读格式化
- `event_manager.py` — HITL / client-delegate 的 asyncio.Event 管理

## API Endpoints

Router 前缀为 `/guineapig-aiagent/<module>`（**不是** `/api/v1/`）。鉴权：`X-Admin-Token` / `Authorization: Bearer`。

| Method | Path | Description |
|--------|------|-------------|
| POST | `/guineapig-aiagent/agent/chat` | 一次对话（非流式） |
| POST | `/guineapig-aiagent/agent/chat/stream` | 对话（SSE 流式） |
| POST | `/guineapig-aiagent/agent/chat/confirm` | HITL 确认/取消 |
| POST | `/guineapig-aiagent/agent/chat/cancel` | 取消执行 |
| POST | `/guineapig-aiagent/agent/chat/delegate-result` | 客户端委托步骤回填结果 |
| POST | `/guineapig-aiagent/llm/chat/stream` | LLM 直连流式（含 Skill/Search/RAG 注入） |
| POST | `/guineapig-aiagent/task/submit` | ASR→LLM→TTS 任务管线 |
| POST | `/guineapig-aiagent/asr/transcribe` | 语音转文字 |
| POST | `/guineapig-aiagent/memory/summarize` | 记忆摘要 |
| POST | `/guineapig-aiagent/rag/embed` / `rag/delete-embeddings` | RAG 向量写入/删除 |
| POST | `/guineapig-aiagent/skill/process` | Skill 处理 |
| GET | `/`, `/health`, `/metrics` | 服务信息 / 健康检查 / Prometheus |

## SSE Event Types

`StreamEventType`（`app/agent/models.py`）：
`plan_ready, step_started, step_completed, step_failed, step_awaiting_client, awaiting_confirmation, execution_complete, error, log, replan_started, replan_generated, replan_failed`

## LLM Integration

- 使用官方 **`openai` SDK**（`OpenAI` / `AsyncOpenAI`），OpenAI 兼容协议
- 默认指向 DeepSeek（`LLM_BASE_URL=https://api.deepseek.com`, `LLM_MODEL_NAME=deepseek-chat`）
- 客户端缓存 + 有界重试：`app/core/llm_clients.py`；base URL 自动规范化为 `/v1`
- 默认模型由 backend 通过 `aimodel` 配置下发，可在请求上下文中覆盖

## Context Management

- 对话上下文存 Redis，15 天滚动窗口
- `memory/summarize`（由 backend 每 12h 触发）生成摘要，回调 backend `/inner/api/v1/memory/update-content`
- LLM 管道注入顺序（`app/services/llm_pipeline.py`）：SkillSelection → SkillContext → NetworkSearch → RAGRetrieval → DefaultSkillInjector → LLMStream → CommandParsing
- 外部内容经 `prompt_context.py` 包装为 `<context>` 以缓解提示注入

## Tool Trust Boundary

| 执行侧 | 能力 |
|--------|------|
| server（aiagent） | `web_search`、`rag`、`memory*`、`llm_chat`、`mcp`（sse/streamable-http） |
| client（Electron） | `cli`、`skill`、`mcp`（stdio） |

client 端能力步骤标记 `execution_location=client`，执行器发出 `STEP_AWAITING_CLIENT` 并阻塞，
等待客户端 `POST /agent/chat/delegate-result` 后继续。

## Observability

- **Langfuse**：LLM/生成观测（`langfuse_client.py`，`start_observation`）
- **Prometheus**：`/metrics`，`http_requests_total` / `http_request_duration_seconds` / `service_up`
- **自定义指标**：`otel_service.py` 将对话指标写入 Redis hash（`otel:metrics:*`），由 backend 同步至 MySQL

## Error Handling

1. 步骤超时 / 连接 / 鉴权失败 → `executor/errors.py` 分类，回喂为错误结果
2. 终态失败 → `executor/replanner.py` 有界自纠错（受 `AGENT_REPLAN_ENABLED/MAX` 控制）
3. 工具输出截断 → `executor/truncate.py`（行/字节双向限制，UTF-8 安全）
4. LLM 调用失败 → 记录并降级

## Performance Targets

- ASR / TTS：取决于外部服务
- LLM 生成：流式，首 token 延迟优先
- Agent 编排：单次对话可能包含多次 LLM 调用（意图分析、DAG 生成、步骤、总结）
