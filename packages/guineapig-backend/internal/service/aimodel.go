package service

import (
	"context"
	"crypto/rsa"
	"errors"
	"guineapig/config"
	"guineapig/internal/model"
	"guineapig/internal/request"
	"guineapig/internal/response"
	"guineapig/pkg/utils"
	"sync"
)

var SupportedProviders = map[string]bool{
	"OpenAI":    true,
	"DeepSeek":  true,
	"Anthropic": true,
	"Qwen":      true,
	"Ollama":    true,
	"Vllm":      true,
	"Other":     true,
}

var SupportedModelTypes = map[string]bool{
	"LLM":       true,
	"OCR":       true,
	"EMBEDDING": true,
	"RERANKER":  true,
	"OTHER":     true,
}

func CreateAiModel(ctx context.Context, req *request.AiModelCreateRequest) (*response.AiModelCreateResponse, error) {
	if req.UserId <= 0 {
		return nil, errors.New("user_id 不能为空")
	}
	if req.ModelName == "" {
		return nil, errors.New("model_name 不能为空")
	}
	if req.ApiUrl == "" {
		return nil, errors.New("api_url 不能为空")
	}
	if req.ApiKey == "" {
		return nil, errors.New("api_key 不能为空")
	}
	if req.ProviderCode != "" && !SupportedProviders[req.ProviderCode] {
		return nil, errors.New("不支持的供应商类型")
	}
	if req.ModelType != "" && !SupportedModelTypes[req.ModelType] {
		return nil, errors.New("不支持的模型类型")
	}

	if req.ProviderCode == "" {
		req.ProviderCode = "Other"
	}
	if req.ModelType == "" {
		req.ModelType = "LLM"
	}

	m := &model.UserAiModel{
		UserId:       req.UserId,
		ModelCode:    utils.UUID(),
		ModelName:    req.ModelName,
		ApiUrl:       req.ApiUrl,
		ApiKey:       req.ApiKey,
		ProviderCode: req.ProviderCode,
		ModelType:    req.ModelType,
		Status:       req.Status,
		Established:  req.Established,
	}

	if err := m.Create(ctx); err != nil {
		return nil, err
	}

	return &response.AiModelCreateResponse{Id: m.Id}, nil
}

func UpdateAiModel(ctx context.Context, req *request.AiModelUpdateRequest) error {
	if req.Id <= 0 {
		return errors.New("id 不能为空")
	}
	if req.UserId <= 0 {
		return errors.New("user_id 不能为空")
	}
	if req.ProviderCode != "" && !SupportedProviders[req.ProviderCode] {
		return errors.New("不支持的供应商类型")
	}
	if req.ModelType != "" && !SupportedModelTypes[req.ModelType] {
		return errors.New("不支持的模型类型")
	}

	existing, err := model.MUserAiModel.FindById(ctx, req.Id)
	if err != nil {
		return err
	}
	if existing == nil {
		return errors.New("记录不存在")
	}
	if existing.UserId != req.UserId {
		return errors.New("无权操作该记录")
	}

	m := &model.UserAiModel{
		Id:           req.Id,
		ApiUrl:       req.ApiUrl,
		ApiKey:       req.ApiKey,
		ProviderCode: req.ProviderCode,
		ModelType:    req.ModelType,
		ModelName:    req.ModelName,
		Status:       req.Status,
		Established:  req.Established,
	}
	// 更新操作不修改 api_key，保持 DB 中原有的加密值
	return m.Update(ctx)
}

// UpdateAiModelEstablished 仅更新模型的 established 字段（连通状态）
func UpdateAiModelEstablished(ctx context.Context, req *request.AiModelUpdateEstablishedRequest) error {
	if req.Id <= 0 {
		return errors.New("id 不能为空")
	}
	if req.UserId <= 0 {
		return errors.New("user_id 不能为空")
	}

	existing, err := model.MUserAiModel.FindById(ctx, req.Id)
	if err != nil {
		return err
	}
	if existing == nil {
		return errors.New("记录不存在")
	}
	if existing.UserId != req.UserId {
		return errors.New("无权操作该记录")
	}

	return model.MUserAiModel.UpdateField(ctx, req.Id, "established", req.Established)
}

