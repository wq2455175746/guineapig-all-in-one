package service

import (
	"context"
	"testing"

	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
	"guineapig/internal/model"
	"guineapig/pkg/plugin"
)

func setupSingleTurnTest(t *testing.T) *gorm.DB {
	t.Helper()
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	if err := db.AutoMigrate(&model.ChatConversation{}, &model.ChatMessage{}); err != nil {
		t.Fatalf("automigrate: %v", err)
	}
	plugin.DB = db
	return db
}

func TestBuildLLMMessagesSingleTurn(t *testing.T) {
	db := setupSingleTurnTest(t)
	ctx := context.Background()

	conv := &model.ChatConversation{
		Id:           1,
		UserId:       2070049592501604352,
		SystemPrompt: "你是一个有用的AI助手。",
	}
	if err := db.WithContext(ctx).Create(conv).Error; err != nil {
		t.Fatalf("create conv: %v", err)
	}

	// 多条历史消息
	for i, c := range []string{"第一条", "第二条", "第三条当前问题"} {
		msg := &model.ChatMessage{
			ConversationId: 1,
			Role:           "user",
			Content:        c,
			Status:         "completed",
			Version:        1,
		}
		if i == 1 {
			msg.Role = "assistant"
		}
		if err := db.WithContext(ctx).Create(msg).Error; err != nil {
			t.Fatalf("create msg: %v", err)
		}
	}

	// 大模型：完整历史
	full, err := buildLLMMessages(ctx, conv)
	if err != nil {
		t.Fatalf("buildLLMMessages full: %v", err)
	}
	if len(full) != 4 {
		t.Fatalf("expected 4 messages (sys+3 history), got %d: %v", len(full), full)
	}

	// 小模型：单轮，只保留 system + 最新用户消息
	single, err := buildLLMMessages(ctx, conv, true)
	if err != nil {
		t.Fatalf("buildLLMMessages single: %v", err)
	}
	if len(single) != 2 {
		t.Fatalf("expected 2 messages (sys+latest user), got %d: %v", len(single), single)
	}
	if single[0]["role"] != "system" {
		t.Fatalf("expected first role system, got %s", single[0]["role"])
	}
	if single[1]["role"] != "user" || single[1]["content"] != "第三条当前问题" {
		t.Fatalf("expected latest user message, got %v", single[1])
	}
}
