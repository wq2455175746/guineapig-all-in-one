# Memory Summarization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ability to select a date and summarize all conversations from that date into structured memories using LLM.

**Architecture:** Frontend button + DatePicker → Backend POST API that fetches conversations/messages, creates placeholder memory record, returns ID, then async forwards to AiAgent. AiAgent calls LLM with MEMORY_template.md, generates structured memory, calls backend update API.

**Tech Stack:** Vue 3 / PrimeVue, Go / Echo / GORM, Python / FastAPI / OpenAI SDK

## Global Constraints

- Backend routes registered via `init()` + `AddPostRouter("/memory/summarize", handler)`
- GORM Updates must use `map[string]any` (not struct) to avoid zero-value skip
- AiAgent routers prefix: `/guineapig-aiagent/memory`
- AiAgent uses `settings.BACKEND_BASE_URL` to call backend
- Frontend userId from `localStorage.getItem('user_id')`

---

### Task 1: Backend Request/Response Structs

**Files:**
- Modify: `packages/guineapig-backend/internal/request/memory.go`
- Modify: `packages/guineapig-backend/internal/response/memory.go`

**Interfaces:**
- Produces: `request.MemorySummarizeRequest`, `request.MemoryUpdateContentRequest`, `response.MemoryUpdateContentResponse` (actually we can just reuse existing response patterns)

- [ ] **Add MemorySummarizeRequest to request/memory.go**

```go
// MemorySummarizeRequest 记忆归纳请求
type MemorySummarizeRequest struct {
	UserId int64  `json:"user_id"`
	Date   string `json:"date"` // format: "2006-01-02"
}

// MemoryUpdateContentRequest aiagent 回调更新记忆内容
type MemoryUpdateContentRequest struct {
	Id               int64      `json:"id"`
	Name             string     `json:"name"`
	Mem              string     `json:"mem"`
	MemType          string     `json:"mem_type"`
	ConversationIds  string     `json:"conversation_ids"`
	SourceMsgCount   int        `json:"source_msg_count"`
	TimeRangeStartAt *time.Time `json:"time_range_start_at"`
	TimeRangeEndAt   *time.Time `json:"time_range_end_at"`
}
```

- [ ] **Add MemorySummarizeResponse to response/memory.go**

```go
// MemorySummarizeResponse 记忆归纳响应
type MemorySummarizeResponse struct {
	MemoryId int64 `json:"memory_id"`
}
```

- [ ] **Commit**

```bash
git add packages/guineapig-backend/internal/request/memory.go packages/guineapig-backend/internal/response/memory.go
git commit -m "feat(backend): add memory summarize request/response structs"
```

### Task 2: Backend Model — Create Placeholder + Update Content

**Files:**
- Modify: `packages/guineapig-backend/internal/model/chat_memory.go`

**Interfaces:**
- Produces: `CreatePlaceholder(ctx, userId int64, timeRangeStart, timeRangeEnd time.Time) (int64, error)`
- Produces: `UpdateContent(ctx, req *request.MemoryUpdateContentRequest) error`

- [ ] **Add CreatePlaceholder method to chat_memory.go**

```go
func (*ChatMemory) CreatePlaceholder(ctx context.Context, userId int64, timeRangeStart, timeRangeEnd time.Time) (int64, error) {
	now := time.Now()
	m := &ChatMemory{
		Name:             "记忆归纳中...",
		UserId:           userId,
		ConversationIds:  nil,
		Mem:              "",
		MemType:          "",
		TimeRangeStartAt: &timeRangeStart,
		TimeRangeEndAt:   &timeRangeEnd,
		SourceMsgCount:   0,
		Version:          1,
		IsActive:         1,
		CreatedAt:        now,
		UpdatedAt:        now,
	}
	err := plugin.GetDB(ctx).Create(m).Error
	if err != nil {
		return 0, err
	}
	return m.Id, nil
}
```

