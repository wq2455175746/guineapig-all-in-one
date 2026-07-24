# 文件嵌入 Milvus 功能实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现文件嵌入到 Milvus 向量数据库的完整流程，包括前端触发嵌入、后端编排任务、aiagent 异步处理向量化和进度回调。

**Architecture:** Client → Backend → AiAgent → Milvus 的三层异步流程。Backend 负责任务编排和进度存储(DB+Redis)，AiAgent 负责文件下载、文本分块、向量化和 Milvus 写入。

**Tech Stack:** Go 1.24 (Echo v4, GORM, go-redis), Python 3.11+ (FastAPI, pymilvus, boto3, ollama/openai API), Vue 3 + PrimeVue

**Design doc:** `docs/superpowers/specs/2026-06-23-file-embedding-milvus-design.md`

## Global Constraints

- 严格分层：Backend 不直接调用 AI 模型
- GORM JSON 列必须用指针类型
- embedding_config JSON 更新用 map[string]any
- Redis key 格式: `rag_embedding_task:{file_id}:{task_id}`
- AiAgent 使用 OpenAI 兼容格式调 embedding API

---

### Task 1: Backend - 新增请求/响应 DTO

**Files:**
- Modify: `packages/guineapig-backend/internal/request/file.go`
- Modify: `packages/guineapig-backend/internal/response/file.go`

**Interfaces:**
- Produces: `request.FileEmbedRequest{FileId, ResRagId}`, `request.FileEmbedProgressRequest{FileId, TaskId, Progress}`, `response.FileEmbedResponse{TaskId}`

- [ ] **Step 1: 在 request/file.go 末尾添加 FileEmbedRequest 和 FileEmbedProgressRequest**

```go
type FileEmbedRequest struct {
	FileId    int64 `json:"file_id"`
	ResRagId int64 `json:"res_rag_id"`
}

type FileEmbedProgressRequest struct {
	FileId   int64  `json:"file_id"`
	TaskId   string `json:"task_id"`
	Progress int    `json:"progress"`
}
```

- [ ] **Step 2: 在 response/file.go 末尾添加 FileEmbedResponse**

```go
type FileEmbedResponse struct {
	TaskId string `json:"task_id"`
}
```

---

### Task 2: Backend - 新增 GORM 模型方法

**Files:**
- Modify: `packages/guineapig-backend/internal/model/res_files.go`
- Modify: `packages/guineapig-backend/internal/model/res_rags.go`

**Interfaces:**
- Consumes: from Task 1 DTO types
- Produces: `model.MResFiles.UpdateEmbeddingConfig(ctx, id, embeddingConfigStr)`, `model.MResFiles.UpdateIsEmbedded(ctx, id)`, `model.MResRags.UpdateRagMetadata(ctx, id, metadataStr)`, `model.MResRags.UpdateIsUsed(ctx, id)`

- [ ] **Step 1: 在 res_files.go 的 Delete 方法后添加 UpdateEmbeddingConfig**

```go
func (*ResFiles) UpdateEmbeddingConfig(ctx context.Context, id int64, embeddingConfig string) error {
	updates := map[string]any{
		"embedding_config": embeddingConfig,
		"updated_at":       time.Now(),
	}
	return plugin.GetDB(ctx).Model(&ResFiles{}).Where("id = ? AND deleted_at IS NULL", id).
		Updates(updates).Error
}
```

- [ ] **Step 2: 在 res_files.go 添加 UpdateIsEmbedded**

```go
func (*ResFiles) UpdateIsEmbedded(ctx context.Context, id int64) error {
	updates := map[string]any{
		"is_embedded": 1,
		"updated_at":  time.Now(),
	}
	return plugin.GetDB(ctx).Model(&ResFiles{}).Where("id = ? AND deleted_at IS NULL", id).
		Updates(updates).Error
}
```

- [ ] **Step 3: 在 res_rags.go 的 Delete 方法后添加 UpdateRagMetadata**

```go
func (*ResRags) UpdateRagMetadata(ctx context.Context, id int64, metadata string) error {
	updates := map[string]any{
		"rag_metadata": metadata,
		"updated_at":   time.Now(),
	}
	return plugin.GetDB(ctx).Model(&ResRags{}).Where("id = ? AND deleted_at IS NULL", id).
		Updates(updates).Error
}
```

---

### Task 3: Backend - Service 层实现

**Files:**
- Modify: `packages/guineapig-backend/internal/service/file.go`

**Interfaces:**
- Consumes: request types from Task 1, model methods from Task 2
- Produces: `service.EmbedFile(ctx, req)`, `service.UpdateEmbedProgress(ctx, req)`

