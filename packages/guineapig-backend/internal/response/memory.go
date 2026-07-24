package response

import "time"

// ConversationHistoryItem 对话历史列表项（offset 分页用）
type ConversationHistoryItem struct {
	Id           int64      `json:"id,string"`
	Title        string     `json:"title"`
	ModelId      int64      `json:"modelId,string"`
	ModelName    string     `json:"modelName"`
	Status       string     `json:"status"`
	MessageCount int        `json:"messageCount"`
	StartAt      *time.Time `json:"startAt"`
	EndAt        *time.Time `json:"endAt"`
	CreatedAt    time.Time  `json:"createdAt"`
	UpdatedAt    time.Time  `json:"updatedAt"`
}

// ConversationHistoryListResponse 对话历史列表响应
type ConversationHistoryListResponse struct {
	Items []ConversationHistoryItem `json:"items"`
	Total int64                     `json:"total"`
}

// MemoryItem 记忆列表项
type MemoryItem struct {
	Id               int64      `json:"id,string"`
	Name             string     `json:"name"`
	UserId           int64      `json:"user_id,string"`
	MemType          string     `json:"mem_type"`
	TimeRangeStartAt *time.Time `json:"time_range_start_at"`
	TimeRangeEndAt   *time.Time `json:"time_range_end_at"`
	SourceMsgCount   int        `json:"source_msg_count"`
	Mem              string     `json:"mem"`
	Version          int        `json:"version"`
	IsActive         int8       `json:"is_active"`
	CreatedAt        time.Time  `json:"created_at"`
	UpdatedAt        time.Time  `json:"updated_at"`
}

// MemoryListResponse 记忆列表响应
type MemoryListResponse struct {
	Items []MemoryItem `json:"items"`
	Total int64        `json:"total"`
}

// MemorySummarizeResponse 记忆归纳响应
type MemorySummarizeResponse struct {
	MemoryId int64 `json:"memory_id,string"`
}
