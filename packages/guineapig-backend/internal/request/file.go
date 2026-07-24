package request

type FileCreateRequest struct {
	UserId      int64  `json:"user_id,string"`
	Name        string `json:"name"`
	FileDesc    string `json:"file_desc"`
	FileURL     string `json:"file_url"`
	FileType    int    `json:"file_type"`
	FileSize    int64  `json:"file_size"`
	FileMd5     string `json:"file_md5"`
	StorageType int8   `json:"storage_type"`
}

type FileUpdateRequest struct {
	Id       int64  `json:"id,string"`
	UserId   int64  `json:"user_id,string"`
	Name     string `json:"name"`
	FileDesc string `json:"file_desc"`
	FileType int    `json:"file_type"`
}

type FileDeleteRequest struct {
	Id     int64 `json:"id,string"`
	UserId int64 `json:"user_id,string"`
}

type FileListRequest struct {
	UserId     int64  `json:"user_id" query:"user_id"`
	PageSize   int    `json:"pageSize" query:"pageSize"`
	PageNum    int    `json:"pageNum" query:"pageNum"`
	Keywords   string `json:"keywords" query:"keywords"`
	FileType   *int   `json:"file_type" query:"file_type"`
	IsEmbedded *int   `json:"is_embedded" query:"is_embedded"`
}

type FileEmbedRequest struct {
	FileId    int64 `json:"file_id,string"`
	ResRagId int64 `json:"res_rag_id,string"`
}

type FileEmbedProgressRequest struct {
	FileId   int64  `json:"file_id"`
	TaskId   string `json:"task_id"`
	Progress int    `json:"progress"`
	Error    string `json:"error,omitempty"`
}