- [ ] **Add UpdateContent method to chat_memory.go**

```go
func (*ChatMemory) UpdateContent(ctx context.Context, req *request.MemoryUpdateContentRequest) error {
	now := time.Now()
	updates := map[string]any{
		"name":                req.Name,
		"mem":                 req.Mem,
		"mem_type":            req.MemType,
		"conversation_ids":    req.ConversationIds,
		"source_msg_count":    req.SourceMsgCount,
		"time_range_start_at": req.TimeRangeStartAt,
		"time_range_end_at":   req.TimeRangeEndAt,
		"updated_at":          now,
	}
	return plugin.GetDB(ctx).Model(&ChatMemory{}).
		Where("id = ? AND deleted_at IS NULL", req.Id).
		Updates(updates).Error
}
```

- [ ] **Commit**

```bash
git add packages/guineapig-backend/internal/model/chat_memory.go
git commit -m "feat(backend): add CreatePlaceholder and UpdateContent model methods"
```

### Task 3: Backend Service — SummarizeMemory with Async Forwarding

**Files:**
- Modify: `packages/guineapig-backend/internal/service/chat_memory.go`

**Interfaces:**
- Consumes: `model.MChatMemory.CreatePlaceholder`, `model.MChatMemory.UpdateContent`
- Consumes: `model.MChatConversation` (list by time range), `model.MChatMessage` (list by conv ids)
- Consumes: `model.MUserAiModel.ListOptions` (first LLM model)
- Produces: `CreateMemorySummary(ctx, req *request.MemorySummarizeRequest) (int64, error)`
- Produces: `UpdateMemoryContent(ctx, req *request.MemoryUpdateContentRequest) error`

- [ ] **Add CreateMemorySummary function**

