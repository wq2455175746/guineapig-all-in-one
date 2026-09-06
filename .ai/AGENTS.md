# GuineaPig AI Agent Navigation Map

## MANDATORY FIRST STEPS

```bash
# 1. 读取当前焦点
cat .ai/CURRENT_FOCUS

# 2. 读取架构规则
cat docs/ARCHITECTURE.md

# 3. 检查失败历史
tail -20 .ai/traces/failures.log

# 4. 运行验证
make validate
```

## Module Routing Map

| 任务类型 | 目标 Package | 技术栈 |
|---------|-------------|--------|
| 后端 API / 业务逻辑 / 数据库 | `packages/guineapig-backend` | Go 1.24, Echo v4, GORM, Redis, Zap |
| AI Agent / ASR / TTS / LLM | `packages/guineapig-aiagent` | Python 3.13+, FastAPI, uv, PyTorch |
| 运营管理 Web 前端 | `packages/guineapig-ops-web` | Vue 3, Vite, PrimeVue |
| 桌面客户端 | `packages/guineapig-client` | Electron, Vue 3, Vite |

## AI Agent 内部模块路由

| 模块路径 | 职责 | 关键函数 |
|---------|------|---------|
| `app/routers/agent.py` | Agent 入口路由（同步+SSE 流式） | `chat()`, `chat_stream()` |
| `app/routers/llm.py` | LLM 直连流式端点 | `chat_stream()` |
| `app/agent/capability_registry.py` | MCP 能力清单扫描 | `scan()` |
| `app/agent/intent.py` | 意图分类 Pipeline | `QuickFilter`, `IntentScanner`, `DeepAnalyzer`, `IntentDecision` |
| `app/agent/dag.py` | DAG 计划生成 | `DAGGenerator` |
| `app/agent/executor/engine.py` | DAG 执行引擎 | `DAGExecutionEngine.execute()` |
| `app/agent/executor/handlers.py` | 能力执行器 | `CapabilityHandlers` |
| `app/agent/models.py` | Agent 数据模型 | IntentDecisionResult, StreamEvent, DAGDefinition 等 |
| `app/reporting/otel_metrics.py` | OTel 指标上报（Redis HINCRBY） | `report_chat_metrics()` |
| `app/services/otel_service.py` | OTel 指标写入 Redis | `report_metrics()` |
| `app/core/llm_clients.py` | LLM 客户端复用 + 有界重试 | `get_llm_client()`, `call_with_retry()` |
| `app/core/milvus_clients.py` | Milvus 客户端线程本地缓存 | `thread-local MilvusClient` |
| `app/services/zip_utils.py` | ZIP 安全解压（防 ZIP SLIP / zip bomb） | `extract_zip_safe()`, `safe_zip_target()` |
| `app/services/prompt_context.py` | 提示注入缓解（context 分隔 + 转义） | `wrap_context()` |
| `app/middleware.py` | 鉴权（X-Admin-Token）+ request_id 日志 | `AdminTokenAuthMiddleware`, `RequestIDMiddleware` |

## Backend 内部模块路由

| 模块路径 | 职责 |
|---------|------|
| `internal/router/` + `internal/service/` | 标准 CRUD 路由 + 业务逻辑 |
| `internal/service/otel_sync.go` | Asynq Worker: Redis→MySQL OTel 指标同步 |
| `internal/service/user_chat_config.go` | Redis 用户聊天配置缓存（跨渠道模型选择） |
| `internal/service/chat_sync.go` | 同步消息处理（IM Bot 消息 → LLM → 回复） |
| `internal/service/chat_bot_binding.go` | Bot 消息分发 + BotUserID 绑定 |
| `internal/model/chat_otel.go` | 指标模型 + UpsertCount |
| `internal/model/res_bot.go` | Bot 配置 GORM 模型 |
| `internal/router/bot/` | Bot 管理 API（list/update/delete） |
| `pkg/tasks/` | Asynq 任务类型定义 + Handler 注册 |
| `pkg/plugin/` | DB/Redis/Asynq Server/Scheduler 初始化 |
| `pkg/auth/` | HMAC 会话 Token（签发/验签，常量时间比较） | `IssueUserToken`, `ParseUserToken` |
| `pkg/middleware/auth.go` | 三套鉴权：`X-User-Token`/`X-Admin-Token`/`X-Inner-Token` | `CurrentUserID`, `IsAdminSession`, `BindRequester` |
| `pkg/utils/httpclient.go` | 共享 HTTP client 连接池 + aiagent 调用附加鉴权 | `NewHTTPClient()`, `AttachAiAgentAuth()` |
| `pkg/utils/s3key.go` | S3 key 属主解析（预签名下载 IDOR 校验） | `KeyOwnerUserID()` |

