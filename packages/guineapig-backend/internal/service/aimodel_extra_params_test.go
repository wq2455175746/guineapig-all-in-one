package service

import (
	"context"
	"encoding/json"
	"testing"

	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
	"guineapig/internal/model"
	"guineapig/internal/request"
	"guineapig/pkg/plugin"
)

func setupExtraParamsTest(t *testing.T) {
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

func TestExtraParamsPassthrough(t *testing.T) {
	setupExtraParamsTest(t)
	ctx := context.Background()

	extra := json.RawMessage(`{"temperature":0.7,"top_p":0.9}`)
	_, err := CreateAiModel(ctx, &request.AiModelCreateRequest{
		UserId:       2070049592501604352,
		ModelName:    "guineapig-extra",
		ApiUrl:       "http://localhost:8201/",
		ApiKey:       "test-key",
		ProviderCode: "Vllm",
		ModelType:    "LLM",
		ExtraParams:  extra,
	})
	if err != nil {
		t.Fatalf("create: %v", err)
	}

	resp, err := ListAiModel(ctx, &request.AiModelListRequest{UserId: 2070049592501604352})
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	items, total := resp.Items, resp.Total
	if total != 1 {
		t.Fatalf("expected total=1, got %d", total)
	}
	if items[0].ExtraParams == nil {
		t.Fatal("expected extra_params in response, got nil")
	}
	got := map[string]any{}
	if err := json.Unmarshal(items[0].ExtraParams, &got); err != nil {
		t.Fatalf("response extra_params not valid json: %v", err)
	}
	if got["temperature"] != 0.7 {
		t.Fatalf("expected temperature=0.7, got %v", got["temperature"])
	}
	if got["top_p"] != 0.9 {
		t.Fatalf("expected top_p=0.9, got %v", got["top_p"])
	}
}

func TestExtraParamsOmittedWhenNil(t *testing.T) {
	setupExtraParamsTest(t)
	ctx := context.Background()

	_, err := CreateAiModel(ctx, &request.AiModelCreateRequest{
		UserId:       2070049592501604352,
		ModelName:    "no-extra",
		ApiUrl:       "http://localhost:8201/",
		ApiKey:       "test-key",
		ProviderCode: "Vllm",
		ModelType:    "LLM",
	})
	if err != nil {
		t.Fatalf("create: %v", err)
	}

	var row model.UserAiModel
	if err := plugin.DB.WithContext(ctx).Where("model_name = ?", "no-extra").First(&row).Error; err != nil {
		t.Fatalf("find row: %v", err)
	}
	if row.ExtraParams != nil {
		t.Fatalf("expected nil extra_params in db, got %q", *row.ExtraParams)
	}

	resp, err := ListAiModel(ctx, &request.AiModelListRequest{UserId: 2070049592501604352})
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	items, total := resp.Items, resp.Total
	if total != 1 {
		t.Fatalf("expected total=1, got %d", total)
	}
	if items[0].ExtraParams != nil {
		t.Fatal("expected extra_params omitted in response, got value")
	}
}

func TestExtraParamsUpdate(t *testing.T) {
	setupExtraParamsTest(t)
	ctx := context.Background()

	_, err := CreateAiModel(ctx, &request.AiModelCreateRequest{
		UserId:       2070049592501604352,
		ModelName:    "before",
		ApiUrl:       "http://localhost:8201/",
		ApiKey:       "test-key",
		ProviderCode: "Vllm",
		ModelType:    "LLM",
		ExtraParams:  json.RawMessage(`{"a":1}`),
	})
	if err != nil {
		t.Fatalf("create: %v", err)
	}

	var row model.UserAiModel
	if err := plugin.DB.WithContext(ctx).Where("model_name = ?", "before").First(&row).Error; err != nil {
		t.Fatalf("find row: %v", err)
	}

	newExtra := json.RawMessage(`{"b":2}`)
	err = UpdateAiModel(ctx, &request.AiModelUpdateRequest{
		Id:           row.Id,
		UserId:       2070049592501604352,
		ModelName:    "after",
		ApiUrl:       "http://localhost:8201/",
		ProviderCode: "Vllm",
		ModelType:    "LLM",
		ExtraParams:  newExtra,
	})
	if err != nil {
		t.Fatalf("update: %v", err)
	}

	var updated model.UserAiModel
	if err := plugin.DB.WithContext(ctx).Where("id = ?", row.Id).First(&updated).Error; err != nil {
		t.Fatalf("find updated: %v", err)
	}
	if updated.ExtraParams == nil {
		t.Fatal("expected extra_params after update, got nil")
	}
	got := map[string]any{}
	if err := json.Unmarshal([]byte(*updated.ExtraParams), &got); err != nil {
		t.Fatalf("updated extra_params not valid json: %v", err)
	}
	if got["b"] != float64(2) {
		t.Fatalf("expected b=2, got %v", got["b"])
	}
}
