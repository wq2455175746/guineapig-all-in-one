# 知识库管理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 guineapig-backend 和 guineapig-client 中实现知识库管理全套 CRUD 功能

**Architecture:** 后端使用 Go + Echo + GORM 完成 CRUD API，前端使用 Vue 3 + PrimeVue 新增 RagTab.vue 组件

**Tech Stack:** Go 1.24, Echo v4, GORM, MySQL, Vue 3, PrimeVue

## Global Constraints

- 后端 GORM JSON 列必须用 string 指针类型（*string）
- GORM Updates 使用 map[string]any 而非 struct
- API 响应格式统一为 {code, message, result, requestId}
- 路由注册使用 init() + router.AddGetRouter / AddPostRouter 模式
- 前端 API 调用使用原生 fetch()，API_BASE_URL 来自 VITE_API_BASE_URL

---

### Task 1: Backend — Model/Request/Response/Service/Router 全链路

**Files:**
- Create: `packages/guineapig-backend/internal/model/res_rags.go`
- Create: `packages/guineapig-backend/internal/request/rag.go`
- Create: `packages/guineapig-backend/internal/response/rag.go`
- Create: `packages/guineapig-backend/internal/service/rag.go`
- Create: `packages/guineapig-backend/internal/router/rag/list.go`
- Create: `packages/guineapig-backend/internal/router/rag/create.go`
- Create: `packages/guineapig-backend/internal/router/rag/update.go`
- Create: `packages/guineapig-backend/internal/router/rag/delete.go`
- Modify: `packages/guineapig-backend/internal/router/router.go`
- Modify: `packages/guineapig-backend/internal/model/user_aimodel.go` (新增 ListOptionsByType)
- Modify: `packages/guineapig-backend/internal/service/aimodel.go` (新增 ListAiModelOptionsByType)
- Modify: `packages/guineapig-backend/internal/router/aimodel/options.go` (新增 OptionsByType handler)

**Interfaces:**
- Consumes: 现有 GORM model 模式, router 注册模式, 响应格式
- Produces: `POST /api/v1/rag/create`, `POST /api/v1/rag/update`, `POST /api/v1/rag/delete`, `GET /api/v1/rag/list`, `GET /api/v1/aimodel/options-by-type`

- [ ] **Step 1: Create model/res_rags.go**

```go
// packages/guineapig-backend/internal/model/res_rags.go
package model

import (
	"context"
	"errors"
	"guineapig/internal/request"
	"guineapig/pkg/plugin"
	"time"

	"gorm.io/gorm"
)

var MResRags = &ResRags{}

type ResRags struct {
	Id                int64     `gorm:"column:id;primaryKey;autoIncrement"`
	UserId            int64     `gorm:"column:user_id"`
	Name              string    `gorm:"column:name"`
	RagDesc           string    `gorm:"column:rag_desc"`
	RagMetadata       *string   `gorm:"column:rag_metadata;type:json"`
	ChunkSize         int       `gorm:"column:chunk_size;default:500"`
	OverlapSize       int       `gorm:"column:overlap_size;default:50"`
	DimensionSize     int       `gorm:"column:dimension_size;default:1024"`
	EmbeddingModelId  int64     `gorm:"column:embedding_model_id"`
	EmbeddingModelName string   `gorm:"column:embedding_model_name"`
	RerankerModelId   int64     `gorm:"column:reranker_model_id"`
	RerankerModelName string    `gorm:"column:reranker_model_name"`
	DocCount          int64     `gorm:"column:doc_count;default:0"`
	CreatedBy         string    `gorm:"column:created_by"`
	CreatedAt         time.Time `gorm:"column:created_at"`
	UpdatedBy         string    `gorm:"column:updated_by"`
	UpdatedAt         time.Time `gorm:"column:updated_at"`
	DeletedAt         *int64    `gorm:"column:deleted_at"`
}

func (*ResRags) TableName() string {
	return "res_rags"
}

func (m *ResRags) Create(ctx context.Context) error {
	m.CreatedAt = time.Now()
	m.UpdatedAt = time.Now()
	return plugin.GetDB(ctx).Create(m).Error
}

func (m *ResRags) Update(ctx context.Context) error {
	m.UpdatedAt = time.Now()

	updates := map[string]any{
		"updated_at": m.UpdatedAt,
	}

	if m.RagDesc != "" {
		updates["rag_desc"] = m.RagDesc
	}

	return plugin.GetDB(ctx).Model(m).Where("id = ? AND deleted_at IS NULL", m.Id).Updates(updates).Error
}

func (*ResRags) Delete(ctx context.Context, id int64, userId int64) error {
	now := time.Now().Unix()
	return plugin.GetDB(ctx).Model(&ResRags{}).Where("id = ? AND user_id = ? AND deleted_at IS NULL", id, userId).
		Update("deleted_at", now).Error
}

func (*ResRags) FindById(ctx context.Context, id int64) (*ResRags, error) {
	var m ResRags
	err := plugin.GetDB(ctx).Where("id = ? AND deleted_at IS NULL", id).First(&m).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, err
	}
	return &m, nil
}

func (*ResRags) FindByUserIdAndName(ctx context.Context, userId int64, name string) (*ResRags, error) {
	var m ResRags
	err := plugin.GetDB(ctx).Model(&ResRags{}).
		Where("user_id = ? AND name = ? AND deleted_at IS NULL", userId, name).
		First(&m).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, err
	}
	return &m, nil
}

func (*ResRags) List(ctx context.Context, req *request.RagListRequest) ([]*ResRags, int64, error) {
	query := plugin.GetDB(ctx).Model(&ResRags{}).Where("deleted_at IS NULL")

	if req.UserId > 0 {
		query = query.Where("user_id = ?", req.UserId)
	}

	if req.Keywords != "" {
		searchKey := "%" + req.Keywords + "%"
		query = query.Where("(name LIKE ? OR rag_desc LIKE ?)", searchKey, searchKey)
	}

	var total int64
	if err := query.Count(&total).Error; err != nil {
		return nil, 0, err
	}

	if req.PageSize > 0 && req.PageNum > 0 {
		offset := (req.PageNum - 1) * req.PageSize
		query = query.Offset(offset).Limit(req.PageSize)
	}

	query = query.Order("id desc")

	var items []*ResRags
	if err := query.Find(&items).Error; err != nil {
		return nil, 0, err
	}

	return items, total, nil
}
```

