package service

import (
	"context"
	"encoding/json"

	"guineapig/internal/model"
	"guineapig/pkg/plugin"
	"guineapig/pkg/plugin/logger"
)

// Bot 控制通道。
//
// 多副本下 IM Bot 长连接只由专用实例持有（RUN_BOTS=true），
// 而 bind/unbind 请求可能落在任意副本。任意副本处理完绑定变更后
// 通过 Redis Pub/Sub 广播指令，仅 Bot 实例订阅并执行本地启停，
// 从而保证"解绑在全局生效"，而不是只停处理请求的那个副本。
const botControlChannel = "bot:control"

type botControlMsg struct {
	Action   string `json:"action"` // start | stop
	Platform string `json:"platform"`
	UserID   int64  `json:"user_id"`
}

// PublishBotControl 广播 Bot 启停指令（任意副本可调用）。
func PublishBotControl(ctx context.Context, action, platform string, userID int64) {
	payload, err := json.Marshal(botControlMsg{Action: action, Platform: platform, UserID: userID})
	if err != nil {
		logger.Errorf("[BotControl] 序列化指令失败: %v", err)
		return
	}
	if err := plugin.GetClient().Publish(ctx, botControlChannel, payload).Err(); err != nil {
		logger.Errorf("[BotControl] 发布指令失败: action=%s, platform=%s, user_id=%d, err=%v",
			action, platform, userID, err)
	}
}

// SubscribeBotControl 订阅 Bot 启停指令并应用到本地 BotManager（仅 Bot 实例调用）。
func SubscribeBotControl(ctx context.Context) {
	sub := plugin.GetClient().Subscribe(ctx, botControlChannel)
	defer sub.Close()

	logger.Infof("[BotControl] 已订阅 Bot 控制通道: %s", botControlChannel)
	ch := sub.Channel()
	for {
		select {
		case <-ctx.Done():
			return
		case msg, ok := <-ch:
			if !ok {
				return
			}
			var m botControlMsg
			if err := json.Unmarshal([]byte(msg.Payload), &m); err != nil {
				logger.Warnf("[BotControl] 解析指令失败: %v", err)
				continue
			}
			applyBotControl(ctx, m)
		}
	}
}

func applyBotControl(ctx context.Context, m botControlMsg) {
	switch m.Action {
	case "start":
		binding, err := model.MBotBinding.FindByUserAndPlatform(ctx, m.UserID, m.Platform)
		if err != nil || binding == nil {
			logger.Warnf("[BotControl] 找不到绑定，忽略 start: platform=%s, user_id=%d", m.Platform, m.UserID)
			return
		}
		if err := startBotForBinding(ctx, binding); err != nil {
			logger.Errorf("[BotControl] 启动 Bot 失败: platform=%s, user_id=%d, err=%v", m.Platform, m.UserID, err)
		}
	case "stop":
		if err := BotManagerInstance.StopBot(m.Platform, m.UserID); err != nil {
			logger.Warnf("[BotControl] 停止 Bot 失败: platform=%s, user_id=%d, err=%v", m.Platform, m.UserID, err)
		}
	}
}