## Architecture Constraints

1. **层级依赖规则**：`client` -> `backend` -> `aiagent`，不可反向依赖
2. **backend 只做业务逻辑**，AI 相关操作必须走 aiagent
3. **数据流向**：Client 上传音频到 S3 -> Backend 入库任务 -> AIAgent 消费任务
4. **配置管理**：backend 使用 Viper + YAML + `.env`，aiagent 使用环境变量
5. **日志规范**：backend 使用 Zap，aiagent 使用 Python logging，统一带上 request_id
6. **例外规则**：aiagent 可直写 Redis OTel 指标（HINCRBY），backend Asynq Worker 定期 SCAN → MySQL UPSERT
7. **定时任务**：统一使用 Asynq（Scheduler + Server），禁止 goroutine + ticker

See `.ai/rules/architecture.md` for full rules.

## Common Task Templates

### 添加后端 API
1. `internal/model/` 定义 GORM 模型
2. `internal/request/` 定义请求结构体
3. `internal/response/` 定义响应结构体
4. `internal/service/` 实现业务逻辑
5. `internal/router/{resource}/` 注册路由 handler
6. `internal/router/router.go` 注册路由组

### 添加 AI 能力
1. `packages/guineapig-aiagent/app/routers/` 定义新端点
2. `packages/guineapig-aiagent/app/services/` 实现能力服务
3. `packages/guineapig-aiagent/app/agent/` 注册到能力清单（CapabilityInventory）
4. 如果需要 DAG 执行：在 `executor/handlers.py` 添加 Handler
5. 更新 backend 的 aiagent client 调用

### 修改前端页面
1. `packages/guineapig-ops-web/src/views/` 页面组件
2. `packages/guineapig-ops-web/src/api/` API 调用层
3. `packages/guineapig-ops-web/src/router/` 路由配置

### 添加 Agent SSE 流式端点
1. `app/routers/agent.py` 定义 SSE 端点（返回 `StreamingResponse`）
2. `app/agent/executor/engine.py` 如果新增执行流程，扩展 `DAGExecutionEngine`
3. 确保 use `async for` 迭代 async generator（避免 AP-014）
4. metrics report 放在 generator 外部（避免 AP-015）
5. 注册新事件类型到 `StreamEventType`

### 添加 OTel 指标
1. Python 侧：`otel_service.py` 调用 `hincrby()` + `expire()`（2 天 TTL）
2. Go 侧：`chat_otel.go` 新增 `metricFields` 数组条目
3. 不需要改 Redis key 管理（TTL 自动过期 + UPSERT 自动累加）

### 添加 Backend Asynq 定时任务
1. `internal/service/` 实现业务处理函数
2. `pkg/tasks/` 定义 TaskType 常量 + Handler 函数
3. `pkg/plugin/` 中注册 Scheduler cron 表达式 + Server Handler
4. 使用 `RunAsync()` 非阻塞启动（与 Echo 共存）

### 添加 IM Bot（飞书/企微/钉钉）
1. `internal/router/bot/*.go` — 定义 Bot 管理 API（list/update/delete）
2. `internal/model/res_bot.go` — Bot 配置 GORM 模型（AppId, AppSecret, WebhookUrl）
3. `internal/service/bot.go` — BotManager + Bot interface 实现
4. `internal/service/chat_bot_binding.go` — Bot 消息处理入口（dispatch to SyncChatMessage）
5. `internal/service/chat_sync.go` — 同步方式处理 Bot 消息（findOrCreateExtConversation → LLM → 回复）
6. 前端 `views/info/InfoChannelMgr.vue` — Bot 管理页面
7. Bot AppSecret 使用 RSA 加密传输

