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

func setupEstablishedTest(t *testing.T) {
	t.Helper()
	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	if err := db.AutoMigrate(&model.UserAiModel{}); err != nil {
		t.Fatalf("automigrate: %v", err)
	}
	plugin.DB = db
}

func TestCreateAiModelSetsEstablishedToOne(t *testing.T) {
	setupEstablishedTest(t)
	ctx := context.Background()

	resp, err := CreateAiModel(ctx, &request.AiModelCreateRequest{
		UserId:       2070049592501604352,
		ModelName:    "new-model",
		ApiUrl:       "http://localhost:8201/",
		ApiKey:       "test-key",
		ProviderCode: "Vllm",
		ModelType:    "LLM",
	})
	if err != nil {
		t.Fatalf("create: %v", err)
	}

	var row model.UserAiModel
	if err := plugin.DB.WithContext(ctx).Where("id = ?", resp.Id).First(&row).Error; err != nil {
		t.Fatalf("find row: %v", err)
	}
	if row.Established != 1 {
		t.Fatalf("expected established=1 on create, got %d", row.Established)
	}
}

func TestCreateAiModelDefaultMaxTokens(t *testing.T) {
	setupEstablishedTest(t)
	ctx := context.Background()

	resp, err := CreateAiModel(ctx, &request.AiModelCreateRequest{
		UserId:       2070049592501604352,
		ModelName:    "default-max-tokens",
		ApiUrl:       "http://localhost:8201/",
		ApiKey:       "test-key",
		ProviderCode: "Vllm",
		ModelType:    "LLM",
	})
	if err != nil {
		t.Fatalf("create: %v", err)
	}

	var row model.UserAiModel
	if err := plugin.DB.WithContext(ctx).Where("id = ?", resp.Id).First(&row).Error; err != nil {
		t.Fatalf("find row: %v", err)
	}
	if row.MaxTokens != 4096 {
		t.Fatalf("expected default max_tokens=4096, got %d", row.MaxTokens)
	}
}

func TestCreateAiModelWithMaxTokens(t *testing.T) {
	setupEstablishedTest(t)
	ctx := context.Background()

	resp, err := CreateAiModel(ctx, &request.AiModelCreateRequest{
		UserId:       2070049592501604352,
		ModelName:    "custom-max-tokens",
		ApiUrl:       "http://localhost:8201/",
		ApiKey:       "test-key",
		ProviderCode: "Vllm",
		ModelType:    "LLM",
		MaxTokens:    2048,
	})
	if err != nil {
		t.Fatalf("create: %v", err)
	}

	var row model.UserAiModel
	if err := plugin.DB.WithContext(ctx).Where("id = ?", resp.Id).First(&row).Error; err != nil {
		t.Fatalf("find row: %v", err)
	}
	if row.MaxTokens != 2048 {
		t.Fatalf("expected max_tokens=2048, got %d", row.MaxTokens)
	}
}

func TestUpdateAiModelPreservesMaxTokensWhenOmitted(t *testing.T) {
	setupEstablishedTest(t)
	ctx := context.Background()

	resp, err := CreateAiModel(ctx, &request.AiModelCreateRequest{
		UserId:       2070049592501604352,
		ModelName:    "preserve-max-tokens",
		ApiUrl:       "http://localhost:8201/",
		ApiKey:       "test-key",
		ProviderCode: "Vllm",
		ModelType:    "LLM",
		MaxTokens:    4096,
	})
	if err != nil {
		t.Fatalf("create: %v", err)
	}

	err = UpdateAiModel(ctx, &request.AiModelUpdateRequest{
		Id:           resp.Id,
		UserId:       2070049592501604352,
		ModelName:    "preserve-max-tokens-2",
		ApiUrl:       "http://localhost:8201/",
		ProviderCode: "Vllm",
		ModelType:    "LLM",
	})
	if err != nil {
		t.Fatalf("update: %v", err)
	}

	var row model.UserAiModel
	if err := plugin.DB.WithContext(ctx).Where("id = ?", resp.Id).First(&row).Error; err != nil {
		t.Fatalf("find row: %v", err)
	}
	if row.MaxTokens != 4096 {
		t.Fatalf("expected max_tokens preserved as 4096, got %d", row.MaxTokens)
	}
}

