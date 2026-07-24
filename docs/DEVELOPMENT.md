# GuineaPig Development Guide

## Project Overview

GuineaPig 是一个以语音交互为核心的 AI 桌面助手 monorepo 项目，包含 4 个独立 package：

| Package | Language | Purpose |
|---------|----------|---------|
| `guineapig-backend` | Go 1.24 | 业务编排层，提供 REST API |
| `guineapig-aiagent` | Python 3.11+ | AI 能力服务 (ASR/TTS/LLM) |
| `guineapig-ops-web` | JavaScript (Vue 3) | 运营管理后台 |
| `guineapig-client` | JavaScript (Electron) | 桌面客户端 |

## Prerequisites

- Go 1.24.0+
- Python 3.11+
- Node.js 18+
- Docker & Docker Compose (for local services: MySQL, Redis, MinIO)
- Make

## Quick Start

```bash
# 1. 初始化 Harness 工作区
make init

# 2. 启动基础设施 (MySQL, Redis, MinIO)
docker compose -f docker-compose.dev.yml up -d

# 3. 安装各 package 依赖
cd packages/guineapig-backend && go mod download && cd ../..
cd packages/guineapig-aiagent && pip install -r requirements.txt && cd ../..
cd packages/guineapig-ops-web && npm install && cd ../..
cd packages/guineapig-client && npm install && cd ../..

# 4. 启动开发环境
make dev
```

## Development Workflow

### guineapig-backend (Go)

```bash
cd packages/guineapig-backend

# 运行
make dev

# 编译验证
make build

# 运行测试
make test

# 代码检查
go vet ./...
gofmt -l .
```

**路由注册模式**: 使用 `init()` 自动注册，每个资源目录下添加路由文件：

```go
// internal/router/user/list_user.go
func init() {
    router.AddGetRouter("/api/v1/users", listUser)
}
```

### guineapig-aiagent (Python)

```bash
cd packages/guineapig-aiagent

# 运行
make dev

# 安装依赖
pip install -r requirements.txt

# 代码检查 (ruff)
ruff check .
```

**API 注册模式**: 使用 FastAPI APIRouter：

```python
# api/v1/tasks.py
router = APIRouter(prefix="/api/v1/tasks")

@router.post("/process")
async def process_task(request: TaskRequest):
    ...
```

### guineapig-ops-web (Vue 3)

```bash
cd packages/guineapig-ops-web

# 开发模式
npm run dev

# 构建
npm run build

# 代码检查
npx eslint src/
```

### guineapig-client (Electron)

```bash
cd packages/guineapig-client

# 开发模式
npm run dev

# 构建安装包
npm run build:electron
```

## Architecture Constraints

1. **层级依赖**: `client` -> `backend` -> `aiagent`，不可反向依赖
2. **backend 只做业务逻辑**, AI 相关操作必须通过 aiagent
3. **跨 package 通信**只通过 HTTP/WebSocket API 契约，不共享代码
4. **音频文件通过 S3 中转**: client 上传 -> backend 入库 -> aiagent 消费

See `docs/ARCHITECTURE.md` for detailed architecture rules.

## Code Conventions

### Go (guineapig-backend)

- 使用 `internal/request/` 和 `internal/response/` 分别定义请求/响应结构体
- GORM Model 定义在 `internal/model/`
- 业务逻辑在 `internal/service/` 中实现
- 日志使用 Zap，通过 `logger.WithContext(ctx)` 自动携带 request_id
- 配置使用 Viper + YAML + `.env` 分层

### Python (guineapig-aiagent)

- API 端点定义在 `api/v1/`
- 业务服务在 `services/`
- 数据模型在 `models/`
- 异步任务使用 FastAPI BackgroundTasks
- 所有外部调用添加超时和重试

### JavaScript (guineapig-ops-web / guineapig-client)

- 页面组件在 `src/views/`
- API 调用层在 `src/api/`
- 状态管理使用 Pinia stores
- UI 组件库使用 Element Plus (ops-web)

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
| guineapig-backend | 8080 | HTTP |
| guineapig-aiagent | 8000 | HTTP |
| guineapig-ops-web | 3000 | HTTP (dev) |
| MySQL | 3306 | TCP |
| Redis | 6379 | TCP |
| MinIO (S3) | 9000 | HTTP |

### Environment Variables

每个 package 有自己的 `.env` 文件。参考 `.env.example` 配置：

```bash
# guineapig-backend/.env
DB_HOST=localhost
DB_PORT=3306
DB_USER=guineapig
DB_PASSWORD=secret
REDIS_ADDR=localhost:6379
S3_ENDPOINT=http://localhost:9000

# guineapig-aiagent/.env
DEEPSEEK_API_KEY=sk-xxx
S3_ENDPOINT=http://localhost:9000
BACKEND_URL=http://localhost:8080
```

敏感信息（密码、API Key）不提交 git。参考各 package 的 `.env.example` 创建本地 `.env`。

## Harness Workflow

```bash
# 保存当前任务检查点
make checkpoint

# 记录经验教训
make memory-add

# 查看当前焦点
cat .ai/CURRENT_FOCUS

# 查看失败历史
tail -20 .ai/traces/failures.log

# 运行完整验证
make validate
```

See `.ai/AGENTS.md` for the complete AI agent navigation guide.

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
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple  # 国内镜像
```

### Docker 服务无法启动
```bash
docker compose -f docker-compose.dev.yml down -v  # 清除数据卷
docker compose -f docker-compose.dev.yml up -d     # 重新启动
```

### 端口冲突
修改对应 package 的配置文件中的端口号，或停用占用端口的进程。
