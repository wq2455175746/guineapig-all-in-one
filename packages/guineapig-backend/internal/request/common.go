package request

// SearchRequest 通用搜索请求参数
type SearchRequest struct {
	PageSize int    `json:"pageSize" query:"pageSize"`
	PageNum  int    `json:"pageNum" query:"pageNum"`
	Keywords string `json:"keywords" query:"keywords"`
}

func (r *SearchRequest) GetKeywords() string {
	if r == nil {
		return ""
	}
	return r.Keywords
}

func (s *SearchRequest) Limit() int {
	if s == nil || s.PageSize <= 0 {
		return 0
	}
	return s.PageSize
}

func (s *SearchRequest) Offset() int {
	if s == nil || s.PageNum <= 0 || s.PageSize <= 0 {
		return 0
	}
	return (s.PageNum - 1) * s.PageSize
}

// Host ip地址映射
type Host struct {
	Ip       string `json:"ip" form:"ip"`
	Hostname string `json:"hostname" form:"hostname"`
}

// Env 环境变量
type Env struct {
	Name  string `json:"name" form:"name"`
	Value string `json:"value" form:"value"`
}
