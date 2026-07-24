package response

import "time"

// WebSocket 通用消息信封
type WSEnvelope struct {
	Type    string         `json:"type"`    // chat.send / chat.content / chat.command / chat.command_result / chat.done / chat.error / chat.cancel / ping / pong
	From    string         `json:"from"`    // client / backend / aiagent
	To      string         `json:"to"`      // client / aiagent
	Payload map[string]any `json:"payload"`
	Meta    *WSMeta        `json:"meta,omitempty"`
}

type WSMeta struct {
	ConversationID int64  `json:"conversation_id,string,omitempty"`
	MessageID      int64  `json:"message_id,string,omitempty"`
	UserID         int64  `json:"user_id,string,omitempty"`
	SessionID      string `json:"session_id,omitempty"`
	Error          string `json:"error,omitempty"`
}

// 命令执行结果项（从 Client 回传）
type CommandResultItem struct {
	Index    int    `json:"index"`
	Stdout   string `json:"stdout"`
	Stderr   string `json:"stderr"`
	ExitCode int    `json:"exitCode"`
}

type ChatMessageResponse struct {
	MessageId      int64            `json:"messageId,string"`
	ConversationId int64            `json:"conversationId,string"`
	Its            int64            `json:"its"`
	UserId         int64            `json:"userId,string"`
	DeviceId       string           `json:"deviceId"`
	Role           string           `json:"role"`
	Content        string           `json:"content"`
	Attachments    []AttachmentItem `json:"attachments"`
}

type AttachmentItem struct {
	Id        int64  `json:"id,string"`
	Type      string `json:"type"`
	URL       string `json:"url"`
	Name      string `json:"name"`
	Size      int64  `json:"size"`
	LocalPath string `json:"localPath,omitempty"` // 本地缓存路径，用于音频播放
}

// ConversationItem 会话列表项
type ConversationItem struct {
	Id                 int64      `json:"id,string"`
	Title              string     `json:"title"`
	ModelId            int64      `json:"modelId,string"`
	MessageCount       int        `json:"messageCount"`
	Status             string     `json:"status"`
	StartAt            *time.Time `json:"startAt"`
	EndAt              *time.Time `json:"endAt"`
	CreatedAt          time.Time  `json:"createdAt"`
	UpdatedAt          time.Time  `json:"updatedAt"`
	LastMessagePreview string     `json:"lastMessagePreview"`
}

// PaginatedResponse 游标分页通用响应
type PaginatedResponse struct {
	Items      interface{} `json:"items"`
	HasMore    bool        `json:"hasMore"`
	NextCursor string      `json:"nextCursor"`
}

// MessageItem 消息列表项
type MessageItem struct {
	Id             int64     `json:"id,string"`
	ConversationId int64     `json:"conversationId,string"`
	Role           string    `json:"role"`
	Content        string    `json:"content"`
	Attachments    *string   `json:"attachments"`
	Commands       *string   `json:"commands"`
	Status         string    `json:"status"`
	TokenUsage     int       `json:"tokenUsage"`
	ResponseTimeMs int       `json:"responseTimeMs"`
	CreatedAt      time.Time `json:"createdAt"`
	UpdatedAt      time.Time `json:"updatedAt"`
}

// SkillInfo 用户已开启的 Skill 信息，传给 aiagent
type SkillInfo struct {
	Name        string `json:"name"`
	Description string `json:"description"`
	ObjectKey   string `json:"object_key"`
}

// CommandItem LLM 返回的待执行命令
type CommandItem struct {
	Type        string `json:"type"`
	Description string `json:"description"`
	Command     string `json:"command"`
	Cwd         string `json:"cwd,omitempty"`
	Risk        string `json:"risk"`
}

// ========== Agent 委托执行 ==========

// AgentDelegateStepPayload 委托客户端执行的步骤信息
type AgentDelegateStepPayload struct {
	StepID     string `json:"step_id"`
	Capability string `json:"capability"`
	Action     string `json:"action"`
	Params     any    `json:"params,omitempty"`
}

// AgentDelegateResultRequest 客户端回传的委托执行结果
type AgentDelegateResultRequest struct {
	StepID     string         `json:"step_id"`
	Capability string         `json:"capability"`
	Result     map[string]any `json:"result,omitempty"`
	Error      string         `json:"error,omitempty"`
}

