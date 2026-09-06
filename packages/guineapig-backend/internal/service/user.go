package service

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"guineapig/config"
	"guineapig/internal/model"
	"guineapig/internal/request"
	"guineapig/internal/response"
	"guineapig/internal/router/common"
	"guineapig/pkg/auth"
	"guineapig/pkg/constant"
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

// DecryptUserInfo 返回用户的敏感字段信息。
// requesterUserID 为 Token 推导的 caller identity（0 表示 admin/inner 会话，可查询任意用户）；
// 用户会话要求 requester == 目标用户，杜绝 IDOR。
func DecryptUserInfo(ctx context.Context, req *request.DecryptUserInfoRequest, requesterUserID int64) (*response.DecryptedUserInfoResponse, error) {
	if requesterUserID > 0 && req.UserId != requesterUserID {
		return nil, errors.New("无权查看该用户信息")
	}

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

	// 2. 校验验证码（从配置/环境变量读取，不再硬编码 8888）
	regCode := config.Global.RegisterCode
	if regCode == "" {
		regCode = "8888"
	}
	if req.Code != regCode {
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

	// 7. HMAC-SHA256(fullApiKey) 用于存储（替代弱 MD5，密钥来自 JWT_SECRET）
	storedKey := utils.HMACApiKey(config.Global.JwtSecret, fullApiKey)

	// 8. 保存到 user_apikey 表
	apiKeyRecord := &model.UserApiKey{
		UserId: user.Id,
		ApiKey: storedKey,
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
	// 1. 兼容两种 api_key 提交方式：
	//    - 新版客户端：RSA 加密密文（需后端私钥解密）
	//    - 旧版/测试：明文 sk-xxx（解密失败则原样使用）
	apiKey := req.ApiKey
	if decrypted, err := DecryptKey(req.ApiKey); err == nil && decrypted != "" {
		apiKey = decrypted
	}

	// 2. 根据 api_key 查找 apikey 记录（存储态为 HMAC-SHA256；兼容旧 MD5 数据）
	storedHMAC := utils.HMACApiKey(config.Global.JwtSecret, apiKey)
	apiKeyRecord, err := model.MUserApiKey.FindByStoredKey(ctx, storedHMAC)
	if err != nil {
		logger.ErrorReqIdf(ctx, "find api_key error: %v", err)
		return nil, err
	}
	if apiKeyRecord == nil {
		// 旧数据兼容：MD5 存储的 api_key
		storedMD5 := utils.MD5ApiKey(apiKey)
		apiKeyRecord, err = model.MUserApiKey.FindByStoredKey(ctx, storedMD5)
		if err != nil {
			logger.ErrorReqIdf(ctx, "find api_key(MD5) error: %v", err)
			return nil, err
		}
	}
	if apiKeyRecord == nil {
		return nil, common.BizError(constant.ParamErr, "api_key 不存在或已禁用")
	}

	// 3. 根据 user_id 查找用户信息
	user, err := model.MUser.FindById(ctx, apiKeyRecord.UserId)
	if err != nil {
		logger.ErrorReqIdf(ctx, "find user by id error: %v, userId: %d", err, apiKeyRecord.UserId)
		return nil, err
	}
	if user == nil {
		return nil, errors.New("用户不存在")
	}

	// 4. 签发 HMAC 签名会话 Token，供后续 /api/v1 请求与 WS 握手鉴权
	sessionToken, err := auth.IssueUserToken(config.Global.JwtSecret, user.Id, auth.TokenTTL)
	if err != nil {
		logger.ErrorReqIdf(ctx, "issue session token error: %v, userId: %d", err, user.Id)
		return nil, err
	}

	// 5. 返回 user_id、email 和会话 Token
	return &response.ClientLoginResponse{
		UserId: user.Id,
		Email:  user.Email,
		Token:  sessionToken,
	}, nil
}
