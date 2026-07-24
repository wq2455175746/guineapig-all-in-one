package request

// BotBindRequest 绑定 IM 平台 Bot
type BotBindRequest struct {
	UserId    int64  `json:"user_id,string"`
	Platform  string `json:"platform"` // feishu | wechat | dingtalk
	AppId     string `json:"app_id"`
	AppSecret string `json:"app_secret"`
	BotName   string `json:"bot_name"`
	ExtraJSON string `json:"extra_config"`
}

// BotUnbindRequest 解绑 IM 平台 Bot
type BotUnbindRequest struct {
	UserId   int64  `json:"user_id,string"`
	Platform string `json:"platform"`
}

// BotInfoRequest 查询绑定信息
type BotInfoRequest struct {
	UserId   int64  `json:"user_id" query:"user_id"`
	Platform string `json:"platform" query:"platform"` // 不传返回全部
}

// BotBindingListRequest 分页查询绑定列表（管理后台用）
type BotBindingListRequest struct {
	UserId    int64  `json:"user_id" query:"user_id"`
	Platform  string `json:"platform" query:"platform"`
	BotStatus int    `json:"bot_status" query:"bot_status"`
	PageSize  int    `json:"pageSize" query:"pageSize"`
	PageNum   int    `json:"pageNum" query:"pageNum"`
}
