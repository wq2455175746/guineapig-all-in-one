package response

type AiModelItem struct {
	Id           int64  `json:"id,string"`
	ModelCode    string `json:"model_code"`
	ModelName    string `json:"model_name"`
	ApiUrl       string `json:"api_url"`
	ProviderCode string `json:"provider_code"`
	ModelType    string `json:"model_type"`
	ApiKey       string `json:"api_key"`
	Status       int8   `json:"status"`
	Established  int8   `json:"established"`
}

type AiModelListResponse struct {
	Items []AiModelItem `json:"items"`
	Total int64         `json:"total"`
}

type AiModelTestResponse struct {
	Connected bool   `json:"connected"`
	Message   string `json:"message,omitempty"`
}

type AiModelCreateResponse struct {
	Id int64 `json:"id,string"`
}

type AiModelOption struct {
	Id        int64  `json:"id,string"`
	ModelName string `json:"model_name"`
}
