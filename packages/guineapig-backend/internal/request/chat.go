package request

type AttachmentItem struct {
	Id        int64  `json:"id,string"`            // 文件ID（嵌入文件用）
	Type      string `json:"type"`
	URL       string `json:"url"`
	Name      string `json:"name"`
	Size      int64  `json:"size"`
	LocalPath string `json:"localPath,omitempty"` // 本地缓存路径，用于音频播放
}

type ChatSendRequest struct {
	ReqMsgType       int              `json:"reqMsgType"`       // 0=文本, 1=音频
	UserId           int64            `json:"userId,string"`
	DeviceId         string           `json:"deviceId"`
	ModelId          int64            `json:"modelId,string"`    // 会话关联的模型ID
	ConversationId   int64            `json:"conversationId,string"` // 已有会话ID，新建时传0
	StartAt          int64            `json:"startAt"`          // 会话提交时间戳
	Content          string           `json:"content"`
	WebSearchEnabled bool             `json:"webSearchEnabled"` // 是否开启联网搜索
	AgentModeEnabled bool             `json:"agent_mode"`       // 是否启用 Agent 模式
	Attachments      []AttachmentItem `json:"attachments"`
}

// ConversationListRequest 会话列表游标分页请求
type ConversationListRequest struct {
	UserId int64  `query:"user_id"`
	Cursor string `query:"cursor"` // 游标：上一页最后一条的 updated_at (ISO8601)
	Limit  int    `query:"limit"`  // 每页条数，默认20
	Source string `query:"source"` // 按来源过滤：client | feishu | wechat | dingtalk
}

// MessageListRequest 消息列表请求
type MessageListRequest struct {
	ConversationId int64 `query:"conversation_id"`
	Limit          int   `query:"limit"`  // 每页条数，默认100
	Cursor         int64 `query:"cursor"` // 游标：上一页最后一条消息的 id
}

