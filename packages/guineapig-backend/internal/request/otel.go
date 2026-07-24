package request

type OtelCreateRequest struct {
	Name           string `json:"name"`
	UserId         int64  `json:"user_id,string"`
	ConversationIDs string `json:"conversation_ids"`
	StatDate       string `json:"stat_date"`
	Type           string `json:"type"`
	OtelValue      string `json:"otel_value"`
	OtelLabel      string `json:"otel_label"`
}

type OtelListRequest struct {
	UserId   int64  `json:"user_id" query:"user_id"`
	PageSize int    `json:"pageSize" query:"pageSize"`
	PageNum  int    `json:"pageNum" query:"pageNum"`
	Keywords string `json:"keywords" query:"keywords"`
	StatDate string `json:"stat_date" query:"stat_date"`
}

type OtelDeleteRequest struct {
	Id     int64 `json:"id,string"`
	UserId int64 `json:"user_id,string"`
}

type ChartDataRequest struct {
	UserId    int64  `json:"user_id" query:"user_id"`
	Chart     string `json:"chart" query:"chart"`
	StartDate string `json:"start_date" query:"start_date"`
	EndDate   string `json:"end_date" query:"end_date"`
}