func TestUpdateAiModelWithMaxTokens(t *testing.T) {
	setupEstablishedTest(t)
	ctx := context.Background()

	resp, err := CreateAiModel(ctx, &request.AiModelCreateRequest{
		UserId:       2070049592501604352,
		ModelName:    "update-max-tokens",
		ApiUrl:       "http://localhost:8201/",
		ApiKey:       "test-key",
		ProviderCode: "Vllm",
		ModelType:    "LLM",
		MaxTokens:    4096,
	})
	if err != nil {
		t.Fatalf("create: %v", err)
	}

	err = UpdateAiModel(ctx, &request.AiModelUpdateRequest{
		Id:           resp.Id,
		UserId:       2070049592501604352,
		ModelName:    "update-max-tokens-2",
		ApiUrl:       "http://localhost:8201/",
		ProviderCode: "Vllm",
		ModelType:    "LLM",
		MaxTokens:    2048,
	})
	if err != nil {
		t.Fatalf("update: %v", err)
	}

	var row model.UserAiModel
	if err := plugin.DB.WithContext(ctx).Where("id = ?", resp.Id).First(&row).Error; err != nil {
		t.Fatalf("find row: %v", err)
	}
	if row.MaxTokens != 2048 {
		t.Fatalf("expected max_tokens=2048 after update, got %d", row.MaxTokens)
	}
}

func TestUpdateAiModelPreservesEstablished(t *testing.T) {
	setupEstablishedTest(t)
	ctx := context.Background()

	resp, err := CreateAiModel(ctx, &request.AiModelCreateRequest{
		UserId:       2070049592501604352,
		ModelName:    "keep-status",
		ApiUrl:       "http://localhost:8201/",
		ApiKey:       "test-key",
		ProviderCode: "Vllm",
		ModelType:    "LLM",
	})
	if err != nil {
		t.Fatalf("create: %v", err)
	}

	// 编辑时不传 established，应保留原连通状态
	err = UpdateAiModel(ctx, &request.AiModelUpdateRequest{
		Id:           resp.Id,
		UserId:       2070049592501604352,
		ModelName:    "keep-status-2",
		ApiUrl:       "http://localhost:8201/",
		ProviderCode: "Vllm",
		ModelType:    "LLM",
	})
	if err != nil {
		t.Fatalf("update: %v", err)
	}

	var row model.UserAiModel
	if err := plugin.DB.WithContext(ctx).Where("id = ?", resp.Id).First(&row).Error; err != nil {
		t.Fatalf("find row: %v", err)
	}
	if row.Established != 1 {
		t.Fatalf("expected established preserved as 1, got %d", row.Established)
	}
}

func TestCreateAiModelWithSmallModelFlag(t *testing.T) {
	setupEstablishedTest(t)
	ctx := context.Background()

	resp, err := CreateAiModel(ctx, &request.AiModelCreateRequest{
		UserId:       2070049592501604352,
		ModelName:    "small-model",
		ApiUrl:       "http://localhost:8201/",
		ApiKey:       "test-key",
		ProviderCode: "Vllm",
		ModelType:    "LLM",
		IsSmallModel: 1,
	})
	if err != nil {
		t.Fatalf("create: %v", err)
	}

	var row model.UserAiModel
	if err := plugin.DB.WithContext(ctx).Where("id = ?", resp.Id).First(&row).Error; err != nil {
		t.Fatalf("find row: %v", err)
	}
	if row.IsSmallModel != 1 {
		t.Fatalf("expected is_small_model=1 on create, got %d", row.IsSmallModel)
	}
}

func TestUpdateAiModelSetsSmallModelFlag(t *testing.T) {
	setupEstablishedTest(t)
	ctx := context.Background()

	resp, err := CreateAiModel(ctx, &request.AiModelCreateRequest{
		UserId:       2070049592501604352,
		ModelName:    "toggle-small",
		ApiUrl:       "http://localhost:8201/",
		ApiKey:       "test-key",
		ProviderCode: "Vllm",
		ModelType:    "LLM",
	})
	if err != nil {
		t.Fatalf("create: %v", err)
	}

	// 编辑时打开小模型标记
	err = UpdateAiModel(ctx, &request.AiModelUpdateRequest{
		Id:           resp.Id,
		UserId:       2070049592501604352,
		ModelName:    "toggle-small-2",
		ApiUrl:       "http://localhost:8201/",
		ProviderCode: "Vllm",
		ModelType:    "LLM",
		IsSmallModel: 1,
	})
	if err != nil {
		t.Fatalf("update: %v", err)
	}

	var row model.UserAiModel
	if err := plugin.DB.WithContext(ctx).Where("id = ?", resp.Id).First(&row).Error; err != nil {
		t.Fatalf("find row: %v", err)
	}
	if row.IsSmallModel != 1 {
		t.Fatalf("expected is_small_model=1 after update, got %d", row.IsSmallModel)
	}
}