- [ ] **Step 2: Create request/rag.go**

```go
// packages/guineapig-backend/internal/request/rag.go
package request

type RagCreateRequest struct {
	UserId           int64  `json:"user_id"`
	Name             string `json:"name"`
	RagDesc          string `json:"rag_desc"`
	ChunkSize        int    `json:"chunk_size"`
	OverlapSize      int    `json:"overlap_size"`
	DimensionSize    int    `json:"dimension_size"`
	EmbeddingModelId int64  `json:"embedding_model_id"`
	RerankerModelId  int64  `json:"reranker_model_id"`
}

type RagUpdateRequest struct {
	Id      int64  `json:"id"`
	UserId  int64  `json:"user_id"`
	RagDesc string `json:"rag_desc"`
}

type RagDeleteRequest struct {
	Id     int64 `json:"id"`
	UserId int64 `json:"user_id"`
}

type RagListRequest struct {
	UserId   int64  `json:"user_id" query:"user_id"`
	PageSize int    `json:"pageSize" query:"pageSize"`
	PageNum  int    `json:"pageNum" query:"pageNum"`
	Keywords string `json:"keywords" query:"keywords"`
}
```

- [ ] **Step 3: Create response/rag.go**

```go
// packages/guineapig-backend/internal/response/rag.go
package response

type RagItem struct {
	Id                int64  `json:"id"`
	UserId            int64  `json:"user_id"`
	Name              string `json:"name"`
	RagDesc           string `json:"rag_desc"`
	ChunkSize         int    `json:"chunk_size"`
	OverlapSize       int    `json:"overlap_size"`
	DimensionSize     int    `json:"dimension_size"`
	EmbeddingModelId  int64  `json:"embedding_model_id"`
	EmbeddingModelName string `json:"embedding_model_name"`
	RerankerModelId   int64  `json:"reranker_model_id"`
	RerankerModelName string `json:"reranker_model_name"`
	DocCount          int64  `json:"doc_count"`
	CreatedAt         string `json:"created_at"`
	UpdatedAt         string `json:"updated_at"`
}

type RagListResponse struct {
	Items []RagItem `json:"items"`
	Total int64     `json:"total"`
}

type RagCreateResponse struct {
	Id int64 `json:"id"`
}
```

- [ ] **Step 4: Create service/rag.go**

