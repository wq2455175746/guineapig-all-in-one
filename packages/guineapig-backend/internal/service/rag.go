package service

import (
	"context"
	"encoding/json"
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
		UserId:             req.UserId,
		Name:               req.Name,
		RagDesc:            req.RagDesc,
		ChunkSize:          chunkSize,
		OverlapSize:        overlapSize,
		DimensionSize:      dimensionSize,
		EmbeddingModelId:   req.EmbeddingModelId,
		EmbeddingModelName: embeddingModel.ModelName,
		RerankerModelId:    req.RerankerModelId,
		RerankerModelName:  rerankerModel.ModelName,
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

func ListRag(ctx context.Context, req *request.RagListRequest) (*response.RagListResponse, error) {
	items, total, err := model.MResRags.List(ctx, req)
	if err != nil {
		return nil, err
	}

	resItems := make([]response.RagItem, 0, len(items))
	for _, item := range items {
		ragMetadata := ""
		if item.RagMetadata != nil {
			ragMetadata = *item.RagMetadata
		}
		resItems = append(resItems, response.RagItem{
			Id:                 item.Id,
			UserId:             item.UserId,
			Name:               item.Name,
			RagDesc:            item.RagDesc,
			RagMetadata:        ragMetadata,
			ChunkSize:          item.ChunkSize,
			OverlapSize:        item.OverlapSize,
			DimensionSize:      item.DimensionSize,
			EmbeddingModelId:   item.EmbeddingModelId,
			EmbeddingModelName: item.EmbeddingModelName,
			RerankerModelId:    item.RerankerModelId,
			RerankerModelName:  item.RerankerModelName,
			DocCount:           item.DocCount,
			CreatedAt:          item.CreatedAt.Format("2006-01-02 15:04:05"),
			UpdatedAt:          item.UpdatedAt.Format("2006-01-02 15:04:05"),
		})
	}

	return &response.RagListResponse{
		Items: resItems,
		Total: total,
	}, nil
}
