package service

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"guineapig/internal/model"
	"guineapig/internal/request"
	"guineapig/pkg/plugin"
	"guineapig/pkg/plugin/logger"
	"guineapig/pkg/utils"
	"time"

	"github.com/redis/go-redis/v9"
)

// ========== Redis Key 常量 ==========
const (
	RedisKeyStreamCache     = "chat:stream:%d:%d"   // chat:stream:{conversation_id}:{message_id}
	RedisKeyContext         = "chat:context:%d:%d"  // chat:context:{user_id}:{conversation_id}
	RedisKeyLastActive      = "chat:last_active:%d" // chat:last_active:{user_id}
	RedisKeyPendingMessages = "chat:pending_messages"

	StreamCacheTTL  = 3600 * time.Second
	ContextCacheTTL = 7200 * time.Second
	LastActiveTTL   = 86400 * time.Second
)

// ========== 模型配置 ==========

// ModelConfig 解密后的 LLM 连接参数
type ModelConfig struct {
	ApiUrl    string
	ApiKey    string
	ModelName string
	MaxTokens int
}

// RagContext RAG 知识库检索配置（从 DB 解析后直接透传给 aiagent）
type RagContext struct {
	RagNames           []string `json:"rag_names"`
	EmbeddingApiUrl    string   `json:"embedding_api_url"`
	EmbeddingApiKey    string   `json:"embedding_api_key"`
	EmbeddingModelName string   `json:"embedding_model_name"`
	RerankerApiUrl     string   `json:"reranker_api_url"`
	RerankerApiKey     string   `json:"reranker_api_key"`
	RerankerModelName  string   `json:"reranker_model_name"`
	TopK               int      `json:"top_k"`
	RerankTopK         int      `json:"rerank_top_k"`
}

// ========== 构建 LLM 上下文 ==========

// buildLLMMessages 从 DB 加载会话历史消息，构建 LLM 消息数组
func buildLLMMessages(ctx context.Context, conversation *model.ChatConversation) ([]map[string]string, error) {
	var messages []map[string]string

	// System prompt
	systemPrompt := conversation.SystemPrompt
	if systemPrompt == "" {
		systemPrompt = "你是一个有用的AI助手。"
	}
	messages = append(messages, map[string]string{"role": "system", "content": systemPrompt})

	// 从 DB 加载最近 20 条已完成的消息
	db := plugin.GetDB(ctx)
	var msgs []model.ChatMessage
	if err := db.Where("conversation_id = ? AND status = 'completed'", conversation.Id).
		Order("created_at ASC").
		Limit(20).
		Find(&msgs).Error; err != nil {
		return nil, fmt.Errorf("查询历史消息失败: %w", err)
	}

	for _, m := range msgs {
		messages = append(messages, map[string]string{"role": m.Role, "content": m.Content})
	}

	return messages, nil
}

// ========== 加载模型配置 ==========

// loadModelConfig 加载并解密 AI 模型配置
func loadModelConfig(ctx context.Context, modelId, userId int64) (*ModelConfig, error) {
	aiModel, err := model.MUserAiModel.FindById(ctx, modelId)
	if err != nil {
		return nil, fmt.Errorf("查找AI模型失败: %w", err)
	}
	if aiModel == nil {
		return nil, errors.New("AI模型不存在")
	}

	// 解密 api_key
	apiKey, err := DecryptApiKey(ctx, modelId, userId)
	if err != nil {
		return nil, fmt.Errorf("解密API Key失败: %w", err)
	}

	defaultMaxTokens := aiModel.MaxTokens
	if defaultMaxTokens <= 0 {
		defaultMaxTokens = 8192
	}

	return &ModelConfig{
		ApiUrl:    aiModel.ApiUrl,
		ApiKey:    apiKey,
		ModelName: aiModel.ModelName,
		MaxTokens: defaultMaxTokens,
	}, nil
}

// ========== Redis 操作 ==========

// updateContextCache 将最近消息写入 Redis 上下文缓存
func updateContextCache(ctx context.Context, userId, conversationId int64) {
	db := plugin.GetDB(ctx)
	var msgs []model.ChatMessage
	if err := db.Where("conversation_id = ? AND status IN ('completed','streaming')", conversationId).
		Order("created_at DESC").
		Limit(10).
		Find(&msgs).Error; err != nil {
		return
	}

	rdb := plugin.GetClient()
	ctxKey := fmt.Sprintf(RedisKeyContext, userId, conversationId)

	pipe := rdb.Pipeline()
	_ = pipe.Del(ctx, ctxKey).Err()
	// 逆序写入（chronological order）
	for i := len(msgs) - 1; i >= 0; i-- {
		m := msgs[i]
		entry, _ := json.Marshal(map[string]string{
			"role":    m.Role,
			"content": m.Content,
		})
		_ = pipe.RPush(ctx, ctxKey, entry).Err()
	}
	_, _ = pipe.Exec(ctx)
	_ = rdb.Expire(ctx, ctxKey, ContextCacheTTL).Err()
}

// updateLastActive 更新会话最后活跃时间（Sorted Set）
func updateLastActive(ctx context.Context, userId, conversationId int64) {
	rdb := plugin.GetClient()
	key := fmt.Sprintf(RedisKeyLastActive, userId)
	_ = rdb.ZAdd(ctx, key, redis.Z{
		Score:  float64(time.Now().Unix()),
		Member: conversationId,
	}).Err()
	_ = rdb.Expire(ctx, key, LastActiveTTL).Err()
}

// ========== RAG 上下文解析 ==========