```go
import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

// AiAgentMemoryRequest 转发到 aiagent 的记忆归类的参数
type AiAgentMemoryRequest struct {
	MemoryId       int64              `json:"memory_id"`
	UserId         int64              `json:"user_id"`
	ModelInfo      *ModelInfo         `json:"model_info"`
	Conversations  []*ConvBrief       `json:"conversations"`
	Messages       []*MsgBrief        `json:"messages"`
	TimeRangeStart string             `json:"time_range_start"`
	TimeRangeEnd   string             `json:"time_range_end"`
}

type ModelInfo struct {
	ApiKey    string `json:"api_key"`
	BaseUrl   string `json:"base_url"`
	ModelName string `json:"model_name"`
}

type ConvBrief struct {
	Id        int64  `json:"id"`
	Title     string `json:"title"`
	CreatedAt string `json:"created_at"`
}

type MsgBrief struct {
	ConversationId int64  `json:"conversation_id"`
	Role           string `json:"role"`
	Content        string `json:"content"`
	CreatedAt      string `json:"created_at"`
}

// CreateMemorySummary 创建记忆归纳
func CreateMemorySummary(ctx context.Context, req *request.MemorySummarizeRequest) (int64, error) {
	if req.UserId <= 0 {
		return 0, errors.New("user_id 不能为空")
	}
	if req.Date == "" {
		return 0, errors.New("date 不能为空")
	}

	// 1. 解析日期
	date, err := time.ParseInLocation("2006-01-02", req.Date, time.Local)
	if err != nil {
		return 0, fmt.Errorf("日期格式错误: %w", err)
	}

	// 2. 计算时间范围
	startTime := time.Date(date.Year(), date.Month(), date.Day(), 0, 0, 0, 0, time.Local)
	endTime := time.Date(date.Year(), date.Month(), date.Day(), 23, 59, 59, 0, time.Local)

	// 3. 校验结束时间不能超过今天 00:00
	todayStart := time.Now().In(time.Local).Truncate(24 * time.Hour)
	if endTime.After(todayStart) || endTime.Equal(todayStart) {
		return 0, errors.New("结束时间不能超过今天 00:00")
	}

	// 4. 查询对话列表
	type ConvRow struct {
		Id        int64
		Title     string
		CreatedAt time.Time
	}
	var convs []*ConvRow
	db := plugin.GetDB(ctx).Table("chat_conversations").
		Select("id, title, created_at").
		Where("user_id = ? AND status = 'active' AND created_at BETWEEN ? AND ?", req.UserId, startTime, endTime)
	if err := db.Find(&convs).Error; err != nil {
		return 0, fmt.Errorf("查询对话列表失败: %w", err)
	}
	if len(convs) == 0 {
		return 0, errors.New("该日期无对话记录")
	}

	// 5. 查询消息
	convIds := make([]int64, len(convs))
	for i, c := range convs {
		convIds[i] = c.Id
	}
	type MsgRow struct {
		ConversationId int64
		Role           string
		Content        string
		CreatedAt      time.Time
	}
	var msgs []*MsgRow
	if err := plugin.GetDB(ctx).Table("chat_messages").
		Select("conversation_id, role, content, created_at").
		Where("conversation_id IN ? AND created_at BETWEEN ? AND ?", convIds, startTime, endTime).
		Order("created_at ASC").
		Find(&msgs).Error; err != nil {
		return 0, fmt.Errorf("查询消息失败: %w", err)
	}

	// 6. 查询第一个 LLM 模型
	aimodels, err := model.MUserAiModel.ListOptionsByType(ctx, req.UserId, "LLM")
	if err != nil {
		return 0, fmt.Errorf("查询AI模型失败: %w", err)
	}
	if len(aimodels) == 0 {
		return 0, errors.New("未找到可用的 LLM 模型")
	}
	aiModel := aimodels[0]

	// 7. 创建占位记忆记录
	memoryId, err := model.MChatMemory.CreatePlaceholder(ctx, req.UserId, startTime, endTime)
	if err != nil {
		return 0, fmt.Errorf("创建记忆记录失败: %w", err)
	}

	// 8. 异步转发到 aiagent
	aiAgentReq := &AiAgentMemoryRequest{
		MemoryId:       memoryId,
		UserId:         req.UserId,
		ModelInfo: &ModelInfo{
			ApiKey:    aiModel.ApiKey,
			BaseUrl:   aiModel.ApiUrl,
			ModelName: aiModel.ModelName,
		},
		TimeRangeStart: startTime.Format(time.RFC3339),
		TimeRangeEnd:   endTime.Format(time.RFC3339),
	}
	for _, c := range convs {
		aiAgentReq.Conversations = append(aiAgentReq.Conversations, &ConvBrief{
			Id: c.Id, Title: c.Title, CreatedAt: c.CreatedAt.Format(time.RFC3339),
		})
	}
	for _, m := range msgs {
		aiAgentReq.Messages = append(aiAgentReq.Messages, &MsgBrief{
			ConversationId: m.ConversationId, Role: m.Role, Content: m.Content, CreatedAt: m.CreatedAt.Format(time.RFC3339),
		})
	}

	go func() {
		forwardCtx := context.Background()
		if err := forwardToAiAgent(forwardCtx, aiAgentReq); err != nil {
			plugin.GetLogger().Errorf("转发记忆归纳到 aiagent 失败: %v", err)
		}
	}()

	return memoryId, nil
}

func forwardToAiAgent(ctx context.Context, req *AiAgentMemoryRequest) error {
	body, err := json.Marshal(req)
	if err != nil {
		return fmt.Errorf("序列化失败: %w", err)
	}

	// aiagent 地址从配置获取（如 config.yaml 或环境变量），这里通过 plugin.GetConfig()
	aiAgentURL := plugin.GetConfig().AiAgentBaseURL // 需要有这个配置项
	if aiAgentURL == "" {
		aiAgentURL = "http://localhost:8000"
	}

	url := fmt.Sprintf("%s/guineapig-aiagent/memory/summarize", aiAgentURL)
	resp, err := http.Post(url, "application/json", bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("请求 aiagent 失败: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("aiagent 返回非200状态码: %d", resp.StatusCode)
	}
	return nil
}
```

