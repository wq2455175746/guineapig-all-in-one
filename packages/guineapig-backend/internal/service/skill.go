package service

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"guineapig/config"
	"guineapig/internal/model"
	"guineapig/internal/request"
	"guineapig/internal/response"
	"guineapig/pkg/utils"
	"io"
	"net/http"
	"time"
)

// SkillAiAgentResult aiagent 解析 zip 后的返回结果
type SkillAiAgentResult struct {
	Name     string `json:"name"`
	Description string `json:"description"`
	Version  string `json:"version"`
	FileStat string `json:"file_stat"`
	Metadata string `json:"metadata"`
}

// CreateSkill 创建 skill：调用 aiagent 解析 zip，然后存入数据库
func CreateSkill(ctx context.Context, req *request.SkillCreateRequest) (*response.SkillCreateResponse, error) {
	if req.UserId <= 0 {
		return nil, errors.New("user_id 不能为空")
	}
	if req.ZipKey == "" {
		return nil, errors.New("zip_key 不能为空")
	}

	// 1. 调用 aiagent 解析 zip 文件
	result, err := callAiAgentSkillProcess(ctx, req.ZipKey)
	if err != nil {
		return nil, fmt.Errorf("解析 skill 文件失败: %w", err)
	}

	// 2. 检查同名 skill 是否已存在
	existing, err := model.MResSkills.FindByUserIdAndName(ctx, req.UserId, result.Name)
	if err != nil {
		return nil, err
	}
	if existing != nil {
		return nil, errors.New("同名 skill 已存在")
	}

	// 3. 保存 S3 object key 到 zip_url（不使用完整 HTTP URL）
	m := &model.ResSkills{
		UserId:       req.UserId,
		Name:         result.Name,
		Description:  result.Description,
		SkillVersion: result.Version,
		ZipUrl:       req.ZipKey,
		FileStat:     result.FileStat,
		Metadata:     result.Metadata,
		Status:       1,
	}

	if err := m.Create(ctx); err != nil {
		return nil, err
	}

	return &response.SkillCreateResponse{Id: m.Id}, nil
}

func UpdateSkill(ctx context.Context, req *request.SkillUpdateRequest) error {
	if req.Id <= 0 {
		return errors.New("id 不能为空")
	}
	if req.UserId <= 0 {
		return errors.New("user_id 不能为空")
	}

	existing, err := model.MResSkills.FindById(ctx, req.Id)
	if err != nil {
		return err
	}
	if existing == nil {
		return errors.New("记录不存在")
	}
	if existing.UserId != req.UserId {
		return errors.New("无权操作该记录")
	}

	m := &model.ResSkills{
		Id:     req.Id,
		Name:   req.Name,
		Description:   req.Description,
		Status: req.Status,
	}
	return m.Update(ctx)
}

func DeleteSkill(ctx context.Context, req *request.SkillDeleteRequest) error {
	if req.Id <= 0 {
		return errors.New("id 不能为空")
	}
	if req.UserId <= 0 {
		return errors.New("user_id 不能为空")
	}

	existing, err := model.MResSkills.FindById(ctx, req.Id)
	if err != nil {
		return err
	}
	if existing == nil {
		return errors.New("记录不存在")
	}
	if existing.UserId != req.UserId {
		return errors.New("无权操作该记录")
	}

	return model.MResSkills.Delete(ctx, req.Id, req.UserId)
}

func ListSkill(ctx context.Context, req *request.SkillListRequest) (*response.SkillListResponse, error) {
	items, total, err := model.MResSkills.List(ctx, req)
	if err != nil {
		return nil, err
	}

	resItems := make([]response.SkillItem, 0, len(items))
	for _, item := range items {
		resItems = append(resItems, response.SkillItem{
			Id:           item.Id,
			UserId:       item.UserId,
			Name:         item.Name,
			Description:  item.Description,
			SkillVersion: item.SkillVersion,
			ZipUrl:       item.ZipUrl,
			FileStat:     item.FileStat,
			Metadata:     item.Metadata,
			Status:       item.Status,
			CreatedAt:    item.CreatedAt.Format("2006-01-02 15:04:05"),
			UpdatedAt:    item.UpdatedAt.Format("2006-01-02 15:04:05"),
		})
	}

	return &response.SkillListResponse{
		Items: resItems,
		Total: total,
	}, nil
}

// callAiAgentSkillProcess 调用 guineapig-aiagent 的 skill 解析接口
func callAiAgentSkillProcess(ctx context.Context, objectKey string) (*SkillAiAgentResult, error) {
	baseURL := config.Global.AiAgent.BaseUrl
	if baseURL == "" {
		return nil, errors.New("AIAGENT_BASE_URL 未配置")
	}

	reqBody, err := json.Marshal(map[string]string{
		"objectKey": objectKey,
	})
	if err != nil {
		return nil, fmt.Errorf("序列化 skill 解析请求失败: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost,
		baseURL+"/guineapig-aiagent/skill/process",
		bytes.NewReader(reqBody))
	if err != nil {
		return nil, fmt.Errorf("创建 skill 解析请求失败: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")
	utils.AttachAiAgentAuth(httpReq)

	client := utils.NewHTTPClient(120 * time.Second)
	resp, err := client.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("skill 解析请求失败: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("读取 skill 解析响应失败: %w", err)
	}

	if resp.StatusCode != 200 {
		return nil, fmt.Errorf("skill 解析返回非 200 状态码: %d, body: %s", resp.StatusCode, string(body))
	}

	// 解析 aiagent 响应: {"success":true,"errCode":0,"errMessage":"success","result":{...}}
	var aiagentResp struct {
		Success    bool                `json:"success"`
		ErrCode    int                 `json:"errCode"`
		ErrMessage string              `json:"errMessage"`
		Result     *SkillAiAgentResult `json:"result"`
	}
	if err := json.Unmarshal(body, &aiagentResp); err != nil {
		return nil, fmt.Errorf("解析 skill 解析响应失败: %w", err)
	}

	if !aiagentResp.Success || aiagentResp.Result == nil {
		return nil, fmt.Errorf("skill 解析失败: %s", aiagentResp.ErrMessage)
	}

	// 验证必填字段
	if aiagentResp.Result.Name == "" {
		return nil, errors.New("skill 缺少 name 字段")
	}

	return aiagentResp.Result, nil
}
