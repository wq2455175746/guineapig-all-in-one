package request

type McpCreateRequest struct {
	UserId       int64  `json:"user_id,string"`
	Name         string `json:"name"`
	McpDesc      string `json:"description"`
	McpType      string `json:"type"`
	McpBody      string `json:"mcp_body"`
	McpTools     string `json:"mcp_tools"`
	McpResources string `json:"mcp_resources"`
	McpPrompt    string `json:"mcp_prompt"`
	ReqTimeout   int    `json:"timeout"`
	Status       int8   `json:"status"`
}

type McpUpdateRequest struct {
	Id           int64  `json:"id,string"`
	UserId       int64  `json:"user_id,string"`
	Name         string `json:"name"`
	McpDesc      string `json:"description"`
	McpType      string `json:"type"`
	McpBody      string `json:"mcp_body"`
	McpTools     string `json:"mcp_tools"`
	McpResources string `json:"mcp_resources"`
	McpPrompt    string `json:"mcp_prompt"`
	ReqTimeout   int    `json:"timeout"`
	Status       int8   `json:"status"`
}

type McpDeleteRequest struct {
	Id     int64 `json:"id,string"`
	UserId int64 `json:"user_id,string"`
}

type McpListRequest struct {
	UserId   int64  `json:"user_id" query:"user_id"`
	PageSize int    `json:"pageSize" query:"pageSize"`
	PageNum  int    `json:"pageNum" query:"pageNum"`
	Keywords string `json:"keywords" query:"keywords"`
}
