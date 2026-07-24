package service

// ChartSeriesDef 定义 ECharts series 中一条线的数据来源
type ChartSeriesDef struct {
	Name  string `json:"name"`  // 显示名称，如"请求次数"
	Field string `json:"field"` // SQL 结果列名
}

// ChartQueryDef 定义图表查询的 SQL 模板和字段映射
type ChartQueryDef struct {
	SQL     string            // SQL 模板（按用户过滤），用 ? 作为参数占位符
	SQLAll  string            // SQL 模板（所有用户），不包含 user_id 过滤条件
	XField  string            // 结果中作为 xAxis 的列名
	Series  []ChartSeriesDef  // series 定义列表
}

// chartQueryDefs 所有可用的图表查询定义
// 后续可迁移到 DB/配置文件，实现运营后台动态配置
var chartQueryDefs = map[string]*ChartQueryDef{
	"request_count": {
		SQL: `SELECT stat_date,
		             COALESCE(CAST(otel_value->>'$.count' AS SIGNED), 0) AS value
		      FROM chat_otel
		      WHERE user_id = ? AND name = 'request_count' AND type = 'metric'
		        AND stat_date >= ? AND stat_date <= ?
		      ORDER BY stat_date ASC`,
		SQLAll: `SELECT stat_date,
		                COALESCE(CAST(otel_value->>'$.count' AS SIGNED), 0) AS value
		         FROM chat_otel
		         WHERE name = 'request_count' AND type = 'metric'
		           AND stat_date >= ? AND stat_date <= ?
		         ORDER BY stat_date ASC`,
		XField: "stat_date",
		Series: []ChartSeriesDef{
			{Name: "请求次数", Field: "value"},
		},
	},
	"token_usage": {
		SQL: `SELECT stat_date,
		             COALESCE(SUM(CASE WHEN name = 'input_token' THEN CAST(otel_value->>'$.count' AS SIGNED) ELSE 0 END), 0) AS input_token,
		             COALESCE(SUM(CASE WHEN name = 'output_token' THEN CAST(otel_value->>'$.count' AS SIGNED) ELSE 0 END), 0) AS output_token
		      FROM chat_otel
		      WHERE user_id = ? AND name IN ('input_token', 'output_token') AND type = 'metric'
		        AND stat_date >= ? AND stat_date <= ?
		      GROUP BY stat_date
		      ORDER BY stat_date ASC`,
		SQLAll: `SELECT stat_date,
		                COALESCE(SUM(CASE WHEN name = 'input_token' THEN CAST(otel_value->>'$.count' AS SIGNED) ELSE 0 END), 0) AS input_token,
		                COALESCE(SUM(CASE WHEN name = 'output_token' THEN CAST(otel_value->>'$.count' AS SIGNED) ELSE 0 END), 0) AS output_token
		         FROM chat_otel
		         WHERE name IN ('input_token', 'output_token') AND type = 'metric'
		           AND stat_date >= ? AND stat_date <= ?
		         GROUP BY stat_date
		         ORDER BY stat_date ASC`,
		XField: "stat_date",
		Series: []ChartSeriesDef{
			{Name: "输入Token", Field: "input_token"},
			{Name: "输出Token", Field: "output_token"},
		},
	},
	"agent_mode_count": {
		SQL: `SELECT stat_date,
		             COALESCE(CAST(otel_value->>'$.count' AS SIGNED), 0) AS value
		      FROM chat_otel
		      WHERE user_id = ? AND name = 'agent_mode_count' AND type = 'metric'
		        AND stat_date >= ? AND stat_date <= ?
		      ORDER BY stat_date ASC`,
		SQLAll: `SELECT stat_date,
		                COALESCE(CAST(otel_value->>'$.count' AS SIGNED), 0) AS value
		         FROM chat_otel
		         WHERE name = 'agent_mode_count' AND type = 'metric'
		           AND stat_date >= ? AND stat_date <= ?
		         ORDER BY stat_date ASC`,
		XField: "stat_date",
		Series: []ChartSeriesDef{
			{Name: "Agent调用", Field: "value"},
		},
	},
}