- [ ] **Add UpdateMemoryContent function**

```go
// UpdateMemoryContent 更新记忆内容（aiagent 回调）
func UpdateMemoryContent(ctx context.Context, req *request.MemoryUpdateContentRequest) error {
	if req.Id <= 0 {
		return errors.New("id 不能为空")
	}
	return model.MChatMemory.UpdateContent(ctx, req)
}
```

- [ ] **Add AiAgentBaseURL to config (check config.go pattern)**

Actually, let me check how config works. Need to add `aiAgentBaseURL` to config struct. Let me read config.go.

- [ ] **Commit**

```bash
git add packages/guineapig-backend/internal/service/chat_memory.go
git commit -m "feat(backend): add CreateMemorySummary service with async aiagent forwarding"
```

### Task 4: Backend Config — Add AiAgentBaseURL

**Files:**
- Read: `packages/guineapig-backend/config/config.go`

Let me check the config pattern first.

- [ ] **Read config.go to understand config structure**

- [ ] **Add AiAgentBaseURL to config**

- [ ] **Commit**

```bash
git add config/config.go
git commit -m "feat(backend): add AiAgentBaseURL config"
```

### Task 5: Backend Router — Summarize + UpdateContent Handlers

**Files:**
- Modify: `packages/guineapig-backend/internal/router/memory/controller.go`
- Modify: `packages/guineapig-backend/internal/router/router.go`

**Interfaces:**
- Consumes: `service.CreateMemorySummary`, `service.UpdateMemoryContent`

- [ ] **Add Summarize handler to controller.go**

```go
func Summarize(e echo.Context) error {
	ctx := utils.NewContext(e)

	var req request.MemorySummarizeRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	memoryId, err := service.CreateMemorySummary(ctx, &req)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, response.MemorySummarizeResponse{MemoryId: memoryId})
}
```

- [ ] **Add UpdateContent handler to controller.go**

```go
func UpdateContent(e echo.Context) error {
	ctx := utils.NewContext(e)

	var req request.MemoryUpdateContentRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	if err := service.UpdateMemoryContent(ctx, &req); err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, nil)
}
```

- [ ] **Register routes in router.go**

```go
// Add after existing memory routes:
AddPostRouter("/memory/summarize", memoryRouter.Summarize)
AddPostRouter("/memory/update-content", memoryRouter.UpdateContent)
```

- [ ] **Commit**

```bash
git add packages/guineapig-backend/internal/router/memory/controller.go packages/guineapig-backend/internal/router/router.go
git commit -m "feat(backend): add memory summarize and update-content routes"
```

### Task 6: AiAgent — Memory Summarize Schemas

**Files:**
- Create: `packages/guineapig-aiagent/app/schemas/memory_models.py`

**Interfaces:**
- Produces: `MemorySummarizeRequest` pydantic model

- [ ] **Create memory_models.py**

```python
"""记忆归纳请求模型"""
from pydantic import BaseModel
from typing import Optional


class ModelInfo(BaseModel):
    api_key: str
    base_url: str
    model_name: str


class ConvBrief(BaseModel):
    id: int
    title: str
    created_at: str


class MsgBrief(BaseModel):
    conversation_id: int
    role: str
    content: str
    created_at: str


class MemorySummarizeRequest(BaseModel):
    memory_id: int
    user_id: int
    model_info: ModelInfo
    conversations: list[ConvBrief]
    messages: list[MsgBrief]
    time_range_start: str
    time_range_end: str
```

- [ ] **Commit**

```bash
git add packages/guineapig-aiagent/app/schemas/memory_models.py
git commit -m "feat(aiagent): add memory summarize request models"
```

### Task 7: AiAgent — Memory Summarize Service

**Files:**
- Create: `packages/guineapig-aiagent/app/services/memory_summarize_service.py`

