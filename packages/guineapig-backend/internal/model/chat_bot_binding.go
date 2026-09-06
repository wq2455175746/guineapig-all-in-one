package model

import (
	"context"
	"errors"
	"guineapig/internal/request"
	"guineapig/pkg/plugin"
	"time"

	"gorm.io/gorm"
)

var MBotBinding = &BotBinding{}

type BotBinding struct {
	Id          int64     `gorm:"column:id;primaryKey;autoIncrement"`
	UserId      int64     `gorm:"column:user_id"`
	Platform    string    `gorm:"column:platform"`
	AppId       string    `gorm:"column:app_id"`
	AppSecret   string    `gorm:"column:app_secret"`
	TenantKey   string    `gorm:"column:tenant_key"`
	BotStatus   int       `gorm:"column:bot_status"`
	BotName     string    `gorm:"column:bot_name"`
	ExtraConfig *string   `gorm:"column:extra_config;type:json"`
	Description string    `gorm:"column:description"`
	CreatedBy   string    `gorm:"column:created_by"`
	CreatedAt   time.Time `gorm:"column:created_at"`
	UpdatedAt   time.Time `gorm:"column:updated_at"`
}

func (*BotBinding) TableName() string {
	return "chat_bot_binding"
}

// Create 创建绑定记录
func (m *BotBinding) Create(ctx context.Context) error {
	m.CreatedAt = time.Now()
	m.UpdatedAt = time.Now()
	return plugin.GetDB(ctx).Create(m).Error
}

// Update 更新绑定记录（map方式避免零值问题）
func (m *BotBinding) Update(ctx context.Context) error {
	m.UpdatedAt = time.Now()
	updates := map[string]any{
		"updated_at": m.UpdatedAt,
	}
	if m.AppSecret != "" {
		updates["app_secret"] = m.AppSecret
	}
	if m.TenantKey != "" {
		updates["tenant_key"] = m.TenantKey
	}
	if m.BotStatus != 0 {
		updates["bot_status"] = m.BotStatus
	}
	if m.BotName != "" {
		updates["bot_name"] = m.BotName
	}
	if m.ExtraConfig != nil {
		updates["extra_config"] = *m.ExtraConfig
	}
	if m.Description != "" {
		updates["description"] = m.Description
	}
	return plugin.GetDB(ctx).Model(m).Where("id = ?", m.Id).Updates(updates).Error
}

// UpdateStatus 单独更新连接状态
func (m *BotBinding) UpdateStatus(ctx context.Context, status int) error {
	return plugin.GetDB(ctx).Model(m).
		Where("id = ?", m.Id).
		Update("bot_status", status).
		Error
}

// Delete 删除绑定记录
func (*BotBinding) Delete(ctx context.Context, id int64) error {
	return plugin.GetDB(ctx).Delete(&BotBinding{}, id).Error
}

// FindById 按ID查找
func (*BotBinding) FindById(ctx context.Context, id int64) (*BotBinding, error) {
	var m BotBinding
	err := plugin.GetDB(ctx).First(&m, id).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, err
	}
	return &m, nil
}

// FindByUserAndPlatform 按用户+平台查找绑定
func (*BotBinding) FindByUserAndPlatform(ctx context.Context, userId int64, platform string) (*BotBinding, error) {
	var m BotBinding
	err := plugin.GetDB(ctx).
		Where("user_id = ? AND platform = ?", userId, platform).
		First(&m).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, err
	}
	return &m, nil
}

// FindByPlatformAndTenant 按平台+租户查找绑定（用于Bot收到消息时反向查找user_id）
func (*BotBinding) FindByPlatformAndTenant(ctx context.Context, platform string, tenantKey string) (*BotBinding, error) {
	var m BotBinding
	err := plugin.GetDB(ctx).
		Where("platform = ? AND tenant_key = ?", platform, tenantKey).
		First(&m).Error
	if err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return nil, nil
		}
		return nil, err
	}
	return &m, nil
}

// ListByUserId 列出用户的所有绑定
func (*BotBinding) ListByUserId(ctx context.Context, userId int64) ([]*BotBinding, error) {
	var items []*BotBinding
	query := plugin.GetDB(ctx).Model(&BotBinding{}).Order("id desc")
	if userId > 0 {
		query = query.Where("user_id = ?", userId)
	}
	err := query.Find(&items).Error
	return items, err
}

// List 分页查询绑定列表（管理后台用）
func (*BotBinding) List(ctx context.Context, req *request.BotBindingListRequest) ([]*BotBinding, int64, error) {
	query := plugin.GetDB(ctx).Model(&BotBinding{})

	if req.UserId > 0 {
		query = query.Where("user_id = ?", req.UserId)
	}
	if req.Platform != "" {
		query = query.Where("platform = ?", req.Platform)
	}
	if req.BotStatus > 0 {
		query = query.Where("bot_status = ?", req.BotStatus)
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

	var items []*BotBinding
	if err := query.Find(&items).Error; err != nil {
		return nil, 0, err
	}
	return items, total, nil
}
