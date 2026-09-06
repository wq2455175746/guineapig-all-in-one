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
	"guineapig/internal/request"
	"guineapig/internal/response"
	"guineapig/pkg/plugin"
	"guineapig/pkg/plugin/logger"
	"guineapig/pkg/utils"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"gorm.io/gorm"
)

// ========== 常量 ==========

const (
	WSWriteWait      = 10 * time.Second
	WSPongWait       = 60 * time.Second
	WSPingPeriod     = (WSPongWait * 9) / 10
	WSMaxMessageSize = 65536
)

// ========== Hub（单例网关）==========

var (
	hub     *Hub
	hubOnce sync.Once
)

type Hub struct {
	mu           sync.RWMutex
	clients      map[int64]*ClientConnection   // user_id → WS 连接
	aiAgentConns map[int64]*AiAgentConn        // conversation_id → aiagent HTTP 连接
}

type ClientConnection struct {
	UserID int64
	Conn   *websocket.Conn
	Send   chan []byte
	hub    *Hub

	done chan struct{} // 连接终止信号，writePump / sendToClient 据此退出或丢弃
	once sync.Once     // 保证 done 只关闭一次
}

type AiAgentConn struct {
	ConversationID int64
	MessageID      int64
	UserID         int64 // 归属用户，Unregister 时只取消该用户自己的会话流
	Cancel         context.CancelFunc
}

func newClientConnection(h *Hub, conn *websocket.Conn, userID int64) *ClientConnection {
	return &ClientConnection{
		UserID: userID,
		Conn:   conn,
		Send:   make(chan []byte, 256),
		hub:    h,
		done:   make(chan struct{}),
	}
}

// Close 终止连接：只关闭 done 信号，绝不关闭 Send channel。
// 此后 sendToClient 会自动丢弃消息，writePump 正常退出，避免向已关闭 channel 写导致的 panic。
func (c *ClientConnection) Close() {
	c.once.Do(func() {
		close(c.done)
	})
	if c.Conn != nil {
		// best-effort 关闭：连接可能已被对端关闭，Close 报错无操作意义
		_ = c.Conn.Close()
	}
}

// newClientStreamContext 返回随 WS 连接生命周期取消的 context：
// 连接断开（done 关闭）或 ctx 被取消时，watch goroutine 退出，不泄漏。
func (h *Hub) newClientStreamContext(client *ClientConnection) (context.Context, context.CancelFunc) {
	ctx, cancel := context.WithCancel(context.Background())
	go func() {
		select {
		case <-client.done:
			cancel()
		case <-ctx.Done():
		}
	}()
	return ctx, cancel
}

func GetHub() *Hub {
	hubOnce.Do(func() {
		hub = &Hub{
			clients:      make(map[int64]*ClientConnection),
			aiAgentConns: make(map[int64]*AiAgentConn),
		}
	})
	return hub
}

// ========== 客户端连接生命周期 ==========

// Register 注册客户端 WS 连接
func (h *Hub) Register(client *ClientConnection) {
	h.mu.Lock()
	defer h.mu.Unlock()

	// 如果已有该用户的旧连接，优雅关闭旧连接（不 close 其 Send，避免写 panic）
	if old, ok := h.clients[client.UserID]; ok {
		old.Close()
	}
	h.clients[client.UserID] = client
}

// Unregister 注销指定的客户端 WS 连接。
// 仅当该连接仍是该用户当前注册的连接时才移除并取消其会话流，
// 避免旧连接（已被新连接替换）退出时误杀新连接。
func (h *Hub) Unregister(client *ClientConnection) {
	if client == nil {
		return
	}
	userID := client.UserID

	var cancels []context.CancelFunc
	h.mu.Lock()
	if cur, ok := h.clients[userID]; ok && cur == client {
		delete(h.clients, userID)

		// 只取消该用户自己会话的活跃 AiAgent 连接，不影响其他用户的流
		for convID, conn := range h.aiAgentConns {
			if conn.UserID == userID {
				delete(h.aiAgentConns, convID)
				if conn.Cancel != nil {
					cancels = append(cancels, conn.Cancel)
				}
			}
		}
	}
	h.mu.Unlock()

	for _, cancel := range cancels {
		cancel()
	}
	// 幂等：可能已在 Register 替换旧连接时调用过 Close
	client.Close()
}