- [ ] **Step 1: 在 service/file.go 的 import 中添加以下包**

```go
import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
	"guineapig/config"
	"guineapig/pkg/plugin"
	"github.com/google/uuid"
)
```

- [ ] **Step 2: 添加 EmbeddingConfig JSON 结构体**

在 FileMetadata struct 后添加:
```go
type EmbeddingConfigData struct {
	EmbeddingProcess int    `json:"embedding_process"`
	ResRagId         int64  `json:"res_rag_id"`
	TaskId           string `json:"task_id"`
}

type RagMetadataData struct {
	IsUsed bool `json:"is_used"`
}
```

- [ ] **Step 3: 实现 EmbedFile 函数**

在 GetFileById 后添加:
```go
func EmbedFile(ctx context.Context, req *request.FileEmbedRequest) (*response.FileEmbedResponse, error) {
	if req.FileId <= 0 {
		return nil, errors.New("file_id 不能为空")
	}
	if req.ResRagId <= 0 {
		return nil, errors.New("res_rag_id 不能为空")
	}

	// 1. 查找文件
	file, err := model.MResFiles.FindById(ctx, req.FileId)
	if err != nil {
		return nil, err
	}
	if file == nil {
		return nil, errors.New("文件不存在")
	}

	// 2. 查找 RAG 知识库
	rag, err := model.MResRags.FindById(ctx, req.ResRagId)
	if err != nil {
		return nil, err
	}
	if rag == nil {
		return nil, errors.New("知识库不存在")
	}

	// 3. 获取 embedding 模型信息（获取模型 URL）
	embeddingModel, err := model.MUserAiModel.FindById(ctx, rag.EmbeddingModelId)
	if err != nil {
		return nil, fmt.Errorf("查询嵌入模型失败: %w", err)
	}
	if embeddingModel == nil {
		return nil, errors.New("嵌入模型不存在")
	}

	// 4. 生成 task_id
	taskId := uuid.New().String()

	// 5. 更新 file.embedding_config
	embedConfig := EmbeddingConfigData{
		EmbeddingProcess: 0,
		ResRagId:         req.ResRagId,
		TaskId:           taskId,
	}
	embedBytes, _ := json.Marshal(embedConfig)
	embedStr := string(embedBytes)
	if err := model.MResFiles.UpdateEmbeddingConfig(ctx, req.FileId, embedStr); err != nil {
		return nil, fmt.Errorf("更新 embedding_config 失败: %w", err)
	}

	// 6. 更新 rag.rag_metadata (is_used = true)
	ragMeta := RagMetadataData{IsUsed: true}
	ragMetaBytes, _ := json.Marshal(ragMeta)
	ragMetaStr := string(ragMetaBytes)
	if err := model.MResRags.UpdateRagMetadata(ctx, req.ResRagId, ragMetaStr); err != nil {
		return nil, fmt.Errorf("更新 rag_metadata 失败: %w", err)
	}

	// 7. 获取文件的完整 S3 URL（从 file_url 和 S3 配置构建）
	s3Key := file.FileURL

	// 8. 异步调用 aiagent
	aiParams := map[string]any{
		"file_id":              req.FileId,
		"res_rag_id":           req.ResRagId,
		"task_id":              taskId,
		"rag_name":             rag.Name,
		"chunk_size":           rag.ChunkSize,
		"overlap_size":         rag.OverlapSize,
		"dimension_size":       rag.DimensionSize,
		"embedding_model_url":  embeddingModel.BaseUrl,
		"embedding_model_name": embeddingModel.ModelName,
		"s3_key":               s3Key,
		"user_id":              file.UserId,
	}

	go callAiAgentEmbedFile(ctx, aiParams)

	return &response.FileEmbedResponse{TaskId: taskId}, nil
}
```

- [ ] **Step 4: 实现 callAiAgentEmbedFile (goroutine内)**

```go
type aiagentEmbedResponse struct {
	Success    bool   `json:"success"`
	ErrCode    int    `json:"errCode"`
	ErrMessage string `json:"errMessage"`
	Result     any    `json:"result"`
}

func callAiAgentEmbedFile(ctx context.Context, params map[string]any) {
	baseURL := config.Global.AiAgent.BaseUrl
	if baseURL == "" {
		return
	}

	reqBody, _ := json.Marshal(params)

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost,
		baseURL+"/guineapig-aiagent/rag/embed",
		bytes.NewReader(reqBody))
	if err != nil {
		return
	}
	httpReq.Header.Set("Content-Type", "application/json")

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(httpReq)
	if err != nil {
		return
	}
	defer resp.Body.Close()
}
```

