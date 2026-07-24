package response

type RagItem struct {
	Id                 int64  `json:"id,string"`
	UserId             int64  `json:"user_id,string"`
	Name               string `json:"name"`
	RagDesc            string `json:"rag_desc"`
	RagMetadata        string `json:"rag_metadata"`
	ChunkSize          int    `json:"chunk_size"`
	OverlapSize        int    `json:"overlap_size"`
	DimensionSize      int    `json:"dimension_size"`
	EmbeddingModelId   int64  `json:"embedding_model_id,string"`
	EmbeddingModelName string `json:"embedding_model_name"`
	RerankerModelId    int64  `json:"reranker_model_id,string"`
	RerankerModelName  string `json:"reranker_model_name"`
	DocCount           int64  `json:"doc_count"`
	CreatedAt          string `json:"created_at"`
	UpdatedAt          string `json:"updated_at"`
}

type RagListResponse struct {
	Items []RagItem `json:"items"`
	Total int64     `json:"total"`
}

type RagCreateResponse struct {
	Id int64 `json:"id,string"`
}