### 添加 Docker / docker-compose
1. `packages/*/Dockerfile` — 多阶段构建（Go/Python/Vue）
2. `docker-compose.yml` — 开发环境（MySQL 8.0, Redis 7, MinIO, aiagent, backend, frontend）
3. `docker-compose.prod.yml` — 生产环境（resource limits, restart policies, named volumes）
4. `Makefile` 根目录 + 各 package 子 Makefile（dev/build/docker-build/docker-push/validate）
5. Backend 需要 `/health` 端点（前置 Auth 中间件）供 Docker HEALTHCHECK / K8s probe

### 添加 Helm Chart
1. `deployment/{service}/helm/` — 每个服务独立 Chart
2. 模板文件：deployment.yaml, service.yaml, configmap.yaml, secret.yaml, ingress.yaml, pvc.yaml
3. 环境 values：values.yaml（默认）, values-dev.yaml, values-test.yaml, values-pre.yaml, values-release.yaml
4. 参考模板模式：`_helpers.tpl`（release.name/namespace）, checksum/config 注解触发滚动更新
5. Backend 用 ConfigMap 挂载 config.yaml（变量用 ${ENV_VAR} 从 Secret 注入）
6. AiAgent 用 Secret envFrom 注入环境变量，PVC 挂载 /app/data
7. Ops-web 用 ConfigMap 挂载 nginx.conf（反向代理 + WebSocket 到 backend）

### 添加跨渠道用户配置缓存（Redis）
1. `internal/service/user_chat_config.go` — `SetUserChatConfig` + `GetUserChatConfig`
2. Redis Key: `chat:config:{user_id}` Hash（model_id, web_search_enabled, agent_mode_enabled）
3. Client chat 时保存配置 → Bot 消息时读取 ← Redis 不可用时降级到默认模型
4. `chat_hub.go` handleChatSend 中调用 SetUserChatConfig
5. `chat_sync.go` SyncChatMessage 中调用 GetUserChatConfig 决定模型和联网搜索

## Memory & Rules

| 文件 | 用途 |
|-----|------|
| `.ai/memory/lessons.json` | 经验教训库（结构化） |
| `.ai/memory/anti-patterns.md` | 已知错误模式 |
| `.ai/memory/successful-patterns.md` | 成功模式库 |
| `.ai/rules/architecture.md` | 架构规则（AI 可读，含 Agent Pipeline / Asynq / OTel 数据流图） |
| `.ai/traces/failures.log` | 失败记录 |
| `.ai/checkpoints/` | 任务检查点（自动保存） |

## Harness Auto-Updater

`scripts/harness_autoupdate.py` 在 PostCompact hook 上自动运行：
- 保存当前任务检查点到 `.ai/checkpoints/`
- 记录 session 事件到 `.ai/traces/failures.log`
- 保留最近 3 个 checkpoint，自动清理旧的

## Key Docs

| 文件 | 用途 |
|-----|------|
| `docs/ARCHITECTURE.md` | 系统架构概览 |
| `docs/DEVELOPMENT.md` | 开发环境搭建 |
| `docs/PRODUCT_SENSE.md` | 产品设计理念 |
| `docs/design-docs/` | 设计方案 |
| `docs/exec-plans/` | 执行计划 |
| `docs/superpowers/` | AI 开发超能力技能 |
| `.ai/rules/architecture.md` | 详尽架构规则（AI 可读图形式） |

## Before Each Task

1. Read `.ai/CURRENT_FOCUS` to check current task context
2. Read `.ai/memory/lessons.json` for lessons learned
3. Read `.ai/memory/anti-patterns.md` for known pitfalls
4. Run `make validate` to ensure clean state

## After Each Task

1. Run `make validate` to verify changes
2. Update `.ai/CURRENT_FOCUS` with new task state
3. Run `make memory-add` to record lessons learned
4. Check `scripts/check_dependencies.py` for layer violations
