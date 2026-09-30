package service

import (
	"context"
	"testing"

	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
	"guineapig/internal/model"
	"guineapig/internal/request"
	"guineapig/pkg/plugin"
)

func TestSendChatMessageReuseConversationUpdatesModelId(t *testing.T) {
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	if err := db.AutoMigrate(&model.ChatConversation{}, &model.ChatMessage{}); err != nil {
		t.Fatalf("automigrate: %v", err)
	}
	plugin.DB = db
	ctx := context.Background()

	const userID = int64(2070049592501604352)

	// 模拟"旧模型已删除，会话仍引用其 id"的场景
	conv := &model.ChatConversation{
		UserId:  userID,
		Title:   "stale-model-conv",
		ModelId: 5,
		Status:  "active",
	}
	if err := conv.Create(ctx); err != nil {
		t.Fatalf("create conversation: %v", err)
	}

	// 复用该会话发送消息，当前选择的模型为 6
	_, err = SendChatMessage(ctx, &request.ChatSendRequest{
		UserId:         userID,
		ModelId:        6,
		ConversationId: conv.Id,
		Content:        "hi",
	})
	if err != nil {
		t.Fatalf("send chat message: %v", err)
	}

	var reloaded model.ChatConversation
	if err := db.Where("id = ?", conv.Id).First(&reloaded).Error; err != nil {
		t.Fatalf("reload conversation: %v", err)
	}
	if reloaded.ModelId != 6 {
		t.Fatalf("expected conversation.model_id updated to 6, got %d", reloaded.ModelId)
	}
}