// readPump 从 WS 读取消息（每客户端一个 goroutine）
func (h *Hub) readPump(client *ClientConnection) {
	defer func() {
		h.Unregister(client)
	}()

	client.Conn.SetReadLimit(WSMaxMessageSize)
	client.Conn.SetReadDeadline(time.Now().Add(WSPongWait))
	client.Conn.SetPongHandler(func(string) error {
		client.Conn.SetReadDeadline(time.Now().Add(WSPongWait))
		return nil
	})

	for {
		_, message, err := client.Conn.ReadMessage()
		if err != nil {
			if websocket.IsUnexpectedCloseError(err, websocket.CloseGoingAway, websocket.CloseNormalClosure) {
				logger.Warnf("[Hub] WS 读取错误: user_id=%d, err=%v", client.UserID, err)
			}
			break
		}

		h.handleMessage(client, message)
	}
}

// writePump 写入消息到 WS（每客户端一个 goroutine）
func (h *Hub) writePump(client *ClientConnection) {
	ticker := time.NewTicker(WSPingPeriod)
	defer func() {
		ticker.Stop()
		client.Conn.Close()
	}()

	for {
		select {
		case <-client.done:
			return
		case message, ok := <-client.Send:
			client.Conn.SetWriteDeadline(time.Now().Add(WSWriteWait))
			if !ok {
				client.Conn.WriteMessage(websocket.CloseMessage, []byte{})
				return
			}
			if err := client.Conn.WriteMessage(websocket.TextMessage, message); err != nil {
				return
			}
		case <-ticker.C:
			client.Conn.SetWriteDeadline(time.Now().Add(WSWriteWait))
			if err := client.Conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				return
			}
		}
	}
}

// ========== 消息路由 ==========

func (h *Hub) handleMessage(client *ClientConnection, raw []byte) {
	var env response.WSEnvelope
	if err := json.Unmarshal(raw, &env); err != nil {
		logger.Warnf("[Hub] 消息解析失败: user_id=%d, err=%v", client.UserID, err)
		return
	}

	switch env.Type {
	case "chat.send":
		// 检查是否为 agent 模式
		if agentMode, ok := env.Payload["agent_mode"].(bool); ok && agentMode {
			h.handleAgentSend(client, &env)
		} else {
			h.handleChatSend(client, &env)
		}
	case "chat.agent_send":
		h.handleAgentSend(client, &env)
	case "chat.agent_delegate_result":
		h.handleAgentDelegateResult(client, &env)
	case "chat.agent_confirm":
		h.handleAgentConfirm(client, &env)
	case "chat.agent_cancel":
		h.handleAgentCancel(client, &env)
	case "chat.agent_skip_step":
		h.handleAgentSkipStep(client, &env)
	case "chat.agent_modify_step":
		h.handleAgentModifyStep(client, &env)
	case "chat.agent_intervene":
		h.handleAgentIntervene(client, &env)
	case "chat.command_result":
		h.handleCommandResult(client, &env)
	case "chat.cancel":
		h.handleCancel(client, &env)
	case "ping":
		h.sendToClient(client, &response.WSEnvelope{Type: "pong"})
	default:
		logger.Warnf("[Hub] 未知消息类型: type=%s, user_id=%d", env.Type, client.UserID)
	}
}

// ========== Chat Send 处理（核心）==========

