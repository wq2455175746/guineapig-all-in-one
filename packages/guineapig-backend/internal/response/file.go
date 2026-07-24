package response

type FileItem struct {
	Id              int64  `json:"id,string"`
	UserId          int64  `json:"user_id,string"`
	Name            string `json:"name"`
	FileDesc        string `json:"file_desc"`
	FileURL         string `json:"file_url"`
	FileSize        int64  `json:"file_size"`
	FileMd5         string `json:"file_md5"`
	FileType        int    `json:"file_type"`
	IsEmbedded      int8   `json:"is_embedded"`
	StorageType     int8   `json:"storage_type"`
	EmbeddingConfig string `json:"embedding_config"`
	CreatedAt       string `json:"created_at"`
	UpdatedAt       string `json:"updated_at"`
}

type FileListResponse struct {
	Items []FileItem `json:"items"`
	Total int64      `json:"total"`
}

type FileCreateResponse struct {
	Id int64 `json:"id,string"`
}

type FileEmbedResponse struct {
	TaskId string `json:"task_id"`
}