// resolveRagContextFromLatestMessage 从最近一条用户消息的 attachments 中提取
// 已嵌入文件 ID，解析 RAG 配置（文件 → 知识库 → 模型 → 解密），返回 RagContext。
// 消息无嵌入文件附件或解析失败时返回 nil。
func resolveRagContextFromLatestMessage(ctx context.Context, conversationId, userId int64) (*RagContext, error) {
	// 1. 查询最近一条用户消息的 attachments
	db := plugin.GetDB(ctx)
	var latestUserMsg model.ChatMessage
	if err := db.Where("conversation_id = ? AND role = 'user' AND status = 'completed'", conversationId).
		Order("created_at DESC").
		First(&latestUserMsg).Error; err != nil {
		// 无用户消息（不应发生），不阻断
		return nil, nil
	}

	if latestUserMsg.Attachments == nil || *latestUserMsg.Attachments == "" {
		return nil, nil
	}

	// 2. 解析 attachments JSON
	var attachments []request.AttachmentItem
	if err := json.Unmarshal([]byte(*latestUserMsg.Attachments), &attachments); err != nil {
		return nil, fmt.Errorf("解析 attachments JSON 失败: %w", err)
	}

	// 3. 收集 embedded_file 类型的 file_ids
	var fileIds []int64
	for _, att := range attachments {
		if att.Type == "embedded_file" && att.Id > 0 {
			fileIds = append(fileIds, att.Id)
		}
	}
	if len(fileIds) == 0 {
		return nil, nil
	}

	return resolveRagContext(ctx, fileIds, userId)
}

// resolveRagContext 从 file_ids 列表解析 RAG 配置
func resolveRagContext(ctx context.Context, fileIds []int64, userId int64) (*RagContext, error) {
	// 0. 单次解析的 DB 操作统一加超时，避免流式 goroutine 中 DB 挂起
	ctx, cancel := context.WithTimeout(ctx, utils.DBQueryTimeout)
	defer cancel()

	// 1. 批量查询所有文件，提取唯一 res_rag_id 集合
	ragIdSet := make(map[int64]struct{})
	if len(fileIds) > 0 {
		files, err := model.MResFiles.FindByIds(ctx, fileIds)
		if err != nil {
			return nil, fmt.Errorf("查询文件失败: %w", err)
		}
		for _, file := range files {
			if file.EmbeddingConfig == nil || *file.EmbeddingConfig == "" {
				continue
			}
			var cfg struct {
				ResRagId int64 `json:"res_rag_id"`
			}
			if err := json.Unmarshal([]byte(*file.EmbeddingConfig), &cfg); err != nil {
				logger.Warnf("[RAG] 解析 embedding_config 失败: file_id=%d, err=%v", file.Id, err)
				continue
			}
			if cfg.ResRagId > 0 {
				ragIdSet[cfg.ResRagId] = struct{}{}
			}
		}
	}
	if len(ragIdSet) == 0 {
		return nil, nil
	}

	// 2. 批量查询各 RAG 的集合名称，收集唯一的模型 ID
	ragIds := make([]int64, 0, len(ragIdSet))
	for ragId := range ragIdSet {
		ragIds = append(ragIds, ragId)
	}
	rags, err := model.MResRags.FindByIds(ctx, ragIds)
	if err != nil {
		return nil, fmt.Errorf("查询知识库失败: %w", err)
	}

	var ragNames []string
	var embeddingModelId, rerankerModelId int64
	for _, rag := range rags {
		ragNames = append(ragNames, rag.Name)
		if embeddingModelId == 0 && rag.EmbeddingModelId > 0 {
			embeddingModelId = rag.EmbeddingModelId
		}
		if rerankerModelId == 0 && rag.RerankerModelId > 0 {
			rerankerModelId = rag.RerankerModelId
		}
	}
	if len(ragNames) == 0 {
		return nil, nil
	}
	if embeddingModelId == 0 || rerankerModelId == 0 {
		return nil, fmt.Errorf("RAG 模型配置不完整: embedding=%d, reranker=%d", embeddingModelId, rerankerModelId)
	}

	// 3. 加载嵌入模型配置
	embeddingModel, err := loadRerankerModelConfig(ctx, embeddingModelId, userId)
	if err != nil {
		return nil, fmt.Errorf("加载嵌入模型失败: %w", err)
	}
	// 4. 加载重排序模型配置
	rerankerModel, err := loadRerankerModelConfig(ctx, rerankerModelId, userId)
	if err != nil {
		return nil, fmt.Errorf("加载重排序模型失败: %w", err)
	}

	return &RagContext{
		RagNames:           ragNames,
		EmbeddingApiUrl:    embeddingModel.ApiUrl,
		EmbeddingApiKey:    embeddingModel.ApiKey,
		EmbeddingModelName: embeddingModel.ModelName,
		RerankerApiUrl:     rerankerModel.ApiUrl,
		RerankerApiKey:     rerankerModel.ApiKey,
		RerankerModelName:  rerankerModel.ModelName,
		TopK:               20,
		RerankTopK:         3,
	}, nil
}

// loadRerankerModelConfig 加载并解密 AI 模型配置（用于嵌入/重排序模型）
func loadRerankerModelConfig(ctx context.Context, modelId, userId int64) (*ModelConfig, error) {
	aiModel, err := model.MUserAiModel.FindById(ctx, modelId)
	if err != nil {
		return nil, fmt.Errorf("查找AI模型失败: %w", err)
	}
	if aiModel == nil {
		return nil, errors.New("AI模型不存在")
	}

	apiKey, err := DecryptApiKey(ctx, modelId, userId)
	if err != nil {
		return nil, fmt.Errorf("解密API Key失败: %w", err)
	}

	return &ModelConfig{
		ApiUrl:    aiModel.ApiUrl,
		ApiKey:    apiKey,
		ModelName: aiModel.ModelName,
	}, nil
}
