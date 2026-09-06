package service

import (
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
	"time"

	"gorm.io/gorm"
)

// SendChatMessage 创建会话 + 用户消息，如为音频则调用 aiagent ASR 解析后返回
func SendChatMessage(ctx context.Context, req *request.ChatSendRequest) (*response.ChatMessageResponse, error) {
	if req.UserId <= 0 {
		return nil, errors.New("userId 不能为空")
	}
	if req.ModelId <= 0 {
		return nil, errors.New("modelId 不能为空")
	}
	if req.ReqMsgType == 0 && req.Content == "" {
		return nil, errors.New("文本消息 content 不能为空")
	}

	now := time.Now()

	// 1. 获取或创建会话
	var conversation *model.ChatConversation
	if req.ConversationId > 0 {
		// 使用已有会话
		var err error
		conversation, err = model.MChatConversation.FindById(ctx, req.ConversationId)
		if err != nil {
			return nil, fmt.Errorf("会话不存在: %w", err)
		}
		if conversation == nil {
			return nil, errors.New("会话不存在")
		}
		// 会话属主校验（req.UserId 已由鉴权中间件覆盖为 Token 身份）
		if conversation.UserId != req.UserId {
			return nil, errors.New("无权操作该会话")
		}
		// 更新会话时间
		conversation.UpdatedAt = now
		if err := plugin.GetDB(ctx).Model(&model.ChatConversation{}).
			Where("id = ?", conversation.Id).
			Update("updated_at", now).Error; err != nil {
			logger.Errorf("[SendChatMessage] 更新会话时间失败: conversation_id=%d, err=%v", conversation.Id, err)
		}
	} else {
		// 创建新会话
		title := req.Content
		if title == "" {
			title = "新对话"
		}
		if len([]rune(title)) > 50 {
			title = string([]rune(title)[:50])
		}
		// 去掉换行
		title = strings.Split(title, "\n")[0]

		startAt := time.UnixMilli(req.StartAt)
		if req.StartAt <= 0 {
			startAt = now
		}

		conversation = &model.ChatConversation{
			UserId:       req.UserId,
			Title:        title,
			ModelId:      req.ModelId,
			Status:       "active",
			MessageCount: 0,
			StartAt:      &startAt,
		}
		if err := conversation.Create(ctx); err != nil {
			return nil, fmt.Errorf("创建会话失败: %w", err)
		}
	}

	// 2. 序列化附件为 JSON
	var attachmentsJSON *string
	if len(req.Attachments) > 0 {
		b, err := json.Marshal(req.Attachments)
		if err != nil {
			return nil, fmt.Errorf("序列化附件失败: %w", err)
		}
		s := string(b)
		attachmentsJSON = &s
	}

	// 3. 创建用户消息
	content := req.Content
	msg := &model.ChatMessage{
		ConversationId: conversation.Id,
		Role:           "user",
		Content:        content,
		Attachments:    attachmentsJSON,
		Status:         "completed",
		Version:        1,
	}
	if err := msg.Create(ctx); err != nil {
		return nil, fmt.Errorf("创建消息失败: %w", err)
	}

	// 4. 如果是音频消息，调用 aiagent ASR
	if req.ReqMsgType == 1 {
		for _, att := range req.Attachments {
			if att.Type == "audio" && att.URL != "" {
				asrText, err := callAiAgentASR(ctx, att.URL)
				if err != nil {
					// ASR 失败不阻断，记录错误状态
					msg.Status = "error"
					msg.ErrorMessage = fmt.Sprintf("ASR 识别失败: %v", err)
					if uerr := updateMessageStatus(ctx, msg.Id, msg.Status, msg.ErrorMessage); uerr != nil {
						logger.Errorf("[SendChatMessage] ASR 失败更新消息状态出错: message_id=%d, err=%v", msg.Id, uerr)
					}
				} else {
					content = asrText
					msg.Content = asrText
					// 更新消息内容为 ASR 结果
					if uerr := updateMessageContent(ctx, msg.Id, asrText); uerr != nil {
						logger.Errorf("[SendChatMessage] 更新 ASR 消息内容失败: message_id=%d, err=%v", msg.Id, uerr)
					}
				}
				break // 只处理第一个音频附件
			}
		}
	}

	// 5. 更新会话消息计数（原子自增，避免并发覆盖）
	if err := plugin.GetDB(ctx).Model(&model.ChatConversation{}).
		Where("id = ?", conversation.Id).
		UpdateColumn("message_count", gorm.Expr("message_count + 1")).Error; err != nil {
		logger.Errorf("[SendChatMessage] 更新会话消息计数失败: conversation_id=%d, err=%v", conversation.Id, err)
	}

	// 6. 构建响应
	respItems := make([]response.AttachmentItem, 0, len(req.Attachments))
	for _, att := range req.Attachments {
		respItems = append(respItems, response.AttachmentItem{
			Type: att.Type,
			URL:  att.URL,
			Name: att.Name,
			Size: att.Size,
		})
	}

	return &response.ChatMessageResponse{
		MessageId:      msg.Id,
		ConversationId: conversation.Id,
		Its:            time.Now().UnixMilli(),
		UserId:         req.UserId,
		DeviceId:       req.DeviceId,
		Role:           "user",
		Content:        content,
		Attachments:    respItems,
	}, nil
}

