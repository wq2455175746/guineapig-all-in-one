package service

import (
	"context"
	"errors"
	"fmt"
	"guineapig/internal/bot"
	"guineapig/internal/model"
	"guineapig/internal/request"
	"guineapig/internal/response"
	"guineapig/pkg/plugin/logger"
	"strings"
)

// BotManagerInstance 全局 BotManager 实例
var BotManagerInstance = bot.NewBotManager()

// init BotManager 消息处理
func init() {
	BotManagerInstance.SetOnMessage(handleBotMessage)
}

// handleBotMessage Bot 消息处理回调
// 完整链路：存消息 → 调 AiAgent → 回复
func handleBotMessage(ctx context.Context, msg *bot.BotMessage) error {
	if msg.BotUserID <= 0 {
		return errors.New("BotMessage.BotUserID 无效")
	}
	if msg.ExtChatID == "" {
		return errors.New("BotMessage.ExtChatID 为空")
	}
	if msg.Content == "" {
		return nil // 空消息不处理
	}

	logger.Infof("[Bot] 处理消息: platform=%s, user_id=%d, extChatID=%s, content=%s",
		msg.Platform, msg.BotUserID, msg.ExtChatID, msg.Content)

	// 1. 通过 SyncChatMessage 调用 AiAgent 获取回复
	reply, err := SyncChatMessage(ctx, msg.BotUserID, msg.Platform, msg.ExtChatID, msg.Content)
	if err != nil {
		logger.Errorf("[Bot] SyncChatMessage 失败: %v", err)
		// 发送错误提示给用户
		errReply := &bot.BotReply{
			Text: fmt.Sprintf("🤖 处理消息时出错，请稍后重试"),
		}
		if err := BotManagerInstance.SendMessage(msg.Platform, msg.BotUserID, msg.ExtChatID, errReply); err != nil {
			logger.Errorf("[Bot] 发送错误提示消息失败: platform=%s, user_id=%d, err=%v", msg.Platform, msg.BotUserID, err)
		}
		return err
	}

	// 2. 发送 AI 回复到 IM 平台
	botReply := &bot.BotReply{Text: reply}
	if err := BotManagerInstance.SendMessage(msg.Platform, msg.BotUserID, msg.ExtChatID, botReply); err != nil {
		logger.Errorf("[Bot] 发送消息失败: %v", err)
		return err
	}

	logger.Infof("[Bot] 回复已发送: platform=%s, user_id=%d, extChatID=%s",
		msg.Platform, msg.BotUserID, msg.ExtChatID)
	return nil
}

// BindBot 绑定 IM 平台 Bot
func BindBot(ctx context.Context, req *request.BotBindRequest) (*response.BotBindResponse, error) {
	if req.Platform == "" {
		return nil, errors.New("platform 不能为空")
	}
	if req.AppId == "" {
		return nil, errors.New("app_id 不能为空")
	}
	if req.AppSecret == "" {
		return nil, errors.New("app_secret 不能为空")
	}

	// RSA 解密 AppSecret（支持加密和明文两种格式，向后兼容）
	appSecret := req.AppSecret
	if !strings.HasPrefix(appSecret, "-----") && len(appSecret) > 50 {
		decrypted, err := DecryptKey(appSecret)
		if err == nil && decrypted != "" {
			appSecret = decrypted
		}
	}

	// 检查是否已存在绑定
	existing, err := model.MBotBinding.FindByUserAndPlatform(ctx, req.UserId, req.Platform)
	if err != nil {
		return nil, fmt.Errorf("查询绑定失败: %w", err)
	}

	binding := &model.BotBinding{}
	if existing != nil {
		// 更新已有绑定
		binding = existing
		binding.AppId = req.AppId
		binding.AppSecret = appSecret
		binding.BotName = req.BotName
		if req.ExtraJSON != "" {
			binding.ExtraConfig = &req.ExtraJSON
		}
		if err := binding.Update(ctx); err != nil {
			return nil, fmt.Errorf("更新绑定失败: %w", err)
		}
	} else {
		// 创建新绑定
		var extraConfig *string
		if req.ExtraJSON != "" {
			extraConfig = &req.ExtraJSON
		}
		binding = &model.BotBinding{
			UserId:      req.UserId,
			Platform:    req.Platform,
			AppId:       req.AppId,
			AppSecret:   appSecret,
			BotName:     req.BotName,
			ExtraConfig: extraConfig,
			BotStatus:   0,
		}
		if err := binding.Create(ctx); err != nil {
			return nil, fmt.Errorf("创建绑定失败: %w", err)
		}
	}

	// 启动 Bot 连接
	if err := startBotForBinding(ctx, binding); err != nil {
		logger.Errorf("[BotBind] 启动 Bot 失败: user_id=%d, platform=%s, err=%v",
			req.UserId, req.Platform, err)
		if uerr := binding.UpdateStatus(ctx, 2); uerr != nil { // 连接失败
			logger.Errorf("[BotBind] 更新连接失败状态出错: binding_id=%d, err=%v", binding.Id, uerr)
		}
		return &response.BotBindResponse{
			Id:        binding.Id,
			Platform:  binding.Platform,
			BotStatus: 2,
		}, nil
	}

	if err := binding.UpdateStatus(ctx, 1); err != nil { // 已连接
		logger.Errorf("[BotBind] 更新已连接状态失败: binding_id=%d, err=%v", binding.Id, err)
	}
	return &response.BotBindResponse{
		Id:        binding.Id,
		Platform:  binding.Platform,
		BotStatus: 1,
	}, nil
}

