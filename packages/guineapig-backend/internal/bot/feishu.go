package bot

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	gconfig "guineapig/config"
	"guineapig/pkg/ratelimit"

	lark "github.com/larksuite/oapi-sdk-go/v3"
	"github.com/larksuite/oapi-sdk-go/v3/event/dispatcher"
	larkim "github.com/larksuite/oapi-sdk-go/v3/service/im/v1"
	larkws "github.com/larksuite/oapi-sdk-go/v3/ws"
)

func init() {
	Register(PlatformFeishu, func() Bot {
		return &FeishuBot{}
	})
}

// FeishuBot 飞书 Bot 实现
type FeishuBot struct {
	config      BotConfig
	client      *lark.Client
	wsCli       *larkws.Client
	eventCh     chan *BotMessage
	stopCh      chan struct{}
	closeOnce   sync.Once
	running     atomic.Bool
	rateLimiter *ratelimit.TokenBucket
}

// Platform 返回平台标识
func (b *FeishuBot) Platform() string {
	return PlatformFeishu
}

// IsRunning 检查连接状态
func (b *FeishuBot) IsRunning() bool {
	return b.running.Load()
}

// EventChan 返回消息事件通道
func (b *FeishuBot) EventChan() <-chan *BotMessage {
	return b.eventCh
}

// Start 启动 FeishuBot WebSocket 连接
func (b *FeishuBot) Start(ctx context.Context, config BotConfig) error {
	b.config = config
	b.eventCh = make(chan *BotMessage, 256)
	b.stopCh = make(chan struct{})

	// 初始化消息发送限流器（默认 5 QPS）
	qps := gconfig.Global.RateLimiter.BotQps
	if qps <= 0 {
		qps = 5
	}
	b.rateLimiter = ratelimit.NewTokenBucket(float64(qps), qps)

	// 创建飞书 SDK Client
	b.client = lark.NewClient(config.AppID, config.AppSecret)

	// 创建事件分发器并注册 im.message.receive_v1 事件处理
	eventHandler := dispatcher.NewEventDispatcher("", "").
		OnP2MessageReceiveV1(func(ctx context.Context, event *larkim.P2MessageReceiveV1) error {
			return b.handleMessageReceive(ctx, event)
		})

	// 创建 WebSocket 事件订阅客户端
	b.wsCli = larkws.NewClient(config.AppID, config.AppSecret,
		larkws.WithEventHandler(eventHandler),
		larkws.WithAutoReconnect(true),
	)

	// 启动 WebSocket 连接（异步）
	go func() {
		if err := b.wsCli.Start(ctx); err != nil {
			b.running.Store(false)
		}
	}()

	b.running.Store(true)
	return nil
}

// Stop 停止 FeishuBot
func (b *FeishuBot) Stop() error {
	if !b.running.Load() {
		return nil
	}
	b.running.Store(false)
	b.closeOnce.Do(func() {
		close(b.stopCh)
		close(b.eventCh)
	})
	return nil
}

// SendMessage 发送文本消息到飞书
func (b *FeishuBot) SendMessage(ctx context.Context, extChatID string, reply *BotReply) error {
	if !b.running.Load() {
		return errors.New("bot 未连接")
	}

	// 限流等待（最多等 5 秒）
	for i := 0; i < 100; i++ {
		if b.rateLimiter.Allow() {
			break
		}
		time.Sleep(50 * time.Millisecond)
	}

	content := map[string]string{
		"text": reply.Text,
	}
	contentJSON, _ := json.Marshal(content)

	req := larkim.NewCreateMessageReqBuilder().
		ReceiveIdType("chat_id").
		Body(larkim.NewCreateMessageReqBodyBuilder().
			ReceiveId(extChatID).
			MsgType("text").
			Content(string(contentJSON)).
			Build()).
		Build()

	resp, err := b.client.Im.Message.Create(ctx, req)
	if err != nil {
		return err
	}
	if !resp.Success() {
		return errors.New(resp.Msg)
	}
	return nil
}

// handleMessageReceive 处理飞书消息接收事件（私聊+群聊）
func (b *FeishuBot) handleMessageReceive(ctx context.Context, event *larkim.P2MessageReceiveV1) error {
	if !b.running.Load() {
		return nil
	}
	if event.Event == nil || event.Event.Message == nil {
		return nil
	}

	msg := event.Event.Message
	chatID := safeString(msg.ChatId)

	// 只处理文本消息
	msgType := safeString(msg.MessageType)
	if msgType != "text" {
		return nil
	}

	// 解析文本内容（飞书文本消息格式: {"text":"xxx"}）
	contentRaw := safeString(msg.Content)
	if contentRaw == "" {
		return nil
	}

	var content struct {
		Text string `json:"text"`
	}
	if err := json.Unmarshal([]byte(contentRaw), &content); err != nil {
		return nil
	}

	contentText := strings.TrimSpace(content.Text)
	if contentText == "" {
		return nil
	}

	// 提取 sender 信息
	senderID := ""
	sender := event.Event.Sender
	if sender != nil && sender.SenderId != nil {
		if sender.SenderId.OpenId != nil {
			senderID = *sender.SenderId.OpenId
		} else if sender.SenderId.UserId != nil {
			senderID = *sender.SenderId.UserId
		}
	}

	// 转为统一消息结构
	botMsg := &BotMessage{
		Platform:  PlatformFeishu,
		BotUserID: b.config.BotUserID,
		ExtChatID: chatID,
		ExtSender: senderID,
		Content:   contentText,
		Raw:       event,
	}

	// 发送到事件通道（非阻塞，丢弃溢出消息避免阻塞事件处理）
	select {
	case b.eventCh <- botMsg:
	default:
	}

	return nil
}

// safeString 安全解引用 *string
func safeString(s *string) string {
	if s == nil {
		return ""
	}
	return *s
}
