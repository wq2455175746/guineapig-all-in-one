# 对话记录归纳为记忆 — 设计文档

## 概述

用户可选择一个日期，系统自动将该日期内的全部对话记录通过 LLM 归纳为结构化记忆（4 种类型），存入 `chat_memory` 表并供后续检索使用。

## 流程

```
MemoryTab.vue ──POST /memory/summarize──→ Backend ──→ DB insert(占位) ──→ 返回 memory_id
                                                     │
                                                     ├── async ──HTTP──→ AiAgent
                                                     │                  │
                                                     │          读 MEMORY_template.md
                                                     │          调用 LLM 归纳
                                                     │          回调 Backend 更新记忆
```

## 组件设计

### 1. 前端 — MemoryTab.vue

**新增元素**：
- 工具栏左侧「归纳记忆」按钮（Button, icon="pi pi-book"）
- DatePicker 弹出对话框（PrimeVue `<DatePicker>` Basic 模式）

**交互流程**：
1. 点击按钮 → 弹出 DatePicker，默认选中昨天
2. DatePicker 最大日期 = 昨天（今天 00:00 之前）
3. 用户确认 → `POST /api/v1/memory/summarize` 发送 `{ user_id, date: "YYYY-MM-DD" }`
4. 收到后端响应 → toast 提示成功
5. 自动刷新记忆列表

### 2. 后端 — guineapig-backend

#### 2a. `POST /api/v1/memory/summarize`

**Request**:
```json
{
  "user_id": 1,
  "date": "2026-06-25"
}
```

**处理逻辑**：
1. 时间范围：`start_time = date + " 00:00:00"`, `end_time = date + " 23:59:59"`
2. 校验 `end_time` <= 今天 00:00
3. 查 `chat_conversations`：`WHERE user_id=? AND status='active' AND created_at BETWEEN ? AND ?`
4. 查 `chat_messages`：`WHERE conversation_id IN (上面查到的 IDs) AND created_at BETWEEN ? AND ?`
5. 查 `user_aimodel`：`WHERE user_id=? AND status=1 AND established=1 AND model_type='LLM' ORDER BY id ASC LIMIT 1`
6. 插入 `chat_memory`：name="记忆归纳中...", mem="", mem_type=""，返回 memory_id
7. 同步返回 `{ memory_id }` 给客户端
8. 异步 goroutine 转发到 aiagent：含 memory_id, user_id, conversations, messages, model_info

#### 2b. `POST /api/v1/memory/update-content` (aiagent 回调)

**Request**:
```json
{
  "id": 123,
  "name": "6月25日对话摘要",
  "mem": "# 记忆内容...",
  "mem_type": "daily_summary",
  "conversation_ids": "1,2,3",
  "source_msg_count": 42,
  "time_range_start_at": "2026-06-25T00:00:00+08:00",
  "time_range_end_at": "2026-06-25T23:59:59+08:00"
}
```

**处理**：更新 `chat_memory` 对应 ID 的记录字段。

**新增文件**：
- `internal/service/chat_memory.go` — 增加 `CreateMemorySummary`、`UpdateMemoryContent` 函数
- `internal/router/memory/controller.go` — 增加 `Summarize`、`UpdateContent` handler
- `internal/request/memory.go` — 增加请求结构体

**路由**：`/api/v1/memory/summarize` (POST), `/api/v1/memory/update-content` (POST)

### 3. AiAgent — guineapig-aiagent

#### `POST /guineapig-aiagent/memory/summarize`

**参数**（从 backend 转发）：
```json
{
  "memory_id": 123,
  "user_id": 1,
  "model_info": {
    "api_key": "sk-xxx",
    "base_url": "https://api.deepseek.com/v1",
    "model_name": "deepseek-chat"
  },
  "conversations": [{"id": 1, "title": "...", ...}],
  "messages": [{"conversation_id": 1, "role": "user", "content": "...", ...}],
  "time_range_start": "2026-06-25T00:00:00",
  "time_range_end": "2026-06-25T23:59:59"
}
```

**处理逻辑**：
1. 读取 `asset/MEMORY_template.md`
2. 组织 LLM prompt，包含：
   - 系统指令：你是记忆归纳助手，请将对话归纳为结构化记忆
   - 4 种记忆类型说明
   - MEMORY_template.md 格式
   - 对话内容（conversations + messages）
3. 调用 LLM（使用 model_info 传入的参数）
4. 解析 LLM 回复，提取 name, mem_type, mem (markdown), confidence_score
5. 调用 backend `POST /api/v1/memory/update-content` 回写

**4 种记忆类型**：
| 类型 | 说明 |
|------|------|
| daily_summary | 对用户某一天的整体概括 |
| topic_summary | 按话题/项目/领域聚合 |
| key_fact | 确定性信息（身份、技能、关系等） |
| preference | 用户偏好、风格要求、操作习惯 |

**新增文件**：
- `app/routers/memory.py` — 路由定义
- `app/services/memory_summarize_service.py` — LLM prompt + 调用 + 结果解析
- `app/schemas/memory_models.py` — 请求响应模型

## 数据流

```
Client                          Backend                         AiAgent
  │                                │                               │
  │── POST /memory/summarize ────→│                               │
  │                                ├── 查 conversations+msgs      │
  │                                ├── 查 user_aimodel           │
  │                                ├── 插入 chat_memory(占位)    │
  │←──── { memory_id } ───────────│                               │
  │                                │── async POST ──────────────→│
  │                                │                               ├── 读 template
  │                                │                               ├── 调用 LLM
  │                                │                               ├── 解析结果
  │                                │← POST /memory/update-content─│
  │                                ├── 更新 chat_memory           │
  │                                │                               │
```

## 错误处理

- Backend 校验：date 不能为 null，end_time 不能超过今天 00:00
- 无对话数据：直接返回提示"该日期无对话记录"，不调用 aiagent
- AiAgent LLM 调用失败：记忆保留占位状态，内容为空
- Backend 转发 aiagent 超时：不影响客户端，后台记录错误日志