**Interfaces:**
- Produces: `process_memory_summarize(req: MemorySummarizeRequest)`
- Consumes: `openai.OpenAI` for LLM call
- Consumes: `settings.BACKEND_BASE_URL` for callback

- [ ] **Create memory_summarize_service.py**

```python
"""记忆归纳服务 — 使用 LLM 将对话归纳为结构化记忆"""

import os
import json
import httpx
from openai import OpenAI

from app.config import settings
from app.core.log import logger
from app.schemas.memory_models import MemorySummarizeRequest

MEMORY_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "asset",
    "MEMORY_template.md",
)

MEMORY_TYPE_DESCRIPTIONS = """
记忆类型说明（请选择最合适的一种）：
- daily_summary：对用户某一天（或某一段连续对话）的整体概括，记录当天聊了什么、发生了什么
- topic_summary：按话题/项目/领域聚合的记忆，跨时间维度归纳用户在某个主题下的所有讨论
- key_fact：用户表达的确定性信息，包括身份、职业、技能、关系、偏好设置等静态或半静态属性
- preference：用户明确表达的喜好、风格要求、操作习惯，通常以"I prefer..."、"下次请..."、"我不喜欢..."等形式出现
"""

SYSTEM_PROMPT = """你是一个专业的记忆归纳助手。请将用户的对话内容归纳为结构化的记忆。

请严格按照以下格式输出（JSON格式）：
{
  "name": "简短的记忆名称（15字以内）",
  "mem_type": "daily_summary 或 topic_summary 或 key_fact 或 preference",
  "mem": "完整的记忆内容（使用 Markdown 格式，参考记忆模板）",
  "confidence_score": 1-10之间的整数
}

请确保：
1. name 要简洁明了，能概括记忆核心
2. mem 要使用 Markdown 格式组织，包含引用对话原文
3. 只输出 JSON，不要包含其他说明文字"""


def _load_memory_template() -> str:
    """加载记忆模板文件"""
    try:
        with open(MEMORY_TEMPLATE_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning(f"记忆模板文件不存在: {MEMORY_TEMPLATE_PATH}")
        return ""


def _build_conversation_text(req: MemorySummarizeRequest) -> str:
    """将对话数据组织成 LLM 可读的文本"""
    lines = []
    lines.append(f"时间范围：{req.time_range_start} ~ {req.time_range_end}")
    lines.append("")
    lines.append("=== 对话列表 ===")
    for conv in req.conversations:
        lines.append(f"对话 #{conv.id}: {conv.title} ({conv.created_at})")
    lines.append("")
    lines.append("=== 消息内容 ===")
    for msg in req.messages:
        role_label = "用户" if msg.role == "user" else ("助手" if msg.role == "assistant" else msg.role)
        lines.append(f"[{role_label}] {msg.content}")
    return "\n".join(lines)


def process_memory_summarize(req: MemorySummarizeRequest):
    """处理记忆归纳请求"""
    logger.info(f"[MemorySummarize] 开始处理: memory_id={req.memory_id}, user_id={req.user_id}")

    # 1. 加载模板 + 构建 prompt
    template = _load_memory_template()
    conversation_text = _build_conversation_text(req)

    user_prompt = f"""{MEMORY_TYPE_DESCRIPTIONS}

参考格式（记忆模板）：
{template}

对话内容：
{conversation_text}

请根据以上对话内容，生成结构化的记忆。"""

    # 2. 调用 LLM
    try:
        client = OpenAI(
            api_key=req.model_info.api_key,
            base_url=req.model_info.base_url,
        )

        logger.info(f"[MemorySummarize] 调用 LLM: model={req.model_info.model_name}")
        completion = client.chat.completions.create(
            model=req.model_info.model_name,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=4096,
        )
        result_text = completion.choices[0].message.content.strip()
        logger.info(f"[MemorySummarize] LLM 返回: {result_text[:200]}...")
    except Exception as e:
        logger.error(f"[MemorySummarize] LLM 调用失败: {e}")
        raise

    # 3. 解析 JSON 结果
    # 处理可能的 markdown 代码块包裹
    if result_text.startswith("```"):
        # 去掉 ```json 和 ``` 包裹
        lines = result_text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        result_text = "\n".join(lines)

    try:
        parsed = json.loads(result_text.strip())
    except json.JSONDecodeError as e:
        logger.error(f"[MemorySummarize] JSON 解析失败: {e}, raw={result_text}")
        raise ValueError(f"LLM 返回结果解析失败: {e}")

    name = parsed.get("name", f"记忆归纳 {req.time_range_start[:10]}")
    mem_type = parsed.get("mem_type", "daily_summary")
    mem_content = parsed.get("mem", result_text)
    confidence_score = parsed.get("confidence_score", 5)

    # 4. 回调 backend 更新记忆内容
    conv_ids_str = ",".join(str(c.id) for c in req.conversations)
    source_msg_count = len(req.messages)

    callback_payload = {
        "id": req.memory_id,
        "name": name,
        "mem": mem_content,
        "mem_type": mem_type,
        "conversation_ids": conv_ids_str,
        "source_msg_count": source_msg_count,
        "time_range_start_at": req.time_range_start,
        "time_range_end_at": req.time_range_end,
    }

    backend_url = f"{settings.BACKEND_BASE_URL}/api/v1/memory/update-content"
    logger.info(f"[MemorySummarize] 回调 backend: {backend_url}")

    try:
        resp = httpx.post(backend_url, json=callback_payload, timeout=30)
        resp.raise_for_status()
        logger.info(f"[MemorySummarize] 回调成功: memory_id={req.memory_id}")
    except Exception as e:
        logger.error(f"[MemorySummarize] 回调 backend 失败: {e}")
        raise

    return {
        "memory_id": req.memory_id,
        "name": name,
        "mem_type": mem_type,
    }
