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
	"io"
	"log"
	"net/http"
	"time"

	"github.com/hibiken/asynq"
)

// ListConversationHistory 对话历史列表（offset 分页）
func ListConversationHistory(ctx context.Context, req *request.ConversationHistoryListRequest) (*response.ConversationHistoryListResponse, error) {
	pageSize := req.PageSize
	pageNum := req.PageNum
	if pageSize <= 0 {
		pageSize = 10
	}
	if pageNum <= 0 {
		pageNum = 1
	}

	type ConvRow struct {
		Id           int64
		Title        string
		ModelId      int64
		Status       string
		MessageCount int
		StartAt      *time.Time
		EndAt        *time.Time
		CreatedAt    time.Time
		UpdatedAt    time.Time
		ModelName    string
	}

	db := plugin.GetDB(ctx).Table("chat_conversations c").
		Select("c.*, COALESCE(m.model_name, '') as model_name").
		Joins("LEFT JOIN user_aimodel m ON c.model_id = m.id").
		Where("c.status = 'active'")
	if req.UserId > 0 {
		db = db.Where("c.user_id = ?", req.UserId)
	}

	if req.Keywords != "" {
		searchKey := "%" + req.Keywords + "%"
		db = db.Where("c.title LIKE ?", searchKey)
	}

	var total int64
	countDb := plugin.GetDB(ctx).Model(&model.ChatConversation{}).
		Where("status = 'active'")
	if req.UserId > 0 {
		countDb = countDb.Where("user_id = ?", req.UserId)
	}
	if req.Keywords != "" {
		searchKey := "%" + req.Keywords + "%"
		countDb = countDb.Where("title LIKE ?", searchKey)
	}
	if err := countDb.Count(&total).Error; err != nil {
		return nil, fmt.Errorf("查询总数失败: %w", err)
	}

	offset := (pageNum - 1) * pageSize
	var rows []ConvRow
	if err := db.Offset(offset).Limit(pageSize).Order("c.updated_at DESC").Find(&rows).Error; err != nil {
		return nil, fmt.Errorf("查询对话历史失败: %w", err)
	}

	resItems := make([]response.ConversationHistoryItem, 0, len(rows))
	for _, r := range rows {
		resItems = append(resItems, response.ConversationHistoryItem{
			Id:           r.Id,
			Title:        r.Title,
			ModelId:      r.ModelId,
			ModelName:    r.ModelName,
			Status:       r.Status,
			MessageCount: r.MessageCount,
			StartAt:      r.StartAt,
			EndAt:        r.EndAt,
			CreatedAt:    r.CreatedAt,
			UpdatedAt:    r.UpdatedAt,
		})
	}

	return &response.ConversationHistoryListResponse{
		Items: resItems,
		Total: total,
	}, nil
}

// ListMemory 记忆列表
func ListMemory(ctx context.Context, req *request.MemoryListRequest) (*response.MemoryListResponse, error) {
	items, total, err := model.MChatMemory.List(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("查询记忆列表失败: %w", err)
	}

	resItems := make([]response.MemoryItem, 0, len(items))
	for _, item := range items {
		memContent := item.Mem
		// 截断过长的记忆内容用于列表展示
		if len(memContent) > 500 {
			memContent = memContent[:500]
		}
		resItems = append(resItems, response.MemoryItem{
			Id:               item.Id,
			Name:             item.Name,
			UserId:           item.UserId,
			MemType:          item.MemType,
			TimeRangeStartAt: item.TimeRangeStartAt,
			TimeRangeEndAt:   item.TimeRangeEndAt,
			SourceMsgCount:   item.SourceMsgCount,
			Mem:              memContent,
			Version:          item.Version,
			IsActive:         item.IsActive,
			CreatedAt:        item.CreatedAt,
			UpdatedAt:        item.UpdatedAt,
		})
	}

	return &response.MemoryListResponse{
		Items: resItems,
		Total: total,
	}, nil
}

