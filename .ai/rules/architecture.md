# Architecture Rules

## Layer Dependency Rules

```
┌─────────────────────────────────┐
│     guineapig-client            │  Electron + Vue 3
│     (桌面客户端)                  │
├─────────────────────────────────┤
│     guineapig-ops-web           │  Vue 3 + Vite + Element Plus
│     (运营管理 Web)                │
└──────────┬──────────────────────┘
           │ HTTP/WebSocket
┌──────────▼──────────────────────┐
│     guineapig-backend           │  Go + Echo v4 + GORM
│     (业务后端)                    │
└──────────┬──────────────────────┘
           │ HTTP/gRPC
┌──────────▼──────────────────────┐
│     guineapig-aiagent           │  FastAPI + ASR + TTS + LLM
│     (AI 能力服务)                 │
└──────────┬──────────────────────┘
           │
    ┌──────┴──────┐
    │  MySQL/Redis │  S3
    └─────────────┘
```

## Critical Rules

1. **backend 禁止直接调用 AI 模型**：所有 LLM/ASR/TTS 调用必须通过 aiagent
2. **禁止跨 package 代码共享**：各 package 独立部署，通过 API 契约通信
3. **数据层仅 backend 直连**：MySQL/Redis 只有 backend 直连，aiagent 通过 backend API 获取/更新数据
4. **例外：aiagent 可直写 Redis OTel 指标**：`otel:metrics:{stat_date}:{user_id}` Hash 由 aiagent HINCRBY 写入，backend Asynq 任务定期 SCAN + UPSERT 到 MySQL。Redis key 设置 2 天 TTL 自动过期
5. **音频文件通过 S3 中转**：client 上传到 S3，传递路径给 backend，aiagent 从 S3 读取
6. **Backend 定时任务迁移到 Asynq 分布式队列**：不再使用 goroutine + ticker，统一使用 Asynq Scheduler（定时触发）+ Server（Worker 消费）模式

## Tech Stack Per Package

### guineapig-backend
- Go 1.24.0
- Echo v4 (HTTP 框架)
- GORM (ORM, MySQL 驱动)
- go-redis (缓存)
- Viper (配置)
- Zap (日志)

### guineapig-aiagent
- Python 3.11+ / FastAPI
- SenseVoice-Small (ASR)
- CosyVoice2-0.5B (TTS)
- DeepSeek API (LLM, OpenAI 兼容接口)
- MCP / Agent Skills / RAG Embedding
- Milvus (向量数据库)
- OpenAI Python SDK (所有 LLM 调用统一通过 OpenAI 兼容接口)

### guineapig-ops-web
- Vue 3 + Vite
- Element Plus (UI)
- ECharts (图表)

### guineapig-client
- Electron
- Vue 3 (渲染进程)

## AI Agent Pipeline 架构

```
                              ┌─ TRIVIAL ──> _direct_llm_stream() (SSE 流式短路)
                              │
用户请求 ──> Phase 0: QuickFilter ── SIMPLE ──> Phase 1: IntentScanner (关键词匹配)
                              │                    │
                              └─ COMPLEX ──> Phase 2: DeepAnalyzer (LLM 深度分析)
                                                  │
                                             Phase 3: IntentDecision (综合判定)
                                                  │
                                             DAGGenerator (LLM 生成执行计划)
                                                  │
                                             DAGExecutionEngine (拓扑排序 → 逐步执行)
                                                  │
                                             SSE 事件流 (chunk/tool_call/done/error)
```

- **TRIVIAL 短路**：问候/闲聊类问题直接调用 LLM 流式返回，跳过所有 Pipeline 阶段
- **SIMPLE 路径**：关键词匹配后直接查询能力清单，不使用 LLM 分析
- **COMPLEX 路径**：全流程 Pipeline（DeepAnalyzer→IntentDecision→DAGGenerator→DAGExecutionEngine）
- **Fallback 降级**：所有分支最终都可以降级到 `_direct_llm_stream()` 返回 SSE 流

## Data Flow (核心语音对话流程)

1. Client 上传 MP3 到 S3
2. Client 提交任务到 Backend（user_id, s3_path, task_id）
3. Backend 任务入库 MySQL
4. Backend 转发任务到 AIAgent
5. AIAgent 从 S3 拉取音频 -> ASR 解析 -> 读取 Redis 上下文 -> LLM 驱动循环 -> TTS 生成
6. 对话结束或强制结束 -> 状态入库 -> 上下文归档 S3

## Configuration Rules

- 敏感信息（密码、API Key）只在 `.env` 文件中，不提交 git
- `config.yaml` 中使用 `${VAR}` 占位符引用环境变量
- 每个 package 有自己的配置，不共享配置文件

## Asynq Task Queue

```
┌──────────────────┐     ┌──────────────┐     ┌──────────────────────┐
│ Asynq Scheduler  │ ──> │   Redis      │ ──> │  Asynq Server        │
│ (定时触发)         │     │  (任务队列)    │     │  (Worker 消费)        │
└──────────────────┘     └──────────────┘     └──────────────────────┘
```

- Backend `pkg/tasks/` 定义任务类型和 Handler
- `Scheduler` 注册 cron 表达式定时入队
- `Server` 注册 Handler 异步消费
- 替代旧的 goroutine+ticker + rdb.Del() 模式

## OTel Metrics 数据流

