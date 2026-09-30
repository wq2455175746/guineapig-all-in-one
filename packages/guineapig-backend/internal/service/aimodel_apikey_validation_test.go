package service

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"encoding/base64"
	"encoding/pem"
	"os"
	"path/filepath"
	"testing"

	"gorm.io/driver/sqlite"
	"gorm.io/gorm"
	"guineapig/config"
	"guineapig/internal/model"
	"guineapig/internal/request"
	"guineapig/pkg/plugin"
)

func encryptForTest(t *testing.T, pub *rsa.PublicKey, plain string) string {
	t.Helper()
	cipher, err := rsa.EncryptPKCS1v15(rand.Reader, pub, []byte(plain))
	if err != nil {
		t.Fatalf("encrypt: %v", err)
	}
	return base64.StdEncoding.EncodeToString(cipher)
}

func setupApiKeyValidation(t *testing.T) *rsa.PublicKey {
	t.Helper()
	priv, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("gen key: %v", err)
	}
	dir := t.TempDir()
	keyPath := filepath.Join(dir, "private.key")
	pemData := pem.EncodeToMemory(&pem.Block{Type: "RSA PRIVATE KEY", Bytes: x509.MarshalPKCS1PrivateKey(priv)})
	if err := os.WriteFile(keyPath, pemData, 0600); err != nil {
		t.Fatalf("write key: %v", err)
	}
	config.Global.Rsa.PrivateKey = keyPath

	privateKeyMu.Lock()
	privateKey = nil
	privateKeyMu.Unlock()

	db, err := gorm.Open(sqlite.Open(":memory:"), &gorm.Config{})
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	if err := db.AutoMigrate(&model.UserAiModel{}); err != nil {
		t.Fatalf("automigrate: %v", err)
	}
	plugin.DB = db
	return &priv.PublicKey
}

func TestCreateAiModelRejectsEmptyApiKey(t *testing.T) {
	pub := setupApiKeyValidation(t)
	ctx := context.Background()

	_, err := CreateAiModel(ctx, &request.AiModelCreateRequest{
		UserId:       2070049592501604352,
		ModelName:    "empty-key",
		ApiUrl:       "http://localhost:8201/",
		ApiKey:       encryptForTest(t, pub, ""),
		ProviderCode: "Vllm",
		ModelType:    "LLM",
	})
	if err == nil {
		t.Fatal("expected error for empty api_key, got nil")
	}
}

func TestCreateAiModelAcceptsNonEmptyApiKey(t *testing.T) {
	pub := setupApiKeyValidation(t)
	ctx := context.Background()

	_, err := CreateAiModel(ctx, &request.AiModelCreateRequest{
		UserId:       2070049592501604352,
		ModelName:    "real-key",
		ApiUrl:       "http://localhost:8201/",
		ApiKey:       encryptForTest(t, pub, "sk-real-key"),
		ProviderCode: "Vllm",
		ModelType:    "LLM",
	})
	if err != nil {
		t.Fatalf("expected ok, got %v", err)
	}
}

func TestUpdateAiModelRejectsEmptyApiKey(t *testing.T) {
	pub := setupApiKeyValidation(t)
	ctx := context.Background()

	resp, err := CreateAiModel(ctx, &request.AiModelCreateRequest{
		UserId:       2070049592501604352,
		ModelName:    "target",
		ApiUrl:       "http://localhost:8201/",
		ApiKey:       encryptForTest(t, pub, "sk-ok"),
		ProviderCode: "Vllm",
		ModelType:    "LLM",
	})
	if err != nil {
		t.Fatalf("create: %v", err)
	}

	err = UpdateAiModel(ctx, &request.AiModelUpdateRequest{
		Id:           resp.Id,
		UserId:       2070049592501604352,
		ModelName:    "target2",
		ApiUrl:       "http://localhost:8201/",
		ApiKey:       encryptForTest(t, pub, ""),
		ProviderCode: "Vllm",
		ModelType:    "LLM",
	})
	if err == nil {
		t.Fatal("expected error for empty api_key on update, got nil")
	}
}

func TestUpdateAiModelWithoutApiKeyKeepsExisting(t *testing.T) {
	pub := setupApiKeyValidation(t)
	ctx := context.Background()

	resp, err := CreateAiModel(ctx, &request.AiModelCreateRequest{
		UserId:       2070049592501604352,
		ModelName:    "keep",
		ApiUrl:       "http://localhost:8201/",
		ApiKey:       encryptForTest(t, pub, "sk-keep"),
		ProviderCode: "Vllm",
		ModelType:    "LLM",
	})
	if err != nil {
		t.Fatalf("create: %v", err)
	}

	// 不传 api_key（前端不修改密钥时）应成功
	err = UpdateAiModel(ctx, &request.AiModelUpdateRequest{
		Id:           resp.Id,
		UserId:       2070049592501604352,
		ModelName:    "keep2",
		ApiUrl:       "http://localhost:8201/",
		ProviderCode: "Vllm",
		ModelType:    "LLM",
	})
	if err != nil {
		t.Fatalf("expected ok without api_key, got %v", err)
	}
}