```go
// packages/guineapig-backend/internal/service/rag.go
package service

import (
	"context"
	"errors"
	"fmt"
	"guineapig/internal/model"
	"guineapig/internal/request"
	"guineapig/internal/response"
)

func CreateRag(ctx context.Context, req *request.RagCreateRequest) (*response.RagCreateResponse, error) {
	if req.UserId <= 0 {
		return nil, errors.New("user_id 不能为空")
	}
	if req.Name == "" {
		return nil, errors.New("知识库名称不能为空")
	}

	// 检查同名知识库
	existing, err := model.MResRags.FindByUserIdAndName(ctx, req.UserId, req.Name)
	if err != nil {
		return nil, err
	}
	if existing != nil {
		return nil, errors.New("同名知识库已存在")
	}

	// 获取嵌入模型名称
	embeddingModel, err := model.MUserAiModel.FindById(ctx, req.EmbeddingModelId)
	if err != nil {
		return nil, fmt.Errorf("查询嵌入模型失败: %w", err)
	}
	if embeddingModel == nil {
		return nil, errors.New("嵌入模型不存在")
	}
	if embeddingModel.UserId != req.UserId {
		return nil, errors.New("无权使用该嵌入模型")
	}

	// 获取 reranker 模型名称
	rerankerModel, err := model.MUserAiModel.FindById(ctx, req.RerankerModelId)
	if err != nil {
		return nil, fmt.Errorf("查询 reranker 模型失败: %w", err)
	}
	if rerankerModel == nil {
		return nil, errors.New("reranker 模型不存在")
	}
	if rerankerModel.UserId != req.UserId {
		return nil, errors.New("无权使用该 reranker 模型")
	}

	chunkSize := req.ChunkSize
	if chunkSize <= 0 {
		chunkSize = 500
	}
	overlapSize := req.OverlapSize
	if overlapSize <= 0 {
		overlapSize = 50
	}
	dimensionSize := req.DimensionSize
	if dimensionSize <= 0 {
		dimensionSize = 1024
	}

	m := &model.ResRags{
		UserId:            req.UserId,
		Name:              req.Name,
		RagDesc:           req.RagDesc,
		ChunkSize:         chunkSize,
		OverlapSize:       overlapSize,
		DimensionSize:     dimensionSize,
		EmbeddingModelId:  req.EmbeddingModelId,
		EmbeddingModelName: embeddingModel.ModelName,
		RerankerModelId:   req.RerankerModelId,
		RerankerModelName: rerankerModel.ModelName,
	}

	if err := m.Create(ctx); err != nil {
		return nil, err
	}

	return &response.RagCreateResponse{Id: m.Id}, nil
}

func UpdateRag(ctx context.Context, req *request.RagUpdateRequest) error {
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

	m := &model.ResRags{
		Id:      req.Id,
		RagDesc: req.RagDesc,
	}
	return m.Update(ctx)
}

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

	return model.MResRags.Delete(ctx, req.Id, req.UserId)
}

func ListRag(ctx context.Context, req *request.RagListRequest) (*response.RagListResponse, error) {
	items, total, err := model.MResRags.List(ctx, req)
	if err != nil {
		return nil, err
	}

	resItems := make([]response.RagItem, 0, len(items))
	for _, item := range items {
		resItems = append(resItems, response.RagItem{
			Id:                item.Id,
			UserId:            item.UserId,
			Name:              item.Name,
			RagDesc:           item.RagDesc,
			ChunkSize:         item.ChunkSize,
			OverlapSize:       item.OverlapSize,
			DimensionSize:     item.DimensionSize,
			EmbeddingModelId:  item.EmbeddingModelId,
			EmbeddingModelName: item.EmbeddingModelName,
			RerankerModelId:   item.RerankerModelId,
			RerankerModelName: item.RerankerModelName,
			DocCount:          item.DocCount,
			CreatedAt:         item.CreatedAt.Format("2006-01-02 15:04:05"),
			UpdatedAt:         item.UpdatedAt.Format("2006-01-02 15:04:05"),
		})
	}

	return &response.RagListResponse{
		Items: resItems,
		Total: total,
	}, nil
}
```

- [ ] **Step 5: Create 4 router handlers**

```go
// packages/guineapig-backend/internal/router/rag/list.go
package rag

import (
	"guineapig/internal/request"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	"guineapig/pkg/utils"

	"github.com/labstack/echo/v4"
)

func List(e echo.Context) error {
	ctx := utils.NewContext(e)
	var req request.RagListRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	resp, err := service.ListRag(ctx, &req)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}
```

```go
// packages/guineapig-backend/internal/router/rag/create.go
package rag

import (
	"errors"
	"guineapig/internal/request"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	"guineapig/pkg/utils"

	"github.com/labstack/echo/v4"
)

func Create(e echo.Context) error {
	ctx := utils.NewContext(e)
	var req request.RagCreateRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	if req.UserId <= 0 {
		return common.ResponseParamError(e, errors.New("user_id 不能为空"))
	}
	if req.Name == "" {
		return common.ResponseParamError(e, errors.New("知识库名称不能为空"))
	}

	resp, err := service.CreateRag(ctx, &req)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}
```

