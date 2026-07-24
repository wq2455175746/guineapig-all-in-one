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
	Id                 int64     `gorm:"column:id;primaryKey;autoIncrement"`
	UserId             int64     `gorm:"column:user_id"`
	Name               string    `gorm:"column:name"`
	RagDesc            string    `gorm:"column:rag_desc"`
	RagMetadata        *string   `gorm:"column:rag_metadata;type:json"`
	ChunkSize          int       `gorm:"column:chunk_size;default:500"`
	OverlapSize        int       `gorm:"column:overlap_size;default:50"`
	DimensionSize      int       `gorm:"column:dimension_size;default:1024"`
	EmbeddingModelId   int64     `gorm:"column:embedding_model_id"`
	EmbeddingModelName string   `gorm:"column:embedding_model_name"`
	RerankerModelId    int64     `gorm:"column:reranker_model_id"`
	RerankerModelName  string    `gorm:"column:reranker_model_name"`
	DocCount           int64     `gorm:"column:doc_count;default:0"`
	CreatedBy          string    `gorm:"column:created_by"`
	CreatedAt          time.Time `gorm:"column:created_at"`
	UpdatedBy          string    `gorm:"column:updated_by"`
	UpdatedAt          time.Time `gorm:"column:updated_at"`
	DeletedAt          *int64    `gorm:"column:deleted_at"`
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

func (*ResRags) UpdateRagMetadata(ctx context.Context, id int64, metadata string) error {
	updates := map[string]any{
		"rag_metadata": metadata,
		"updated_at":   time.Now(),
	}
	return plugin.GetDB(ctx).Model(&ResRags{}).Where("id = ? AND deleted_at IS NULL", id).
		Updates(updates).Error
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
