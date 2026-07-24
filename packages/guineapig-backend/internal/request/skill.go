package request

type SkillCreateRequest struct {
	UserId  int64  `json:"user_id,string"`
	ZipUrl  string `json:"zip_url"`
	ZipKey  string `json:"zip_key"`  // S3 object key
}

type SkillUpdateRequest struct {
	Id     int64  `json:"id,string"`
	UserId int64  `json:"user_id,string"`
	Name   string `json:"name"`
	Description string `json:"description"`
	Status int8   `json:"status"`
}

type SkillDeleteRequest struct {
	Id     int64 `json:"id,string"`
	UserId int64 `json:"user_id,string"`
}

type SkillListRequest struct {
	UserId   int64  `json:"user_id" query:"user_id"`
	PageSize int    `json:"pageSize" query:"pageSize"`
	PageNum  int    `json:"pageNum" query:"pageNum"`
	Keywords string `json:"keywords" query:"keywords"`
}

type SkillPresignedUploadRequest struct {
	UserId   int64  `json:"user_id" query:"user_id"`
	Filename string `json:"filename" query:"filename"`
}