// GetMemory 获取单条记忆
// requesterUserID 为 Token 推导的 caller identity（0 表示 admin 会话）；用户会话要求 requester == 资源属主。
func GetMemory(ctx context.Context, id int64, requesterUserID int64) (*response.MemoryItem, error) {
	m, err := model.MChatMemory.FindById(ctx, id)
	if err != nil {
		return nil, fmt.Errorf("查询记忆失败: %w", err)
	}
	if m == nil {
		return nil, errors.New("记忆不存在")
	}
	if requesterUserID > 0 && m.UserId != requesterUserID {
		return nil, errors.New("无权访问该记忆")
	}

	return &response.MemoryItem{
		Id:               m.Id,
		Name:             m.Name,
		UserId:           m.UserId,
		MemType:          m.MemType,
		TimeRangeStartAt: m.TimeRangeStartAt,
		TimeRangeEndAt:   m.TimeRangeEndAt,
		SourceMsgCount:   m.SourceMsgCount,
		Mem:              m.Mem,
		Version:          m.Version,
		IsActive:         m.IsActive,
		CreatedAt:        m.CreatedAt,
		UpdatedAt:        m.UpdatedAt,
	}, nil
}

// DeleteMemory 删除记忆
func DeleteMemory(ctx context.Context, req *request.MemoryDeleteRequest) error {
	if req.Id <= 0 {
		return errors.New("id 不能为空")
	}
	if req.UserId <= 0 {
		return errors.New("user_id 不能为空")
	}

	existing, err := model.MChatMemory.FindById(ctx, req.Id)
	if err != nil {
		return fmt.Errorf("查询记忆失败: %w", err)
	}
	if existing == nil {
		return errors.New("记录不存在")
	}
	if existing.UserId != req.UserId {
		return errors.New("无权操作该记录")
	}

	return model.MChatMemory.Delete(ctx, req.Id, req.UserId)
}

// MemoryBrief 已有的记忆摘要（用于 LLM 融合参考）
type MemoryBrief struct {
	Id               int64      `json:"id"`
	Name             string     `json:"name"`
	MemType          string     `json:"mem_type"`
	Mem              string     `json:"mem"`
	TimeRangeStartAt *time.Time `json:"time_range_start_at"`
	TimeRangeEndAt   *time.Time `json:"time_range_end_at"`
	Version          int        `json:"version"`
	CreatedAt        time.Time  `json:"created_at"`
}

// AiAgentMemoryRequest 转发到 aiagent 的记忆归类的参数
type AiAgentMemoryRequest struct {
	MemoryId         int64            `json:"memory_id"`
	MemoryIds        map[string]int64 `json:"memory_ids"`
	UserId           int64            `json:"user_id"`
	ModelInfo        *ModelInfo       `json:"model_info"`
	Conversations    []*ConvBrief     `json:"conversations"`
	Messages         []*MsgBrief      `json:"messages"`
	TimeRangeStart   string           `json:"time_range_start"`
	TimeRangeEnd     string           `json:"time_range_end"`
	ExistingMemories []*MemoryBrief   `json:"existing_memories"`
}

type ModelInfo struct {
	ApiKey    string `json:"api_key"`
	BaseUrl   string `json:"base_url"`
	ModelName string `json:"model_name"`
}

type ConvBrief struct {
	Id        int64  `json:"id"`
	Title     string `json:"title"`
	CreatedAt string `json:"created_at"`
}

type MsgBrief struct {
	ConversationId int64  `json:"conversation_id"`
	Role           string `json:"role"`
	Content        string `json:"content"`
	CreatedAt      string `json:"created_at"`
}