- [ ] **Step 5: 实现 UpdateEmbedProgress**

在 callAiAgentEmbedFile 后添加:
```go
func UpdateEmbedProgress(ctx context.Context, req *request.FileEmbedProgressRequest) error {
	if req.FileId <= 0 {
		return errors.New("file_id 不能为空")
	}
	if req.TaskId == "" {
		return errors.New("task_id 不能为空")
	}
	if req.Progress < 0 || req.Progress > 100 {
		return errors.New("progress 必须介于 0-100")
	}

	redisKey := fmt.Sprintf("rag_embedding_task:%d:%s", req.FileId, req.TaskId)

	if req.Progress == 100 {
		// 1. 设置 file.is_embedded = 1
		if err := model.MResFiles.UpdateIsEmbedded(ctx, req.FileId); err != nil {
			return fmt.Errorf("更新 is_embedded 失败: %w", err)
		}

		// 2. 更新 embedding_config 中 progress = 100
		file, err := model.MResFiles.FindById(ctx, req.FileId)
		if err != nil || file == nil {
			return fmt.Errorf("查找文件失败: %w", err)
		}

		var embedConfig EmbeddingConfigData
		if file.EmbeddingConfig != nil {
			json.Unmarshal([]byte(*file.EmbeddingConfig), &embedConfig)
		}
		embedConfig.EmbeddingProcess = 100
		embedBytes, _ := json.Marshal(embedConfig)
		if err := model.MResFiles.UpdateEmbeddingConfig(ctx, req.FileId, string(embedBytes)); err != nil {
			return fmt.Errorf("更新 embedding_config 失败: %w", err)
		}

		// 3. 删除 Redis key
		plugin.GetClient().Del(ctx, redisKey)
	} else {
		// 更新进度到 Redis
		plugin.GetClient().Set(ctx, redisKey, req.Progress, 24*time.Hour)

		// 同步更新 DB embedding_config
		file, err := model.MResFiles.FindById(ctx, req.FileId)
		if err != nil || file == nil {
			return fmt.Errorf("查找文件失败: %w", err)
		}
		var embedConfig EmbeddingConfigData
		if file.EmbeddingConfig != nil {
			json.Unmarshal([]byte(*file.EmbeddingConfig), &embedConfig)
		}
		embedConfig.EmbeddingProcess = req.Progress
		embedBytes, _ := json.Marshal(embedConfig)
		if err := model.MResFiles.UpdateEmbeddingConfig(ctx, req.FileId, string(embedBytes)); err != nil {
			return fmt.Errorf("更新 embedding_config 失败: %w", err)
		}
	}

	return nil
}
```

- [ ] **Step 6: 修改 service/rag.go 的 DeleteRag 函数检查 is_used**

```go
func DeleteRag(ctx context.Context, req *request.RagDeleteRequest) error {
	if req.Id <= 0 {
		return errors.New("id 不能为空")
	}
	if req.UserId <= 0 {
		return errors.New("user_id 不能为空")
	}

	existing, err := model.MResRags.FindById(ctx, req.Id)
	if err != nil {
		return err
	}
	if existing == nil {
		return errors.New("记录不存在")
	}
	if existing.UserId != req.UserId {
		return errors.New("无权操作该记录")
	}

	// 检查 rag_metadata 中的 is_used
	if existing.RagMetadata != nil {
		var meta struct {
			IsUsed bool `json:"is_used"`
		}
		if err := json.Unmarshal([]byte(*existing.RagMetadata), &meta); err == nil && meta.IsUsed {
			return errors.New("该知识库已被文件使用，无法删除")
		}
	}

	return model.MResRags.Delete(ctx, req.Id, req.UserId)
}
```

注意: 需要在 service/rag.go 中添加 `"encoding/json"` 到 import。

---

### Task 4: Backend - 新增 Router Handlers 和注册路由

**Files:**
- Create: `packages/guineapig-backend/internal/router/file/embed.go`
- Modify: `packages/guineapig-backend/internal/router/router.go`

**Interfaces:**
- Consumes: `service.EmbedFile`, `service.UpdateEmbedProgress`
- Produces: `POST /api/v1/file/embed`, `POST /api/v1/file/embed-progress`

- [ ] **Step 1: 创建 router/file/embed.go**

