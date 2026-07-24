package service

import (
	"context"
	"errors"
	"guineapig/internal/model"
	"guineapig/internal/request"
	"guineapig/internal/response"
)

// stringPtr 将非空字符串转为 *string，空字符串转为 nil
func stringPtr(s string) *string {
	if s == "" {
		return nil
	}
	return &s
}

func CreateMcp(ctx context.Context, req *request.McpCreateRequest) (*response.McpCreateResponse, error) {
	if req.UserId <= 0 {
		return nil, errors.New("user_id 不能为空")
	}
	if req.Name == "" {
		return nil, errors.New("name 不能为空")
	}
	if req.McpType == "" {
		return nil, errors.New("type 不能为空")
	}

	// 检查同名 mcp 是否已存在
	existing, err := model.MResMcp.FindByUserIdAndName(ctx, req.UserId, req.Name)
	if err != nil {
		return nil, err
	}
	if existing != nil {
		return nil, errors.New("同名 MCP 已存在")
	}

	// 默认超时时间
	timeout := req.ReqTimeout
	if timeout <= 0 {
		timeout = 60
	}

	m := &model.ResMcp{
		UserId:       req.UserId,
		Name:         req.Name,
		McpDesc:      req.McpDesc,
		McpType:      req.McpType,
		McpBody:      stringPtr(req.McpBody),
		McpTools:     stringPtr(req.McpTools),
		McpResources: stringPtr(req.McpResources),
		McpPrompt:    stringPtr(req.McpPrompt),
		ReqTimeout:   timeout,
		Status:       req.Status,
	}

	if err := m.Create(ctx); err != nil {
		return nil, err
	}

	return &response.McpCreateResponse{Id: m.Id}, nil
}

func UpdateMcp(ctx context.Context, req *request.McpUpdateRequest) error {
	if req.Id <= 0 {
		return errors.New("id 不能为空")
	}
	if req.UserId <= 0 {
		return errors.New("user_id 不能为空")
	}

	existing, err := model.MResMcp.FindById(ctx, req.Id)
	if err != nil {
		return err
	}
	if existing == nil {
		return errors.New("记录不存在")
	}
	if existing.UserId != req.UserId {
		return errors.New("无权操作该记录")
	}

	m := &model.ResMcp{
		Id:           req.Id,
		Name:         req.Name,
		McpDesc:      req.McpDesc,
		McpType:      req.McpType,
		McpBody:      stringPtr(req.McpBody),
		McpTools:     stringPtr(req.McpTools),
		McpResources: stringPtr(req.McpResources),
		McpPrompt:    stringPtr(req.McpPrompt),
		ReqTimeout:   req.ReqTimeout,
		Status:       req.Status,
	}
	return m.Update(ctx)
}

func DeleteMcp(ctx context.Context, req *request.McpDeleteRequest) error {
	if req.Id <= 0 {
		return errors.New("id 不能为空")
	}
	if req.UserId <= 0 {
		return errors.New("user_id 不能为空")
	}

	existing, err := model.MResMcp.FindById(ctx, req.Id)
	if err != nil {
		return err
	}
	if existing == nil {
		return errors.New("记录不存在")
	}
	if existing.UserId != req.UserId {
		return errors.New("无权操作该记录")
	}

	return model.MResMcp.Delete(ctx, req.Id, req.UserId)
}

func ListMcp(ctx context.Context, req *request.McpListRequest) (*response.McpListResponse, error) {
	items, total, err := model.MResMcp.List(ctx, req)
	if err != nil {
		return nil, err
	}

	// 复制切片避免循环变量指针问题（McpTools 等已是 *string 可直接赋值）
	resItems := make([]response.McpItem, 0, len(items))
	for _, item := range items {
		mcpBody := ""
		if item.McpBody != nil {
			mcpBody = *item.McpBody
		}
		resItems = append(resItems, response.McpItem{
			Id:           item.Id,
			UserId:       item.UserId,
			Name:         item.Name,
			McpDesc:      item.McpDesc,
			McpType:      item.McpType,
			McpBody:      mcpBody,
			McpTools:     item.McpTools,
			McpResources: item.McpResources,
			McpPrompt:    item.McpPrompt,
			ReqTimeout:   item.ReqTimeout,
			Status:       item.Status,
			CreatedAt:    item.CreatedAt.Format("2006-01-02 15:04:05"),
			UpdatedAt:    item.UpdatedAt.Format("2006-01-02 15:04:05"),
		})
	}

	return &response.McpListResponse{
		Items: resItems,
		Total: total,
	}, nil
}
