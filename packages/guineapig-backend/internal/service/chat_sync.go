package service

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"guineapig/config"
	"guineapig/internal/model"
	"guineapig/pkg/plugin"
	"guineapig/pkg/plugin/logger"
	"net/http"
	"strings"
	"time"
)

// SyncChatMessage 同步方式处理 IM Bot 聊天消息
// 1. 查找/创建 conversation（按 source + ext_chat_id）
// 2. 存储用户消息
// 3. 调用 AiAgent LLM 流式接口，收集完整回复
// 4. 存储助手消息
// 5. 返回回复文本
func SyncChatMessage(ctx context.Context, userID int64, platform, extChatID, content string) (string, error) {
	// 1. 查找或创建会话
	conversation, err := findOrCreateExtConversation(ctx, userID, platform, extChatID, content)
	if err != nil {
		return "", fmt.Errorf("获取会话失败: %w", err)
	}

	// 2. 存储用户消息
	userMsg := &model.ChatMessage{
		ConversationId: conversation.Id,
		Role:           "user",
		Content:        content,
		Status:         "completed",
		Version:        1,
	}
	if err := userMsg.Create(ctx); err != nil {
		return "", fmt.Errorf("存储用户消息失败: %w", err)
	}

	// 更新会话消息计数
	_ = plugin.GetDB(ctx).Model(&model.ChatConversation{}).
		Where("id = ?", conversation.Id).
		UpdateColumn("message_count", conversation.MessageCount+1)

	// 3. 构建 LLM 上下文
	messages, err := buildLLMMessages(ctx, conversation)
	if err != nil {
		return "", fmt.Errorf("构建 LLM 上下文失败: %w", err)
	}

	// 4. 加载模型配置
	// 优先从 Redis 读取用户最近一次 client chat 的配置（模型选择和联网搜索开关）
	// Redis 中无缓存时使用第一个可用模型（兼容旧版行为）
	modelID, webSearchEnabled, _ := GetUserChatConfig(ctx, userID)
	var modelConfig *ModelConfig
	if modelID > 0 {
		modelConfig, err = loadModelConfig(ctx, modelID, userID)
	} else {
		modelConfig, err = loadDefaultModelConfig(ctx, userID)
	}
	if err != nil {
		return "", fmt.Errorf("加载模型配置失败: %w", err)
	}

	// 5. 调用 AiAgent 获取回复（传入 user_id 和 session_id 以便指标上报）
	reply, err := callAiAgentLLM(ctx, modelConfig, messages,
		userID, fmt.Sprintf("conv_%d", conversation.Id), webSearchEnabled)
	if err != nil {
		return "", fmt.Errorf("调用 AiAgent 失败: %w", err)
	}

	// 6. 存储助手消息
	assistantMsg := &model.ChatMessage{
		ConversationId: conversation.Id,
		Role:           "assistant",
		Content:        reply,
		Status:         "completed",
		Version:        1,
	}
	if err := assistantMsg.Create(ctx); err != nil {
		logger.Errorf("[SyncChat] 存储助手消息失败: %v", err)
	}

	return reply, nil
}

// findOrCreateExtConversation 查找或创建外部平台会话
func findOrCreateExtConversation(ctx context.Context, userID int64, platform, extChatID, firstContent string) (*model.ChatConversation, error) {
	db := plugin.GetDB(ctx)

	// 先查已有会话
	var conversation model.ChatConversation
	err := db.Where("user_id = ? AND source = ? AND ext_chat_id = ?",
		userID, platform, extChatID).
		First(&conversation).Error

	if err == nil {
		// 已有会话，更新时间
		now := time.Now()
		_ = db.Model(&conversation).
			Where("id = ?", conversation.Id).
			Update("updated_at", now).Error
		conversation.UpdatedAt = now
		return &conversation, nil
	}

	// 创建新会话
	title := firstContent
	if title == "" {
		title = platform + "对话"
	}
	if len([]rune(title)) > 50 {
		title = string([]rune(title)[:50])
	}
	title = strings.Split(title, "\n")[0]

	now := time.Now()
	conversation = model.ChatConversation{
		UserId:       userID,
		Title:        title,
		Source:       platform,
		ExtChatId:    extChatID,
		Status:       "active",
		MessageCount: 0,
		StartAt:      &now,
	}
	if err := conversation.Create(ctx); err != nil {
		return nil, fmt.Errorf("创建会话失败: %w", err)
	}

	return &conversation, nil
}

