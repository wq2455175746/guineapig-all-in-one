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
	"guineapig/internal/response"
	"guineapig/pkg/plugin"
	"guineapig/pkg/plugin/logger"
	"guineapig/pkg/utils"
	"io"
	"net/http"
	"strings"
	"time"
)

// ========== SSE 事件结构 ==========

// agentSSEEvent 表示 aiagent /agent/chat/stream 返回的 SSE 事件
type agentSSEEvent struct {
	Event string                 `json:"-"`    // event type (from "event:" line)
	Data  map[string]interface{} `json:"data"` // parsed JSON from "data:" line
}

// ========== Agent 代理流 — 调用 aiagent /agent/chat/stream ==========

// proxyAiAgentAgentStream 调用 aiagent 的 /agent/chat/stream SSE 端点，
// 逐事件代理到客户端 WebSocket。
// contentBuf 用于累积 content 事件的文本，可为 nil。
//
// 返回 agent 执行完成后的完整响应（包含 timeline），
// 或空 map（非 proceed 时 JSON 响应）。
func (h *Hub) proxyAiAgentAgentStream(
	ctx context.Context,
	conversationID, messageID int64,
	requestBody map[string]any,
	client *ClientConnection,
	userID int64,
	contentBuf *strings.Builder,
) (map[string]any, error) {

	baseURL := config.Global.AiAgent.BaseUrl
	if baseURL == "" {
		return nil, fmt.Errorf("AIAGENT_BASE_URL 未配置")
	}

	reqBody, err := json.Marshal(requestBody)
	if err != nil {
		return nil, fmt.Errorf("序列化 agent 请求失败: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost,
		baseURL+"/guineapig-aiagent/agent/chat/stream",
		bytes.NewReader(reqBody))
	if err != nil {
		return nil, fmt.Errorf("创建请求失败: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Accept", "text/event-stream")
	utils.AttachAiAgentAuth(httpReq)

	httpClient := utils.NewHTTPClient(300 * time.Second) // 5min（多步 DAG 执行）
	resp, err := httpClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("请求 aiagent agent 失败: %w", err)
	}
	defer resp.Body.Close()

	// 非 200 → 可能是 JSON 错误响应（非 proceed 等）
	if resp.StatusCode != 200 {
		respBody, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("aiagent agent 返回错误: %d, %s", resp.StatusCode, string(respBody))
	}

	// 检查 Content-Type 判断是 SSE 还是 JSON
	contentType := resp.Header.Get("Content-Type")
	if !strings.Contains(contentType, "text/event-stream") {
		// JSON 响应（非 proceed 的情况）
		respBody, _ := io.ReadAll(resp.Body)
		var jsonResp map[string]any
		if err := json.Unmarshal(respBody, &jsonResp); err == nil {
			// 直接以 JSON 格式返回给客户端
			h.sendToClient(client, &response.WSEnvelope{
				Type: "chat.agent_result",
				From: "aiagent",
				To:   "client",
				Payload: map[string]any{
					"type":    "json",
					"payload": jsonResp,
				},
				Meta: &response.WSMeta{
					ConversationID: conversationID,
					MessageID:      messageID,
					UserID:         userID,
				},
			})
			return jsonResp, nil
		}
		return nil, fmt.Errorf("aiagent 返回非 SSE 响应: %s", contentType)
	}

	// ── SSE 流解析 ──
	reader := bufio.NewReader(resp.Body)
	var currentEvent string
	var finalData map[string]any

	for {
		line, err := reader.ReadString('\n')
		if err != nil {
			if errors.Is(err, io.EOF) {
				break
			}
			return finalData, fmt.Errorf("读取 SSE 流失败: %w", err)
		}

		line = strings.TrimRight(line, "\r\n")

		if strings.HasPrefix(line, "event: ") {
			currentEvent = strings.TrimPrefix(line, "event: ")
			continue
		}

		if strings.HasPrefix(line, "data: ") {
			dataStr := strings.TrimPrefix(line, "data: ")
			var dataMap map[string]any
			if err := json.Unmarshal([]byte(dataStr), &dataMap); err != nil {
				logger.Warnf("[AgentProxy] SSE data 解析失败: %v, data=%s", err, dataStr[:min(len(dataStr), 100)])
				continue
			}

			if currentEvent == "" {
				continue
			}

			// 根据事件类型转发到 WS
			switch currentEvent {
			case "plan_ready":
				logger.Infof("[AgentProxy] 收到 plan_ready: conv_id=%d", conversationID)
				h.sendToClient(client, &response.WSEnvelope{
					Type: "chat.agent_plan",
					From: "aiagent",
					To:   "client",
					Payload: map[string]any{
						"original_intent": dataMap["original_intent"],
						"total_steps":     dataMap["total_steps"],
						"steps":           dataMap["steps"],
					},
					Meta: &response.WSMeta{
						ConversationID: conversationID,
						MessageID:      messageID,
						UserID:         userID,
					},
				})

			case "step_started":
				h.sendToClient(client, &response.WSEnvelope{
					Type: "chat.agent_step_started",
					From: "aiagent",
					To:   "client",
					Payload: map[string]any{
						"step_id":    dataMap["step_id"],
						"capability": dataMap["capability"],
						"action":     dataMap["action"],
						"step":       dataMap["step"],
					},
					Meta: &response.WSMeta{
						ConversationID: conversationID,
						MessageID:      messageID,
						UserID:         userID,
					},
				})

			case "step_completed":
				h.sendToClient(client, &response.WSEnvelope{
					Type: "chat.agent_step_completed",
					From: "aiagent",
					To:   "client",
					Payload: map[string]any{
						"step_id":        dataMap["step_id"],
						"result_summary": dataMap["result_summary"],
						"duration_ms":    dataMap["duration_ms"],
						"output_key":     dataMap["output_key"],
					},
					Meta: &response.WSMeta{
						ConversationID: conversationID,
						MessageID:      messageID,
						UserID:         userID,
					},
				})

			case "step_failed":
				h.sendToClient(client, &response.WSEnvelope{
					Type: "chat.agent_step_failed",
					From: "aiagent",
					To:   "client",
					Payload: map[string]any{
						"step_id":     dataMap["step_id"],
						"error":       dataMap["error"],
						"duration_ms": dataMap["duration_ms"],
						"step":        dataMap["step"],
					},
					Meta: &response.WSMeta{
						ConversationID: conversationID,
						MessageID:      messageID,
						UserID:         userID,
					},
				})

			case "step_awaiting_client":
				// 需要客户端执行 → 发送 delegate 事件
				h.sendToClient(client, &response.WSEnvelope{
					Type: "chat.agent_delegate",
					From: "aiagent",
					To:   "client",
					Payload: map[string]any{
						"step_id":    dataMap["step_id"],
						"capability": dataMap["capability"],
						"action":     dataMap["action"],
						"params":     dataMap["params"],
					},
					Meta: &response.WSMeta{
						ConversationID: conversationID,
						MessageID:      messageID,
						UserID:         userID,
					},
				})

			case "execution_complete":
				finalData = dataMap
				// 转发最终结果给客户端
				h.sendToClient(client, &response.WSEnvelope{
					Type: "chat.agent_execution_complete",
					From: "aiagent",
					To:   "client",
					Payload: map[string]any{
						"status":          dataMap["status"],
						"total_steps":     dataMap["total_steps"],
						"completed_steps": dataMap["completed_steps"],
						"duration_ms":     dataMap["duration_ms"],
						"summary":         dataMap["summary"],
						"timeline":        dataMap["timeline"],
					},
					Meta: &response.WSMeta{
						ConversationID: conversationID,
						MessageID:      messageID,
						UserID:         userID,
					},
				})

			case "content":
				content, _ := dataMap["content"].(string)
				if content != "" {
					if contentBuf != nil {
						contentBuf.WriteString(content)
					}
					h.sendToClient(client, &response.WSEnvelope{
						Type: "chat.content",
						From: "aiagent",
						To:   "client",
						Payload: map[string]any{
							"content": content,
						},
						Meta: &response.WSMeta{
							ConversationID: conversationID,
							MessageID:      messageID,
							UserID:         userID,
						},
					})
				}

			case "log":
				h.sendToClient(client, &response.WSEnvelope{
					Type: "chat.agent_log",
					From: "aiagent",
					To:   "client",
					Payload: map[string]any{
						"step_id": dataMap["step_id"],
						"level":   dataMap["level"],
						"message": dataMap["message"],
					},
					Meta: &response.WSMeta{
						ConversationID: conversationID,
						MessageID:      messageID,
						UserID:         userID,
					},
				})

			case "rejected":
				h.sendToClient(client, &response.WSEnvelope{
					Type: "chat.agent_rejected",
					From: "aiagent",
					To:   "client",
					Payload: map[string]any{
						"reason":          dataMap["reason"],
						"original_intent": dataMap["original_intent"],
					},
					Meta: &response.WSMeta{
						ConversationID: conversationID,
						MessageID:      messageID,
						UserID:         userID,
					},
				})

			case "error":
				errMsg, _ := dataMap["message"].(string)
				h.sendToClient(client, &response.WSEnvelope{
					Type: "chat.agent_error",
					From: "aiagent",
					To:   "client",
					Payload: map[string]any{
						"error": errMsg,
					},
					Meta: &response.WSMeta{
						ConversationID: conversationID,
						MessageID:      messageID,
						UserID:         userID,
						Error:          errMsg,
					},
				})

			case "awaiting_confirmation":
				h.sendToClient(client, &response.WSEnvelope{
					Type: "chat.agent_awaiting_confirmation",
					From: "aiagent",
					To:   "client",
					Payload: map[string]any{
						"original_intent": dataMap["original_intent"],
						"total_steps":     dataMap["total_steps"],
						"steps":           dataMap["steps"],
					},
					Meta: &response.WSMeta{
						ConversationID: conversationID,
						MessageID:      messageID,
						UserID:         userID,
					},
				})
			}
		}
	}

	return finalData, nil
}

// ========== Agent Send 处理 ==========

// handleAgentSend 处理 agent 模式的消息发送
func (h *Hub) handleAgentSend(client *ClientConnection, env *response.WSEnvelope) {
	ctx := context.Background()

	// 1. 解析 ChatSendRequest（复用标准 send 的请求格式）
	req, err := parseSendRequest(env.Payload)
	if err != nil {
		h.sendError(client, fmt.Sprintf("参数错误: %v", err))
		return
	}

	// 2. 创建/获取会话 + 用户消息（以 WS 连接鉴权身份覆盖 payload 中的 userId）
	req.UserId = client.UserID
	msgResp, err := SendChatMessage(ctx, req)
	if err != nil {
		h.sendError(client, fmt.Sprintf("创建消息失败: %v", err))
		return
	}

	convID := msgResp.ConversationId
	userMsgID := msgResp.MessageId

	// 3. 发回确认（让 client 创建 assistant placeholder）
	h.sendToClient(client, &response.WSEnvelope{
		Type: "chat.send_ack",
		From: "backend",
		To:   "client",
		Payload: map[string]any{
			"message_id":      userMsgID,
			"conversation_id": convID,
		},
		Meta: &response.WSMeta{
			ConversationID: convID,
			MessageID:      userMsgID,
			UserID:         client.UserID,
		},
	})

	// 保存用户配置到 Redis（供飞书等外部渠道读取）
	if err := SetUserChatConfig(ctx, client.UserID, req.ModelId, req.WebSearchEnabled, req.AgentModeEnabled); err != nil {
		logger.Warnf("[Agent] 保存用户聊天配置失败: user_id=%d, err=%v", client.UserID, err)
	}

	// 4. 加载三种记忆（按顺序：语言记忆 → 场景记忆 → 工作记忆）
	// 4a. 语言记忆（RAG）：从最新用户消息的附件解析知识库配置
	var ragContext *RagContext
	ragContext, ragErr := resolveRagContextFromLatestMessage(ctx, convID, client.UserID)
	if ragErr != nil {
		logger.Warnf("[Agent] 解析 RAG 上下文失败: conversation_id=%d, user_id=%d, err=%v", convID, client.UserID, ragErr)
	}

	// 4b. 场景记忆：加载用户活跃的 chat_memory 记录
	var sceneMemories []map[string]string
	{
		db := plugin.GetDB(ctx)
		var memories []model.ChatMemory
		if err := db.Where("user_id = ? AND is_active = 1 AND deleted_at IS NULL", client.UserID).
			Order("id DESC").Limit(10).Find(&memories).Error; err == nil && len(memories) > 0 {
			for _, m := range memories {
				memText := m.Mem
				if len([]rune(memText)) > 500 {
					memText = string([]rune(memText)[:500])
				}
				sceneMemories = append(sceneMemories, map[string]string{
					"type":    m.MemType,
					"name":    m.Name,
					"content": memText,
				})
			}
		}
	}

	// 4c. 工作记忆（对话历史）：加载最近的消息
	var conversationHistory []map[string]string
	{
		conversation, err := model.MChatConversation.FindById(ctx, convID)
		if err == nil && conversation != nil {
			llmMessages, err := buildLLMMessages(ctx, conversation)
			if err == nil {
				conversationHistory = llmMessages
			}
		}
	}

	logger.Infof("[AgentSend] 记忆加载完成: rag=%v, scene=%d, history=%d",
		ragContext != nil, len(sceneMemories), len(conversationHistory))

	// 5. 构建 agent 请求体
	// MCP 服务从数据库读取（res_mcps），不依赖前端传递
	mcpServers := h.loadUserMcpServers(client.UserID)

	// 技能列表（初始化为空 slice 避免序列化为 null）
	skills := make([]map[string]any, 0)
	if skillList, ok := env.Payload["skills"].([]any); ok {
		for _, s := range skillList {
			if sm, ok := s.(map[string]any); ok {
				skills = append(skills, sm)
			}
		}
	}

	// 构建请求体 — aiagent 的 /agent/chat/stream 参数格式
	agentReq := map[string]any{
		"message":              req.Content,
		"user_id":              client.UserID,
		"session_id":           fmt.Sprintf("conv_%d", convID),
		"conversation_history": conversationHistory,
		"mcp_servers":          mcpServers,
		"skills":               skills,
		"rag_context":          ragContext,
		"scene_memory":         sceneMemories,
	}

	logger.Infof("[AgentSend] 请求 aiagent agent: user_id=%d, conv_id=%d, content='%s'",
		client.UserID, convID, truncateString(req.Content, 50))

	// 5. 可取消的 aiagent 请求上下文：随 WS 连接生命周期取消（断开即停），
	//    同时注册 AiAgentConn 供 handleCancel / Unregister 取消
	aiCtx, cancel := h.newClientStreamContext(client)
	aiAgentConn := &AiAgentConn{
		ConversationID: convID,
		MessageID:      userMsgID,
		UserID:         client.UserID,
		Cancel:         cancel,
	}
	h.mu.Lock()
	h.aiAgentConns[convID] = aiAgentConn
	h.mu.Unlock()

	// 6. 异步调用 aiagent
	go func() {
		defer func() {
			if r := recover(); r != nil {
				logger.Errorf("[AgentSend] goroutine panic: user_id=%d, conv_id=%d, err=%v", client.UserID, convID, r)
			}
		}()
		defer func() {
			cancel()
			h.mu.Lock()
			if cur, ok := h.aiAgentConns[convID]; ok && cur == aiAgentConn {
				delete(h.aiAgentConns, convID)
			}
			h.mu.Unlock()
		}()
		var contentBuf strings.Builder
		finalData, proxyErr := h.proxyAiAgentAgentStream(
			aiCtx, convID, userMsgID, agentReq, client, client.UserID, &contentBuf,
		)

		if proxyErr != nil {
			logger.Errorf("[AgentSend] aiagent 代理失败: conv_id=%d, err=%v", convID, proxyErr)
			h.sendError(client, fmt.Sprintf("Agent 处理失败: %v", proxyErr))
		} else {
			// 保存 assistant 消息到数据库
			fullContent := contentBuf.String()
			assistantMsg := &model.ChatMessage{
				ConversationId: convID,
				Role:           "assistant",
				Content:        fullContent,
				Status:         "completed",
				Version:        1,
			}
			if err := assistantMsg.Create(ctx); err != nil {
				logger.Errorf("[AgentSend] 保存 assistant 消息失败: conv_id=%d, err=%v", convID, err)
			}

			// 发送完成事件
			donePayload := map[string]any{
				"full_content": fullContent,
				"message_id":   userMsgID,
				"agent_result": finalData,
			}
			h.sendToClient(client, &response.WSEnvelope{
				Type:    "chat.done",
				From:    "backend",
				To:      "client",
				Payload: donePayload,
				Meta: &response.WSMeta{
					ConversationID: convID,
					MessageID:      userMsgID,
					UserID:         client.UserID,
				},
			})
		}
	}()
}

// ========== Agent 委托结果处理 ==========

// handleAgentDelegateResult 处理客户端回传的委托执行结果
func (h *Hub) handleAgentDelegateResult(client *ClientConnection, env *response.WSEnvelope) {
	stepID, _ := env.Payload["step_id"].(string)
	capability, _ := env.Payload["capability"].(string)
	result, _ := env.Payload["result"].(map[string]any)
	errorStr, _ := env.Payload["error"].(string)

	convID := int64(0)
	if env.Meta != nil {
		convID = env.Meta.ConversationID
	}

	if stepID == "" {
		h.sendError(client, "缺少 step_id")
		return
	}

	logger.Infof("[AgentDelegate] 收到委托结果: conv_id=%d, step=%s, cap=%s, error=%s",
		convID, stepID, capability, truncateString(errorStr, 100))

	// 1. 发送确认给客户端
	h.sendToClient(client, &response.WSEnvelope{
		Type: "chat.agent_delegate_ack",
		From: "backend",
		To:   "client",
		Payload: map[string]any{
			"step_id":    stepID,
			"capability": capability,
			"accepted":   true,
		},
		Meta: &response.WSMeta{
			ConversationID: convID,
			UserID:         client.UserID,
		},
	})

	// 2. 转发结果到 aiagent（解除 executor 的 delegate 等待）
	sessionID := fmt.Sprintf("conv_%d", convID)
	err := h.callAiAgentAgentControl("/guineapig-aiagent/agent/chat/delegate-result", map[string]any{
		"session_id": sessionID,
		"step_id":    stepID,
		"capability": capability,
		"result":     result,
		"error":      errorStr,
	})
	if err != nil {
		logger.Errorf("[AgentDelegate] 转发结果到 aiagent 失败: conv_id=%d, step=%s, err=%v",
			convID, stepID, err)
	}
}

// ========== Agent 控制信号处理 ==========

// callAiAgentAgentControl 发送控制信号到 aiagent 控制端点
func (h *Hub) callAiAgentAgentControl(path string, body map[string]any) error {
	baseURL := config.Global.AiAgent.BaseUrl
	if baseURL == "" {
		return fmt.Errorf("AIAGENT_BASE_URL 未配置")
	}

	reqBody, err := json.Marshal(body)
	if err != nil {
		return fmt.Errorf("序列化控制请求失败: %w", err)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost,
		baseURL+path,
		bytes.NewReader(reqBody))
	if err != nil {
		return fmt.Errorf("创建控制请求失败: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")
	utils.AttachAiAgentAuth(httpReq)

	httpClient := utils.NewHTTPClient(10 * time.Second)
	resp, err := httpClient.Do(httpReq)
	if err != nil {
		return fmt.Errorf("发送控制信号失败: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("aiagent 控制端点返回错误: %d, %s", resp.StatusCode, string(respBody))
	}

	return nil
}

// handleAgentConfirm 处理用户确认执行计划
func (h *Hub) handleAgentConfirm(client *ClientConnection, env *response.WSEnvelope) {
	convID := int64(0)
	if env.Meta != nil {
		convID = env.Meta.ConversationID
	}

	sessionID := fmt.Sprintf("conv_%d", convID)
	logger.Infof("[AgentControl] 确认执行: conv_id=%d, session=%s", convID, sessionID)

	err := h.callAiAgentAgentControl("/guineapig-aiagent/agent/chat/confirm", map[string]any{
		"session_id": sessionID,
	})
	if err != nil {
		logger.Errorf("[AgentControl] 确认请求失败: %v", err)
		h.sendError(client, fmt.Sprintf("确认执行失败: %v", err))
	}
}

// handleAgentCancel 处理用户取消执行
func (h *Hub) handleAgentCancel(client *ClientConnection, env *response.WSEnvelope) {
	convID := int64(0)
	if env.Meta != nil {
		convID = env.Meta.ConversationID
	}

	sessionID := fmt.Sprintf("conv_%d", convID)
	logger.Infof("[AgentControl] 取消执行: conv_id=%d, session=%s", convID, sessionID)

	err := h.callAiAgentAgentControl("/guineapig-aiagent/agent/chat/cancel", map[string]any{
		"session_id": sessionID,
	})
	if err != nil {
		logger.Errorf("[AgentControl] 取消请求失败: %v", err)
	}
}

// handleAgentSkipStep 处理用户跳过步骤
func (h *Hub) handleAgentSkipStep(client *ClientConnection, env *response.WSEnvelope) {
	stepID, _ := env.Payload["step_id"].(string)
	convID := int64(0)
	if env.Meta != nil {
		convID = env.Meta.ConversationID
	}

	logger.Infof("[AgentControl] 跳过步骤: conv_id=%d, step=%s", convID, stepID)

	// 跳过步骤 = 投递一个带 error 的 delegate 结果
	sessionID := fmt.Sprintf("conv_%d", convID)
	err := h.callAiAgentAgentControl("/guineapig-aiagent/agent/chat/delegate-result", map[string]any{
		"session_id": sessionID,
		"step_id":    stepID,
		"capability": "",
		"result":     map[string]any{},
		"error":      "user_skipped",
	})
	if err != nil {
		logger.Errorf("[AgentControl] 跳过步骤请求失败: %v", err)
	}
}

// handleAgentModifyStep 处理用户修改步骤参数
func (h *Hub) handleAgentModifyStep(client *ClientConnection, env *response.WSEnvelope) {
	stepID, _ := env.Payload["step_id"].(string)
	params, _ := env.Payload["params"].(map[string]any)
	convID := int64(0)
	if env.Meta != nil {
		convID = env.Meta.ConversationID
	}

	logger.Infof("[AgentControl] 修改步骤参数: conv_id=%d, step=%s", convID, stepID)

	// 投递修改后的参数作为 delegate 结果
	sessionID := fmt.Sprintf("conv_%d", convID)
	err := h.callAiAgentAgentControl("/guineapig-aiagent/agent/chat/delegate-result", map[string]any{
		"session_id": sessionID,
		"step_id":    stepID,
		"capability": "",
		"result": map[string]any{
			"modified_params": params,
			"note":            "参数已由用户修改",
		},
		"error": "",
	})
	if err != nil {
		logger.Errorf("[AgentControl] 修改步骤请求失败: %v", err)
	}
}

// handleAgentIntervene 处理用户的干预操作（暂停/继续/全部取消）
func (h *Hub) handleAgentIntervene(client *ClientConnection, env *response.WSEnvelope) {
	action, _ := env.Payload["action"].(string)
	convID := int64(0)
	if env.Meta != nil {
		convID = env.Meta.ConversationID
	}

	logger.Infof("[AgentControl] 干预操作: conv_id=%d, action=%s", convID, action)

	if action == "cancel-all" {
		sessionID := fmt.Sprintf("conv_%d", convID)
		err := h.callAiAgentAgentControl("/guineapig-aiagent/agent/chat/cancel", map[string]any{
			"session_id": sessionID,
		})
		if err != nil {
			logger.Errorf("[AgentControl] 取消请求失败: %v", err)
		}
	}
	// pause / resume 暂只做前端状态管理，不通知 aiagent
}

// ========== 辅助函数 ==========

// loadUserMcpServers 从数据库加载用户的启用 MCP 服务，格式化为 aiagent MCPToolSchema
func (h *Hub) loadUserMcpServers(userID int64) []map[string]any {
	servers := make([]map[string]any, 0)
	if userID <= 0 {
		return servers
	}

	ctx := context.Background()
	db := plugin.GetDB(ctx)
	if db == nil {
		logger.Warnf("[Agent] DB 未初始化，无法加载 MCP 服务")
		return servers
	}

	var items []*model.ResMcp
	if err := db.Model(&model.ResMcp{}).
		Where("user_id = ? AND status = 1 AND deleted_at IS NULL", userID).
		Find(&items).Error; err != nil {
		logger.Warnf("[Agent] 查询 MCP 列表失败: %v", err)
		return servers
	}

	// 传输类型映射
	typeMap := map[string]string{
		"stdio":          "stdio",
		"sse":            "sse",
		"streamablehttp": "streamable_http",
	}

	for _, item := range items {
		// 解析 tools JSON（包含 name / description / input_schema）
		tools := make([]map[string]any, 0)
		if item.McpTools != nil && *item.McpTools != "" {
			var parsed []map[string]any
			if err := json.Unmarshal([]byte(*item.McpTools), &parsed); err == nil {
				for _, t := range parsed {
					name, _ := t["name"].(string)
					if name == "" {
						continue
					}
					desc, _ := t["description"].(string)
					tool := map[string]any{
						"name":        name,
						"description": desc,
					}
					// 保留完整 input_schema（含参数签名），
					// 供 aiagent DAG 生成时构造正确的工具调用参数（含 stdio 类型）
					if schema, ok := t["input_schema"]; ok && schema != nil {
						tool["input_schema"] = schema
					}
					tools = append(tools, tool)
				}
			}
		}

		transportType := typeMap[item.McpType]
		if transportType == "" {
			transportType = item.McpType
		}

		// 从 mcp_body 解析连接信息：非 stdio → url/headers；stdio → command/args/env
		mcpURL := ""
		headers := make(map[string]any)
		command := ""
		args := make([]string, 0)
		env := make(map[string]string)
		if item.McpBody != nil && *item.McpBody != "" {
			var bodyMap map[string]any
			if err := json.Unmarshal([]byte(*item.McpBody), &bodyMap); err == nil {
				if transportType == "stdio" {
					if c, ok := bodyMap["command"].(string); ok {
						command = c
					}
					if a, ok := bodyMap["args"].([]any); ok {
						for _, av := range a {
							if s, ok := av.(string); ok {
								args = append(args, s)
							}
						}
					}
					if e, ok := bodyMap["env"].(map[string]any); ok {
						for k, v := range e {
							if s, ok := v.(string); ok {
								env[k] = s
							}
						}
					}
				} else {
					if u, ok := bodyMap["url"].(string); ok {
						mcpURL = u
					}
					if h, ok := bodyMap["headers"].(map[string]any); ok {
						headers = h
					}
				}
			}
		}

		serverEntry := map[string]any{
			"server_name":    item.Name,
			"transport_type": transportType,
			"mcp_url":        mcpURL,
			"headers":        headers,
			"tools":          tools,
		}
		if command != "" {
			serverEntry["command"] = command
			serverEntry["args"] = args
			serverEntry["env"] = env
		}
		servers = append(servers, serverEntry)
	}

	logger.Infof("[Agent] 加载用户 MCP 服务: user_id=%d, count=%d", userID, len(servers))
	return servers
}

func truncateString(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen] + "..."
}