// UnbindBot 解绑 IM 平台 Bot
func UnbindBot(ctx context.Context, req *request.BotUnbindRequest) error {
	if req.Platform == "" {
		return errors.New("platform 不能为空")
	}

	// 停止 Bot 连接
	if err := BotManagerInstance.StopBot(req.Platform, req.UserId); err != nil {
		logger.Warnf("[BotUnbind] 停止 Bot 失败: %v", err)
	}

	// 删除绑定记录
	binding, err := model.MBotBinding.FindByUserAndPlatform(ctx, req.UserId, req.Platform)
	if err != nil {
		return fmt.Errorf("查询绑定失败: %w", err)
	}
	if binding == nil {
		return errors.New("绑定记录不存在")
	}

	return model.MBotBinding.Delete(ctx, binding.Id)
}

// GetBotInfo 查询绑定信息
func GetBotInfo(ctx context.Context, req *request.BotInfoRequest) ([]*response.BotBindingItem, error) {
	var bindings []*model.BotBinding
	var err error

	if req.Platform != "" {
		// 查某个平台的绑定
		b, err := model.MBotBinding.FindByUserAndPlatform(ctx, req.UserId, req.Platform)
		if err != nil {
			return nil, fmt.Errorf("查询绑定失败: %w", err)
		}
		if b != nil {
			// 同步连接状态
			b.BotStatus = syncBotStatus(b)
			bindings = []*model.BotBinding{b}
		}
	} else {
		// 查所有平台的绑定
		all, err := model.MBotBinding.ListByUserId(ctx, req.UserId)
		if err != nil {
			return nil, fmt.Errorf("查询绑定列表失败: %w", err)
		}
		for _, b := range all {
			b.BotStatus = syncBotStatus(b)
		}
		bindings = all
	}

	if err != nil {
		return nil, err
	}

	items := make([]*response.BotBindingItem, 0, len(bindings))
	for _, b := range bindings {
		items = append(items, &response.BotBindingItem{
			Id:          b.Id,
			UserId:      b.UserId,
			Platform:    b.Platform,
			AppId:       b.AppId,
			AppSecret:   desensitizeSecret(b.AppSecret),
			TenantKey:   b.TenantKey,
			BotStatus:   b.BotStatus,
			BotName:     b.BotName,
			Description: b.Description,
			CreatedAt:   b.CreatedAt,
			UpdatedAt:   b.UpdatedAt,
		})
	}
	return items, nil
}

// syncBotStatus 同步 DB 中存储的 Bot 连接状态和实际连接状态
func syncBotStatus(b *model.BotBinding) int {
	if BotManagerInstance.IsRunning(b.Platform, b.UserId) {
		return 1
	}
	return b.BotStatus
}

// startBotForBinding 根据绑定信息启动 Bot
func startBotForBinding(ctx context.Context, binding *model.BotBinding) error {
	var extraJSON string
	if binding.ExtraConfig != nil {
		extraJSON = *binding.ExtraConfig
	}

	config := bot.BotConfig{
		AppID:     binding.AppId,
		AppSecret: binding.AppSecret,
		BotUserID: binding.UserId,
		Platform:  binding.Platform,
		ExtraJSON: extraJSON,
	}

	return BotManagerInstance.StartBot(ctx, config)
}

// StartupBots 启动时恢复所有已绑定的 Bot 连接
func StartupBots(ctx context.Context) {
	bindings, err := model.MBotBinding.ListByUserId(ctx, 0) // 0 查所有
	if err != nil {
		logger.Errorf("[StartupBots] 查询所有绑定失败: %v", err)
		return
	}

	for _, binding := range bindings {
		if binding.BotStatus == 1 {
			if err := startBotForBinding(ctx, binding); err != nil {
				logger.Warnf("[StartupBots] 启动 Bot 失败: user_id=%d, platform=%s, err=%v",
					binding.UserId, binding.Platform, err)
				if uerr := binding.UpdateStatus(ctx, 2); uerr != nil {
					logger.Errorf("[StartupBots] 更新连接失败状态出错: binding_id=%d, err=%v", binding.Id, uerr)
				}
			}
		}
	}
}

// desensitizeSecret 掩码敏感信息
func desensitizeSecret(secret string) string {
	if len(secret) <= 8 {
		return "****"
	}
	return secret[:4] + "****" + secret[len(secret)-4:]
}

// ListBotBinding 管理员分页查询 Bot 绑定列表
func ListBotBinding(ctx context.Context, req *request.BotBindingListRequest) (*response.BotBindingListResponse, error) {
	items, total, err := model.MBotBinding.List(ctx, req)
	if err != nil {
		return nil, fmt.Errorf("查询 Bot 绑定列表失败: %w", err)
	}

	respItems := make([]response.BotBindingItem, 0, len(items))
	for _, b := range items {
		respItems = append(respItems, response.BotBindingItem{
			Id:          b.Id,
			UserId:      b.UserId,
			Platform:    b.Platform,
			AppId:       b.AppId,
			AppSecret:   "***",
			TenantKey:   b.TenantKey,
			BotStatus:   b.BotStatus,
			BotName:     b.BotName,
			Description: b.Description,
			CreatedAt:   b.CreatedAt,
			UpdatedAt:   b.UpdatedAt,
		})
	}

	return &response.BotBindingListResponse{
		Items: respItems,
		Total: total,
	}, nil
}

// LoadBotManager 返回全局 BotManager（供外部使用）
func LoadBotManager() *bot.BotManager {
	return BotManagerInstance
}
