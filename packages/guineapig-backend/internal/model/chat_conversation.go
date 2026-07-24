package model

import (
	"context"
	"guineapig/pkg/plugin"
	"time"
)

var MChatConversation = &ChatConversation{}

type ChatConversation struct {
	Id           int64      `gorm:"column:id;primaryKey;autoIncrement"`
	UserId       int64      `gorm:"column:user_id"`
	Title        string     `gorm:"column:title"`
	ModelId      int64      `gorm:"column:model_id"`
	SystemPrompt string     `gorm:"column:system_prompt"`
	Source       string     `gorm:"column:source"`      // client | feishu | wechat | dingtalk
	ExtChatId    string     `gorm:"column:ext_chat_id"` // 外部 IM 平台会话 ID
	Status       string     `gorm:"column:status"`
	MessageCount int        `gorm:"column:message_count"`
	StartAt      *time.Time `gorm:"column:start_at"`
	EndAt        *time.Time `gorm:"column:end_at"`
	CreatedAt    time.Time  `gorm:"column:created_at"`
	UpdatedAt    time.Time  `gorm:"column:updated_at"`
}

func (*ChatConversation) TableName() string {
	return "chat_conversations"
}

func (m *ChatConversation) Create(ctx context.Context) error {
	m.CreatedAt = time.Now()
	m.UpdatedAt = time.Now()
	return plugin.GetDB(ctx).Create(m).Error
}

func (*ChatConversation) FindById(ctx context.Context, id int64) (*ChatConversation, error) {
	var m ChatConversation
	err := plugin.GetDB(ctx).Where("id = ?", id).First(&m).Error
	if err != nil {
		return nil, err
	}
	return &m, nil
}
