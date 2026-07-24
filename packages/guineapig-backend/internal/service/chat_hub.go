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
	"io"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"
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
	UserID   int64
	Conn     *websocket.Conn
	Send     chan []byte
	hub      *Hub
}

type AiAgentConn struct {
	ConversationID int64
	MessageID      int64
	Cancel         context.CancelFunc
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

	// 如果已有该用户的旧连接，关闭旧连接
	if old, ok := h.clients[client.UserID]; ok {
		close(old.Send)
		old.Conn.Close()
	}
	h.clients[client.UserID] = client
}

// Unregister 注销客户端 WS 连接
func (h *Hub) Unregister(userID int64) {
	h.mu.Lock()
	defer h.mu.Unlock()

	if client, ok := h.clients[userID]; ok {
		close(client.Send)
		delete(h.clients, userID)
	}

	// 清理该用户的所有活跃 AiAgent 连接
	for convID, conn := range h.aiAgentConns {
		if _, ok := h.clients[userID]; !ok {
			// 检查该 AiAgentConn 是否属于当前用户的会话
			// 这里简化处理：遍历时如果 client 不存在对应 aiAgentConn 则清理
			_ = convID
			if conn.Cancel != nil {
				conn.Cancel()
			}
			delete(h.aiAgentConns, convID)
		}
	}
}

