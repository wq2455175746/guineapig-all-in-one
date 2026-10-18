# Backend API Design

## Metadata
- **Status**: implemented (updated to match current code)
- **Created**: 2026-05-21
- **Updated**: 2026-10-17
- **Package**: guineapig-backend
- **Tech**: Go 1.24, Echo v4, GORM (MySQL), go-redis, Asynq

> 说明：本文替换早期"tasks/sessions 模块"的草稿设计，描述**当前代码**的路由与数据模型。
> 权威来源：`packages/guineapig-backend/internal/router/router.go`。

## Overview

guineapig-backend 提供 REST API 作为业务编排层，负责用户、模型、对话、记忆、Skill、MCP、文件、
RAG、可观测指标、IM Bot 等业务，并通过 HTTP 调用 aiagent。

路由**集中注册**在 `internal/router/router.go` 的两个 `init()` 中，按前缀分三组：

| Prefix | Audience | Credential |
|--------|----------|------------|
| `/api/v1` | 客户端 / 用户侧 | User token（`X-User-Token` 或 `Authorization: Bearer`，HMAC-SHA256） |
| `/admin/api/v1` | 运营管理后台 | `X-Admin-Token` |
| `/inner/api/v1` | 内部服务回调（aiagent） | `X-Inner-Token`（fail-closed） |

公开路径（无需鉴权）：`/api/v1/client/login`、`/api/v1/client/register`、`/api/v1/chat/ws`、`/health`、`/api/v1/health`。

## API Modules (`/api/v1`)

### User Module
| Method | Path | Description |
|--------|------|-------------|
| POST | `/client/register` | 客户端注册 |
| POST | `/client/login` | 客户端登录（RSA 加密 API Key） |
| GET | `/users` | 用户列表 |
| GET | `/user/search` | 用户搜索 |
| GET | `/user/decryptUserInfo` | 解密用户敏感信息 |

### AI Model Module
| Method | Path |
|--------|------|
| POST | `/aimodel/create` · `/aimodel/update` · `/aimodel/delete` · `/aimodel/updateEstablished` · `/aimodel/test` |
| GET | `/aimodel/list` · `/aimodel/options` · `/aimodel/options-by-type` · `/aimodel/presigned-upload-url` · `/aimodel/presigned-download-url` |

### Chat Module
| Method | Path | Description |
|--------|------|-------------|
| GET | `/chat/ws` | WebSocket 对话通道（`?token=`） |
| POST | `/chat/send` | 发送消息 |
| GET | `/chat/conversations` | 会话列表 |
| GET | `/chat/messages` | 消息列表 |
| GET | `/chat/conversation-history` | 对话历史 |

### Memory Module
`GET /memory/list` · `GET /memory/get` · `POST /memory/delete` · `POST /memory/summarize` · `POST /memory/update-content`

### Skill Module
`GET /skill/presigned-upload-url` · `POST /skill/create|update|delete` · `GET /skill/list`

### MCP Module
`POST /mcp/create|update|delete` · `GET /mcp/list`

### File Module
`GET /file/presigned-upload-url|presigned-download-url|list` · `POST /file/create|update|delete|embed|embed-progress`

### RAG Module
`POST /rag/create|update|delete` · `GET /rag/list`

### OTEL (custom metrics) Module
`GET /otel/list` · `POST /otel/delete` · `GET /otel/chart/data`

### Bot Module
`POST /bot/bind|unbind` · `GET /bot/info`

## Admin API (`/admin/api/v1`, `X-Admin-Token`)

只读/管理镜像：`users`、`user/search`、`user/decryptUserInfo`、`aimodel/list`、`file/list`、`skill/list`、
`mcp/list`、`memory/list`、`memory/get`、`chat/conversation-history`、`chat/messages`、
`otel/list`、`otel/chart/data`、`task-scheduler/list`、`bot/list`。

## Inner API (`/inner/api/v1`, `X-Inner-Token`)

供 aiagent 回调：`POST /file/embed-progress`、`POST /memory/update-content`。

## Data Models

模型定义在 `internal/model/`，主键为自增 `int64`（Snowflake 仅用于生成新用户 `User.Id`）。
数据库迁移**不自动执行**（`config.yaml` 中 `autoMigrate: false`），schema 由 `sql/` 管理。

| Model | Table | 说明 |
|-------|-------|------|
| `User` | `user` | 用户（注册/登录） |
| `UserApiKey` | `user_apikey` | 用户 API Key（RSA 加密存储） |
| `UserAiModel` | `user_aimodel` | 用户模型配置 |
| `ChatConversation` | `chat_conversations` | 会话 |
| `ChatMessage` | `chat_messages` | 消息 |
| `ChatMemory` | `chat_memory` | 记忆 |
| `ChatOtel` | `chat_otel` | 对话指标 |
| `BotBinding` | `chat_bot_binding` | IM Bot 绑定 |
| `ResFiles` | `res_files` | 文件资源 |
| `ResMcp` | `res_mcps` | MCP 资源 |
| `ResRags` | `res_rags` | 知识库资源 |
| `ResSkills` | `res_skills` | Skill 资源 |

## Response Format

```json
{
  "code": 0,
  "message": "success",
  "result": { },
  "request_id": "uuid"
}
```

列表接口敏感字段返回掩码 `***`。

## Auth & Middleware

全局中间件顺序（`internal/server/server.go`）：`RequestId → RateLimit(concurrency) → Logger → Recover → CORS → Auth`。

- 用户 token 为自研 HMAC-SHA256 签名，配置项名为 `JWT_SECRET`（历史命名），**并非 JWT**。
- 身份从 token 推导；`X-User-Id` 不再作为可信身份（防 IDOR，`BindRequester` 覆盖）。
- 限流当前仅实现**并发限制**；QPS 字段预留未接线。
- AIModel 连接测试有 SSRF 白名单（`AIMODEL_ALLOWED_HOSTS`，默认仅本机回环）。

## Background Jobs (Asynq)

| Task | Schedule | Purpose |
|------|----------|---------|
| `otel:sync` | 每 5 分钟 | Redis 指标 → MySQL `chat_otel` |
| `memory:summarize` | 每 12 小时 | 触发 aiagent 记忆摘要 |
