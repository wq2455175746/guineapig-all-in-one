package response

type McpItem struct {
	Id           int64   `json:"id,string"`
	UserId       int64   `json:"user_id,string"`
	Name         string  `json:"name"`
	McpDesc      string  `json:"description"`
	McpType      string  `json:"type"`
	McpBody      string  `json:"mcp_body"`
	McpTools     *string `json:"mcp_tools,omitempty"`
	McpResources *string `json:"mcp_resources,omitempty"`
	McpPrompt    *string `json:"mcp_prompt,omitempty"`
	ReqTimeout   int     `json:"timeout"`
	Status       int8    `json:"status"`
	CreatedAt    string  `json:"created_at"`
	UpdatedAt    string  `json:"updated_at"`
}

type McpListResponse struct {
	Items []McpItem `json:"items"`
	Total int64     `json:"total"`
}

type McpCreateResponse struct {
	Id int64 `json:"id,string"`
}