func DeleteAiModel(ctx context.Context, req *request.AiModelDeleteRequest) error {
	if req.Id <= 0 {
		return errors.New("id 不能为空")
	}
	if req.UserId <= 0 {
		return errors.New("user_id 不能为空")
	}

	existing, err := model.MUserAiModel.FindById(ctx, req.Id)
	if err != nil {
		return err
	}
	if existing == nil {
		return errors.New("记录不存在")
	}
	if existing.UserId != req.UserId {
		return errors.New("无权操作该记录")
	}

	return model.MUserAiModel.Delete(ctx, req.Id, req.UserId)
}

func ListAiModelOptionsByType(ctx context.Context, userId int64, modelType string) ([]response.AiModelOption, error) {
	if userId <= 0 {
		return nil, errors.New("user_id 不能为空")
	}

	items, err := model.MUserAiModel.ListOptionsByType(ctx, userId, modelType)
	if err != nil {
		return nil, err
	}

	res := make([]response.AiModelOption, 0, len(items))
	for _, item := range items {
		res = append(res, response.AiModelOption{
			Id:        item.Id,
			ModelName: item.ModelName,
		})
	}
	return res, nil
}

func ListAiModelOptions(ctx context.Context, userId int64) ([]response.AiModelOption, error) {
	if userId <= 0 {
		return nil, errors.New("user_id 不能为空")
	}

	items, err := model.MUserAiModel.ListOptions(ctx, userId)
	if err != nil {
		return nil, err
	}

	res := make([]response.AiModelOption, 0, len(items))
	for _, item := range items {
		res = append(res, response.AiModelOption{
			Id:        item.Id,
			ModelName: item.ModelName,
		})
	}
	return res, nil
}

func ListAiModel(ctx context.Context, req *request.AiModelListRequest) (*response.AiModelListResponse, error) {
	items, total, err := model.MUserAiModel.List(ctx, req)
	if err != nil {
		return nil, err
	}

	resItems := make([]response.AiModelItem, 0, len(items))
	for _, item := range items {
		resItems = append(resItems, response.AiModelItem{
			Id:           item.Id,
			ModelCode:    item.ModelCode,
			ModelName:    item.ModelName,
			ApiUrl:       item.ApiUrl,
			ProviderCode: item.ProviderCode,
			ModelType:    item.ModelType,
			ApiKey:       "***", // 加密密钥不返回前端，统一隐藏
			Status:       item.Status,
			Established:  item.Established,
		})
	}

	return &response.AiModelListResponse{
		Items: resItems,
		Total: total,
	}, nil
}

var (
	privateKeyMu sync.Mutex
	privateKey   *rsa.PrivateKey
)

func getPrivateKey() (*rsa.PrivateKey, error) {
	privateKeyMu.Lock()
	defer privateKeyMu.Unlock()

	if privateKey != nil {
		return privateKey, nil
	}

	k, err := utils.LoadPrivateKey(config.Global.Rsa.PrivateKey)
	if err != nil {
		return nil, err
	}

	privateKey = k
	return privateKey, nil
}

// DecryptApiKey 从 DB 中读取加密的 api_key 并解密返回明文
// 供提交任务给 guineapig-aiagent 服务时使用
func DecryptApiKey(ctx context.Context, id, userId int64) (string, error) {
	existing, err := model.MUserAiModel.FindById(ctx, id)
	if err != nil {
		return "", err
	}
	if existing == nil {
		return "", errors.New("记录不存在")
	}
	if existing.UserId != userId {
		return "", errors.New("无权操作该记录")
	}
	if existing.ApiKey == "" {
		return "", errors.New("api_key 为空")
	}

	key, err := getPrivateKey()
	if err != nil {
		return "", err
	}

	return utils.DecryptRSA(key, existing.ApiKey)
}

// DecryptKey 直接解密给定的 RSA 加密字符串（不查 DB）
// 供 test connection 等场景使用：前端传加密 key，后端解密后使用
func DecryptKey(encrypted string) (string, error) {
	key, err := getPrivateKey()
	if err != nil {
		return "", err
	}
	return utils.DecryptRSA(key, encrypted)
}

// GetEncryptedApiKey 从 DB 读取加密的 api_key（不解密），供 test connection 使用
func GetEncryptedApiKey(ctx context.Context, id, userId int64) (string, error) {
	existing, err := model.MUserAiModel.FindById(ctx, id)
	if err != nil {
		return "", err
	}
	if existing == nil {
		return "", errors.New("记录不存在")
	}
	if existing.UserId != userId {
		return "", errors.New("无权操作该记录")
	}
	if existing.ApiKey == "" {
		return "", errors.New("api_key 为空")
	}
	return existing.ApiKey, nil
}
