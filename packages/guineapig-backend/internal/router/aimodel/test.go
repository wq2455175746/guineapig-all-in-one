package aimodel

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"guineapig/internal/request"
	"guineapig/internal/response"
	"guineapig/internal/router/common"
	"guineapig/internal/service"
	gdMid "guineapig/pkg/middleware"
	"guineapig/pkg/utils"

	"github.com/labstack/echo/v4"
)

func TestConnection(e echo.Context) error {
	var req request.AiModelTestRequest
	if err := e.Bind(&req); err != nil {
		return common.ResponseParamError(e, err)
	}
	if req.ApiUrl == "" {
		return common.ResponseParamError(e, errors.New("api_url 不能为空"))
	}
	if req.ModelName == "" {
		return common.ResponseParamError(e, errors.New("model_name 不能为空"))
	}
	// 以 Token 推导的 caller identity 覆盖客户端传入的 user_id，杜绝 IDOR
	gdMid.BindRequester(e, &req.UserId)
	// 支持两种方式获取 api_key：
	// 1. 传 id+user_id → 后端从 DB 取加密 key 后解密
	// 2. 直接传加密的 api_key → 后端解密
	// 3. Ollama / Vllm 不需要 api_key
	if req.ProviderCode != "Ollama" && req.ProviderCode != "Vllm" && req.Id <= 0 && req.ApiKey == "" {
		return common.ResponseParamError(e, errors.New("需要提供 id 或 api_key"))
	}
	if req.Id > 0 && req.UserId <= 0 {
		return common.ResponseParamError(e, errors.New("user_id 不能为空"))
	}

	ctx := utils.NewContext(e)
	result := doTest(ctx, &req)
	return common.ResponseOk(e, result)
}

func doTest(ctx context.Context, req *request.AiModelTestRequest) *response.AiModelTestResponse {
	// Ollama 走单独的分支（不同 model_type 端点不同）
	if req.ProviderCode == "Ollama" {
		return doTestOllama(ctx, req)
	}

	// Vllm 走单独的分支（reranker 端点不同）
	if req.ProviderCode == "Vllm" {
		return doTestVllm(ctx, req)
	}

	// 非 Ollama：获取并解密 API Key
	var plainKey string
	var err error
	apiURL := strings.TrimRight(req.ApiUrl, "/")
	if req.Id > 0 {
		// 使用 DB 中该模型登记的 api_url，不再信任客户端传入的 api_url
		modelInfo, e := service.GetAiModelBase(ctx, req.Id, req.UserId)
		if e != nil {
			return &response.AiModelTestResponse{Connected: false, Message: fmt.Sprintf("获取模型信息失败: %v", e)}
		}
		apiURL = strings.TrimRight(modelInfo.ApiUrl, "/")

		encryptedKey, e := service.GetEncryptedApiKey(ctx, req.Id, req.UserId)
		if e != nil {
			return &response.AiModelTestResponse{Connected: false, Message: fmt.Sprintf("获取 API Key 失败: %v", e)}
		}
		plainKey, err = service.DecryptKey(encryptedKey)
	} else {
		plainKey, err = service.DecryptKey(req.ApiKey)
	}
	if err != nil {
		return &response.AiModelTestResponse{Connected: false, Message: fmt.Sprintf("解密 API Key 失败: %v", err)}
	}

	// api_url 网络白名单校验（防止 SSRF / 解密密钥外发到任意地址）
	if err := service.IsAllowedTestURL(apiURL); err != nil {
		return &response.AiModelTestResponse{Connected: false, Message: err.Error()}
	}

	var reqBody []byte
	if req.ProviderCode == "Anthropic" {
		reqBody, err = buildAnthropicBody(req.ModelName)
	} else {
		reqBody, err = buildOpenAIBody(req.ModelName)
	}
	if err != nil {
		return &response.AiModelTestResponse{Connected: false, Message: fmt.Sprintf("构建请求失败: %v", err)}
	}

	targetURL := apiURL + "/chat/completions"
	if req.ProviderCode == "Anthropic" {
		targetURL = apiURL + "/v1/messages"
	}

	return sendTestRequest(ctx, targetURL, reqBody, func(r *http.Request) {
		r.Header.Set("Content-Type", "application/json")
		if req.ProviderCode == "Anthropic" {
			r.Header.Set("x-api-key", plainKey)
			r.Header.Set("anthropic-version", "2023-06-01")
		} else {
			r.Header.Set("Authorization", "Bearer "+plainKey)
		}
	})
}