// CreateMemorySummary 创建记忆归纳
func CreateMemorySummary(ctx context.Context, req *request.MemorySummarizeRequest) (int64, error) {
	if req.UserId <= 0 {
		return 0, errors.New("user_id 不能为空")
	}
	if req.Date == "" {
		return 0, errors.New("date 不能为空")
	}

	// 1. 解析日期
	date, err := time.ParseInLocation("2006-01-02", req.Date, time.Local)
	if err != nil {
		return 0, fmt.Errorf("日期格式错误: %w", err)
	}

	// 2. 计算时间范围
	startTime := time.Date(date.Year(), date.Month(), date.Day(), 0, 0, 0, 0, time.Local)
	endTime := time.Date(date.Year(), date.Month(), date.Day(), 23, 59, 59, 0, time.Local)

	// 3. 校验结束时间不能超过今天 00:00
	todayStart := time.Now().In(time.Local).Truncate(24 * time.Hour)
	if endTime.After(todayStart) || endTime.Equal(todayStart) {
		return 0, errors.New("结束时间不能超过今天 00:00")
	}

	// 4. 查询对话列表
	type ConvRow struct {
		Id        int64
		Title     string
		CreatedAt time.Time
	}
	var convs []*ConvRow
	db := plugin.GetDB(ctx).Table("chat_conversations").
		Select("id, title, created_at").
		Where("user_id = ? AND status = 'active' AND created_at BETWEEN ? AND ?", req.UserId, startTime, endTime)
	if err := db.Find(&convs).Error; err != nil {
		return 0, fmt.Errorf("查询对话列表失败: %w", err)
	}
	if len(convs) == 0 {
		return 0, errors.New("该日期无对话记录")
	}

	// 5. 查询消息
	convIds := make([]int64, len(convs))
	for i, c := range convs {
		convIds[i] = c.Id
	}
	type MsgRow struct {
		ConversationId int64
		Role           string
		Content        string
		CreatedAt      time.Time
	}
	var msgs []*MsgRow
	if err := plugin.GetDB(ctx).Table("chat_messages").
		Select("conversation_id, role, content, created_at").
		Where("conversation_id IN ? AND created_at BETWEEN ? AND ?", convIds, startTime, endTime).
		Order("created_at ASC").
		Find(&msgs).Error; err != nil {
		return 0, fmt.Errorf("查询消息失败: %w", err)
	}

	// 5b. 查询过去15天的已有记忆（用于 LLM 融合参考）
	pastMemories, err := model.MChatMemory.ListRecentActive(ctx, req.UserId, 15)
	if err != nil {
		log.Printf("查询已有记忆失败（忽略）: %v", err)
	}
	existingBriefs := make([]*MemoryBrief, 0, len(pastMemories))
	memTruncateLimit := map[string]int{
		"daily_summary": 200,
		"topic_summary": 300,
		"key_fact":      300,
		"preference":    300,
	}
	for _, m := range pastMemories {
		limit, ok := memTruncateLimit[m.MemType]
		if !ok {
			limit = 300
		}
		memContent := m.Mem
		if len([]rune(memContent)) > limit {
			memContent = string([]rune(memContent)[:limit])
		}
		existingBriefs = append(existingBriefs, &MemoryBrief{
			Id:               m.Id,
			Name:             m.Name,
			MemType:          m.MemType,
			Mem:              memContent,
			TimeRangeStartAt: m.TimeRangeStartAt,
			TimeRangeEndAt:   m.TimeRangeEndAt,
			Version:          m.Version,
			CreatedAt:        m.CreatedAt,
		})
	}

	// 6. 查询第一个 LLM 模型
	aimodels, err := model.MUserAiModel.ListOptionsByType(ctx, req.UserId, "LLM")
	if err != nil {
		return 0, fmt.Errorf("查询AI模型失败: %w", err)
	}
	if len(aimodels) == 0 {
		return 0, errors.New("未找到可用的 LLM 模型")
	}
	aiModel := aimodels[0]

	// 7. 解密 api_key（数据库中为 RSA 加密存储）
	decryptedKey, err := DecryptApiKey(ctx, aiModel.Id, req.UserId)
	if err != nil {
		return 0, fmt.Errorf("解密API Key失败: %w", err)
	}

	// 8. 创建 4 个占位记忆记录（每种记忆类型一个）
	memTypes := []string{"daily_summary", "topic_summary", "key_fact", "preference"}
	memoryIds := make(map[string]int64, len(memTypes))
	for _, mt := range memTypes {
		id, err := model.MChatMemory.CreatePlaceholder(ctx, req.UserId, mt, startTime, endTime)
		if err != nil {
			return 0, fmt.Errorf("创建 %s 记忆记录失败: %w", mt, err)
		}
		memoryIds[mt] = id
	}

	// 9. 异步转发到 aiagent
	aiAgentReq := &AiAgentMemoryRequest{
		MemoryId:         memoryIds["daily_summary"],
		MemoryIds:        memoryIds,
		UserId:           req.UserId,
		ModelInfo: &ModelInfo{
			ApiKey:    decryptedKey,
			BaseUrl:   aiModel.ApiUrl,
			ModelName: aiModel.ModelName,
		},
		TimeRangeStart:   startTime.Format(time.RFC3339),
		TimeRangeEnd:     endTime.Format(time.RFC3339),
		ExistingMemories: existingBriefs,
	}
	for _, c := range convs {
		aiAgentReq.Conversations = append(aiAgentReq.Conversations, &ConvBrief{
			Id: c.Id, Title: c.Title, CreatedAt: c.CreatedAt.Format(time.RFC3339),
		})
	}
	for _, m := range msgs {
		aiAgentReq.Messages = append(aiAgentReq.Messages, &MsgBrief{
			ConversationId: m.ConversationId, Role: m.Role, Content: m.Content, CreatedAt: m.CreatedAt.Format(time.RFC3339),
		})
	}

	go func() {
		defer func() {
			if r := recover(); r != nil {
				log.Printf("panic in forwardToAiAgent: %v", r)
			}
		}()
		forwardCtx := context.Background()
		if err := forwardToAiAgent(forwardCtx, aiAgentReq); err != nil {
			log.Printf("转发记忆归纳到 aiagent 失败: %v", err)
		}
	}()

	return memoryIds["daily_summary"], nil
}

