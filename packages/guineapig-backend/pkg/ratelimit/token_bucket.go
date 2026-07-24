package ratelimit

import (
	"sync"
	"time"
)

// TokenBucket 简单的令牌桶限流器（惰性填充，无需后台 Goroutine）
type TokenBucket struct {
	mu       sync.Mutex
	rate     float64   // 每秒生成的令牌数
	capacity float64   // 桶容量（最大突发）
	tokens   float64   // 当前令牌数
	lastTime time.Time // 上次检查时间
}

// NewTokenBucket 创建令牌桶
// rate: 每秒令牌数（QPS）
// burst: 最大突发大小
func NewTokenBucket(rate float64, burst int) *TokenBucket {
	return &TokenBucket{
		rate:     rate,
		capacity: float64(burst),
		tokens:   float64(burst),
		lastTime: time.Now(),
	}
}

// Allow 尝试消费一个令牌，返回是否允许通过
// 若桶为空则返回 false，不阻塞
func (tb *TokenBucket) Allow() bool {
	tb.mu.Lock()
	defer tb.mu.Unlock()

	now := time.Now()
	elapsed := now.Sub(tb.lastTime).Seconds()
	tb.lastTime = now

	// 惰性填充：根据经过时间生成令牌
	tb.tokens += elapsed * tb.rate
	if tb.tokens > tb.capacity {
		tb.tokens = tb.capacity
	}

	if tb.tokens >= 1 {
		tb.tokens--
		return true
	}
	return false
}

// Wait 阻塞直到获取到令牌
func (tb *TokenBucket) Wait() {
	for !tb.Allow() {
		time.Sleep(50 * time.Millisecond)
	}
}