```go
// packages/guineapig-backend/internal/router/rag/update.go
package rag

import (
	"errors"
	"guineapig/internal/request"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	"guineapig/pkg/utils"

	"github.com/labstack/echo/v4"
)

func Update(e echo.Context) error {
	ctx := utils.NewContext(e)
	var req request.RagUpdateRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	if req.Id <= 0 {
		return common.ResponseParamError(e, errors.New("id 不能为空"))
	}
	if req.UserId <= 0 {
		return common.ResponseParamError(e, errors.New("user_id 不能为空"))
	}

	if err := service.UpdateRag(ctx, &req); err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, nil)
}
```

```go
// packages/guineapig-backend/internal/router/rag/delete.go
package rag

import (
	"errors"
	"guineapig/internal/request"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	"guineapig/pkg/utils"

	"github.com/labstack/echo/v4"
)

func Delete(e echo.Context) error {
	ctx := utils.NewContext(e)
	var req request.RagDeleteRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}

	if req.Id <= 0 {
		return common.ResponseParamError(e, errors.New("id 不能为空"))
	}
	if req.UserId <= 0 {
		return common.ResponseParamError(e, errors.New("user_id 不能为空"))
	}

	if err := service.DeleteRag(ctx, &req); err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, nil)
}
```

- [ ] **Step 6: Register routes in router.go**

Add import:
```go
ragRouter "guineapig/internal/router/rag"
```

Add to init():
```go
// RAG 知识库相关
AddPostRouter("/rag/create", ragRouter.Create)
AddPostRouter("/rag/update", ragRouter.Update)
AddPostRouter("/rag/delete", ragRouter.Delete)
AddGetRouter("/rag/list", ragRouter.List)
```

- [ ] **Step 7: Add ListOptionsByType to model/user_aimodel.go**

```go
func (*UserAiModel) ListOptionsByType(ctx context.Context, userId int64, modelType string) ([]*UserAiModel, error) {
	var items []*UserAiModel
	query := plugin.GetDB(ctx).Model(&UserAiModel{}).
		Where("user_id = ? AND status = 1 AND established = 1 AND deleted_at IS NULL", userId)

	if modelType != "" {
		query = query.Where("model_type = ?", modelType)
	}

	err := query.Order("id asc").Find(&items).Error
	return items, err
}
```

- [ ] **Step 8: Add ListAiModelOptionsByType to service/aimodel.go**

```go
func ListAiModelOptionsByType(ctx context.Context, userId int64, modelType string) ([]response.AiModelOption, error) {
	if userId <= 0 {
		return nil, errors.New("user_id 不能为空")
	}

	items, err := model.MUserAiModel.ListOptionsByType(ctx, userId, modelType)
	if err != nil {
		return nil, err
	}

	res := make([]response.AiModelOption, 0, len(items))
	for _, item := range items {
		res = append(res, response.AiModelOption{
			Id:        item.Id,
			ModelName: item.ModelName,
		})
	}
	return res, nil
}
```

- [ ] **Step 9: Add OptionsByType handler**

```go
// In packages/guineapig-backend/internal/router/aimodel/options.go, add:
func OptionsByType(e echo.Context) error {
	ctx := utils.NewContext(e)

	userIdStr := e.QueryParam("user_id")
	userId, err := strconv.ParseInt(userIdStr, 10, 64)
	if err != nil {
		return common.ResponseParamError(e, err)
	}

	modelType := e.QueryParam("model_type")

	resp, err := service.ListAiModelOptionsByType(ctx, userId, modelType)
	if err != nil {
		return common.ResponseServerError(e, err)
	}

	return common.ResponseOk(e, resp)
}
```

Register in router.go:
```go
AddGetRouter("/aimodel/options-by-type", aimodel.OptionsByType)
```

- [ ] **Step 10: Verify Go build**

Run: `cd packages/guineapig-backend && go build ./...`
Expected: no errors

- [ ] **Step 11: Commit backend**

```bash
git add packages/guineapig-backend/internal/model/res_rags.go \
       packages/guineapig-backend/internal/request/rag.go \
       packages/guineapig-backend/internal/response/rag.go \
       packages/guineapig-backend/internal/service/rag.go \
       packages/guineapig-backend/internal/router/rag/list.go \
       packages/guineapig-backend/internal/router/rag/create.go \
       packages/guineapig-backend/internal/router/rag/update.go \
       packages/guineapig-backend/internal/router/rag/delete.go \
       packages/guineapig-backend/internal/router/router.go \
       packages/guineapig-backend/internal/model/user_aimodel.go \
       packages/guineapig-backend/internal/service/aimodel.go
git commit -m "feat: 后端知识库管理 CRUD API + aimodel options-by-type 接口"
```

### Task 2: Frontend — RagTab.vue 组件