// readPump 从 WS 读取消息（每客户端一个 goroutine）
func (h *Hub) readPump(client *ClientConnection) {
	defer func() {
		h.Unregister(client.UserID)
		client.Conn.Close()
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
	_ = SetUserChatConfig(ctx, client.UserID, req.ModelId, req.WebSearchEnabled, req.AgentModeEnabled)

	// 5. 异步流式回复
	go h.streamAssistantReply(ctx, client, req, msgResp)
}

// streamAssistantReply 异步执行 LLM 流式调用，结果通过 WS 推送
func (h *Hub) streamAssistantReply(ctx context.Context, client *ClientConnection, req *request.ChatSendRequest, msgResp *response.ChatMessageResponse) {
	convID := msgResp.ConversationId

	// 1. 加载会话
	conversation, err := model.MChatConversation.FindById(ctx, convID)
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
	if err := assistantMsg.Create(ctx); err != nil {
		h.sendError(client, fmt.Sprintf("创建消息失败: %v", err))
		return
	}
	assistantMsgID := assistantMsg.Id

	// 3. 构建 LLM 上下文
	llmMessages, err := buildLLMMessages(ctx, conversation)
	if err != nil {
		_ = updateMessageStatus(ctx, assistantMsgID, "error", fmt.Sprintf("构建上下文失败: %v", err))
		h.sendError(client, fmt.Sprintf("构建上下文失败: %v", err))
		return
	}

	// 4. 加载模型配置
	modelConfig, err := loadModelConfig(ctx, conversation.ModelId, client.UserID)
	if err != nil {
		_ = updateMessageStatus(ctx, assistantMsgID, "error", fmt.Sprintf("加载模型配置失败: %v", err))
		h.sendError(client, fmt.Sprintf("加载模型配置失败: %v", err))
		return
	}

	// 5. 查询技能 + RAG 上下文
	var skills []response.SkillInfo
	if skillList, err := model.MResSkills.ListEnabledByUserId(ctx, client.UserID); err == nil {
		for _, s := range skillList {
			skills = append(skills, response.SkillInfo{
				Name:        s.Name,
				Description: s.Description,
				ObjectKey:   s.ZipUrl,
			})
		}
	}

	ragContext, _ := resolveRagContextFromLatestMessage(ctx, convID, client.UserID)

	// 6. 可取消的 aiagent 请求上下文
	aiCtx, cancel := context.WithCancel(ctx)

	// 注册 AiAgentConn（用于后续 command_result 路由和取消）
	aiAgentConn := &AiAgentConn{
		ConversationID: convID,
		MessageID:      assistantMsgID,
		Cancel:         cancel,
	}
	h.mu.Lock()
	h.aiAgentConns[convID] = aiAgentConn
	h.mu.Unlock()

	var commands []response.CommandItem
	var fullContent string
	var proxyErr error

	// 清理函数（流完成时取消 context 并清理 AiAgentConn）
	cleanup := func() {
		cancel()
		h.mu.Lock()
		delete(h.aiAgentConns, convID)
		h.mu.Unlock()
	}

	// 7. 调用 aiagent SSE 流并代理到 WS
	fullContent, commands, proxyErr = h.proxyAiAgentStream(aiCtx, convID, assistantMsgID, llmMessages, modelConfig, skills, client.UserID, req.WebSearchEnabled, ragContext, client)

	// 8. 处理结果
	if proxyErr != nil {
		_ = updateMessageStatus(ctx, assistantMsgID, "error", proxyErr.Error())
		h.sendError(client, proxyErr.Error())
		// 出错时直接清理
		h.mu.Lock()
		delete(h.aiAgentConns, convID)
		h.mu.Unlock()
	} else {
		// 保存 commands
		if len(commands) > 0 {
			cmdJSON, _ := json.Marshal(commands)
			cmdStr := string(cmdJSON)
			_ = model.MChatMessage.UpdateCommands(ctx, assistantMsgID, &cmdStr)
		}

		// 更新 MySQL
		_ = plugin.GetDB(ctx).Model(&model.ChatMessage{}).
			Where("id = ?", assistantMsgID).
			Updates(map[string]any{
				"content":    fullContent,
				"status":     "completed",
				"updated_at": time.Now(),
			}).Error

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

	// 10. 清理（无 commands 时已删 AiAgentConn；有 commands 时保留，由 handleCommandResult 后续删除）
	cleanup()
	_ = plugin.GetDB(ctx).Model(&model.ChatConversation{}).
		Where("id = ?", convID).
		UpdateColumn("message_count", 1).Error
	updateContextCache(ctx, client.UserID, convID)
	updateLastActive(ctx, client.UserID, convID)
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

	reqBody, _ := json.Marshal(reqMap)

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost,
		baseURL+"/guineapig-aiagent/llm/chat/stream",
		bytes.NewReader(reqBody))
	if err != nil {
		return "", nil, fmt.Errorf("创建请求失败: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Accept", "text/event-stream")

	httpClient := &http.Client{Timeout: 120 * time.Second} // 2min（单轮 LLM 调用）
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
	ctx := context.Background()

	convID := int64(0)
	if env.Meta != nil {
		convID = env.Meta.ConversationID
	}
	if convID == 0 {
		h.sendError(client, "缺少 conversation_id")
		return
	}

	// 1. 提取 results
	resultsRaw, ok := env.Payload["results"]
	if !ok {
		h.sendError(client, "缺少 results 字段")
		return
	}

	// 2. 加载会话
	conversation, err := model.MChatConversation.FindById(ctx, convID)
	if err != nil || conversation == nil {
		h.sendError(client, "会话不存在")
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
	if err := assistantMsg.Create(ctx); err != nil {
		h.sendError(client, fmt.Sprintf("创建消息失败: %v", err))
		return
	}
	assistantMsgID := assistantMsg.Id

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
	llmMessages, err := buildLLMMessages(ctx, conversation)
	if err != nil {
		_ = updateMessageStatus(ctx, assistantMsgID, "error", fmt.Sprintf("构建上下文失败: %v", err))
		h.sendError(client, fmt.Sprintf("构建上下文失败: %v", err))
		return
	}

	// 6. 注入命令执行结果到 system message
	llmMessages = injectCommandResultsIntoMessages(llmMessages, resultsRaw)

	// 7. 加载模型配置
	modelConfig, err := loadModelConfig(ctx, conversation.ModelId, client.UserID)
	if err != nil {
		_ = updateMessageStatus(ctx, assistantMsgID, "error", fmt.Sprintf("加载模型配置失败: %v", err))
		h.sendError(client, fmt.Sprintf("加载模型配置失败: %v", err))
		return
	}

	// 8. 查询技能 + RAG 上下文
	var skills []response.SkillInfo
	if skillList, err := model.MResSkills.ListEnabledByUserId(ctx, client.UserID); err == nil {
		for _, s := range skillList {
			skills = append(skills, response.SkillInfo{
				Name:        s.Name,
				Description: s.Description,
				ObjectKey:   s.ZipUrl,
			})
		}
	}
	ragContext, _ := resolveRagContextFromLatestMessage(ctx, convID, client.UserID)

	// 9. 可取消的 aiagent 请求上下文
	aiCtx, cancel := context.WithCancel(ctx)
	aiAgentConn := &AiAgentConn{
		ConversationID: convID,
		MessageID:      assistantMsgID,
		Cancel:         cancel,
	}
	h.mu.Lock()
	h.aiAgentConns[convID] = aiAgentConn
	h.mu.Unlock()

	// 10. 调用 aiagent SSE 流
	fullContent, commands, proxyErr := h.proxyAiAgentStream(aiCtx, convID, assistantMsgID, llmMessages, modelConfig, skills, client.UserID, false, ragContext, client)

	// 清理 AiAgentConn
	h.mu.Lock()
	delete(h.aiAgentConns, convID)
	h.mu.Unlock()
	cancel()

	// 11. 处理结果
	if proxyErr != nil {
		_ = updateMessageStatus(ctx, assistantMsgID, "error", proxyErr.Error())
		h.sendError(client, proxyErr.Error())
	} else {
		// 保存 commands
		if len(commands) > 0 {
			cmdJSON, _ := json.Marshal(commands)
			cmdStr := string(cmdJSON)
			_ = model.MChatMessage.UpdateCommands(ctx, assistantMsgID, &cmdStr)
		}

		// 更新 MySQL
		_ = plugin.GetDB(ctx).Model(&model.ChatMessage{}).
			Where("id = ?", assistantMsgID).
			Updates(map[string]any{
				"content":    fullContent,
				"status":     "completed",
				"updated_at": time.Now(),
			}).Error

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

	// 12. 更新会话
	_ = plugin.GetDB(ctx).Model(&model.ChatConversation{}).
		Where("id = ?", convID).
		UpdateColumn("message_count", 1).Error
	updateContextCache(ctx, client.UserID, convID)
	updateLastActive(ctx, client.UserID, convID)
}

// ========== Cancel 处理 ==========

func (h *Hub) handleCancel(client *ClientConnection, env *response.WSEnvelope) {
	convID := int64(0)
	if env.Meta != nil {
		convID = env.Meta.ConversationID
	}

	h.mu.Lock()
	if conn, ok := h.aiAgentConns[convID]; ok {
		if conn.Cancel != nil {
			conn.Cancel()
		}
		delete(h.aiAgentConns, convID)
	}
	h.mu.Unlock()
}

// ========== WS 连接生命周期（供路由器调用）==========

// ServeWS 处理完整的 WS 连接生命周期：注册 → readPump/writePump → 注销
func (h *Hub) ServeWS(conn *websocket.Conn, userID int64) {
	client := &ClientConnection{
		UserID: userID,
		Conn:   conn,
		Send:   make(chan []byte, 256),
		hub:    h,
	}

	h.Register(client)

	var wg sync.WaitGroup
	wg.Add(2)

	go func() {
		defer wg.Done()
		h.writePump(client)
	}()
	go func() {
		defer wg.Done()
		h.readPump(client)
	}()

	wg.Wait()
}

// ========== 辅助 ==========

func (h *Hub) sendToClient(client *ClientConnection, env *response.WSEnvelope) {
	data, err := json.Marshal(env)
	if err != nil {
		logger.Warnf("[Hub] 序列化消息失败: %v", err)
		return
	}

	// 阻塞发送，超时 10s；防止缓冲区满时静默丢消息
	timer := time.NewTimer(10 * time.Second)
	defer timer.Stop()

	select {
	case client.Send <- data:
	case <-timer.C:
		logger.Errorf("[Hub] 客户端发送缓冲区满(超时10s): user_id=%d, msg_type=%s", client.UserID, env.Type)
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

