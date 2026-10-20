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

func TestSendChatMessageNewConversationSourceIsClient(t *testing.T) {
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

	resp, err := SendChatMessage(ctx, &request.ChatSendRequest{
		UserId:  userID,
		ModelId: 1,
		Content: "hello",
	})
	if err != nil {
		t.Fatalf("send chat message: %v", err)
	}

	var conv model.ChatConversation
	if err := db.Where("id = ?", resp.ConversationId).First(&conv).Error; err != nil {
		t.Fatalf("reload conversation: %v", err)
	}
	if conv.Source != "client" {
		t.Fatalf("expected conversation.source == 'client', got %q", conv.Source)
	}
}
