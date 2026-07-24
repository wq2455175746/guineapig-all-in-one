package service

import (
	"context"
	"crypto/md5"
	"crypto/sha256"
	"errors"
	"fmt"
	"guineapig/internal/model"
	"guineapig/internal/request"
	"guineapig/internal/response"
	"guineapig/pkg/plugin/logger"
	"guineapig/pkg/utils"
)

func SearchUser(ctx context.Context, req *request.SearchUserRequest) (*response.SearchUserResponse, error) {
	items, err := model.MUser.Search(ctx, req.Keywords)
	if err != nil {
		return nil, err
	}
	res := &response.SearchUserResponse{}
	for _, item := range items {
		node := response.User{
			Id:   item.Id,
			Name: item.NickName,
		}
		res.Items = append(res.Items, node)
	}
	return res, nil
}

func ListUser(ctx context.Context, req *request.SearchRequest) (*response.ListUserResponse, error) {
	users, total, err := model.MUser.ListUser(ctx, req)
	if err != nil {
		return nil, err
	}
	// 构建响应
	userInfos := make([]response.User, 0, len(users))
	// 转换用户模型为响应对象
	for _, user := range users {
		userInfos = append(userInfos, response.User{
			Id:       user.Id,
			UserName: user.UserName,
			Name:     utils.NickName(user.NickName),
			Email:    utils.Email(user.Email),
		})
	}
	// 构建完整响应
	listResponse := &response.ListUserResponse{
		Users: userInfos,
		Total: total,
	}
	return listResponse, nil
}

func DecryptUserInfo(ctx context.Context, req *request.DecryptUserInfoRequest) (*response.DecryptedUserInfoResponse, error) {
	// 获得用户信息
	user, err := model.MUser.FindById(ctx, req.UserId)
	if err != nil {
		logger.ErrorReqIdf(ctx, "get user by id error: %v, userId: %d", err, req.UserId)
		return nil, err
	}

	// 根据请求的字段返回相应的解密信息
	resp := &response.DecryptedUserInfoResponse{
		Field: req.Field,
	}
	switch req.Field {
	case "email":
		resp.Value = user.Email
	case "name":
		resp.Value = user.NickName
	default:
		return nil, err
	}
	return resp, nil
}

func Register(ctx context.Context, req *request.RegisterRequest) (*response.RegisterResponse, error) {
	// 1. 校验邮箱
	if req.Email == "" {
		return nil, errors.New("邮箱不能为空")
	}

	// 2. 校验验证码（暂时硬编码为 8888）
	if req.Code != "8888" {
		return nil, errors.New("验证码错误")
	}

	// 3. 检查邮箱是否已注册
	existing, err := model.MUser.FindByEmail(ctx, req.Email)
	if err != nil {
		logger.ErrorReqIdf(ctx, "find user by email error: %v, email: %s", err, req.Email)
		return nil, err
	}
	if existing != nil {
		return nil, errors.New("该邮箱已注册")
	}

	// 4. 生成 UUID 作为用户名
	uuidStr := "user_" + utils.UUID()

	// 5. 创建用户（使用雪花算法生成 ID）
	user := &model.User{
		Id:       utils.SnowflakeID(),
		UserName: uuidStr,
		Email:    req.Email,
		Password: "xxx",
		Source:   "CUSTOM",
	}
	if err := user.Create(ctx); err != nil {
		logger.ErrorReqIdf(ctx, "save user error: %v, email: %s", err, req.Email)
		return nil, err
	}

	// 6. 生成 API Key
	// SHA256(uuid) → hex → sk-{hex}
	sha256Hash := fmt.Sprintf("%x", sha256.Sum256([]byte(uuidStr)))
	fullApiKey := "sk-" + sha256Hash

	// 7. MD5(fullApiKey) 用于存储
	md5Hash := fmt.Sprintf("%x", md5.Sum([]byte(fullApiKey)))

	// 8. 保存到 user_apikey 表
	apiKeyRecord := &model.UserApiKey{
		UserId: user.Id,
		ApiKey: md5Hash,
		Status: 1,
	}
	if err := apiKeyRecord.Create(ctx); err != nil {
		logger.ErrorReqIdf(ctx, "create api_key error: %v, userId: %d", err, user.Id)
		return nil, err
	}

	return &response.RegisterResponse{
		ApiKey: fullApiKey,
	}, nil
}

func ClientLogin(ctx context.Context, req *request.ClientLoginRequest) (*response.ClientLoginResponse, error) {
	// 1. 根据 api_key 查找 apikey 记录
	apiKeyRecord, err := model.MUserApiKey.FindByApiKey(ctx, req.ApiKey)
	if err != nil {
		logger.ErrorReqIdf(ctx, "find api_key error: %v, apiKey: %s", err, req.ApiKey)
		return nil, err
	}
	if apiKeyRecord == nil {
		return nil, errors.New("api_key 不存在或已禁用")
	}

	// 2. 根据 user_id 查找用户信息
	user, err := model.MUser.FindById(ctx, apiKeyRecord.UserId)
	if err != nil {
		logger.ErrorReqIdf(ctx, "find user by id error: %v, userId: %d", err, apiKeyRecord.UserId)
		return nil, err
	}
	if user == nil {
		return nil, errors.New("用户不存在")
	}

	// 3. 返回 user_id 和 email
	return &response.ClientLoginResponse{
		UserId: user.Id,
		Email:  user.Email,
	}, nil
}
