package response

type SkillItem struct {
	Id           int64  `json:"id,string"`
	UserId       int64  `json:"user_id,string"`
	Name         string `json:"name"`
	Description  string `json:"description"`
	SkillVersion string `json:"skill_version"`
	ZipUrl       string `json:"zip_url"`
	FileStat     string `json:"file_stat"`
	Metadata     string `json:"metadata"`
	Status       int8   `json:"status"`
	CreatedAt    string `json:"created_at"`
	UpdatedAt    string `json:"updated_at"`
}

type SkillListResponse struct {
	Items []SkillItem `json:"items"`
	Total int64       `json:"total"`
}

type SkillCreateResponse struct {
	Id int64 `json:"id,string"`
}
