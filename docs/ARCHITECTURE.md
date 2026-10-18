# GuineaPig Architecture

> 本文档描述**当前代码实现**的架构事实（端口、路由前缀、鉴权、依赖、数据流）。
> 与代码不一致处，以代码为准。设计/方案类文档见 `docs/design-docs/`。

## Layer Definitions

```
┌─────────────────────────────────────────────┐
│  Layer 4: Presentation                       │
│  guineapig-client (Electron 42 + Vue 3)     │  桌面客户端
│  guineapig-ops-web (Vue 3 + Vite + PrimeVue)│  运营管理 Web
├─────────────────────────────────────────────┤
│  Layer 3: Business                           │
│  guineapig-backend (Go 1.24 + Echo v4)      │  业务编排层
├─────────────────────────────────────────────┤
│  Layer 2: AI Capability                      │
│  guineapig-aiagent (Python 3.13 + FastAPI)  │  AI 能力服务
├─────────────────────────────────────────────┤
│  Layer 1: Infrastructure                     │
│  MySQL / Redis / S3 (MinIO) / Milvus        │  数据存储
└─────────────────────────────────────────────┘
```

> 说明：ASR / TTS 在**运行期是外部 HTTP 服务**（由 aiagent 通过 `ASR_API_URL` / `TTS_API_URL` 调用），
> 并非内嵌在 aiagent 进程中的模型。**Milvus 为 RAG 所需的外部依赖**（默认 `localhost:19530`），
> 本仓库 `docker-compose.yml` 只包含 MySQL / Redis / MinIO。

## Dependency Rules

### Layer Communication
1. **Layer 4 -> Layer 3**: HTTP REST / WebSocket only. No shared code.
2. **Layer 3 -> Layer 2**: HTTP REST only. Backend never imports AI libraries.
3. **Layer 2 -> Layer 1**: Direct access to S3 (read/write audio, skill zip), Redis (context cache), Milvus (RAG), MySQL **only via Backend API**.
4. **Layer 3 -> Layer 1**: Direct access to MySQL (business data) and Redis (session/cache/queue).

### Forbidden Dependencies
- ❌ Backend directly importing `openai`, `anthropic`, `langchain`, or any AI/ML library
- ❌ Frontend/Client directly calling AIAgent (must go through Backend)
- ❌ Cross-package `internal/` imports between packages
- ❌ AIAgent directly writing to MySQL (must go through Backend API)

### Allowed Dependencies
- ✅ Backend calling AIAgent via HTTP for ASR/TTS/LLM/Agent tasks
- ✅ Client/OpsWeb calling Backend for all business operations
- ✅ AIAgent reading/writing S3 for audio and skill files
- ✅ AIAgent reading/writing Redis for conversation context and metrics
- ✅ AIAgent calling Backend `/inner/api/v1/*` with `X-Inner-Token` for progress/memory callbacks

## Tech Stack Per Package

### guineapig-backend
| Component | Technology | Purpose |
|-----------|-----------|---------|
| Language | Go 1.24.0 | Backend service |
| HTTP | Echo v4.13 | REST API framework |
| WebSocket | gorilla/websocket | Client chat channel |
| ORM | GORM (mysql + sqlite) | MySQL database access |
| Cache | go-redis v9 | Redis caching / session |
| Queue | Asynq (Redis-backed) | Scheduled / async tasks |
| Object Storage | aws-sdk-go-v2 (S3) | Presigned upload/download |
| Config | Viper + godotenv | YAML + `.env` configuration |
| Logging | Zap | Structured logging |
| IM SDK | larksuite/oapi-sdk-go v3 | Feishu / Lark bot |
| ID | bwmarrin/snowflake | New user ID generation |

> 端口 **6880**（`packages/guineapig-backend/config.yaml`）。用户 token 为自研 **HMAC-SHA256** 签名（形如 `base64url(userID:expiry).base64url(sig)`），
> 配置项名为 `jwtSecret`/`JWT_SECRET` 但并非 JWT。主键为自增 `int64`，Snowflake 仅用于生成新用户 `User.Id`。