```go
package file

import (
	"errors"
	"guineapig/internal/request"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	"guineapig/pkg/utils"

	"github.com/labstack/echo/v4"
)

func Embed(e echo.Context) error {
	ctx := utils.NewContext(e)
	var req request.FileEmbedRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	if req.FileId <= 0 {
		return common.ResponseParamError(e, errors.New("file_id 不能为空"))
	}
	if req.ResRagId <= 0 {
		return common.ResponseParamError(e, errors.New("res_rag_id 不能为空"))
	}

	result, err := service.EmbedFile(ctx, &req)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, result)
}
```

- [ ] **Step 2: 创建 router/file/embed_progress.go**

```go
package file

import (
	"errors"
	"guineapig/internal/request"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	"guineapig/pkg/utils"

	"github.com/labstack/echo/v4"
)

func EmbedProgress(e echo.Context) error {
	ctx := utils.NewContext(e)
	var req request.FileEmbedProgressRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	if req.FileId <= 0 {
		return common.ResponseParamError(e, errors.New("file_id 不能为空"))
	}
	if req.TaskId == "" {
		return common.ResponseParamError(e, errors.New("task_id 不能为空"))
	}

	if err := service.UpdateEmbedProgress(ctx, &req); err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, nil)
}
```

- [ ] **Step 3: 在 router.go 的 init() 文件管理区域注册新路由**

```go
// 文件管理相关
AddGetRouter("/file/presigned-upload-url", fileRouter.PresignedUploadURL)
AddGetRouter("/file/presigned-download-url", fileRouter.PresignedDownloadURL)
AddGetRouter("/file/list", fileRouter.List)
AddPostRouter("/file/create", fileRouter.Create)
AddPostRouter("/file/update", fileRouter.Update)
AddPostRouter("/file/delete", fileRouter.Delete)
AddPostRouter("/file/embed", fileRouter.Embed)
AddPostRouter("/file/embed-progress", fileRouter.EmbedProgress)
```

---

### Task 5: Backend - 构建验证

- [ ] **Step 1: Go 编译检查**

运行: `cd packages/guineapig-backend && go build ./...`
预期: exit 0, 无错误

如果编译失败，逐一修复:
1. 缺少 uuid 依赖: `go get github.com/google/uuid`
2. `service/rag.go` 缺少 import: 添加 `"encoding/json"`

---

### Task 6: AiAgent - Config 和 Schema 配置

**Files:**
- Modify: `packages/guineapig-aiagent/app/config.py`
- Create: `packages/guineapig-aiagent/app/schemas/rag_models.py`

- [ ] **Step 1: 在 config.py 的 Settings 类中添加 Milvus 和 Backend 配置**

在 `TTS_PROMPT_TEXT` 后添加:
```python
# RAG / Milvus 嵌入配置
MILVUS_HOST: str = Field("localhost", alias="MILVUS_HOST")
MILVUS_PORT: str = Field("19530", alias="MILVUS_PORT")
BACKEND_BASE_URL: str = Field("http://guineapig-backend:6880", alias="BACKEND_BASE_URL")
```

- [ ] **Step 2: 创建 schemas/rag_models.py**

```python
"""RAG 嵌入请求/响应模型"""

from pydantic import BaseModel, Field


class RagEmbedRequest(BaseModel):
    """RAG 文件嵌入请求"""
    file_id: int = Field(..., description="文件 ID")
    res_rag_id: int = Field(..., description="知识库 ID")
    task_id: str = Field(..., description="任务 ID")
    rag_name: str = Field(..., description="知识库名称")
    chunk_size: int = Field(500, description="分段大小")
    overlap_size: int = Field(50, description="重叠大小")
    dimension_size: int = Field(1024, description="向量维度")
    embedding_model_url: str = Field(..., description="嵌入模型 URL")
    embedding_model_name: str = Field(..., description="嵌入模型名称")
    s3_key: str = Field(..., description="S3 对象键")
    user_id: int = Field(..., description="用户 ID")


class RagEmbedResponse(BaseModel):
    """RAG 嵌入响应"""
    task_id: str = Field(..., description="任务 ID")
    message: str = Field("embedding started", description="响应消息")
```

---

### Task 7: AiAgent - RAG Embedding 服务

**Files:**
- Create: `packages/guineapig-aiagent/app/services/rag_service.py`

- [ ] **Step 1: 创建完整的 rag_service.py**

