# Backend API Design

## Metadata
- **Status**: draft
- **Created**: 2026-05-21
- **Package**: guineapig-backend
- **Tech**: Go 1.24, Echo v4, GORM, Redis

## Overview
guineapig-backend 提供 REST API 作为整个系统的业务编排层，负责用户管理、任务管理、对话会话管理等业务逻辑。

## API Modules

### 1. User Module (`/api/v1/users`)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/api/v1/users/register` | 邮箱注册 | No |
| POST | `/api/v1/users/login` | 邮箱登录 | No |
| GET | `/api/v1/users/:id` | 获取用户信息 | Yes |
| PUT | `/api/v1/users/:id` | 更新用户信息 | Yes |
| GET | `/api/v1/users` | 用户列表 (ops) | Yes |
| DELETE | `/api/v1/users/:id` | 删除用户 (ops) | Yes |

### 2. Task Module (`/api/v1/tasks`)
Voice dialogue task lifecycle management.

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/api/v1/tasks` | 提交语音任务 | Yes |
| GET | `/api/v1/tasks/:id` | 查询任务状态 | Yes |
| GET | `/api/v1/tasks` | 任务列表 | Yes |
| PUT | `/api/v1/tasks/:id/cancel` | 取消任务 | Yes |

### 3. Session Module (`/api/v1/sessions`)
Conversation session management.

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/api/v1/sessions` | 创建会话 | Yes |
| GET | `/api/v1/sessions/:id` | 获取会话详情 | Yes |
| GET | `/api/v1/sessions` | 会话列表 | Yes |
| DELETE | `/api/v1/sessions/:id` | 删除会话 | Yes |

### 4. AIAgent Proxy Module (`/api/v1/ai`)
Proxy to AIAgent for management purposes.

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/api/v1/ai/tasks/process` | 手动触发 AI 处理 | Yes |
| GET | `/api/v1/ai/status` | AIAgent 状态 | Yes |

## Data Models

### Task
```go
type Task struct {
    ID        uint      `gorm:"primarykey" json:"id"`
    TaskID    string    `gorm:"uniqueIndex;not null" json:"task_id"`
    UserID    uint      `gorm:"index;not null" json:"user_id"`
    SessionID uint      `gorm:"index" json:"session_id"`
    S3Path    string    `gorm:"not null" json:"s3_path"`
    Status    string    `gorm:"default:pending" json:"status"` // pending, processing, completed, failed, cancelled
    Result    string    `gorm:"type:text" json:"result,omitempty"`
    CreatedAt time.Time `json:"created_at"`
    UpdatedAt time.Time `json:"updated_at"`
}
```

### Session
```go
type Session struct {
    ID        uint      `gorm:"primarykey" json:"id"`
    UserID    uint      `gorm:"index;not null" json:"user_id"`
    Title     string    `json:"title"`
    Status    string    `gorm:"default:active" json:"status"` // active, archived
    CreatedAt time.Time `json:"created_at"`
    UpdatedAt time.Time `json:"updated_at"`
}
```

## Response Format
```json
{
  "code": 0,
  "message": "success",
  "data": { },
  "request_id": "uuid"
}
```

## Error Codes
| Code | Description |
|------|-------------|
| 0 | Success |
| 10001 | Invalid request |
| 10002 | Unauthorized |
| 10003 | Not found |
| 10004 | Internal error |
| 20001 | Task already exists |
| 20002 | Task not found |
| 20003 | AIAgent unavailable |
