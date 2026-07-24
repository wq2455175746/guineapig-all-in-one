package bot

import "context"

// Platform 常量
const (
	PlatformFeishu   = "feishu"
	PlatformWechat   = "wechat"
	PlatformDingtalk = "dingtalk"
)

// BotMessage 平台无关的统一消息结构
type BotMessage struct {
	Platform  string // feishu | wechat | dingtalk
	BotUserID int64  // bot_creator 的 user_id（由 bot 启动时注入）
	ExtChatID string // IM 平台会话 ID
	ExtSender string // IM 平台发送者 ID
	Content   string // 文本内容
	Raw       any    // 原始事件（透传）
}

// BotReply 统一回复结构
type BotReply struct {
	Text string
}

// BotConfig Bot 启动配置
type BotConfig struct {
	AppID     string
	AppSecret string
	BotUserID int64  // bot_creator 的 user_id
	Platform  string // feishu | wechat | dingtalk
	ExtraJSON string // 各平台私有配置（JSON 字符串）
}

// Bot 接口 — 每种 IM 平台一个实现
type Bot interface {
	// Platform 返回平台标识
	Platform() string

	// Start 启动 Bot（建立 WebSocket / 注册 Webhook）
	Start(ctx context.Context, config BotConfig) error

	// Stop 停止 Bot
	Stop() error

	// SendMessage 发送消息到 IM 平台
	SendMessage(ctx context.Context, extChatID string, reply *BotReply) error

	// EventChan 返回消息事件通道
	EventChan() <-chan *BotMessage

	// IsRunning 检查连接状态
	IsRunning() bool
}

// Factory Bot 实例工厂
type Factory func() Bot

var factories = make(map[string]Factory)

// Register 注册平台 Bot 工厂
func Register(platform string, factory Factory) {
	factories[platform] = factory
}

// Create 创建 Bot 实例
func Create(platform string) Bot {
	factory, ok := factories[platform]
	if !ok {
		return nil
	}
	return factory()
}