**Files:**
- Create: `packages/guineapig-client/src/renderer-overlay/views/RagTab.vue`
- Modify: `packages/guineapig-client/src/renderer-overlay/views/ResourcePage.vue`

**Interfaces:**
- Consumes: `GET /api/v1/rag/list`, `POST /api/v1/rag/create`, `POST /api/v1/rag/update`, `POST /api/v1/rag/delete`, `GET /api/v1/aimodel/options-by-type`

- [ ] **Step 1: Create RagTab.vue**

Full component with:
- Top toolbar: left "添加知识库" button, right search bar with search icon + refresh button
- DataView grid layout (5 columns) with paginator
- Each card shows: name, desc, chunk_size, overlap_size, dimension_size, embedding_model_name, reranker_model_name
- Card bottom-right: update + delete buttons
- Delete disabled when doc_count > 0
- Add dialog with name validation (字母数字下划线，数字不能开头)
- Update dialog: only desc editable

```vue
<template>
  <div class="rag-layout">
    <!-- 顶部工具栏 -->
    <div class="rag-toolbar">
      <div class="rag-toolbar-left">
        <Button label="添加知识库" icon="pi pi-plus" severity="secondary" raised size="small"
          @click="openAddDialog" />
      </div>
      <div class="search-area">
        <IconField>
          <InputIcon class="pi pi-search" />
          <InputText v-model="searchQuery" placeholder="搜索知识库名称或描述..." @keydown.enter="handleSearch" />
        </IconField>
        <Button icon="pi pi-refresh" severity="secondary" raised size="small" @click="fetchList"
          :loading="loading" />
      </div>
    </div>

    <!-- 卡片列表 -->
    <DataView :value="items" layout="grid" paginator :rows="pageSize" :rowsPerPageOptions="[10, 20, 50]"
      :totalRecords="total" :lazy="true" @page="onPage" dataKey="id" class="rag-dataview">
      <template #grid="slotProps">
        <div class="rag-grid">
          <div v-for="item in slotProps.items" :key="item.id" class="rag-card">
            <!-- 名称 -->
            <div class="rag-card-name">{{ item.name }}</div>

            <!-- 描述 -->
            <div class="rag-card-desc" v-tooltip.top="item.rag_desc">{{ item.rag_desc || '暂无描述' }}</div>

            <!-- 参数 -->
            <div class="rag-card-meta">
              <div class="meta-row">
                <span class="meta-label">分段大小</span>
                <span class="meta-value">{{ item.chunk_size }}</span>
              </div>
              <div class="meta-row">
                <span class="meta-label">重叠大小</span>
                <span class="meta-value">{{ item.overlap_size }}</span>
              </div>
              <div class="meta-row">
                <span class="meta-label">嵌入维度</span>
                <span class="meta-value">{{ item.dimension_size }}</span>
              </div>
              <div class="meta-row">
                <span class="meta-label">嵌入模型</span>
                <span class="meta-value">{{ item.embedding_model_name }}</span>
              </div>
              <div class="meta-row">
                <span class="meta-label">Reranker</span>
                <span class="meta-value">{{ item.reranker_model_name }}</span>
              </div>
              <div class="meta-row">
                <span class="meta-label">文档数</span>
                <span class="meta-value">{{ item.doc_count }}</span>
              </div>
            </div>

            <!-- 操作按钮 -->
            <div class="rag-card-actions">
              <Button icon="pi pi-pencil" severity="secondary" rounded size="small" v-tooltip.top="'编辑'"
                @click="openEditDialog(item)" />
              <Button icon="pi pi-trash" severity="danger" rounded size="small" v-tooltip.top="'删除'"
                :disabled="item.doc_count > 0" @click="confirmDelete($event, item)" />
            </div>
          </div>
        </div>
      </template>
      <template #empty>
        <div class="empty-state">
          <i class="pi pi-database" style="font-size: 48px; color: #d0d5dd; margin-bottom: 16px"></i>
          <p class="empty-text">{{ loading ? '加载中...' : '暂无知识库，点击上方按钮添加' }}</p>
        </div>
      </template>
    </DataView>

    <!-- 添加对话框 -->
    <Dialog v-model:visible="addDialogVisible" header="添加知识库" :modal="true" :style="{ width: '800px' }"
      :draggable="false">
      <div class="dialog-form">
        <div class="form-row">
          <div class="field">
            <label class="field-label">知识库名称 <span style="color:red">*</span></label>
            <InputText v-model="addForm.name" placeholder="字母、数字、下划线，数字不能开头" class="field-input"
              @input="validateName" />
            <small v-if="nameError" style="color:red">{{ nameError }}</small>
          </div>
          <div class="field">
            <label class="field-label">知识库描述</label>
            <InputText v-model="addForm.rag_desc" placeholder="知识库描述（选填）" class="field-input" />
          </div>
        </div>
        <div class="form-row">
          <div class="field">
            <label class="field-label">分段大小</label>
            <InputNumber v-model="addForm.chunk_size" :min="1" :max="10000" class="field-input" />
          </div>
          <div class="field">
            <label class="field-label">重叠大小</label>
            <InputNumber v-model="addForm.overlap_size" :min="0" :max="1000" class="field-input" />
          </div>
        </div>
        <div class="form-row">
          <div class="field">
            <label class="field-label">嵌入维度</label>
            <InputNumber v-model="addForm.dimension_size" :min="1" :max="10000" class="field-input" />
          </div>
          <div class="field">
            <label class="field-label">嵌入模型 <span style="color:red">*</span></label>
            <Select v-model="addForm.embedding_model_id" :options="embeddingOptions" optionLabel="model_name"
              optionValue="id" placeholder="选择嵌入模型" class="field-input" :loading="embeddingLoading" />
          </div>
        </div>
        <div class="form-row">
          <div class="field">
            <label class="field-label">Reranker 模型 <span style="color:red">*</span></label>
            <Select v-model="addForm.reranker_model_id" :options="rerankerOptions" optionLabel="model_name"
              optionValue="id" placeholder="选择 Reranker 模型" class="field-input" :loading="rerankerLoading" />
          </div>
        </div>
        <div class="dialog-actions">
          <Button label="取消" severity="secondary" outlined @click="addDialogVisible = false" />
          <Button label="确定" @click="handleAdd" :loading="addLoading" :disabled="!!nameError || !addForm.name" />
        </div>
      </div>
    </Dialog>

    <!-- 编辑对话框 -->
    <Dialog v-model:visible="editDialogVisible" header="编辑知识库" :modal="true" :style="{ width: '600px' }"
      :draggable="false">
      <div class="dialog-form">
        <div class="form-row">
          <div class="field">
            <label class="field-label">知识库名称</label>
            <InputText :value="editForm.name" disabled class="field-input" />
          </div>
        </div>
        <div class="form-row">
          <div class="field">
            <label class="field-label">知识库描述</label>
            <InputText v-model="editForm.rag_desc" placeholder="修改知识库描述" class="field-input" />
          </div>
        </div>
        <div class="form-row">
          <div class="field">
            <label class="field-label">分段大小</label>
            <InputNumber :value="editForm.chunk_size" disabled class="field-input" />
          </div>
          <div class="field">
            <label class="field-label">重叠大小</label>
            <InputNumber :value="editForm.overlap_size" disabled class="field-input" />
          </div>
        </div>
        <div class="form-row">
          <div class="field">
            <label class="field-label">嵌入模型</label>
            <InputText :value="editForm.embedding_model_name" disabled class="field-input" />
          </div>
          <div class="field">
            <label class="field-label">Reranker 模型</label>
            <InputText :value="editForm.reranker_model_name" disabled class="field-input" />
          </div>
        </div>
        <div class="dialog-actions">
          <Button label="取消" severity="secondary" outlined @click="editDialogVisible = false" />
          <Button label="保存" @click="handleUpdate" :loading="updateLoading" />
        </div>
      </div>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import DataView from 'primevue/dataview'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import InputNumber from 'primevue/inputnumber'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import Select from 'primevue/select'
import Dialog from 'primevue/dialog'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:6880'
const userId = Number(localStorage.getItem('user_id'))

const confirm = useConfirm()
const toast = useToast()

// ========== 数据类型 ==========
interface RagItem {
  id: number
  user_id: number
  name: string
  rag_desc: string
  chunk_size: number
  overlap_size: number
  dimension_size: number
  embedding_model_id: number
  embedding_model_name: string
  reranker_model_id: number
  reranker_model_name: string
  doc_count: number
  created_at: string
  updated_at: string
}

interface AiModelOption {
  id: number
  model_name: string
}

// ========== 列表加载 ==========
const items = ref<RagItem[]>([])
const loading = ref(false)
const total = ref(0)
const pageNum = ref(1)
const pageSize = ref(10)

onMounted(() => {
  fetchList()
})

async function fetchList() {
  loading.value = true
  try {
    const params = new URLSearchParams({
      user_id: String(userId),
      pageNum: String(pageNum.value),
      pageSize: String(pageSize.value),
    })
    if (searchQuery.value.trim()) {
      params.set('keywords', searchQuery.value.trim())
    }
    const res = await fetch(`${API_BASE_URL}/api/v1/rag/list?${params}`)
    const body = await res.json()
    if (body.code === 0 && body.result) {
      items.value = body.result.items || []
      total.value = body.result.total || 0
    } else {
      toast.add({ severity: 'error', summary: '加载失败', detail: body.message || '请求异常', life: 3000 })
    }
  } catch (e: any) {
    toast.add({ severity: 'error', summary: '网络错误', detail: e.message, life: 3000 })
  } finally {
    loading.value = false
  }
}

function onPage(event: any) {
  pageNum.value = Math.floor(event.first / event.rows) + 1
  pageSize.value = event.rows
  fetchList()
}

// ========== 搜索 ==========
const searchQuery = ref('')

function handleSearch() {
  pageNum.value = 1
  fetchList()
}

// ========== 模型选项加载 ==========
const embeddingOptions = ref<AiModelOption[]>([])
const rerankerOptions = ref<AiModelOption[]>([])
const embeddingLoading = ref(false)
const rerankerLoading = ref(false)

async function loadModelOptions() {
  embeddingLoading.value = true
  rerankerLoading.value = true
  try {
    const [embedRes, rerankRes] = await Promise.all([
      fetch(`${API_BASE_URL}/api/v1/aimodel/options-by-type?user_id=${userId}&model_type=EMBEDDING`),
      fetch(`${API_BASE_URL}/api/v1/aimodel/options-by-type?user_id=${userId}&model_type=RERANKER`),
    ])
    const embedBody = await embedRes.json()
    const rerankBody = await rerankRes.json()
    if (embedBody.code === 0) embeddingOptions.value = embedBody.result || []
    if (rerankBody.code === 0) rerankerOptions.value = rerankBody.result || []
  } catch (e: any) {
    console.warn('加载模型选项失败:', e)
  } finally {
    embeddingLoading.value = false
    rerankerLoading.value = false
  }
}

// ========== 添加对话框 ==========
const addDialogVisible = ref(false)
const addLoading = ref(false)
const nameError = ref('')

const addForm = ref({
  name: '',
  rag_desc: '',
  chunk_size: 500,
  overlap_size: 50,
  dimension_size: 1024,
  embedding_model_id: null as number | null,
  reranker_model_id: null as number | null,
})

function validateName() {
  const v = addForm.value.name
  if (!v) {
    nameError.value = ''
    return
  }
  if (/^\d/.test(v)) {
    nameError.value = '名称不能以数字开头'
    return
  }
  if (!/^[a-zA-Z0-9_]+$/.test(v)) {
    nameError.value = '只能包含字母、数字、下划线'
    return
  }
  nameError.value = ''
}

function openAddDialog() {
  addForm.value = { name: '', rag_desc: '', chunk_size: 500, overlap_size: 50, dimension_size: 1024, embedding_model_id: null, reranker_model_id: null }
  nameError.value = ''
  loadModelOptions()
  addDialogVisible.value = true
}

async function handleAdd() {
  if (!addForm.value.name || nameError.value) return
  if (!addForm.value.embedding_model_id || !addForm.value.reranker_model_id) {
    toast.add({ severity: 'warn', summary: '请选择', detail: '请选择嵌入模型和 Reranker 模型', life: 3000 })
    return
  }

  addLoading.value = true
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/rag/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        name: addForm.value.name,
        rag_desc: addForm.value.rag_desc,
        chunk_size: addForm.value.chunk_size,
        overlap_size: addForm.value.overlap_size,
        dimension_size: addForm.value.dimension_size,
        embedding_model_id: addForm.value.embedding_model_id,
        reranker_model_id: addForm.value.reranker_model_id,
      }),
    })
    const body = await res.json()
    if (body.code !== 0) {
      toast.add({ severity: 'error', summary: '创建失败', detail: body.detail || body.message, life: 3000 })
      return
    }
    toast.add({ severity: 'success', summary: '创建成功', detail: `知识库「${addForm.value.name}」已创建`, life: 2000 })
    addDialogVisible.value = false
    pageNum.value = 1
    await fetchList()
  } catch (e: any) {
    toast.add({ severity: 'error', summary: '网络错误', detail: e.message, life: 3000 })
  } finally {
    addLoading.value = false
  }
}

// ========== 编辑对话框 ==========
const editDialogVisible = ref(false)
const updateLoading = ref(false)
const editForm = ref({
  id: 0,
  name: '',
  rag_desc: '',
  chunk_size: 0,
  overlap_size: 0,
  dimension_size: 0,
  embedding_model_name: '',
  reranker_model_name: '',
})

function openEditDialog(item: RagItem) {
  editForm.value = {
    id: item.id,
    name: item.name,
    rag_desc: item.rag_desc,
    chunk_size: item.chunk_size,
    overlap_size: item.overlap_size,
    dimension_size: item.dimension_size,
    embedding_model_name: item.embedding_model_name,
    reranker_model_name: item.reranker_model_name,
  }
  editDialogVisible.value = true
}

async function handleUpdate() {
  updateLoading.value = true
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/rag/update`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: editForm.value.id,
        user_id: userId,
        rag_desc: editForm.value.rag_desc,
      }),
    })
    const body = await res.json()
    if (body.code !== 0) {
      toast.add({ severity: 'error', summary: '更新失败', detail: body.detail || body.message, life: 3000 })
      return
    }
    toast.add({ severity: 'success', summary: '更新成功', detail: '描述已更新', life: 2000 })
    editDialogVisible.value = false
    await fetchList()
  } catch (e: any) {
    toast.add({ severity: 'error', summary: '网络错误', detail: e.message, life: 3000 })
  } finally {
    updateLoading.value = false
  }
}