func (h *Hub) handleChatSend(client *ClientConnection, env *response.WSEnvelope) {
	ctx := context.Background()

	// 1. 解析 ChatSendRequest
	req, err := parseSendRequest(env.Payload)
	if err != nil {
		h.sendError(client, fmt.Sprintf("参数错误: %v", err))
		return
	}

	// 2. 创建/获取会话 + 用户消息（复用 service/chat.go 的 SendChatMessage）
	//    以 WS 连接鉴权身份覆盖 payload 中的 userId，杜绝 WS 侧伪造他人 userId
	req.UserId = client.UserID
	msgResp, err := SendChatMessage(ctx, req)
	if err != nil {
		h.sendError(client, fmt.Sprintf("创建消息失败: %v", err))
		return
	}

	// 3. 发回用户消息的确认（包含 conversationId、messageId）
	h.sendToClient(client, &response.WSEnvelope{
		Type: "chat.send_ack",
		From: "backend",
		To:   "client",
		Payload: map[string]any{
			"message_id":      msgResp.MessageId,
			"conversation_id": msgResp.ConversationId,
		},
		Meta: &response.WSMeta{
			ConversationID: msgResp.ConversationId,
			MessageID:      msgResp.MessageId,
			UserID:         client.UserID,
		},
	})

	// 4. 保存用户配置到 Redis（供飞书等外部渠道读取）
	if err := SetUserChatConfig(ctx, client.UserID, req.ModelId, req.WebSearchEnabled, req.AgentModeEnabled); err != nil {
		logger.Warnf("[Hub] 保存用户聊天配置失败: user_id=%d, err=%v", client.UserID, err)
	}

	// 5. 异步流式回复
	go h.streamAssistantReply(ctx, client, req, msgResp)
}

