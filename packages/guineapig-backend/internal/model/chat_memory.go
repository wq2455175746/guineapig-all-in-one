package model

import (
	"context"
	"guineapig/internal/request"
	"guineapig/pkg/plugin"
	"time"
)

var MChatMemory = &ChatMemory{}

type ChatMemory struct {
	Id               int64      `gorm:"column:id;primaryKey;autoIncrement"`
	Name             string     `gorm:"column:name"`
	UserId           int64      `gorm:"column:user_id"`
	ConversationIds  *string    `gorm:"column:conversation_ids"`
	Mem              string     `gorm:"column:mem"`
	MemType          string     `gorm:"column:mem_type"`
	TimeRangeStartAt *time.Time `gorm:"column:time_range_start_at"`
	TimeRangeEndAt   *time.Time `gorm:"column:time_range_end_at"`
	SourceMsgCount   int        `gorm:"column:source_msg_count"`
	Version          int        `gorm:"column:version"`
	IsActive         int8       `gorm:"column:is_active"`
	ExpireAt         *time.Time `gorm:"column:expire_at"`
	ConfidenceScore  *int8      `gorm:"column:confidence_score"`
	CreatedBy        *string    `gorm:"column:created_by"`
	CreatedAt        time.Time  `gorm:"column:created_at"`
	UpdatedBy        *string    `gorm:"column:updated_by"`
	UpdatedAt        time.Time  `gorm:"column:updated_at"`
	DeletedAt        *int       `gorm:"column:deleted_at"`
}

func (*ChatMemory) TableName() string {
	return "chat_memory"
}

func (m *ChatMemory) Delete(ctx context.Context, id int64, userId int64) error {
	now := int(time.Now().Unix())
	return plugin.GetDB(ctx).Model(&ChatMemory{}).
		Where("id = ? AND user_id = ? AND deleted_at IS NULL", id, userId).
		Update("deleted_at", now).Error
}

func (*ChatMemory) FindById(ctx context.Context, id int64) (*ChatMemory, error) {
	var m ChatMemory
	err := plugin.GetDB(ctx).Where("id = ? AND deleted_at IS NULL", id).First(&m).Error
	if err != nil {
		return nil, err
	}
	return &m, nil
}

func (*ChatMemory) List(ctx context.Context, req *request.MemoryListRequest) ([]*ChatMemory, int64, error) {
	query := plugin.GetDB(ctx).Model(&ChatMemory{}).Where("deleted_at IS NULL")

	if req.UserId > 0 {
		query = query.Where("user_id = ?", req.UserId)
	}
	if req.Keywords != "" {
		searchKey := "%" + req.Keywords + "%"
		query = query.Where("(name LIKE ? OR mem_type LIKE ?)", searchKey, searchKey)
	}

	var total int64
	if err := query.Count(&total).Error; err != nil {
		return nil, 0, err
	}

	pageSize := req.PageSize
	pageNum := req.PageNum
	if pageSize <= 0 {
		pageSize = 10
	}
	if pageNum <= 0 {
		pageNum = 1
	}
	offset := (pageNum - 1) * pageSize
	query = query.Offset(offset).Limit(pageSize).Order("id desc")

	var items []*ChatMemory
	if err := query.Find(&items).Error; err != nil {
		return nil, 0, err
	}
	return items, total, nil
}

func (*ChatMemory) CreatePlaceholder(ctx context.Context, userId int64, memType string, timeRangeStart, timeRangeEnd time.Time) (int64, error) {
	now := time.Now()
	m := &ChatMemory{
		Name:             "记忆归纳中...",
		UserId:           userId,
		ConversationIds:  nil,
		Mem:              "",
		MemType:          memType,
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

// ListRecentActive 查询用户过去 days 天内的活跃记忆（排除空内容占位记录）
func (*ChatMemory) ListRecentActive(ctx context.Context, userId int64, days int) ([]*ChatMemory, error) {
	startTime := time.Now().AddDate(0, 0, -days)
	var items []*ChatMemory
	err := plugin.GetDB(ctx).Model(&ChatMemory{}).
		Where("user_id = ? AND deleted_at IS NULL AND is_active = 1 AND mem != '' AND created_at >= ?", userId, startTime).
		Order("created_at DESC").
		Find(&items).Error
	if err != nil {
		return nil, err
	}
	return items, nil
}

func (*ChatMemory) UpdateContent(ctx context.Context, req *request.MemoryUpdateContentRequest) error {
	now := time.Now()
	updates := map[string]any{
		"name":                req.Name,
		"mem":                 req.Mem,
		"mem_type":            req.MemType,
		"conversation_ids": func() any {
			if req.ConversationIds == "" {
				return nil
			}
			return req.ConversationIds
		}(),
		"source_msg_count":    req.SourceMsgCount,
		"time_range_start_at": req.TimeRangeStartAt,
		"time_range_end_at":   req.TimeRangeEndAt,
		"updated_at":          now,
	}
	return plugin.GetDB(ctx).Model(&ChatMemory{}).
		Where("id = ? AND deleted_at IS NULL", req.Id).
		Updates(updates).Error
}