```python
"""
RAG 嵌入服务 — 文件下载、分块、向量化、写入 Milvus、进度回调
"""

import os
import json
import uuid
import time
import requests
from datetime import datetime

from app.config import settings
from app.core.log import logger
from app.core.oss_wrapper_utils import download_file_from_s3


class TextChunker:
    """文本分块工具"""

    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def split_text(self, text: str) -> list:
        if not text or not text.strip():
            return []
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        start = 0
        max_iterations = len(text) // max(1, self.chunk_size - self.overlap) + 10
        iteration = 0

        while start < len(text) and iteration < max_iterations:
            iteration += 1
            end = min(start + self.chunk_size, len(text))

            # 尝试在句子边界切割
            if end < len(text):
                found_sep = False
                for sep in ["。", "！", "？", "\n", ".", "!", "?", ";", "；"]:
                    last_sep = text.rfind(sep, start, end)
                    if last_sep != -1 and last_sep > start + self.chunk_size // 2:
                        end = last_sep + 1
                        found_sep = True
                        break
                if not found_sep and end <= start:
                    end = min(start + 1, len(text))

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(chunk_text)

            # 移动 start
            new_start = end - self.overlap
            if new_start <= start:
                new_start = start + 1
            start = new_start

            # 剩余文本太少时直接追加
            if len(text) - start < self.chunk_size // 2 < len(text) - start:
                remaining = text[start:].strip()
                if remaining:
                    chunks.append(remaining)
                break

        return chunks


class EmbeddingService:
    """向量化服务 — 使用 OpenAI 兼容格式"""

    def __init__(self, api_url: str, model_name: str, timeout: int = 30):
        self.api_url = api_url.rstrip("/")
        # 确保 URL 指向 /v1/embeddings
        if not self.api_url.endswith("/embeddings"):
            if self.api_url.endswith("/v1"):
                self.api_url += "/embeddings"
            elif "/v1" not in self.api_url:
                self.api_url = self.api_url.rstrip("/") + "/v1/embeddings"
            else:
                self.api_url = self.api_url.rstrip("/") + "/embeddings"
        self.model_name = model_name
        self.timeout = timeout

    def get_embedding(self, text: str) -> list | None:
        if not text or not text.strip():
            return None
        try:
            resp = requests.post(
                self.api_url,
                json={"model": self.model_name, "input": text},
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                embeddings = data.get("data", [])
                if embeddings:
                    return embeddings[0].get("embedding")
            return None
        except Exception as e:
            logger.error(f"向量化失败: {e}")
            return None


class MilvusWriter:
    """Milvus 写入服务"""

    def __init__(self, host: str = "localhost", port: str = "19530"):
        self.host = host
        self.port = port
        self._connected = False
        self._connect()

    def _connect(self):
        from pymilvus import connections
        try:
            connections.connect(alias="default", host=self.host, port=self.port)
            self._connected = True
            logger.info(f"已连接 Milvus: {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"连接 Milvus 失败: {e}")
            raise

    def ensure_collection(self, collection_name: str, dimension: int):
        """确保数据库和集合存在"""
        from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, utility

        db_name = "guineapig_user_rag"
        # 创建数据库（如果不存在）
        try:
            from pymilvus import connections
            conn = connections.get_connection_alias()
            from pymilvus import db
            databases = db.list_database()
            if db_name not in databases:
                db.create_database(db_name)
                logger.info(f"创建 Milvus 数据库: {db_name}")
            db.using_database(db_name)
        except Exception as e:
            logger.warning(f"创建/切换数据库失败: {e}，尝试直接使用")

        # 创建集合（如果不存在）
        if utility.has_collection(collection_name):
            logger.info(f"集合已存在: {collection_name}")
            return Collection(collection_name)

        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=36, is_primary=True),
            FieldSchema(name="user_id", dtype=DataType.VARCHAR, max_length=64, is_partition_key=True),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dimension),
            FieldSchema(name="text_chunk", dtype=DataType.VARCHAR, max_length=65535),
        ]
        schema = CollectionSchema(fields=fields, description="用户 RAG 文档集合")
        collection = Collection(name=collection_name, schema=schema)

        # 创建索引
        index_params = {
            "metric_type": "IP",
            "index_type": "IVF_FLAT",
            "params": {"nlist": 128},
        }
        collection.create_index(field_name="embedding", index_params=index_params)
        logger.info(f"创建 Milvus 集合: {collection_name}, 维度: {dimension}")
        return collection

    def insert_batch(self, collection, ids: list, user_ids: list, embeddings: list, text_chunks: list):
        """批量插入数据"""
        collection.load()
        insert_data = [ids, user_ids, embeddings, text_chunks]
        try:
            collection.insert(insert_data)
            collection.flush()
            logger.info(f"插入 {len(ids)} 条数据到 Milvus")
            return True
        except Exception as e:
            logger.error(f"插入 Milvus 失败: {e}")
            return False


def report_progress(backend_url: str, file_id: int, task_id: str, progress: int):
    """回调后端进度接口"""
    try:
        resp = requests.post(
            f"{backend_url}/api/v1/file/embed-progress",
            json={
                "file_id": file_id,
                "task_id": task_id,
                "progress": progress,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info(f"报告进度 {progress}% 成功: file_id={file_id}, task_id={task_id}")
        else:
            logger.warning(f"报告进度失败: {resp.status_code}")
    except Exception as e:
        logger.warning(f"报告进度异常: {e}")


def process_file_embedding(params: dict):
    """
    处理文件嵌入的主逻辑（异步后台任务）

    Args:
        params: 包含 file_id, res_rag_id, task_id, rag_name, chunk_size,
                overlap_size, dimension_size, embedding_model_url,
                embedding_model_name, s3_key, user_id
    """
    file_id = params["file_id"]
    task_id = params["task_id"]
    rag_name = params["rag_name"]
    user_id = params["user_id"]
    s3_key = params["s3_key"]

    logger.info(f"[RAG Embed] 开始处理: file_id={file_id}, task_id={task_id}, rag={rag_name}")

    try:
        # 1. 下载文件
        today = datetime.now().strftime("%Y%m%d")
        local_dir = os.path.join(settings.DATA_DIR, "res", str(user_id), today)
        os.makedirs(local_dir, exist_ok=True)
        local_filename = os.path.basename(s3_key)
        if not local_filename:
            local_filename = f"file_{file_id}"
        local_path = os.path.join(local_dir, local_filename)

        logger.info(f"[RAG Embed] 下载 S3 文件: {s3_key} -> {local_path}")
        success = download_file_from_s3(s3_key, local_path)
        if not success:
            logger.error(f"[RAG Embed] S3 下载失败: {s3_key}")
            return
        logger.info(f"[RAG Embed] 文件下载完成: {local_path}")

        # 2. 读取文件
        text = ""
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                text = f.read()
        except UnicodeDecodeError:
            try:
                with open(local_path, "r", encoding="gbk") as f:
                    text = f.read()
            except Exception as e:
                logger.error(f"[RAG Embed] 读取文件失败: {e}")
                return

        if not text.strip():
            logger.warning(f"[RAG Embed] 文件内容为空: {local_path}")
            return

        logger.info(f"[RAG Embed] 文件大小: {len(text)} 字符")

        # 3. 文本分块
        chunker = TextChunker(
            chunk_size=params.get("chunk_size", 500),
            overlap=params.get("overlap_size", 50),
        )
        chunks = chunker.split_text(text)
        if not chunks:
            logger.warning("[RAG Embed] 没有生成文本块")
            return
        logger.info(f"[RAG Embed] 分块完成: {len(chunks)} 块")

        # 4. 向量化
        embedder = EmbeddingService(
            api_url=params["embedding_model_url"],
            model_name=params["embedding_model_name"],
        )
        embeddings = []
        total_chunks = len(chunks)
        for i, chunk in enumerate(chunks):
            embedding = embedder.get_embedding(chunk)
            if embedding:
                embeddings.append(embedding)
            else:
                logger.warning(f"[RAG Embed] 第 {i+1}/{total_chunks} 块向量化失败，跳过")

            # 每处理 5 块或最后一块时报告进度
            if (i + 1) % 5 == 0 or i == total_chunks - 1:
                progress = int((i + 1) / total_chunks * 100)
                report_progress(
                    settings.BACKEND_BASE_URL, file_id, task_id, progress
                )

        if not embeddings:
            logger.error("[RAG Embed] 所有文本块向量化失败")
            return

        logger.info(f"[RAG Embed] 向量化完成: {len(embeddings)}/{total_chunks}")

        # 5. 写入 Milvus
        writer = MilvusWriter(host=settings.MILVUS_HOST, port=settings.MILVUS_PORT)
        collection = writer.ensure_collection(
            collection_name=rag_name,
            dimension=params.get("dimension_size", 1024),
        )

        ids = [str(uuid.uuid4()) for _ in range(len(embeddings))]
        user_ids = [str(user_id)] * len(embeddings)
        text_chunks = chunks[:len(embeddings)]

        writer.insert_batch(collection, ids, user_ids, embeddings, text_chunks)

        # 6. 报告 100% 完成
        report_progress(settings.BACKEND_BASE_URL, file_id, task_id, 100)
        logger.info(f"[RAG Embed] 嵌入完成: file_id={file_id}, task_id={task_id}")

    except Exception as e:
        logger.error(f"[RAG Embed] 处理异常: {e}")

    finally:
        # 清理临时文件
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
                logger.debug(f"[RAG Embed] 临时文件已删除: {local_path}")
            except Exception:
                pass
```