// streamAssistantReply 异步执行 LLM 流式调用，结果通过 WS 推送
func (h *Hub) streamAssistantReply(ctx context.Context, client *ClientConnection, req *request.ChatSendRequest, msgResp *response.ChatMessageResponse) {
	defer func() {
		if r := recover(); r != nil {
			logger.Errorf("[Hub] streamAssistantReply panic: user_id=%d, err=%v", client.UserID, r)
		}
	}()

	convID := msgResp.ConversationId

	// 可取消的 aiagent 请求上下文：随 WS 连接生命周期取消（断开/被替换即停），
	// 同时注册 AiAgentConn 供 handleCancel / Unregister 取消
	aiCtx, cancel := h.newClientStreamContext(client)
	aiAgentConn := &AiAgentConn{
		ConversationID: convID,
		UserID:         client.UserID,
		Cancel:         cancel,
	}
	h.mu.Lock()
	h.aiAgentConns[convID] = aiAgentConn
	h.mu.Unlock()

	// 结果落库 context：WS 断开不影响消息终态写入（取消的 context 会使 DB 写失败，
	// 导致消息永远停留在 streaming）
	writeCtx, writeCancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer writeCancel()

	// 清理函数（流完成时取消 context 并清理 AiAgentConn）。
	// 身份校验：只删除自己的注册项，避免覆盖同会话的新流。
	cleanup := func() {
		cancel()
		h.mu.Lock()
		if cur, ok := h.aiAgentConns[convID]; ok && cur == aiAgentConn {
			delete(h.aiAgentConns, convID)
		}
		h.mu.Unlock()
	}
	defer cleanup()

	// 1. 加载会话
	conversation, err := model.MChatConversation.FindById(aiCtx, convID)
	if err != nil || conversation == nil {
		h.sendError(client, "会话不存在")
		return
	}

	// 2. 创建 assistant 占位消息
	assistantMsg := &model.ChatMessage{
		ConversationId: convID,
		Role:           "assistant",
		Content:        "",
		Status:         "streaming",
		Version:        1,
	}
	if err := assistantMsg.Create(aiCtx); err != nil {
		h.sendError(client, fmt.Sprintf("创建消息失败: %v", err))
		return
	}
	assistantMsgID := assistantMsg.Id
	aiAgentConn.MessageID = assistantMsgID

	// 3. 构建 LLM 上下文
	llmMessages, err := buildLLMMessages(aiCtx, conversation)
	if err != nil {
		if uerr := updateMessageStatus(writeCtx, assistantMsgID, "error", fmt.Sprintf("构建上下文失败: %v", err)); uerr != nil {
			logger.Errorf("[Hub] 构建上下文失败更新消息状态出错: message_id=%d, err=%v", assistantMsgID, uerr)
		}
		h.sendError(client, fmt.Sprintf("构建上下文失败: %v", err))
		return
	}

	// 4. 加载模型配置
	modelConfig, err := loadModelConfig(aiCtx, conversation.ModelId, client.UserID)
	if err != nil {
		if uerr := updateMessageStatus(writeCtx, assistantMsgID, "error", fmt.Sprintf("加载模型配置失败: %v", err)); uerr != nil {
			logger.Errorf("[Hub] 加载模型配置失败更新消息状态出错: message_id=%d, err=%v", assistantMsgID, uerr)
		}
		h.sendError(client, fmt.Sprintf("加载模型配置失败: %v", err))
		return
	}

	// 5. 查询技能 + RAG 上下文
	var skills []response.SkillInfo
	if skillList, err := model.MResSkills.ListEnabledByUserId(aiCtx, client.UserID); err == nil {
		for _, s := range skillList {
			skills = append(skills, response.SkillInfo{
				Name:        s.Name,
				Description: s.Description,
				ObjectKey:   s.ZipUrl,
			})
		}
	}

	ragContext, ragErr := resolveRagContextFromLatestMessage(aiCtx, convID, client.UserID)
	if ragErr != nil {
		logger.Warnf("[Hub] 解析 RAG 上下文失败: conversation_id=%d, user_id=%d, err=%v", convID, client.UserID, ragErr)
	}

	var commands []response.CommandItem
	var fullContent string
	var proxyErr error

	// 6. 调用 aiagent SSE 流并代理到 WS
	fullContent, commands, proxyErr = h.proxyAiAgentStream(aiCtx, convID, assistantMsgID, llmMessages, modelConfig, skills, client.UserID, req.WebSearchEnabled, ragContext, client)

	// 7. 处理结果
	if proxyErr != nil {
		if uerr := updateMessageStatus(writeCtx, assistantMsgID, "error", proxyErr.Error()); uerr != nil {
			logger.Errorf("[Hub] 流式失败更新消息状态出错: message_id=%d, err=%v", assistantMsgID, uerr)
		}
		h.sendError(client, proxyErr.Error())
	} else {
		// 保存 commands
		if len(commands) > 0 {
			cmdJSON, err := json.Marshal(commands)
			if err != nil {
				logger.Errorf("[Hub] 序列化 commands 失败: message_id=%d, err=%v", assistantMsgID, err)
			} else {
				cmdStr := string(cmdJSON)
				if uerr := model.MChatMessage.UpdateCommands(writeCtx, assistantMsgID, &cmdStr); uerr != nil {
					logger.Errorf("[Hub] 保存 commands 失败: message_id=%d, err=%v", assistantMsgID, uerr)
				}
			}
		}

		// 更新 MySQL
		if uerr := plugin.GetDB(writeCtx).Model(&model.ChatMessage{}).
			Where("id = ?", assistantMsgID).
			Updates(map[string]any{
				"content":    fullContent,
				"status":     "completed",
				"updated_at": time.Now(),
			}).Error; uerr != nil {
			logger.Errorf("[Hub] 更新助手消息失败: message_id=%d, err=%v", assistantMsgID, uerr)
		}

		// 发送完成事件（只在有命令时才携带 commands，避免已通过 chat.command 转发后重复弹出对话框）
		donePayload := map[string]any{
			"full_content": fullContent,
			"message_id":   assistantMsgID,
		}
		if len(commands) > 0 {
			donePayload["commands"] = commands
		}
		h.sendToClient(client, &response.WSEnvelope{
			Type: "chat.done",
			From: "backend",
			To:   "client",
			Payload: donePayload,
			Meta: &response.WSMeta{
				ConversationID: convID,
				MessageID:      assistantMsgID,
				UserID:         client.UserID,
			},
		})
	}

	// 8. 清理（defer cleanup）+ 会话状态更新
	if err := plugin.GetDB(writeCtx).Model(&model.ChatConversation{}).
		Where("id = ?", convID).
		UpdateColumn("message_count", gorm.Expr("message_count + 1")).Error; err != nil {
		logger.Errorf("[Hub] 更新会话消息计数失败: conversation_id=%d, err=%v", convID, err)
	}
	updateContextCache(writeCtx, client.UserID, convID)
	updateLastActive(writeCtx, client.UserID, convID)
}

