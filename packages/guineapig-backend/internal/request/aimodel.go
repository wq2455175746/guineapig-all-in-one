package request

import "encoding/json"

type AiModelCreateRequest struct {
	UserId       int64           `json:"user_id,string"`
	ModelName    string          `json:"model_name"`
	ApiUrl       string          `json:"api_url"`
	ApiKey       string          `json:"api_key"`
	ProviderCode string          `json:"provider_code"`
	ModelType    string          `json:"model_type"`
	MaxTokens    int             `json:"max_tokens"`
	IsSmallModel int8            `json:"is_small_model"`
	Status       int8            `json:"status"`
	Established  int8            `json:"established"`
	ExtraParams  json.RawMessage `json:"extra_params"`
}

type AiModelUpdateRequest struct {
	Id           int64           `json:"id,string"`
	UserId       int64           `json:"user_id,string"`
	ModelName    string          `json:"model_name"`
	ApiUrl       string          `json:"api_url"`
	ApiKey       string          `json:"api_key"`
	ProviderCode string          `json:"provider_code"`
	ModelType    string          `json:"model_type"`
	MaxTokens    int             `json:"max_tokens"`
	IsSmallModel int8            `json:"is_small_model"`
	Status       int8            `json:"status"`
	Established  int8            `json:"established"`
	ExtraParams  json.RawMessage `json:"extra_params"`
}

type AiModelTestRequest struct {
	ApiUrl       string `json:"api_url"`
	ApiKey       string `json:"api_key"`
	ModelName    string `json:"model_name"`
	ProviderCode string `json:"provider_code"`
	ModelType    string `json:"model_type"`
	Id           int64  `json:"id,string"`
	UserId       int64  `json:"user_id,string"`
}

type AiModelUpdateEstablishedRequest struct {
	Id          int64 `json:"id,string"`
	UserId      int64 `json:"user_id,string"`
	Established int8  `json:"established"`
}

type AiModelDeleteRequest struct {
	Id     int64 `json:"id,string"`
	UserId int64 `json:"user_id,string"`
}

type AiModelListRequest struct {
	UserId   int64  `json:"user_id" query:"user_id"`
	PageSize int    `json:"pageSize" query:"pageSize"`
	PageNum  int    `json:"pageNum" query:"pageNum"`
	Keywords string `json:"keywords" query:"keywords"`
}
