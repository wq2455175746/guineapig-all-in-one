package request

import "time"

// ConversationHistoryListRequest 对话历史列表请求（offset 分页）
type ConversationHistoryListRequest struct {
	UserId   int64  `json:"user_id" query:"user_id"`
	PageSize int    `json:"pageSize" query:"pageSize"`
	PageNum  int    `json:"pageNum" query:"pageNum"`
	Keywords string `json:"keywords" query:"keywords"`
}

// MemoryListRequest 记忆列表请求
type MemoryListRequest struct {
	UserId   int64  `json:"user_id" query:"user_id"`
	PageSize int    `json:"pageSize" query:"pageSize"`
	PageNum  int    `json:"pageNum" query:"pageNum"`
	Keywords string `json:"keywords" query:"keywords"`
}

// MemoryDeleteRequest 删除记忆请求
type MemoryDeleteRequest struct {
	Id     int64 `json:"id,string"`
	UserId int64 `json:"user_id,string"`
}

// MemorySummarizeRequest 记忆归纳请求
type MemorySummarizeRequest struct {
	UserId int64  `json:"user_id,string"`
	Date   string `json:"date"` // format: "2006-01-02"
}

// MemoryUpdateContentRequest aiagent 回调更新记忆内容
type MemoryUpdateContentRequest struct {
	Id               int64      `json:"id,string"`
	Name             string     `json:"name"`
	Mem              string     `json:"mem"`
	MemType          string     `json:"mem_type"`
	ConversationIds  string     `json:"conversation_ids"`
	SourceMsgCount   int        `json:"source_msg_count"`
	TimeRangeStartAt *time.Time `json:"time_range_start_at"`
	TimeRangeEndAt   *time.Time `json:"time_range_end_at"`
}