```
aiagent (HINCRBY) ──> Redis Hash ──> backend Asynq Worker ──> MySQL UPSERT
     │              otel:metrics:       (SCAN + HGETALL)       INSERT ... ON
     │              {date}:{uid}                               DUPLICATE KEY
     │              2天 TTL                                    UPDATE JSON_SET
     └── 指标: input_token, output_token, request_count, ...
```

- aiagent 使用 `otel_service.py` 直接 HINCRBY 写入 Redis（唯一 Redis 直写例外）
- Backend `otel_sync.go` Asynq Worker 定期 SCAN keys → HGETALL → MySQL Batch UPSERT
- Redis key 不手动删除，由 2 天 TTL 自动过期
- 使用 `UPSERT` (INSERT ... ON DUPLICATE KEY UPDATE) 保证指标累加不丢失

## IM Bot 集成架构

```
IM 平台 (Feishu/WeChat/DingTalk)
    │ Webhook/Callback
┌───▼──────────────────────┐
│  Bot interface            │  BotManager: RegisterBot(platform, bot)
│  - FeishuBot              │  handleBotMessage: 消息分发 + BotUserID 自动绑定
│  - WeChatBot (预留)        │  StartupBots(): 启动时注册所有已配置 Bot
│  - DingTalkBot (预留)      │
└──────────┬───────────────┘
           │ SyncChatMessage(ctx, userID, platform, extChatID, content)
┌──────────▼───────────────┐
│  UserChatConfig (Redis)   │  GetUserChatConfig → 读取 modelID/webSearch/agentMode
│  chat:config:{user_id}    │  缓存用户最新 Client 端配置，无缓存时降级到默认模型
└──────────┬───────────────┘
           │ modelID + webSearchEnabled
┌──────────▼───────────────┐
│  callAiAgentLLM           │  POST /guineapig-aiagent/llm/chat/stream
│  (同步方式收集 SSE 流)      │  只走 LLM 路径，不执行 MCP stdio/skill
└──────────┬───────────────┘
           │ reply text
┌──────────▼───────────────┐
│  Bot.sendMessage()        │  向 IM 平台发送回复
└──────────────────────────┘
```

### IM Bot 关键规则
- Bot 消息使用同步方式（`SyncChatMessage`），非 WebSocket 流式（Client 端使用流式）
- Bot 只走 LLM 流路径（`/llm/chat/stream`），不走 Agent 路径（`/agent/chat/stream`），因为 MCP stdio/skill 需要 client 端执行
- Bot AppSecret 使用 RSA 非对称加密传输（前端加密 → 后端解密存储）
- Bot 消息有独立令牌桶限流器（`rateLimiter.botQps`，默认 5 QPS，可配置）
- 每个 Bot 平台独立实现 Bot interface（SendMessage, parseMessage, verifySign）

## Redis 用户聊天配置缓存

```
Client chat 写入:                         Bot 消息读取:
chat_hub.go                               chat_sync.go
  └─ SetUserChatConfig()                    └─ GetUserChatConfig()
       └─ HSET chat:config:{uid}                 └─ HGETALL chat:config:{uid}
            model_id=N                               modelID>0 → loadModelConfig(modelID)
            web_search_enabled=true                  modelID=0 → loadDefaultModelConfig() (降级)
            agent_mode_enabled=false
```

- **Key**: `chat:config:{user_id}` (Hash, 无 TTL，每次 Client chat 更新覆盖)
- **用途**: Client 端每次 chat 携带 modelId/webSearchEnabled/agent_mode，保存到 Redis。Feishu Bot 等外部渠道读取此配置，使用用户最新选择的模型和参数
- **降级策略**: Redis 不可用或 key 不存在时，返回零值 (0/false/false)，SyncChatMessage 降级到 loadDefaultModelConfig 使用第一个可用模型

## Helm Chart 部署结构

```
deployment/
├── backend/helm/              # Go 应用 - port 6880
│   ├── Chart.yaml
│   ├── values-{env}.yaml       # dev/test/pre/release
│   └── templates/
│       ├── deployment.yaml     # config.yaml ConfigMap 挂载, HTTP GET /health 探针
│       ├── service.yaml        # ClusterIP
│       ├── configmap.yaml      # config.yaml 嵌入 (${ENV_VAR} 从 Secret 注入)
│       ├── secret.yaml         # MYSQL_PASSWORD, REDIS_PASSWORD, JWT_SECRET, S3_AK/SK
│       └── ingress.yaml        # 按环境启用
├── aiagent/helm/              # Python FastAPI - port 8000
│   ├── ...                     # Secret envFrom 注入环境变量
│   └── templates/
│       └── pvc.yaml            # /app/data 持久化（技能数据）
└── ops-web/helm/              # Nginx 静态服务 - port 80
    ├── ...                     # ConfigMap 挂载 nginx.conf
    └── templates/
        └── configmap.yaml      # nginx.conf（API 反向代理 + WebSocket 到 backend）
```

### Docker 构建规则
- Backend: `golang:1.24-alpine` builder → `alpine:3.19` runtime (静态编译, CGO_ENABLED=0)
- AiAgent: `python:3.13-slim` (pip install 在 builder stage → runtime 只拷贝 site-packages)
- Ops-web: `node:22-alpine` build → `nginx:alpine` serve (多阶段)
- 所有服务必须暴露 `/health` 端点供 HEALTHCHECK / K8s probe 使用
- Backend 的 `/health` 和 `/api/v1/health` 必须注册在 Auth 中间件之前