---

### Task 8: AiAgent - RAG Router 注册

**Files:**
- Create: `packages/guineapig-aiagent/app/routers/rag.py`
- Modify: `packages/guineapig-aiagent/app/main.py`

- [ ] **Step 1: 创建 routers/rag.py**

```python
"""RAG 嵌入路由"""

import asyncio
from fastapi import APIRouter

from app.core.log import logger
from app.schemas.base_models import success_response, error_response
from app.schemas.rag_models import RagEmbedRequest
from app.services.rag_service import process_file_embedding

router = APIRouter(prefix="/guineapig-aiagent/rag", tags=["rag"])


@router.post("/embed")
async def embed_file(request: RagEmbedRequest):
    """
    接收文件嵌入任务。

    立即返回 task_id，后台异步处理文件下载、分块、向量化和 Milvus 写入。
    """
    logger.info(f"[RAG] 收到嵌入请求: file_id={request.file_id}, "
                f"rag={request.rag_name}, task_id={request.task_id}")

    try:
        # 启动后台异步任务
        params = request.model_dump()
        asyncio.create_task(_run_embedding_async(params))

        return success_response(data={"task_id": request.task_id, "message": "embedding started"})
    except Exception as e:
        logger.error(f"[RAG] 启动嵌入任务失败: {e}")
        return error_response(message=f"启动失败: {str(e)}", code=500)


async def _run_embedding_async(params: dict):
    """在后台线程中运行嵌入处理（避免阻塞事件循环）"""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, process_file_embedding, params)
```

