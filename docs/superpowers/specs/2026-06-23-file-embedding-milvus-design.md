# 文件嵌入 Milvus 功能设计文档

## 概述

实现文件（File Management）嵌入到 Milvus 向量数据库的功能。用户选择知识库（RAG），将文件内容分块、向量化后存入 Milvus。

## 架构

```
FileManagementTab.vue
  → POST /api/v1/file/embed {file_id, res_rag_id}
  → Backend 更新 embedding_config + rag_metadata, goroutine 异步调 aiagent
  → 返回成功, 客户端刷新列表

AiAgent (async goroutine)
  → S3 下载文件 → 文本分块 → OpenAI 兼容 embedding API → 写入 Milvus
  → 每完成一批 POST /api/v1/file/embed-progress 回调
  → Backend 更新 DB embedding_config + Redis
  → 100% 时设 is_embedded=1, 删 Redis key
```

## 组件设计

### 1. Backend - 新增请求/响应 DTO

**`internal/request/file.go`** 新增:

```go
type FileEmbedRequest struct {
    FileId    int64 `json:"file_id"`
    ResRagId int64 `json:"res_rag_id"`
}

type FileEmbedProgressRequest struct {
    FileId   int64  `json:"file_id"`
    TaskId   string `json:"task_id"`
    Progress int    `json:"progress"`  // 0-100
}
```

**`internal/response/file.go`** 新增:

```go
type FileEmbedResponse struct {
    TaskId string `json:"task_id"`
}
```

### 2. Backend - Service 层

**`internal/service/file.go`** 新增方法:

- **`EmbedFile(ctx, req)`**: 查找 ResRags 获取知识库信息（名称、chunk_size、overlap_size、dimension_size、模型 URL/名称）→ 查找 ResFiles 获取文件 S3 URL → 生成 task_id (UUID) → 更新 file.embedding_config `{"embedding_process":0,"res_rag_id":N,"task_id":"xxx"}` → 更新 rag.rag_metadata `{"is_used":true}` → 启动 goroutine 调用 aiagent → 返回 task_id

- **`UpdateEmbedProgress(ctx, req)`**: 更新 file.embedding_config 中的 embedding_process → 写入 Redis `rag_embedding_task:{file_id}:{task_id}` TTL 1天 → 若 progress=100%: 设 is_embedded=1, 删除 Redis key

- **`callAiAgentEmbedFile(ctx, params)`** (goroutine 内): HTTP POST aiagent `/guineapig-aiagent/rag/embed`，传递文件信息、知识库配置和 task_id（由 backend 生成，保证在 goroutine 返回前可用）

### 3. Backend - Router Handlers

- **`router/file/embed.go`**: 绑定 FileEmbedRequest → 调用 service.EmbedFile → 返回 FileEmbedResponse
- **`router/file/embed_progress.go`**: 绑定 FileEmbedProgressRequest → 调用 service.UpdateEmbedProgress

Router 注册:
```
POST /api/v1/file/embed
POST /api/v1/file/embed-progress
```

### 4. Backend - RAG Delete 检查

修改 `router/rag/delete.go` 和 `service/rag.go` 的 Delete 逻辑:
- 检查 `rag_metadata` JSON 中 `is_used` 字段
- `is_used=true` 时返回错误，拒绝删除

### 5. AiAgent - Config 新增

**`app/config.py`** 新增:
```python
MILVUS_HOST: str = Field("localhost", alias="MILVUS_HOST")
MILVUS_PORT: str = Field("19530", alias="MILVUS_PORT")
BACKEND_BASE_URL: str = Field("http://guineapig-backend:8080", alias="BACKEND_BASE_URL")
```

### 6. AiAgent - 新增 Router

**`app/routers/rag.py`** - `POST /guineapig-aiagent/rag/embed`

请求体:
```python
class RagEmbedRequest(BaseModel):
    file_id: int
    res_rag_id: int
    rag_name: str
    chunk_size: int = 500
    overlap_size: int = 50
    dimension_size: int = 1024
    embedding_model_url: str
    embedding_model_name: str
    s3_url: str
    user_id: int
    task_id: str
```

处理流程:
1. 接收 task_id（由 backend 生成）→ 立即返回 `{task_id, message: "embedding started"}`
2. Async 后台任务:
   - 从 S3 URL 下载文件到 `data/res/{user_id}/{date}/`
   - 文本分块 (TextChunker)
   - OpenAI 兼容 embedding API 向量化
   - 写入 Milvus
   - 每 chunk 回调进度

### 7. AiAgent - 新增 Service

**`app/services/rag_service.py`**:

- **`EmbeddingService`**: 使用 OpenAI 兼容格式 `POST {embedding_model_url}/v1/embeddings`，发送 `{"model": name, "input": text}`，带头 `Authorization: Bearer {api_key}`。兼容 Ollama 和标准 OpenAI API。
- **`TextChunker`**: chunk_size/overlap_size 分块，句子边界切割
- **`MilvusWriter`**: 连接 Milvus → 创建库 `guineapig_user_rag` → 创建集合 `{rag_name}`（不存在时建）→ 批量插入数据
- **`report_progress(file_id, task_id, progress)`**: HTTP POST 后端进度接口

### 8. Milvus 集合结构

数据库: `guineapig_user_rag`
集合名: 知识库 name

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR(36) PK | UUID |
| user_id | VARCHAR(64) partition_key | 分区键 |
| embedding | FLOAT_VECTOR({dimension_size}) | 文本嵌入向量 |
| text_chunk | VARCHAR(65535) | 原始文本片段 |

### 9. Frontend - FileManagementTab.vue

- **RAG 列表预加载**: `onMounted` + 刷新时拉取知识库列表，存 `ragList` ref
- **嵌入按钮**: `is_embedded=1` 或 `embedding_process<100` 时 disabled
- **handleEmbed**: 弹出 Select 对话框展示 `ragList` → 确认后 POST `/api/v1/file/embed` → 刷新列表
- **进度展示**: 从 `embedding_config` JSON 解析 `embedding_process`，显示在表格中

### 10. Frontend - RagTab.vue

- **删除按钮**: 检查 `rag_metadata` JSON 中 `is_used=true` 时 disabled

## embedding_config JSON 结构

```json
{
  "embedding_process": 50,
  "res_rag_id": 1,
  "task_id": "xxx-xxx"
}
```

## rag_metadata JSON 结构

```json
{
  "is_used": true
}
```
