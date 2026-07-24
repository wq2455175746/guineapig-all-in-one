# guineapig-backend AI Agent Guide

## Quick Start

```bash
# Read project-level rules first
cat ../../.ai/AGENTS.md
cat ../../docs/ARCHITECTURE.md

# Read backend-specific context
cat CLAUDE.md
```

## Module Map

| 任务 | 目录 | 模式 |
|-----|------|------|
| 添加数据库模型 | `internal/model/` | GORM struct + 全局 Model 变量 |
| 添加 API 端点 | `internal/router/{resource}/` | init() 注册 + handler 函数 |
| 添加业务逻辑 | `internal/service/` | Service struct 模式 |
| 添加中间件 | `pkg/middleware/` | Echo middleware 函数 |
| 添加工具函数 | `pkg/utils/` | 纯函数 |
| 添加常量/错误码 | `pkg/constant/` | const 定义 |

## Code Patterns

### 添加一个新的 CRUD 资源

**Step 1**: `internal/model/task.go`
```go
type Task struct {
    ID     uint   `gorm:"primarykey" json:"id"`
    TaskID string `gorm:"uniqueIndex;not null" json:"task_id"`
    Status string `gorm:"default:pending" json:"status"`
}
var TaskM = &TaskModel{}
type TaskModel struct{}
func (m *TaskModel) Create(ctx context.Context, t *Task) error { ... }
```

**Step 2**: `internal/request/task.go`
```go
type CreateTaskReq struct {
    UserID  uint   `json:"user_id" validate:"required"`
    S3Path  string `json:"s3_path" validate:"required"`
    TaskID  string `json:"task_id" validate:"required,uuid"`
}
```

**Step 3**: `internal/response/task.go`
```go
type TaskResp struct {
    ID     uint   `json:"id"`
    TaskID string `json:"task_id"`
    Status string `json:"status"`
}
```

**Step 4**: `internal/service/task.go`
```go
type TaskService struct{}
func (s *TaskService) Create(ctx context.Context, req *request.CreateTaskReq) (*response.TaskResp, error) { ... }
```

**Step 5**: `internal/router/task/create_task.go`
```go
func init() {
    router.AddPostRouter("/api/v1/tasks", createTask)
}
func createTask(c echo.Context) error { ... }
```

**Step 6**: Register in `internal/router/router.go` (auto via init())

## AIAgent Integration Rules

### Calling AIAgent from Backend
```go
// Use HTTP client, never import AI libraries directly
resp, err := http.Post(aiagentURL+"/api/v1/tasks/process", "application/json", body)
```

### Forbidden Patterns
- ❌ `import "github.com/sashabaranov/go-openai"`
- ❌ `import "github.com/anthropics/anthropic-sdk-go"`
- ❌ Direct LLM/ASR/TTS calls in backend code

## Configuration

- `config.yaml`: Structure definition with `${ENV_VAR}` placeholders
- `.env`: Actual values (DB passwords, API keys, etc.)
- `config/config.go`: ParseConfig() loads both

## Before Committing

```bash
go fmt ./...
go vet ./...
make validate  # from project root
```
