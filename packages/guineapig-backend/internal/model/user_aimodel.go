package model

import (
	"context"
	"errors"
	"guineapig/internal/request"
	"guineapig/pkg/plugin"
	"time"

	"gorm.io/gorm"
)

var MUserAiModel = &UserAiModel{}

type UserAiModel struct {
	Id           int64     `gorm:"column:id;primaryKey;autoIncrement"`
	UserId       int64     `gorm:"column:user_id"`
	ModelCode    string    `gorm:"column:model_code"`
	ModelName    string    `gorm:"column:model_name"`
	MaxTokens    int       `gorm:"column:max_tokens;default:8192"`
	ApiUrl       string    `gorm:"column:api_url"`
	ApiKey       string    `gorm:"column:api_key"`
	ProviderCode string    `gorm:"column:provider_code"`
	ModelType    string    `gorm:"column:model_type"`
	Established  int8      `gorm:"column:established"`
	Status       int8      `gorm:"column:status"`
	CreatedBy    string    `gorm:"column:created_by"`
	CreatedAt    time.Time `gorm:"column:created_at"`
	UpdatedBy    string    `gorm:"column:updated_by"`
	UpdatedAt    time.Time `gorm:"column:updated_at"`
	DeletedAt    *int64    `gorm:"column:deleted_at"`
}

func (*UserAiModel) TableName() string {
	return "user_aimodel"
}

func (m *UserAiModel) Create(ctx context.Context) error {
	m.CreatedAt = time.Now()
	m.UpdatedAt = time.Now()
	return plugin.GetDB(ctx).Create(m).Error
}

func (m *UserAiModel) Update(ctx context.Context) error {
	m.UpdatedAt = time.Now()

	// 使用 map 而不是 struct，确保 status=0 等零值字段也能更新到数据库
	updates := map[string]any{
		"model_name":    m.ModelName,
		"max_tokens":    m.MaxTokens,
		"api_url":       m.ApiUrl,
		"provider_code": m.ProviderCode,
		"model_type":    m.ModelType,
		"status":        m.Status,
		"established":   m.Established,
		"updated_at":    m.UpdatedAt,
	}
	// api_key 只在非空时才包含（前端不修改密钥时不发送，避免覆盖已存储的加密密钥）
	if m.ApiKey != "" {
		updates["api_key"] = m.ApiKey
	}

	return plugin.GetDB(ctx).Model(m).Where("id = ? AND deleted_at IS NULL", m.Id).Updates(updates).Error
}

// UpdateField 更新指定模型的单个字段
func (*UserAiModel) UpdateField(ctx context.Context, id int64, field string, value any) error {
	return plugin.GetDB(ctx).Model(&UserAiModel{}).Where("id = ? AND deleted_at IS NULL", id).
		Update(field, value).Error
}

func (*UserAiModel) Delete(ctx context.Context, id int64, userId int64) error {
	now := time.Now().Unix()
	return plugin.GetDB(ctx).Model(&UserAiModel{}).Where("id = ? AND user_id = ? AND deleted_at IS NULL", id, userId).
		Update("deleted_at", now).Error
}

func (*UserAiModel) FindById(ctx context.Context, id int64) (*UserAiModel, error) {
	var m UserAiModel
	err := plugin.GetDB(ctx).Where("id = ? AND deleted_at IS NULL", id).First(&m).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, err
	}
	return &m, nil
}

// ListOptionsByType 查询指定用户下指定类型的可用模型列表（status=1 AND established=1）
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

// ListOptions 查询指定用户下 status=1 AND established=1 的模型列表，用于聊天下拉选择
func (*UserAiModel) ListOptions(ctx context.Context, userId int64) ([]*UserAiModel, error) {
	var items []*UserAiModel
	err := plugin.GetDB(ctx).Model(&UserAiModel{}).
		Where("user_id = ? AND status = 1 AND established = 1 AND deleted_at IS NULL", userId).
		Order("id asc").
		Find(&items).Error
	return items, err
}

func (*UserAiModel) List(ctx context.Context, req *request.AiModelListRequest) ([]*UserAiModel, int64, error) {
	query := plugin.GetDB(ctx).Model(&UserAiModel{}).Where("deleted_at IS NULL")

	if req.UserId > 0 {
		query = query.Where("user_id = ?", req.UserId)
	}

	if req.Keywords != "" {
		searchKey := "%" + req.Keywords + "%"
		query = query.Where("(model_code LIKE ? OR api_url LIKE ? OR provider_code LIKE ?)", searchKey, searchKey, searchKey)
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

	var items []*UserAiModel
	if err := query.Find(&items).Error; err != nil {
		return nil, 0, err
	}

	return items, total, nil
}