// ========== 删除 ==========
function confirmDelete(event: MouseEvent, item: RagItem) {
  confirm.require({
    target: event.currentTarget as HTMLElement,
    message: `确定要删除知识库「${item.name}」吗？`,
    icon: 'pi pi-exclamation-triangle',
    rejectProps: {
      label: '取消',
      severity: 'secondary',
      outlined: true,
    },
    acceptProps: {
      label: '删除',
      severity: 'danger',
    },
    accept: async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/v1/rag/delete`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: item.id, user_id: userId }),
        })
        const body = await res.json()
        if (body.code !== 0) {
          toast.add({ severity: 'error', summary: '删除失败', detail: body.detail || body.message, life: 3000 })
          return
        }
        items.value = items.value.filter(i => i.id !== item.id)
        total.value--
        toast.add({ severity: 'success', summary: '删除成功', detail: `${item.name} 已删除`, life: 2000 })
      } catch (e: any) {
        toast.add({ severity: 'error', summary: '网络错误', detail: e.message, life: 3000 })
      }
    },
  })
}
</script>

<style scoped>
.rag-layout {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px 0;
  height: 100%;
  overflow: auto;
}

.rag-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 16px;
}

.rag-toolbar-left {
  display: flex;
  gap: 8px;
}

.search-area {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.search-area :deep(.p-inputtext) {
  font-size: 14px;
  padding: 10px 12px 10px 36px;
  width: 280px;
  border-radius: 8px;
  border: 1px solid #e5e5e5;
  transition: all 0.15s ease;
  background: #f8f9fa;
}

.search-area :deep(.p-inputtext:hover) {
  border-color: #ccc;
  background: #fff;
}

.search-area :deep(.p-inputtext:focus) {
  border-color: #333;
  box-shadow: none;
  background: #fff;
}

.search-area :deep(.p-inputicon) {
  font-size: 14px;
  color: #999;
  left: 12px;
}

/* ========== DataView ========== */
.rag-dataview {
  flex: 1;
  padding: 12px;
}

.rag-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  padding: 14px;
}

.rag-card {
  background: #fff;
  border: 1px solid #eee;
  border-radius: 10px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: box-shadow 0.15s ease;
}

.rag-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.rag-card-name {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rag-card-desc {
  font-size: 12px;
  color: #888;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 36px;
}

/* 参数信息 */
.rag-card-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px 0;
  border-top: 1px solid #f0f0f0;
}

.meta-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.meta-label {
  font-size: 11px;
  color: #aaa;
}

.meta-value {
  font-size: 11px;
  color: #666;
}

/* 操作按钮 */
.rag-card-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  padding-top: 4px;
  border-top: 1px solid #f0f0f0;
}

/* ========== 对话框表单 ========== */
.dialog-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-row {
  display: flex;
  gap: 16px;
}

.field {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 13px;
  font-weight: 500;
  color: #333;
}

.field-input {
  width: 100%;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 8px;
}

/* ========== 空状态 ========== */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 0;
}

.empty-text {
  font-size: 16px;
  color: #999;
  margin: 0;
}
</style>
```

- [ ] **Step 2: Modify ResourcePage.vue** — add RagTab import and tab

```vue
<!-- Add tab after knowledge-base tab -->
<Tab value="knowledge-base">文件管理</Tab>
<Tab value="rag">知识库</Tab>

<!-- Add RagTab panel -->
<TabPanel value="knowledge-base">
  <FileManagementTab />
</TabPanel>
<TabPanel value="rag">
  <RagTab />
</TabPanel>
```

Import:
```typescript
import RagTab from './RagTab.vue'
```

- [ ] **Step 3: Commit frontend**

```bash
git add packages/guineapig-client/src/renderer-overlay/views/RagTab.vue \
       packages/guineapig-client/src/renderer-overlay/views/ResourcePage.vue
git commit -m "feat: 前端知识库管理 RagTab 组件 + ResourcePage 集成"
```
