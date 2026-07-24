package request

type RagCreateRequest struct {
	UserId           int64  `json:"user_id,string"`
	Name             string `json:"name"`
	RagDesc          string `json:"rag_desc"`
	ChunkSize        int    `json:"chunk_size"`
	OverlapSize      int    `json:"overlap_size"`
	DimensionSize    int    `json:"dimension_size"`
	EmbeddingModelId int64  `json:"embedding_model_id,string"`
	RerankerModelId  int64  `json:"reranker_model_id,string"`
}

type RagUpdateRequest struct {
	Id      int64  `json:"id,string"`
	UserId  int64  `json:"user_id,string"`
	RagDesc string `json:"rag_desc"`
}

type RagDeleteRequest struct {
	Id     int64 `json:"id,string"`
	UserId int64 `json:"user_id,string"`
}

type RagListRequest struct {
	UserId   int64  `json:"user_id" query:"user_id"`
	PageSize int    `json:"pageSize" query:"pageSize"`
	PageNum  int    `json:"pageNum" query:"pageNum"`
	Keywords string `json:"keywords" query:"keywords"`
}