// proxyAiAgentStream 调用 aiagent SSE 流，代理事件到 WS
func (h *Hub) proxyAiAgentStream(
	ctx context.Context,
	conversationID, messageID int64,
	llmMessages []map[string]string,
	modelConfig *ModelConfig,
	skills []response.SkillInfo,
	userID int64,
	webSearchEnabled bool,
	ragContext *RagContext,
	client *ClientConnection,
) (string, []response.CommandItem, error) {

	baseURL := config.Global.AiAgent.BaseUrl
	if baseURL == "" {
		return "", nil, fmt.Errorf("AIAGENT_BASE_URL 未配置")
	}

	reqMap := map[string]any{
		"messages":    llmMessages,
		"model":       modelConfig.ModelName,
		"api_key":     modelConfig.ApiKey,
		"base_url":    modelConfig.ApiUrl,
		"temperature": 0.7,
		"max_tokens":  modelConfig.MaxTokens,
		"stream":      true,
		"user_id":     userID,
		"session_id":  fmt.Sprintf("conv_%d", conversationID),
	}
	if len(skills) > 0 {
		reqMap["skills"] = skills
	}
	if webSearchEnabled {
		reqMap["web_search_enabled"] = true
	}
	if ragContext != nil {
		reqMap["rag_context"] = ragContext
	}

	reqBody, err := json.Marshal(reqMap)
	if err != nil {
		return "", nil, fmt.Errorf("序列化 aiagent 请求失败: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost,
		baseURL+"/guineapig-aiagent/llm/chat/stream",
		bytes.NewReader(reqBody))
	if err != nil {
		return "", nil, fmt.Errorf("创建请求失败: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Accept", "text/event-stream")

	httpClient := utils.NewHTTPClient(120 * time.Second) // 2min（单轮 LLM 调用）
	resp, err := httpClient.Do(httpReq)
	if err != nil {
		return "", nil, fmt.Errorf("请求 aiagent 失败: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		respBody, _ := io.ReadAll(resp.Body)
		return "", nil, fmt.Errorf("aiagent 返回错误: %d, %s", resp.StatusCode, string(respBody))
	}

	// 逐行读取 SSE 流
	reader := bufio.NewReader(resp.Body)
	fullContent := ""
	var collectedCommands []response.CommandItem

	for {
		line, err := reader.ReadString('\n')
		if err != nil {
			if err == io.EOF {
				break
			}
			return fullContent, nil, fmt.Errorf("读取 stream 失败: %w", err)
		}

		line = strings.TrimSpace(line)
		if !strings.HasPrefix(line, "data: ") {
			continue
		}

		data := strings.TrimPrefix(line, "data: ")

		var event struct {
			Content  string                `json:"content,omitempty"`
			Done     bool                  `json:"done,omitempty"`
			Error    string                `json:"error,omitempty"`
			Commands []response.CommandItem `json:"commands,omitempty"`
		}
		if err := json.Unmarshal([]byte(data), &event); err != nil {
			continue
		}

		if event.Error != "" {
			return fullContent, collectedCommands, errors.New(event.Error)
		}

		if event.Done {
			if len(event.Commands) > 0 {
				collectedCommands = append(collectedCommands, event.Commands...)
			}
			return fullContent, collectedCommands, nil
		}

		if event.Content != "" {
			fullContent += event.Content
			h.sendToClient(client, &response.WSEnvelope{
				Type:    "chat.content",
				From:    "aiagent",
				To:      "client",
				Payload: map[string]any{"content": event.Content},
				Meta: &response.WSMeta{
					ConversationID: conversationID,
					MessageID:      messageID,
					UserID:         userID,
				},
			})
		}
	}

	return fullContent, nil, nil
}

// ========== Command Result 处理 ==========

func (h *Hub) handleCommandResult(client *ClientConnection, env *response.WSEnvelope) {
	convID := int64(0)
	if env.Meta != nil {
		convID = env.Meta.ConversationID
	}
	if convID == 0 {
		h.sendError(client, "缺少 conversation_id")
		return
	}

	// 可取消的 aiagent 请求上下文：随 WS 连接生命周期取消（断开即停）
	aiCtx, cancel := h.newClientStreamContext(client)
	aiAgentConn := &AiAgentConn{
		ConversationID: convID,
		UserID:         client.UserID,
		Cancel:         cancel,
	}
	h.mu.Lock()
	h.aiAgentConns[convID] = aiAgentConn
	h.mu.Unlock()

	// 结果落库 context：WS 断开不影响消息终态写入
	writeCtx, writeCancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer writeCancel()

	cleanup := func() {
		cancel()
		h.mu.Lock()
		if cur, ok := h.aiAgentConns[convID]; ok && cur == aiAgentConn {
			delete(h.aiAgentConns, convID)
		}
		h.mu.Unlock()
	}
	defer cleanup()

	// 1. 提取 results
	resultsRaw, ok := env.Payload["results"]
	if !ok {
		h.sendError(client, "缺少 results 字段")
		return
	}

	// 2. 加载会话
	conversation, err := model.MChatConversation.FindById(aiCtx, convID)
	if err != nil || conversation == nil {
		h.sendError(client, "会话不存在")
		return
	}
	// 会话属主校验，杜绝 WS 侧伪造他人会话
	if conversation.UserId != client.UserID {
		h.sendError(client, "无权操作该会话")
		return
	}

	// 3. 创建新 assistant 占位消息（新的 message_id）
	assistantMsg := &model.ChatMessage{
		ConversationId: convID,
		Role:           "assistant",
		Content:        "",
		Status:         "streaming",
		Version:        1,
	}
	if err := assistantMsg.Create(aiCtx); err != nil {
		h.sendError(client, fmt.Sprintf("创建消息失败: %v", err))
		return
	}
	assistantMsgID := assistantMsg.Id
	aiAgentConn.MessageID = assistantMsgID

	// 4. 发回 send_ack（让 client 创建新占位消息）
	h.sendToClient(client, &response.WSEnvelope{
		Type: "chat.send_ack",
		From: "backend",
		To:   "client",
		Payload: map[string]any{
			"message_id":      assistantMsgID,
			"conversation_id": convID,
		},
		Meta: &response.WSMeta{
			ConversationID: convID,
			MessageID:      assistantMsgID,
			UserID:         client.UserID,
		},
	})

	// 5. 构建 LLM 上下文（不含当前轮结果）
	llmMessages, err := buildLLMMessages(aiCtx, conversation)
	if err != nil {
		if uerr := updateMessageStatus(writeCtx, assistantMsgID, "error", fmt.Sprintf("构建上下文失败: %v", err)); uerr != nil {
			logger.Errorf("[Hub] 构建上下文失败更新消息状态出错: message_id=%d, err=%v", assistantMsgID, uerr)
		}
		h.sendError(client, fmt.Sprintf("构建上下文失败: %v", err))
		return
	}

	// 6. 注入命令执行结果到 system message
	llmMessages = injectCommandResultsIntoMessages(llmMessages, resultsRaw)

	// 7. 加载模型配置
	modelConfig, err := loadModelConfig(aiCtx, conversation.ModelId, client.UserID)
	if err != nil {
		if uerr := updateMessageStatus(writeCtx, assistantMsgID, "error", fmt.Sprintf("加载模型配置失败: %v", err)); uerr != nil {
			logger.Errorf("[Hub] 加载模型配置失败更新消息状态出错: message_id=%d, err=%v", assistantMsgID, uerr)
		}
		h.sendError(client, fmt.Sprintf("加载模型配置失败: %v", err))
		return
	}

	// 8. 查询技能 + RAG 上下文
	var skills []response.SkillInfo
	if skillList, err := model.MResSkills.ListEnabledByUserId(aiCtx, client.UserID); err == nil {
		for _, s := range skillList {
			skills = append(skills, response.SkillInfo{
				Name:        s.Name,
				Description: s.Description,
				ObjectKey:   s.ZipUrl,
			})
		}
	}
	ragContext, ragErr := resolveRagContextFromLatestMessage(aiCtx, convID, client.UserID)
	if ragErr != nil {
		logger.Warnf("[Hub] 解析 RAG 上下文失败: conversation_id=%d, user_id=%d, err=%v", convID, client.UserID, ragErr)
	}

	// 9. 调用 aiagent SSE 流
	fullContent, commands, proxyErr := h.proxyAiAgentStream(aiCtx, convID, assistantMsgID, llmMessages, modelConfig, skills, client.UserID, false, ragContext, client)

	// 10. 处理结果
	if proxyErr != nil {
		if uerr := updateMessageStatus(writeCtx, assistantMsgID, "error", proxyErr.Error()); uerr != nil {
			logger.Errorf("[Hub] 流式失败更新消息状态出错: message_id=%d, err=%v", assistantMsgID, uerr)
		}
		h.sendError(client, proxyErr.Error())
	} else {
		// 保存 commands
		if len(commands) > 0 {
			cmdJSON, err := json.Marshal(commands)
			if err != nil {
				logger.Errorf("[Hub] 序列化 commands 失败: message_id=%d, err=%v", assistantMsgID, err)
			} else {
				cmdStr := string(cmdJSON)
				if uerr := model.MChatMessage.UpdateCommands(writeCtx, assistantMsgID, &cmdStr); uerr != nil {
					logger.Errorf("[Hub] 保存 commands 失败: message_id=%d, err=%v", assistantMsgID, uerr)
				}
			}
		}

		// 更新 MySQL
		if uerr := plugin.GetDB(writeCtx).Model(&model.ChatMessage{}).
			Where("id = ?", assistantMsgID).
			Updates(map[string]any{
				"content":    fullContent,
				"status":     "completed",
				"updated_at": time.Now(),
			}).Error; uerr != nil {
			logger.Errorf("[Hub] 更新助手消息失败: message_id=%d, err=%v", assistantMsgID, uerr)
		}

		// 发送完成事件
		donePayload := map[string]any{
			"full_content": fullContent,
			"message_id":   assistantMsgID,
		}
		if len(commands) > 0 {
			donePayload["commands"] = commands
		}
		h.sendToClient(client, &response.WSEnvelope{
			Type: "chat.done",
			From: "backend",
			To:   "client",
			Payload: donePayload,
			Meta: &response.WSMeta{
				ConversationID: convID,
				MessageID:      assistantMsgID,
				UserID:         client.UserID,
			},
		})
	}

	// 11. 更新会话
	if err := plugin.GetDB(writeCtx).Model(&model.ChatConversation{}).
		Where("id = ?", convID).
		UpdateColumn("message_count", gorm.Expr("message_count + 1")).Error; err != nil {
		logger.Errorf("[Hub] 更新会话消息计数失败: conversation_id=%d, err=%v", convID, err)
	}
	updateContextCache(writeCtx, client.UserID, convID)
	updateLastActive(writeCtx, client.UserID, convID)
}

// ========== Cancel 处理 ==========

func (h *Hub) handleCancel(client *ClientConnection, env *response.WSEnvelope) {
	convID := int64(0)
	if env.Meta != nil {
		convID = env.Meta.ConversationID
	}

	h.mu.Lock()
	if conn, ok := h.aiAgentConns[convID]; ok {
		// 只允许取消自己会话的流
		if conn.UserID == client.UserID {
			if conn.Cancel != nil {
				conn.Cancel()
			}
			delete(h.aiAgentConns, convID)
		}
	}
	h.mu.Unlock()
}

// ========== WS 连接生命周期（供路由器调用）==========

// ServeWS 处理完整的 WS 连接生命周期：注册 → readPump/writePump → 注销
func (h *Hub) ServeWS(conn *websocket.Conn, userID int64) {
	client := newClientConnection(h, conn, userID)

	h.Register(client)

	var wg sync.WaitGroup
	wg.Add(2)

	go func() {
		defer wg.Done()
		defer func() {
			if r := recover(); r != nil {
				logger.Errorf("[Hub] writePump panic: user_id=%d, err=%v", userID, r)
			}
		}()
		h.writePump(client)
	}()
	go func() {
		defer wg.Done()
		defer func() {
			if r := recover(); r != nil {
				logger.Errorf("[Hub] readPump panic: user_id=%d, err=%v", userID, r)
			}
		}()
		h.readPump(client)
	}()

	wg.Wait()
	// 双方泵退出后确保连接资源释放
	client.Close()
}

// ========== 辅助 ==========

func (h *Hub) sendToClient(client *ClientConnection, env *response.WSEnvelope) {
	data, err := json.Marshal(env)
	if err != nil {
		logger.Warnf("[Hub] 序列化消息失败: %v", err)
		return
	}

	// 非阻塞发送：缓冲区满时 drop-and-log，绝不在发送侧阻塞（背压）。
	// 连接已关闭（done）时直接丢弃，不再写入，避免向已关闭 channel 发送 panic。
	select {
	case <-client.done:
		return
	case client.Send <- data:
	default:
		logger.Warnf("[Hub] 客户端发送缓冲区满, 丢弃消息: user_id=%d, msg_type=%s, buf_len=%d",
			client.UserID, env.Type, len(client.Send))
	}
}

func (h *Hub) sendError(client *ClientConnection, msg string) {
	h.sendToClient(client, &response.WSEnvelope{
		Type: "chat.error",
		From: "backend",
		To:   "client",
		Payload: map[string]any{
			"error": msg,
		},
	})
}

// parseSendRequest 从 WS 消息 payload 解析 ChatSendRequest
func parseSendRequest(payload map[string]any) (*request.ChatSendRequest, error) {
	data, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}
	var req request.ChatSendRequest
	if err := json.Unmarshal(data, &req); err != nil {
		return nil, err
	}
	if req.UserId <= 0 {
		return nil, errors.New("userId 不能为空")
	}
	return &req, nil
}

// injectCommandResultsIntoMessages 将命令执行结果注入到 messages 的 system prompt 中
func injectCommandResultsIntoMessages(messages []map[string]string, resultsRaw any) []map[string]string {
	resultsBlock := "\n\n## 命令执行结果\n"

	resultsList, ok := resultsRaw.([]any)
	if ok {
		for i, r := range resultsList {
			rmap, _ := r.(map[string]any)
			exitCode := -1
			stdout := ""
			stderr := ""
			if rmap != nil {
				if ec, ok := rmap["exitCode"].(float64); ok {
					exitCode = int(ec)
				}
				stdout, _ = rmap["stdout"].(string)
				stderr, _ = rmap["stderr"].(string)
			}
			resultsBlock += fmt.Sprintf(
				"命令 %d:\n退出码: %d\nstdout: %s\nstderr: %s\n",
				i+1, exitCode, stdout, stderr,
			)
		}
	}

	resultsBlock += "\n以上是命令执行结果。" +
		"请根据结果判断：如果任务已完成，直接给用户生成最终回复总结完成的内容；" +
		"如果还需要更多步骤（如继续写入文件、读取状态等），可以生成新命令继续执行。" +
		"注意：不要重复执行已经成功的命令。\n"

	// 注入到已有的 system message
	for _, msg := range messages {
		if msg["role"] == "system" {
			msg["content"] += resultsBlock
			return messages
		}
	}

	// 没有 system message 时新建
	result := make([]map[string]string, 0, len(messages)+1)
	result = append(result, map[string]string{"role": "system", "content": resultsBlock})
	result = append(result, messages...)
	return result
}