func forwardToAiAgent(ctx context.Context, req *AiAgentMemoryRequest) error {
	body, err := json.Marshal(req)
	if err != nil {
		return fmt.Errorf("序列化失败: %w", err)
	}

	aiAgentURL := config.Global.AiAgent.BaseUrl
	if aiAgentURL == "" {
		aiAgentURL = "http://localhost:8000"
	}

	url := fmt.Sprintf("%s/guineapig-aiagent/memory/summarize", aiAgentURL)

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return fmt.Errorf("创建请求失败: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")

	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(httpReq)
	if err != nil {
		return fmt.Errorf("请求 aiagent 失败: %w", err)
	}
	defer func() {
		io.Copy(io.Discard, resp.Body)
		resp.Body.Close()
	}()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("aiagent 返回非200状态码: %d", resp.StatusCode)
	}
	return nil
}

// UpdateMemoryContent 更新记忆内容（aiagent 回调）
func UpdateMemoryContent(ctx context.Context, req *request.MemoryUpdateContentRequest) error {
	if req.Id <= 0 {
		return errors.New("id 不能为空")
	}
	return model.MChatMemory.UpdateContent(ctx, req)
}

// MemorySummarizeTaskType Asynq 任务类型 — 每日记忆归纳
const MemorySummarizeTaskType = "memory:summarize"

// HandleMemorySummarizeTask Asynq 任务处理器 — 为所有用户执行昨日记忆归纳
func HandleMemorySummarizeTask(ctx context.Context, t *asynq.Task) error {
	logger.Infof("[MemorySummarize] Asynq 任务开始执行")

	userIds, err := model.MUser.FindAllUserIds(ctx)
	if err != nil {
		logger.Errorf("[MemorySummarize] 查询用户列表失败: %v", err)
		return fmt.Errorf("查询用户列表失败: %w", err)
	}
	if len(userIds) == 0 {
		logger.Infof("[MemorySummarize] 无活跃用户，跳过执行")
		return nil
	}

	yesterday := time.Now().AddDate(0, 0, -1).Format("2006-01-02")
	var successCount, failCount int

	for _, uid := range userIds {
		_, err := CreateMemorySummary(ctx, &request.MemorySummarizeRequest{
			UserId: uid,
			Date:   yesterday,
		})
		if err != nil {
			logger.Errorf("[MemorySummarize] 用户 %d 记忆归纳失败: %v", uid, err)
			failCount++
		} else {
			successCount++
		}
	}

	logger.Infof("[MemorySummarize] Asynq 任务执行完成: 成功=%d, 失败=%d", successCount, failCount)
	return nil
}
