package model

import (
	"context"
	"errors"
	"guineapig/internal/request"
	"guineapig/pkg/plugin"
	"time"

	"gorm.io/gorm"
)

var MResMcp = &ResMcp{}

type ResMcp struct {
	Id         int64     `gorm:"column:id;primaryKey;autoIncrement"`
	UserId     int64     `gorm:"column:user_id"`
	Name       string    `gorm:"column:name"`
	McpDesc    string    `gorm:"column:mcp_desc"`
	McpType    string    `gorm:"column:mcp_type"`
	McpBody      *string   `gorm:"column:mcp_body;type:json"`
	McpTools     *string   `gorm:"column:mcp_tools;type:json"`
	McpResources *string   `gorm:"column:mcp_resources;type:json"`
	McpPrompt    *string   `gorm:"column:mcp_prompt;type:json"`
	McpVersion   string    `gorm:"column:mcp_version"`
	ReqTimeout   int       `gorm:"column:req_timeout"`
	Status       int8      `gorm:"column:status"`
	CreatedBy  string    `gorm:"column:created_by"`
	CreatedAt  time.Time `gorm:"column:created_at"`
	UpdatedBy  string    `gorm:"column:updated_by"`
	UpdatedAt  time.Time `gorm:"column:updated_at"`
	DeletedAt  *int64    `gorm:"column:deleted_at"`
}

func (*ResMcp) TableName() string {
	return "res_mcps"
}

func (m *ResMcp) Create(ctx context.Context) error {
	m.CreatedAt = time.Now()
	m.UpdatedAt = time.Now()
	return plugin.GetDB(ctx).Create(m).Error
}

func (m *ResMcp) Update(ctx context.Context) error {
	m.UpdatedAt = time.Now()

	updates := map[string]any{
		"updated_at":  m.UpdatedAt,
	}

	if m.Name != "" {
		updates["name"] = m.Name
	}
	if m.McpDesc != "" {
		updates["mcp_desc"] = m.McpDesc
	}
	if m.McpType != "" {
		updates["mcp_type"] = m.McpType
	}
	if m.McpBody != nil {
		updates["mcp_body"] = *m.McpBody
	}
	if m.McpTools != nil {
		updates["mcp_tools"] = *m.McpTools
	}
	if m.McpResources != nil {
		updates["mcp_resources"] = *m.McpResources
	}
	if m.McpPrompt != nil {
		updates["mcp_prompt"] = *m.McpPrompt
	}
	if m.McpVersion != "" {
		updates["mcp_version"] = m.McpVersion
	}
	if m.ReqTimeout > 0 {
		updates["req_timeout"] = m.ReqTimeout
	}
	// status 允许 0 或 1，只有当明确设置时才更新
	updates["status"] = m.Status

	return plugin.GetDB(ctx).Model(m).Where("id = ? AND deleted_at IS NULL", m.Id).Updates(updates).Error
}

func (*ResMcp) Delete(ctx context.Context, id int64, userId int64) error {
	now := time.Now().Unix()
	return plugin.GetDB(ctx).Model(&ResMcp{}).Where("id = ? AND user_id = ? AND deleted_at IS NULL", id, userId).
		Update("deleted_at", now).Error
}

func (*ResMcp) FindById(ctx context.Context, id int64) (*ResMcp, error) {
	var m ResMcp
	err := plugin.GetDB(ctx).Where("id = ? AND deleted_at IS NULL", id).First(&m).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, err
	}
	return &m, nil
}

func (*ResMcp) List(ctx context.Context, req *request.McpListRequest) ([]*ResMcp, int64, error) {
	query := plugin.GetDB(ctx).Model(&ResMcp{}).Where("deleted_at IS NULL")

	if req.UserId > 0 {
		query = query.Where("user_id = ?", req.UserId)
	}

	if req.Keywords != "" {
		searchKey := "%" + req.Keywords + "%"
		query = query.Where("(name LIKE ? OR `mcp_desc` LIKE ?)", searchKey, searchKey)
	}

	var total int64
	if err := query.Count(&total).Error; err != nil {
		return nil, 0, err
	}

	if req.PageSize > 0 && req.PageNum > 0 {
		offset := (req.PageNum - 1) * req.PageSize
		query = query.Offset(offset).Limit(req.PageSize)
	} else {
		query = query.Limit(MaxListLimit)
	}

	query = query.Order("id desc")

	var items []*ResMcp
	if err := query.Find(&items).Error; err != nil {
		return nil, 0, err
	}

	return items, total, nil
}

// FindByUserIdAndName 检查同名 mcp 是否已存在
func (*ResMcp) FindByUserIdAndName(ctx context.Context, userId int64, name string) (*ResMcp, error) {
	var m ResMcp
	err := plugin.GetDB(ctx).Model(&ResMcp{}).
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