```

- [ ] **Commit**

```bash
git add packages/guineapig-aiagent/app/services/memory_summarize_service.py
git commit -m "feat(aiagent): add memory summarize service with LLM processing"
```

### Task 8: AiAgent — Memory Router + Main Registration

**Files:**
- Create: `packages/guineapig-aiagent/app/routers/memory.py`
- Modify: `packages/guineapig-aiagent/app/main.py`

**Interfaces:**
- Consumes: `services.memory_summarize_service.process_memory_summarize`
- Consumes: `schemas.memory_models.MemorySummarizeRequest`

- [ ] **Create routers/memory.py**

```python
"""记忆归纳路由"""

from fastapi import APIRouter

from app.core.log import logger
from app.schemas.base_models import success_response, error_response
from app.schemas.memory_models import MemorySummarizeRequest
from app.services.memory_summarize_service import process_memory_summarize

router = APIRouter(prefix="/guineapig-aiagent/memory", tags=["memory"])


@router.post("/summarize")
def summarize_memory(request: MemorySummarizeRequest):
    """
    记忆归纳 — 使用 LLM 将对话归纳为结构化记忆。
    由 guineapig-backend 异步调用。
    """
    logger.info(f"[Memory] 收到记忆归纳请求: memory_id={request.memory_id}")

    try:
        result = process_memory_summarize(request)
        return success_response(data=result)
    except ValueError as e:
        logger.error(f"[Memory] 参数错误: {e}")
        return error_response(message=str(e), code=400)
    except Exception as e:
        logger.error(f"[Memory] 处理异常: {e}")
        return error_response(message=f"处理失败: {str(e)}", code=500)
```

- [ ] **Register router in main.py**

```python
# Add import with other routers:
from app.routers import asr, llm, memory, rag, skill, task

