package model

import (
	"context"
	"guineapig/pkg/plugin"
	"time"
)

var MChatMessage = &ChatMessage{}

type ChatMessage struct {
	Id              int64     `gorm:"column:id;primaryKey;autoIncrement"`
	ConversationId  int64     `gorm:"column:conversation_id"`
	Role            string    `gorm:"column:role"`
	Content         string    `gorm:"column:content"`
	Attachments     *string   `gorm:"column:attachments"`
	Commands        *string   `gorm:"column:commands"`
	Status          string    `gorm:"column:status"`
	ErrorMessage    string    `gorm:"column:error_message"`
	TokenUsage      int       `gorm:"column:token_usage"`
	ResponseTimeMs  int       `gorm:"column:response_time_ms"`
	ParentMessageId int64     `gorm:"column:parent_message_id"`
	Version         int       `gorm:"column:version"`
	CreatedAt       time.Time `gorm:"column:created_at"`
	UpdatedAt       time.Time `gorm:"column:updated_at"`
}

func (*ChatMessage) TableName() string {
	return "chat_messages"
}

func (m *ChatMessage) Create(ctx context.Context) error {
	m.CreatedAt = time.Now()
	m.UpdatedAt = time.Now()
	return plugin.GetDB(ctx).Create(m).Error
}

func (m *ChatMessage) UpdateCommands(ctx context.Context, id int64, commands *string) error {
	return plugin.GetDB(ctx).Model(&ChatMessage{}).
		Where("id = ?", id).
		Update("commands", commands).Error
}