### guineapig-aiagent
| Component | Technology | Purpose |
|-----------|-----------|---------|
| Language | Python 3.13+ | AI service |
| HTTP | FastAPI + Uvicorn | REST API framework (port 8000) |
| LLM | `openai` SDK (OpenAI-compatible, default DeepSeek) | Language model |
| ASR | **External HTTP API** (`ASR_API_URL`) | Speech recognition |
| TTS | **External HTTP API** (`TTS_API_URL`) | Speech synthesis |
| Agent Runtime | 自研 intent → DAG → executor | Plan-then-Execute 编排 |
| Tool Protocol | MCP (sse / streamable-http) | Tool invocation |
| Vector DB | Milvus (pymilvus) | RAG retrieval |
| Tracing | Langfuse | LLM observability |
| Metrics | prometheus-client (+ custom Redis metrics) | Observability |
| Scheduler | APScheduler | Memory monitoring job |

> 路由前缀为 `/guineapig-aiagent/<module>`，**不是** `/api/v1/`。编排为自研 DAG 引擎，**未使用 LangGraph**。

### guineapig-ops-web
| Component | Technology | Purpose |
|-----------|-----------|---------|
| Language | JavaScript (ESM) | Web frontend |
| Framework | Vue 3.5 + Vite 7 | UI framework |
| UI Kit | PrimeVue 4 (Aura theme) | Component library |
| Charts | ECharts 5 | Data visualization |
| Router | vue-router 4 (history) | Routing |
| HTTP | axios | API client |

> 运营后台使用 **PrimeVue**（非 Element Plus），**无 Pinia**（状态用 `ref` + 模块单例），JavaScript 非 TypeScript。
> 开发端口 5173，API 前缀 `/admin/api/v1`（管理）与 `/api/v1`（登录注册）。

### guineapig-client
| Component | Technology | Purpose |
|-----------|-----------|---------|
| Language | TypeScript | Desktop client |
| Framework | Electron 42 + Vue 3.5 | Desktop + UI |
| UI Kit | PrimeVue 4 (Aura theme) | Component library |
| Router | vue-router 4 (hash) | Routing |
| Audio | AudioWorklet + lamejs | Recording & MP3 encoding |
| Crypto | jsencrypt (RSA) | Credential encryption |
| Tools | @modelcontextprotocol/sdk | MCP client (stdio / sse / streamable-http) |

> 客户端有两个渲染进程：主窗口（`index.html`）与浮层窗口（`overlay.html`）。
> **无 Pinia**，**无 ffmpeg**（MP3 由 lamejs 在渲染进程内编码）。开发端口 README 使用 5174。

## Route Prefixes & Auth (Backend)

Backend 的路由全部集中在 `packages/guineapig-backend/internal/router/router.go` 的两个 `init()` 中注册，
按前缀分为三组，由全局 `Auth` 中间件分别鉴权：

| Prefix | Audience | Required credential |
|--------|----------|---------------------|
| `/api/v1` | 客户端 / 用户侧 API | User token：`X-User-Token` 或 `Authorization: Bearer <token>` |
| `/admin/api/v1` | 运营管理后台 | `X-Admin-Token` |
| `/inner/api/v1` | 内部服务回调（aiagent） | `X-Inner-Token`（fail-closed） |

Public paths（无需鉴权）：`/api/v1/client/login`、`/api/v1/client/register`、`/api/v1/chat/ws`（ws token 由查询参数校验）、
`/health`、`/api/v1/health`。

> `X-Device-Id` 仅作为设备标识/CORS 头，**不是**鉴权 token；`X-User-Id` 不再作为可信身份，服务端从 token 推导用户身份。

## AIAgent Route Map