- [ ] **Step 2: 在 main.py 中注册 rag 路由**

```python
from app.routers import asr, llm, rag, skill, task
```

并将 rag 改为:
```python
from app.routers import asr, llm, rag, skill, task
```

在 `app.include_router(skill.router)` 后添加:
```python
app.include_router(rag.router)
```

更新后的 main.py 路由注册部分:
```python
# 注册路由
app.include_router(task.router)
app.include_router(asr.router)
app.include_router(llm.router)
app.include_router(skill.router)
app.include_router(rag.router)
```

---

### Task 9: Frontend - FileManagementTab.vue 嵌入功能

**Files:**
- Modify: `packages/guineapig-client/src/renderer-overlay/views/FileManagementTab.vue`

- [ ] **Step 1: 在 template 中添加嵌入选择对话框**

在模板末尾（`<input ref="fileInputRef"...>` 后）:
```html
<!-- 嵌入知识库选择对话框 -->
<Dialog v-model:visible="embedDialogVisible" header="选择知识库" :modal="true"
  :style="{ width: '400px' }" :draggable="false">
  <div style="display: flex; flex-direction: column; gap: 16px;">
    <div class="field">
      <label class="field-label">选择要嵌入的知识库</label>
      <Select v-model="selectedRagId" :options="ragList" optionLabel="name" optionValue="id"
        placeholder="请选择知识库" class="field-input" :loading="ragLoading" />
    </div>
    <div class="dialog-actions">
      <Button label="取消" severity="secondary" outlined @click="embedDialogVisible = false" />
      <Button label="开始嵌入" @click="confirmEmbed" :loading="embeddingLoading"
        :disabled="!selectedRagId" />
    </div>
  </div>
</Dialog>
```

- [ ] **Step 2: 添加 ragList 相关数据和加载逻辑**

在 script 的 ref 定义区域添加:
```typescript
// ========== 嵌入相关 ==========
const embedDialogVisible = ref(false)
const selectedRagId = ref<number | null>(null)
const embeddingLoading = ref(false)
const embeddingTarget = ref<FileItem | null>(null)
const ragList = ref<RagItem[]>([])
const ragLoading = ref(false)

interface RagItem {
  id: number
  user_id: number
  name: string
  rag_desc: string
}
```

- [ ] **Step 3: 添加 RagList 预加载和嵌入逻辑**