// doTestOllama 测试 Ollama 供应商连接，按 model_type 选择不同的 API 端点
func doTestOllama(ctx context.Context, req *request.AiModelTestRequest) *response.AiModelTestResponse {
	apiURL := strings.TrimRight(req.ApiUrl, "/")

	// api_url 网络白名单校验（防止 SSRF）
	if err := service.IsAllowedTestURL(apiURL); err != nil {
		return &response.AiModelTestResponse{Connected: false, Message: err.Error()}
	}

	var targetURL string
	var reqBody []byte
	var err error

	switch req.ModelType {
	case "EMBEDDING":
		targetURL = apiURL + "/api/embed"
		reqBody, err = json.Marshal(map[string]interface{}{
			"model": req.ModelName,
			"input": "Hello!",
		})
	default:
		// LLM / chat
		targetURL = apiURL + "/api/chat"
		reqBody, err = json.Marshal(map[string]interface{}{
			"model": req.ModelName,
			"messages": []map[string]string{
				{"role": "user", "content": "Hello!"},
			},
			"stream": false,
		})
	}
	if err != nil {
		return &response.AiModelTestResponse{Connected: false, Message: fmt.Sprintf("构建请求失败: %v", err)}
	}

	return sendTestRequest(ctx, targetURL, reqBody, func(r *http.Request) {
		r.Header.Set("Content-Type", "application/json")
	})
}

// doTestVllm 测试 Vllm 供应商连接，按 model_type 选择不同的 API 端点
func doTestVllm(ctx context.Context, req *request.AiModelTestRequest) *response.AiModelTestResponse {
	apiURL := strings.TrimRight(req.ApiUrl, "/")

	// api_url 网络白名单校验（防止 SSRF）
	if err := service.IsAllowedTestURL(apiURL); err != nil {
		return &response.AiModelTestResponse{Connected: false, Message: err.Error()}
	}

	var targetURL string
	var reqBody []byte
	var err error

	switch req.ModelType {
	case "RERANKER":
		targetURL = apiURL + "/v1/rerank"
		reqBody, err = json.Marshal(map[string]interface{}{
			"model":     req.ModelName,
			"query":     "What is the capital of France?",
			"documents": []string{"The capital of France is Paris.", "The capital of Brazil is Brasilia.", "Reranking is fun!"},
		})
	default:
		// LLM / chat using OpenAI-compatible endpoint
		targetURL = apiURL + "/v1/chat/completions"
		reqBody, err = json.Marshal(map[string]interface{}{
			"model": req.ModelName,
			"messages": []map[string]string{
				{"role": "user", "content": "Hello!"},
			},
			"stream": false,
		})
	}
	if err != nil {
		return &response.AiModelTestResponse{Connected: false, Message: fmt.Sprintf("构建请求失败: %v", err)}
	}

	return sendTestRequest(ctx, targetURL, reqBody, func(r *http.Request) {
		r.Header.Set("Content-Type", "application/json")
	})
}

// sendTestRequest 发送 HTTP POST 请求并解析响应结果。
// 绑定 request context（随请求取消）并设置超时，防止悬挂请求。
func sendTestRequest(ctx context.Context, targetURL string, reqBody []byte, headerFn func(*http.Request)) *response.AiModelTestResponse {
	httpReq, err := http.NewRequestWithContext(ctx, "POST", targetURL, bytes.NewReader(reqBody))
	if err != nil {
		return &response.AiModelTestResponse{Connected: false, Message: fmt.Sprintf("创建请求失败: %v", err)}
	}

	if headerFn != nil {
		headerFn(httpReq)
	}

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(httpReq)
	if err != nil {
		return &response.AiModelTestResponse{Connected: false, Message: fmt.Sprintf("连接失败: %v", err)}
	}
	defer func() {
		_, _ = io.Copy(io.Discard, resp.Body)
		resp.Body.Close()
	}()

	if resp.StatusCode >= 200 && resp.StatusCode < 300 {
		return &response.AiModelTestResponse{Connected: true}
	}

	bodyBytes, readErr := io.ReadAll(resp.Body)
	message := fmt.Sprintf("请求失败，HTTP状态码: %d", resp.StatusCode)
	if readErr == nil && len(bodyBytes) > 0 {
		maxLen := 500
		if len(bodyBytes) > maxLen {
			bodyBytes = bodyBytes[:maxLen]
		}
		var errResp struct {
			Error struct {
				Message string `json:"message"`
			} `json:"error"`
		}
		if json.Unmarshal(bodyBytes, &errResp) == nil && errResp.Error.Message != "" {
			message += ": " + errResp.Error.Message
		} else {
			message += ": " + string(bodyBytes)
		}
	}

	return &response.AiModelTestResponse{
		Connected: false,
		Message:   message,
	}
}

func buildOpenAIBody(modelName string) ([]byte, error) {
	body := map[string]interface{}{
		"model": modelName,
		"messages": []map[string]string{
			{"role": "user", "content": "Hello!"},
		},
		"stream": false,
	}
	return json.Marshal(body)
}

func buildAnthropicBody(modelName string) ([]byte, error) {
	body := map[string]interface{}{
		"model":      modelName,
		"max_tokens": 256,
		"messages": []map[string]string{
			{"role": "user", "content": "Hello!"},
		},
	}
	return json.Marshal(body)
}
