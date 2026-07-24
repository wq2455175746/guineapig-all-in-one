package response

type OtelItem struct {
	Id              int64  `json:"id,string"`
	Name            string `json:"name"`
	UserId          int64  `json:"user_id,string"`
	ConversationIDs string `json:"conversation_ids"`
	StatDate        string `json:"stat_date"`
	Type            string `json:"type"`
	OtelValue       string `json:"otel_value"`
	OtelLabel       string `json:"otel_label"`
	CreatedBy       string `json:"created_by"`
	CreatedAt       string `json:"created_at"`
	UpdatedAt       string `json:"updated_at"`
}

type OtelListResponse struct {
	Items []OtelItem `json:"items"`
	Total int64      `json:"total"`
}

// ECharts 通用数据格式
type ChartDataResponse struct {
	XAxis  []string          `json:"xAxis"`
	Series []ChartSeriesItem `json:"series"`
}

type ChartSeriesItem struct {
	Name string    `json:"name"`
	Data []float64 `json:"data"`
}