在 fetchFileList 或 onMounted 的适当位置添加预加载。在 script 的末尾添加:
```typescript
// 解析 embedding_config JSON
function parseEmbeddingConfig(config: string): { embedding_process: number; res_rag_id: number; task_id: string } | null {
  if (!config) return null
  try {
    return JSON.parse(config)
  } catch {
    return null
  }
}

// 判断文件是否正在嵌入中
function isEmbeddingInProgress(data: FileItem): boolean {
  if (data.is_embedded) return false
  const config = parseEmbeddingConfig(data.embedding_config)
  if (!config) return false
  return config.embedding_process > 0 && config.embedding_process < 100
}

// 获取嵌入进度
function getEmbeddingProcess(data: FileItem): number {
  const config = parseEmbeddingConfig(data.embedding_config)
  return config?.embedding_process ?? 0
}

// 预加载知识库列表
async function fetchRagList() {
  ragLoading.value = true
  try {
    const params = new URLSearchParams({ user_id: String(userId), pageSize: '999', pageNum: '1' })
    const res = await fetch(`${API_BASE_URL}/api/v1/rag/list?${params}`)
    const data = await res.json()
    if (data.code === 0) {
      ragList.value = data.result.items || []
    }
  } catch (err) {
    console.warn('加载知识库列表失败:', err)
  } finally {
    ragLoading.value = false
  }
}

function handleEmbed(data: FileItem) {
  embeddingTarget.value = data
  selectedRagId.value = null
  embedDialogVisible.value = true
}

async function confirmEmbed() {
  if (!selectedRagId.value || !embeddingTarget.value) return
  embeddingLoading.value = true
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/file/embed`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_id: embeddingTarget.value.id,
        res_rag_id: selectedRagId.value,
      }),
    })
    const data = await res.json()
    if (data.code === 0) {
      toast.add({ severity: 'success', summary: '嵌入任务已提交', detail: `文件「${embeddingTarget.value.name}」正在嵌入`, life: 3000 })
      embedDialogVisible.value = false
      await fetchFileList()
    } else {
      toast.add({ severity: 'error', summary: '提交失败', detail: data.message, life: 3000 })
    }
  } catch (err) {
    toast.add({ severity: 'error', summary: '请求失败', detail: String(err), life: 3000 })
  } finally {
    embeddingLoading.value = false
  }
}

// 在组件挂载时加载 RAG 列表
fetchRagList()
```

- [ ] **Step 4: 修改 handleEmbed 函数**

删除原有的 handleEmbed 存根（它只显示 toast），已经被 Step 3 中的新 handleEmbed 覆盖。

- [ ] **Step 5: 修改嵌入按钮的 disabled 逻辑**

```html
<Button icon="pi pi-microchip" rounded severity="secondary" v-tooltip.top="'嵌入'"
  :disabled="!canEmbed(data.file_type) || data.is_embedded === 1 || isEmbeddingInProgress(data)"
  @click="handleEmbed(data)" />
```

- [ ] **Step 6: 修改"是否嵌入"列，显示进度**

```html
<Column header="是否嵌入">
  <template #body="{ data }">
    <template v-if="data.is_embedded">
      <Tag value="已嵌入" severity="success" />
    </template>
    <template v-else-if="isEmbeddingInProgress(data)">
      <Tag :value="`嵌入中 ${getEmbeddingProcess(data)}%`" severity="warn" />
    </template>
    <template v-else>
      <Tag value="未嵌入" severity="secondary" />
    </template>
  </template>
</Column>
```

- [ ] **Step 7: 添加 import Dialog 和 Select**

在已有的 import 中添加:
```typescript
import Dialog from 'primevue/dialog'
```

---

### Task 10: Frontend - RagTab.vue 删除按钮 is_used 检查

**Files:**
- Modify: `packages/guineapig-client/src/renderer-overlay/views/RagTab.vue`

- [ ] **Step 1: 扩展 RagItem 接口添加 rag_metadata 字段**

```typescript
interface RagItem {
  // ... 现有字段
  rag_metadata: string  // 新增
}
```

- [ ] **Step 2: 添加解析 rag_metadata 的函数和 isUsed 判断**

```typescript
function isRagInUse(item: RagItem): boolean {
  if (!item.rag_metadata) return false
  try {
    const meta = JSON.parse(item.rag_metadata)
    return meta.is_used === true
  } catch {
    return false
  }
}
```

- [ ] **Step 3: 修改删除按钮 disabled 条件**

将:
```html
:disabled="item.doc_count > 0"
```
改为:
```html
:disabled="item.doc_count > 0 || isRagInUse(item)"
```

---

### Task 11: 最终构建验证

- [ ] **Step 1: Go 编译验证**

运行: `cd packages/guineapig-backend && go build ./...`
预期: exit 0

- [ ] **Step 2: AiAgent 语法检查**

运行: `cd packages/guineapig-aiagent && python -c "from app.services.rag_service import *; print('OK')"`
预期: 打印 OK

注意: 如果 pymilvus 未安装，需要 `pip install pymilvus requests`，但 requirements.txt 中已有 `pymilvus>=2.6.5`，只需确保 `requests` 也在其中。