// loadDefaultModelConfig 加载用户的默认模型配置
func loadDefaultModelConfig(ctx context.Context, userID int64) (*ModelConfig, error) {
	// 查询用户可用的 AI 模型
	modelList, err := model.MUserAiModel.ListOptions(ctx, userID)
	if err != nil {
		return nil, fmt.Errorf("查询模型列表失败: %w", err)
	}
	if len(modelList) == 0 {
		return nil, errors.New("用户未配置 AI 模型")
	}

	aiModel := modelList[0]
	apiKey, err := DecryptApiKey(ctx, aiModel.Id, userID)
	if err != nil {
		return nil, fmt.Errorf("解密 API Key 失败: %w", err)
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

// callAiAgentLLM 调用 AiAgent LLM 接口同步获取回复
// POST /guineapig-aiagent/llm/chat/stream 收集完整 SSE 流
// userID 和 sessionID 传递给 AiAgent 用于指标（otel metrics）上报
// webSearchEnabled 控制是否启用联网搜索
func callAiAgentLLM(ctx context.Context, modelConfig *ModelConfig, messages []map[string]string, userID int64, sessionID string, webSearchEnabled bool) (string, error) {
	baseURL := config.Global.AiAgent.BaseUrl
	if baseURL == "" {
		return "", errors.New("AIAGENT_BASE_URL 未配置")
	}

	// 构建请求体（传入 user_id 和 session_id 以便 AiAgent 上报 otel 指标）
	reqMap := map[string]any{
		"messages":    messages,
		"model":       modelConfig.ModelName,
		"api_key":     modelConfig.ApiKey,
		"base_url":    modelConfig.ApiUrl,
		"temperature": 0.7,
		"max_tokens":  modelConfig.MaxTokens,
		"stream":      true,
		"user_id":     userID,
		"session_id":  sessionID,
	}
	if webSearchEnabled {
		reqMap["web_search_enabled"] = true
	}
	reqBody, _ := json.Marshal(reqMap)

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost,
		baseURL+"/guineapig-aiagent/llm/chat/stream",
		bytes.NewReader(reqBody))
	if err != nil {
		return "", fmt.Errorf("创建请求失败: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")

	client := &http.Client{Timeout: 120 * time.Second}
	resp, err := client.Do(httpReq)
	if err != nil {
		return "", fmt.Errorf("请求 AiAgent 失败: %w", err)
	}
	defer resp.Body.Close()

	// 读取 SSE 流，收集完整回复
	var reply strings.Builder
	scanner := bufio.NewScanner(resp.Body)
	// 增加 scanner buffer 大小以处理长行
	scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024)

	for scanner.Scan() {
		line := scanner.Text()

		// SSE 格式: "data: {json}\n\n"
		if !strings.HasPrefix(line, "data: ") {
			continue
		}

		data := strings.TrimPrefix(line, "data: ")
		if data == "" {
			continue
		}

		var event struct {
			Content string `json:"content"`
			Done    bool   `json:"done"`
			Error   string `json:"error"`
		}
		if err := json.Unmarshal([]byte(data), &event); err != nil {
			continue
		}

		if event.Error != "" {
			return "", fmt.Errorf("AiAgent 返回错误: %s", event.Error)
		}

		reply.WriteString(event.Content)

		if event.Done {
			break
		}
	}

	if err := scanner.Err(); err != nil {
		return "", fmt.Errorf("读取 SSE 流失败: %w", err)
	}

	result := strings.TrimSpace(reply.String())
	if result == "" {
		return "", errors.New("AiAgent 返回空回复")
	}

	return result, nil
}