| Module | Prefix | Endpoints |
|--------|--------|-----------|
| asr | `/guineapig-aiagent/asr` | `POST /transcribe` |
| task | `/guineapig-aiagent/task` | `POST /submit` |
| llm | `/guineapig-aiagent/llm` | `POST /chat/stream` |
| memory | `/guineapig-aiagent/memory` | `POST /summarize` |
| rag | `/guineapig-aiagent/rag` | `POST /embed`, `POST /delete-embeddings` |
| skill | `/guineapig-aiagent/skill` | `POST /process` |
| agent | `/guineapig-aiagent/agent` | `POST /chat`, `POST /chat/stream`, `POST /chat/confirm`, `POST /chat/cancel`, `POST /chat/delegate-result` |
| — | `/` | `GET /`, `GET /health`, `GET /metrics` |

AIAgent 鉴权：`X-Admin-Token` 或 `Authorization: Bearer <token>`，与 `settings.ADMIN_TOKEN` 常量时间比较，fail-closed。

## Data Flow

### Core Voice Dialogue Flow (async)
```
1. Client records audio (AudioWorklet) and encodes MP3 (lamejs)
2. Client requests presigned URL from Backend and uploads MP3 to S3
3. Client sends message over WebSocket: /api/v1/chat/ws?token=<user_token>
4. Backend proxies to AIAgent POST /guineapig-aiagent/agent/chat/stream (SSE)
5. AIAgent:
   a. QuickFilter (Phase 0) -> DeepAnalyzer (Phase 1) -> DAGGenerator
   b. DAGExecutionEngine executes steps (server capabilities direct; client capabilities delegated)
   c. For delegated steps (cli / skill / stdio-mcp) emits STEP_AWAITING_CLIENT
   d. Streams SSE events back to Backend
6. Backend relays SSE events to Client over WebSocket
7. Client:
   - Server-side steps: rendered directly
   - Client-delegated steps: executes locally (CLI whitelist / MCP SDK) and POSTs result to
     AIAgent POST /guineapig-aiagent/agent/chat/delegate-result
8. Audio reply (TTS) is produced via external TTS HTTP API and stored in S3
```

### Tool Execution Trust Boundary
```
Server-side (aiagent):  web_search · rag · memory · llm_chat · mcp (sse/streamable-http)
Client-side (Electron):  cli · skill · mcp (stdio)
```
AIAgent `CapabilityRegistry` 扫描可用能力；`execution_location=client` 的步骤通过
HITL / client-delegate 机制下发到客户端执行。

### Context / Memory Flow (scheduled)
```
1. Asynq scheduler triggers memory:summarize (every 12h) and otel:sync (every 5m)
2. AIAgent POST /guineapig-aiagent/memory/summarize summarizes conversation
3. Summary written back via Backend /inner/api/v1/memory/update-content (X-Inner-Token)
4. Chat metrics written to Redis (otel:metrics:*) and synced to MySQL chat_otel
```

## Port Allocations

| Service | Port | Protocol |
|---------|------|----------|
| guineapig-backend | 6880 | HTTP |
| guineapig-aiagent | 8000 | HTTP |
| guineapig-ops-web | 5173 | HTTP (dev) |
| guineapig-client | 5174 | HTTP (dev, README) |
| MySQL | 3306 | TCP |
| Redis | 6379 | TCP |
| MinIO (S3) | 9000 | HTTP |
| Milvus | 19530 | TCP |

> gRPC 端口（历史文档中的 50051）当前**未使用**。

## Security Rules

1. Backend `/api/v1/*` 需要 user token（HMAC-SHA256）；`/admin/api/v1/*` 需要 `X-Admin-Token`；`/inner/api/v1/*` 需要 `X-Inner-Token`（fail-closed）。
2. AIAgent 内部 API 不对外暴露，仅通过 `X-Admin-Token` 访问（internal network only）。
3. S3 使用 presigned URL 上传/下载（默认 15 分钟过期）。
4. 客户端登录使用 RSA（jsencrypt）公钥加密 API Key 传输；后端 `crypto/rsa` 私钥解密。
5. `.env` 文件不提交 git；敏感配置（DB 密码、S3 密钥、token）以环境变量注入。
6. AIModel 连接测试有 SSRF 白名单（`AIMODEL_ALLOWED_HOSTS`，默认仅本机回环）。
