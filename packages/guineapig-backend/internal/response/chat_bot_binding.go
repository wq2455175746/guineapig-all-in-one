package response

import "time"

// BotBindingItem Bot 绑定信息
type BotBindingItem struct {
	Id          int64     `json:"id,string"`
	UserId      int64     `json:"user_id,string"`
	Platform    string    `json:"platform"`
	AppId       string    `json:"app_id"`
	AppSecret   string    `json:"app_secret"` // 掩码返回
	TenantKey   string    `json:"tenant_key"`
	BotStatus   int       `json:"bot_status"`
	BotName     string    `json:"bot_name"`
	Description string    `json:"description"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

// BotBindResponse 绑定结果
type BotBindResponse struct {
	Id        int64  `json:"id,string"`
	Platform  string `json:"platform"`
	BotStatus int    `json:"bot_status"`
}

// BotBindingListResponse 管理员 Bot 绑定列表
type BotBindingListResponse struct {
	Items []BotBindingItem `json:"items"`
	Total int64            `json:"total"`
}