// callAiAgentASR 调用 guineapig-aiagent 的 ASR 接口
func callAiAgentASR(ctx context.Context, objectKey string) (string, error) {
	baseURL := config.Global.AiAgent.BaseUrl
	if baseURL == "" {
		return "", errors.New("AIAGENT_BASE_URL 未配置")
	}

	reqBody, err := json.Marshal(map[string]string{
		"objectKey": objectKey,
	})
	if err != nil {
		return "", fmt.Errorf("序列化 ASR 请求失败: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost,
		baseURL+"/guineapig-aiagent/asr/transcribe",
		bytes.NewReader(reqBody))
	if err != nil {
		return "", fmt.Errorf("创建 ASR 请求失败: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")

	client := utils.NewHTTPClient(60 * time.Second)
	resp, err := client.Do(httpReq)
	if err != nil {
		return "", fmt.Errorf("ASR 请求失败: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", fmt.Errorf("读取 ASR 响应失败: %w", err)
	}

	if resp.StatusCode != 200 {
		return "", fmt.Errorf("ASR 返回非 200 状态码: %d, body: %s", resp.StatusCode, string(body))
	}

	// 解析 aiagent 响应：{"success":true,"errCode":0,"errMessage":"success","result":{"text":"..."}}
	var aiagentResp struct {
		Success    bool   `json:"success"`
		ErrCode    int    `json:"errCode"`
		ErrMessage string `json:"errMessage"`
		Result     *struct {
			Text string `json:"text"`
		} `json:"result"`
	}
	if err := json.Unmarshal(body, &aiagentResp); err != nil {
		return "", fmt.Errorf("解析 ASR 响应失败: %w", err)
	}

	if !aiagentResp.Success || aiagentResp.Result == nil {
		return "", fmt.Errorf("ASR 识别失败: %s", aiagentResp.ErrMessage)
	}

	return aiagentResp.Result.Text, nil
}

func updateMessageContent(ctx context.Context, msgId int64, content string) error {
	return plugin.GetDB(ctx).Model(&model.ChatMessage{}).
		Where("id = ?", msgId).
		Updates(map[string]any{
			"content":    content,
			"updated_at": time.Now(),
		}).Error
}

// ListConversations 游标分页查询会话列表
func ListConversations(ctx context.Context, req *request.ConversationListRequest) (*response.PaginatedResponse, error) {
	if req.UserId <= 0 {
		return nil, errors.New("userId 不能为空")
	}
	limit := req.Limit
	if limit <= 0 || limit > 100 {
		limit = 20
	}

	type ConvRow struct {
		model.ChatConversation
		LastMessagePreview string `gorm:"column:last_message_preview"`
	}

	db := plugin.GetDB(ctx)
	query := db.Table("chat_conversations c").
		Select("c.*, COALESCE((SELECT content FROM chat_messages WHERE conversation_id = c.id ORDER BY created_at DESC LIMIT 1), '暂无消息') AS last_message_preview").
		Where("c.user_id = ? AND c.status = 'active'", req.UserId)

	if req.Source != "" {
		query = query.Where("c.source = ?", req.Source)
	}

	if req.Cursor != "" {
		cursorTime, err := time.Parse(time.RFC3339, req.Cursor)
		if err == nil {
			query = query.Where("c.updated_at < ?", cursorTime)
		}
	}

	var rows []ConvRow
	if err := query.Order("c.updated_at DESC").Limit(limit + 1).Find(&rows).Error; err != nil {
		return nil, fmt.Errorf("查询会话列表失败: %w", err)
	}

	hasMore := len(rows) > limit
	if hasMore {
		rows = rows[:limit]
	}

	items := make([]response.ConversationItem, 0, len(rows))
	for _, r := range rows {
		items = append(items, response.ConversationItem{
			Id:                 r.Id,
			Title:              r.Title,
			ModelId:            r.ModelId,
			MessageCount:       r.MessageCount,
			Status:             r.Status,
			StartAt:            r.StartAt,
			EndAt:              r.EndAt,
			CreatedAt:          r.CreatedAt,
			UpdatedAt:          r.UpdatedAt,
			LastMessagePreview: r.LastMessagePreview,
		})
	}

	nextCursor := ""
	if hasMore && len(rows) > 0 {
		nextCursor = rows[len(rows)-1].UpdatedAt.Format(time.RFC3339)
	}

	return &response.PaginatedResponse{
		Items:      items,
		HasMore:    hasMore,
		NextCursor: nextCursor,
	}, nil
}

// ListMessages 加载指定会话的消息列表
// requesterUserID 为 Token 推导的 caller identity（0 表示 admin 会话）；用户会话要求会话属主 == requester。
func ListMessages(ctx context.Context, req *request.MessageListRequest, requesterUserID int64) (*response.PaginatedResponse, error) {
	if req.ConversationId <= 0 {
		return nil, errors.New("conversation_id 不能为空")
	}

	// 会话属主校验，杜绝跨用户读取消息
	if requesterUserID > 0 {
		conversation, err := model.MChatConversation.FindById(ctx, req.ConversationId)
		if err != nil || conversation == nil {
			return nil, errors.New("会话不存在")
		}
		if conversation.UserId != requesterUserID {
			return nil, errors.New("无权访问该会话")
		}
	}

	limit := req.Limit
	if limit <= 0 || limit > 200 {
		limit = 100
	}

	db := plugin.GetDB(ctx)
	query := db.Model(&model.ChatMessage{}).
		Where("conversation_id = ? AND status != 'deleted' ", req.ConversationId)

	if req.Cursor > 0 {
		query = query.Where("id < ?", req.Cursor)
	}

	var msgs []model.ChatMessage
	if err := query.Order("created_at DESC, version ASC").Limit(limit + 1).Find(&msgs).Error; err != nil {
		return nil, fmt.Errorf("查询消息列表失败: %w", err)
	}

	hasMore := len(msgs) > limit
	if hasMore {
		msgs = msgs[:limit]
	}

	// 逆序返回，使得前端按时间正序展示
	items := make([]response.MessageItem, 0, len(msgs))
	for i := len(msgs) - 1; i >= 0; i-- {
		m := msgs[i]
		items = append(items, response.MessageItem{
			Id:             m.Id,
			ConversationId: m.ConversationId,
			Role:           m.Role,
			Content:        m.Content,
			Attachments:    m.Attachments,
			Commands:       m.Commands,
			Status:         m.Status,
			TokenUsage:     m.TokenUsage,
			ResponseTimeMs: m.ResponseTimeMs,
			CreatedAt:      m.CreatedAt,
			UpdatedAt:      m.UpdatedAt,
		})
	}

	nextCursor := ""
	if hasMore && len(msgs) > 0 {
		nextCursor = fmt.Sprintf("%d", msgs[len(msgs)-1].Id)
	}

	return &response.PaginatedResponse{
		Items:      items,
		HasMore:    hasMore,
		NextCursor: nextCursor,
	}, nil
}

func updateMessageStatus(ctx context.Context, msgId int64, status, errMsg string) error {
	return plugin.GetDB(ctx).Model(&model.ChatMessage{}).
		Where("id = ?", msgId).
		Updates(map[string]any{
			"status":        status,
			"error_message": errMsg,
			"updated_at":    time.Now(),
		}).Error
}
