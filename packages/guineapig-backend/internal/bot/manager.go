package bot

import (
	"context"
	"fmt"
	"sync"
	"time"
)

// BotManager 多租户多平台 Bot 连接管理器
type BotManager struct {
	mu         sync.RWMutex
	bots       map[string]Bot // key: "{platform}:{user_id}"
	botCancels map[string]context.CancelFunc

	// 消息回调函数（由 service 层注册）
	onMessage func(ctx context.Context, msg *BotMessage) error
}

// NewBotManager 创建 BotManager
func NewBotManager() *BotManager {
	return &BotManager{
		bots:       make(map[string]Bot),
		botCancels: make(map[string]context.CancelFunc),
	}
}

// SetOnMessage 设置消息回调
func (m *BotManager) SetOnMessage(handler func(ctx context.Context, msg *BotMessage) error) {
	m.onMessage = handler
}

// StartBot 启动一个 Bot
func (m *BotManager) StartBot(ctx context.Context, config BotConfig) error {
	key := botKey(config.Platform, config.BotUserID)

	m.mu.Lock()
	defer m.mu.Unlock()

	// 如果已有同平台的 Bot 在运行，先停止
	if existing, ok := m.bots[key]; ok {
		_ = existing.Stop()
		delete(m.bots, key)
		if cancel, ok := m.botCancels[key]; ok {
			cancel()
			delete(m.botCancels, key)
		}
	}

	// 创建 Bot 实例
	bot := Create(config.Platform)
	if bot == nil {
		return fmt.Errorf("不支持的平台: %s", config.Platform)
	}

	// 启动
	if err := bot.Start(ctx, config); err != nil {
		return fmt.Errorf("启动 Bot 失败: %w", err)
	}

	m.bots[key] = bot

	// 创建可取消的 context 用于 dispatch 生命周期管理
	botCtx, botCancel := context.WithCancel(context.Background())
	m.botCancels[key] = botCancel

	// 启动消息分发 goroutine
	go m.dispatchBotEvents(botCtx, bot)

	return nil
}

// StopBot 停止一个 Bot
func (m *BotManager) StopBot(platform string, userID int64) error {
	key := botKey(platform, userID)

	m.mu.Lock()
	defer m.mu.Unlock()

	bot, ok := m.bots[key]
	if !ok {
		return nil
	}

	delete(m.bots, key)
	if cancel, ok := m.botCancels[key]; ok {
		cancel()
		delete(m.botCancels, key)
	}
	return bot.Stop()
}

// GetBot 获取 Bot 实例
func (m *BotManager) GetBot(platform string, userID int64) Bot {
	key := botKey(platform, userID)

	m.mu.RLock()
	defer m.mu.RUnlock()

	return m.bots[key]
}

// IsRunning 检查 Bot 是否在运行
func (m *BotManager) IsRunning(platform string, userID int64) bool {
	bot := m.GetBot(platform, userID)
	if bot == nil {
		return false
	}
	return bot.IsRunning()
}

// dispatchBotEvents 分发单个 Bot 的事件
func (m *BotManager) dispatchBotEvents(ctx context.Context, b Bot) {
	for {
		select {
		case <-ctx.Done():
			return
		case msg, ok := <-b.EventChan():
			if !ok {
				return // eventCh 已关闭
			}
			if m.onMessage != nil {
				_ = m.onMessage(ctx, msg)
			}
		}
	}
}

// SendMessage 通过 BotManager 发送消息到 IM 平台
func (m *BotManager) SendMessage(platform string, userID int64, extChatID string, reply *BotReply) error {
	bot := m.GetBot(platform, userID)
	if bot == nil {
		return fmt.Errorf("bot 未运行: platform=%s, user_id=%d", platform, userID)
	}
	return bot.SendMessage(context.Background(), extChatID, reply)
}

// WaitForReady 等待所有已启动的 Bot 建立连接，超时返回
func (m *BotManager) WaitForReady(timeout time.Duration) {
	deadline := time.Now().Add(timeout)
	for time.Now().Before(deadline) {
		m.mu.RLock()
		allReady := len(m.bots) > 0
		for _, b := range m.bots {
			if !b.IsRunning() {
				allReady = false
				break
			}
		}
		count := len(m.bots)
		m.mu.RUnlock()

		if allReady {
			return
		}
		if count == 0 {
			return // 没有 Bot 需要等待
		}
		time.Sleep(200 * time.Millisecond)
	}
}

// StopAll 停止所有 Bot
func (m *BotManager) StopAll() {
	m.mu.Lock()
	defer m.mu.Unlock()

	for key, bot := range m.bots {
		_ = bot.Stop()
		delete(m.bots, key)
	}
	for key, cancel := range m.botCancels {
		cancel()
		delete(m.botCancels, key)
	}
}

// ListBots 列出所有运行中的 Bot 摘要
func (m *BotManager) ListBots() []BotSummary {
	m.mu.RLock()
	defer m.mu.RUnlock()

	summaries := make([]BotSummary, 0, len(m.bots))
	for key, b := range m.bots {
		platform, userID := parseBotKey(key)
		summaries = append(summaries, BotSummary{
			Platform: platform,
			UserID:   userID,
			Running:  b.IsRunning(),
		})
	}
	return summaries
}

// BotSummary Bot 摘要信息
type BotSummary struct {
	Platform string
	UserID   int64
	Running  bool
}

// botKey [{platform}:{user_id}]
func botKey(platform string, userID int64) string {
	return fmt.Sprintf("%s:%d", platform, userID)
}

// parseBotKey 解析 key
func parseBotKey(key string) (string, int64) {
	var platform string
	var userID int64
	_, _ = fmt.Sscanf(key, "%s:%d", &platform, &userID)
	return platform, userID
}