# Add include_router:
app.include_router(memory.router)
```

- [ ] **Commit**

```bash
git add packages/guineapig-aiagent/app/routers/memory.py packages/guineapig-aiagent/app/main.py
git commit -m "feat(aiagent): add memory summarize route and register in main"
```

### Task 9: Frontend — MemoryTab.vue Add Summarize Button + DatePicker

**Files:**
- Modify: `packages/guineapig-client/src/renderer-overlay/views/MemoryTab.vue`

**Interfaces:**
- Consumes: `POST /api/v1/memory/summarize`

- [ ] **Add DatePicker import and button to template**

```vue
<template>
  <!-- toolbar-left section add button -->
  <div class="toolbar-left">
    <Button icon="pi pi-book" label="归纳记忆" severity="primary" raised size="small"
      @click="showDatePicker = true" :loading="summarizing" />
  </div>

  <!-- DatePicker dialog -->
  <Dialog v-model:visible="showDatePicker" :header="'选择归纳日期'" :modal="true"
    :style="{ width: '360px' }" :draggable="false" :closable="true">
    <div class="datepicker-wrapper">
      <DatePicker v-model="summarizeDate" :maxDate="maxDate" dateFormat="yy-mm-dd"
        placeholder="选择日期" />
    </div>
    <template #footer>
      <Button label="取消" severity="secondary" outlined @click="showDatePicker = false" />
      <Button label="确认归纳" severity="primary" @click="submitSummarize" :loading="summarizing" />
    </template>
  </Dialog>
```

- [ ] **Add script imports and logic**

```typescript
// Add imports
import DatePicker from 'primevue/datepicker'

// Add state
const showDatePicker = ref(false)
const summarizing = ref(false)
const summarizeDate = ref<Date | null>(null)

// Compute max date (yesterday)
const maxDate = ref(new Date(new Date().setDate(new Date().getDate() - 1)))

// Default to yesterday
onMounted(() => {
  const yesterday = new Date()
  yesterday.setDate(yesterday.getDate() - 1)
  summarizeDate.value = yesterday
})

// Add submit function
async function submitSummarize() {
  if (!summarizeDate.value) {
    toast.add({ severity: 'warn', summary: '请选择日期', life: 2000 })
    return
  }

  summarizing.value = true
  try {
    const year = summarizeDate.value.getFullYear()
    const month = String(summarizeDate.value.getMonth() + 1).padStart(2, '0')
    const day = String(summarizeDate.value.getDate()).padStart(2, '0')
    const dateStr = `${year}-${month}-${day}`

    const res = await fetch(`${API_BASE_URL}/api/v1/memory/summarize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, date: dateStr }),
    })
    const body = await res.json()
    if (body.code !== 0) {
      toast.add({ severity: 'error', summary: '归纳失败', detail: body.message, life: 3000 })
      return
    }
    toast.add({ severity: 'success', summary: '记忆归纳任务已提交', life: 2000 })
    showDatePicker.value = false
    fetchList()
  } catch (err) {
    toast.add({ severity: 'error', summary: '请求失败', detail: String(err), life: 3000 })
  } finally {
    summarizing.value = false
  }
}
```

- [ ] **Add CSS for datepicker wrapper**

```css
.datepicker-wrapper {
  display: flex;
  justify-content: center;
  padding: 16px 0;
}
```

- [ ] **Add missing imports** (need `onMounted` from vue, and `Button` is already imported)

- [ ] **Commit**

```bash
git add packages/guineapig-client/src/renderer-overlay/views/MemoryTab.vue
git commit -m "feat(frontend): add memory summarize button with date picker"
```

### Task 10: Backend Config — Read and Add AiAgentBaseURL

**Files:**
- Read: `packages/guineapig-backend/config/config.go` to understand config pattern
- Modify as needed

- [ ] **Read config.go and understand pattern**
- [ ] **Add AiAgentBaseURL to config struct**
- [ ] **Add config field access in plugin package**

- [ ] **Commit**

```bash
git add config/config.go
git commit -m "feat(backend): add AiAgentBaseURL configuration"
```
