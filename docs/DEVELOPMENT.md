# GuineaPig Development Guide

> 本文档描述**当前代码**的开发方式。与代码不一致处，以各 package 的 `Makefile` / `package.json` / `pyproject.toml` 为准。

## Project Overview

GuineaPig 是一个以语音交互为核心的 AI 桌面助手 monorepo 项目，包含 4 个独立 package：

| Package | Language | Purpose |
|---------|----------|---------|
| `guineapig-backend` | Go 1.24 | 业务编排层，提供 REST API + WebSocket |
| `guineapig-aiagent` | Python 3.13+ | AI 能力服务 (ASR/LLM/TTS/Agent/RAG) |
| `guineapig-ops-web` | JavaScript (Vue 3) | 运营管理后台 |
| `guineapig-client` | TypeScript (Electron) | 桌面客户端 |

## Prerequisites

- Go 1.24.0+
- Python 3.13+ (推荐使用 [uv](https://docs.astral.sh/uv/))
- Node.js 20.19+ / 22.12+ (ops-web 要求)
- Docker & Docker Compose (for local services: MySQL, Redis, MinIO)
- Make

## Quick Start

```bash
# 1. 初始化工作区目录（.ai/、docs/exec-plans 等）
make init

# 2. 启动基础设施 (MySQL, Redis, MinIO)
docker compose up -d mysql redis minio

# 3. 安装各 package 依赖
cd packages/guineapig-backend && go mod download && cd ../..
cd packages/guineapig-aiagent && uv sync && cd ../..
cd packages/guineapig-ops-web && npm install && cd ../..
cd packages/guineapig-client && npm install && cd ../..

# 4. 启动开发环境
make dev                    # docker compose --profile all
# 或分别启动：
make dev-backend            # 后端 (Go)      — 端口 6880
make dev-aiagent            # AI Agent (uv)  — 端口 8000
make dev-frontend           # 运营管理后台    — 端口 5173
make dev-client             # 桌面客户端      — 端口 5174 (README)
```

## Development Workflow

### guineapig-backend (Go)

```bash
cd packages/guineapig-backend

make dev            # 有 air 则热重载，否则 go run main.go
make build          # go build -o bin/guineapig main.go
make test           # go test ./... -v -count=1
make validate       # go vet ./...
```

**路由注册模式**: 路由**集中**在 `internal/router/router.go` 注册（不是分散的每文件 `init()`）：

```go
// internal/router/router.go
func init() {
    AddGetRouter("/users", user.ListUser)          // -> /api/v1/users
    AddPostRouter("/client/login", user.ClientLogin)
    // 运营后台：addAdminRouter(...)  -> /admin/api/v1/...
    // 内部回调：addInnerRouter(...)  -> /inner/api/v1/...
}
```

- `internal/model/` — GORM 模型（主键自增 `int64`）
- `internal/request/` / `internal/response/` — API 契约
- `internal/service/` — 业务逻辑（`plugin.GetDB(ctx)` 取 DB）
- 配置：Viper + `config.yaml` + `.env`（`${VAR}` 展开）
- 日志：Zap，`request_id` 由中间件注入

### guineapig-aiagent (Python)

```bash
cd packages/guineapig-aiagent

make dev            # uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
make test           # uv run pytest -q --ignore=test/routers_agent_test.py
make validate       # import 检查
uv run ruff check . # 代码检查（如已安装 ruff）
```

**API 注册模式**: 使用 FastAPI `APIRouter`，前缀为 `/guineapig-aiagent/<module>`：

```python
# app/routers/agent.py
router = APIRouter(prefix="/guineapig-aiagent/agent", tags=["agent"])

@router.post("/chat/stream")
async def agent_chat_stream(request: AgentChatRequest):
    ...
```

- `app/routers/` — API 端点（**不是** `api/v1/`）
- `app/services/` — 原子能力服务（ASR/TTS/LLM/RAG/Memory/Skill）
- `app/agent/` — Agent 引擎：`intent/`（QuickFilter + DeepAnalyzer）、`dag/`（Generator + Validator）、`executor/`（Engine + Handlers + middleware）
- `app/schemas/` — Pydantic 模型；`app/core/` — 客户端/工具（LLM、Milvus、S3、日志）
- 鉴权：`X-Admin-Token`；ASR/TTS 为外部 HTTP API（`ASR_API_URL` / `TTS_API_URL`）

### guineapig-ops-web (Vue 3)

```bash
cd packages/guineapig-ops-web

npm run dev         # Vite dev server (5173)
npm run build       # NODE_ENV=production vite build
npx eslint src/     # 代码检查
```

- Vue 3.5 + Vite 7 + **PrimeVue 4 (Aura)** + ECharts + axios + vue-router（无 Pinia）
- 页面组件在 `src/views/`
- API 封装在 `src/config/`（`axios.js` 注入 `X-Admin-Token`；`api.js` 定义端点，前缀 `/admin/api/v1`）
- 可复用逻辑在 `src/composables/`

### guineapig-client (Electron)

```bash
cd packages/guineapig-client

npm run electron:dev     # 开发模式
npm run build            # vue-tsc && vite build
npm run electron:build   # 构建安装包 (electron-builder)
```

- TypeScript + Electron 42 + Vue 3 + PrimeVue（无 Pinia）
- `src/main/`（主进程：窗口、IPC、MCP、命令执行）、`src/preload/`（contextBridge）
- `src/renderer/`（主窗口）、`src/renderer-overlay/`（浮层窗口）
- `src/composables/useRecorder.ts` + `src/audio/recorder-worklet.js`（AudioWorklet 录音）
- `src/utils/rsa.ts`（jsencrypt 加密登录凭据）

## Architecture Constraints

1. **层级依赖**: `client` / `ops-web` -> `backend` -> `aiagent`，不可反向依赖
2. **backend 只做业务逻辑**，AI 相关操作必须通过 aiagent
3. **跨 package 通信**只通过 HTTP/WebSocket API 契约，不共享代码
4. **音频文件通过 S3 中转**: client 上传 -> backend 入库 -> aiagent 消费
5. **工具信任边界**: server 端能力（web/rag/memory/llm/mcp-sse）在 aiagent 执行；client 端能力（cli/skill/mcp-stdio）通过 delegate 在客户端执行

See `docs/ARCHITECTURE.md` for detailed architecture rules.

## Code Conventions

### Go (guineapig-backend)

- 请求/响应结构体分别在 `internal/request/`、`internal/response/`
- GORM Model 在 `internal/model/`，通过全局单例（如 `model.MUser`）+ `plugin.GetDB(ctx)` 访问
- 业务逻辑在 `internal/service/`
- 日志用 Zap，`logger.WithContext(ctx)` 自动携带 `request_id`
- 配置用 Viper + YAML + `.env`
- 数据库迁移**不自动执行**（`autoMigrate: false`），schema 由 `packages/guineapig-backend/sql/` 管理

### Python (guineapig-aiagent)

- API 端点在 `app/routers/`
- 业务服务在 `app/services/`，Agent 引擎在 `app/agent/`
- 数据模型在 `app/schemas/`
- 外部调用（ASR/TTS/LLM/搜索）统一加超时；LLM 客户端有缓存与有界重试（`app/core/llm_clients.py`）
- 关键配置集中在 `app/config.py`（`pydantic-settings`，读取 `.env`）

### JavaScript / TypeScript (ops-web / client)

- 页面组件在 `src/views/`；API 调用层在 `src/config/`（ops-web）或 `src/renderer/api.ts`（client）
- UI 组件库使用 **PrimeVue 4**
- 状态使用 Vue `ref` / `localStorage` / composables（**不使用 Pinia**）

## Testing

```bash
# 运行所有测试
make test

# 运行单个 package 测试
make test-guineapig-backend

# API 冒烟测试
scripts/verify/test_api.sh

# 跨项目集成测试
scripts/verify/test_cross_project.sh

# 完整验证
make validate
```

**注意**: 集成测试需要所有服务在本地运行。服务未运行时测试会跳过，不视为失败。

## Deployment

```bash
# 一键构建 Docker 镜像
make build-docker

# 本地部署
scripts/docker/deploy-local.sh

# 构建 Electron 客户端安装包
make build-client
```

### Service Ports

| Service | Port | Protocol |
|---------|------|----------|
| guineapig-backend | 6880 | HTTP |
| guineapig-aiagent | 8000 | HTTP |
| guineapig-ops-web | 5173 | HTTP (dev) |
| guineapig-client | 5174 | HTTP (dev) |
| MySQL | 3306 | TCP |
| Redis | 6379 | TCP |
| MinIO (S3) | 9000 | HTTP |
| Milvus | 19530 | TCP |

### Environment Variables

每个 package 有独立的 `.env`（参考各自 `.env.example`）：

```bash
# guineapig-backend/.env
MYSQL_USERNAME=guineapig
MYSQL_PASSWORD=secret
MYSQL_HOST=localhost:3306
REDIS_HOST=localhost:6379
REDIS_PASSWORD=
JWT_SECRET=change-me              # 用户 token HMAC 密钥
ADMIN_TOKEN=...                   # /admin/api/v1 鉴权
INNER_TOKEN=...                   # /inner/api/v1 鉴权（fail-closed）
AIAGENT_BASE_URL=http://localhost:8000
AIMODEL_ALLOWED_HOSTS=api.deepseek.com
S3_BUCKET=...
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY=...
S3_SECRET_KEY=...

# guineapig-aiagent/.env
ADMIN_TOKEN=...                   # 与调用方一致的内部 token
INNER_TOKEN=...                   # 回调 backend /inner/api/v1
CORS_ORIGINS=[...]
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=sk-xxx
LLM_MODEL_NAME=deepseek-chat
ASR_API_URL=http://localhost:9991/v1/audio/transcriptions
TTS_API_URL=http://localhost:9992/inference_zero_shot
MILVUS_HOST=localhost
MILVUS_PORT=19530
BACKEND_BASE_URL=http://localhost:6880
SEARXNG_URL=...
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
```

敏感信息（密码、API Key）不提交 git。参考各 package 的 `.env.example` 创建本地 `.env`。

## Troubleshooting

### Go 模块下载失败
```bash
cd packages/guineapig-backend
go env -w GOPROXY=https://goproxy.cn,direct  # 国内环境
go mod download
```

### Python 依赖安装
```bash
cd packages/guineapig-aiagent
uv sync                                     # 使用 uv.lock
# 或 pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### Docker 服务无法启动
```bash
docker compose down -v   # 清除数据卷
docker compose up -d     # 重新启动
```

### 端口冲突
修改对应 package 配置文件中的端口号，或停用占用端口的进程。
