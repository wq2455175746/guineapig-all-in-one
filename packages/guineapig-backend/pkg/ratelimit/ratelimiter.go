package ratelimit

import (
	"context"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"
)

// RateLimiter 并发控制
type RateLimiter interface {
	// Allow 是否获取到凭证
	Allow(ctx context.Context, key string, limit int) bool
	// Release 释放凭证
	Release(ctx context.Context, key string)
}

// entry 缓存的对象，包括值和过期时间
type entry struct {
	value    int
	expireAt time.Time
}

// MemoryRateLimiter 基于内存的并发控制器
type MemoryRateLimiter struct {
	data map[string]entry
	lock sync.RWMutex // 锁，用于控制并发操作map
}

// NewMemoryRateLimiter 构建内存并发控制器
func NewMemoryRateLimiter() RateLimiter {
	limiter := &MemoryRateLimiter{
		data: make(map[string]entry), // 初始化map
	}
	// 定期删除过期的key
	go limiter.cleanup()

	return limiter
}

// cleanup 定时器清理过期的key
func (rl *MemoryRateLimiter) cleanup() {
	// 每5分钟检查一次过期的key
	ticker := time.NewTicker(time.Minute * 5)
	defer ticker.Stop()

	for range ticker.C {
		// 加锁，确保串行读写map
		rl.lock.Lock()
		now := time.Now()
		for key, e := range rl.data {
			if now.After(e.expireAt) {
				// 过期删除map中的key
				delete(rl.data, key)
			}
		}
		rl.lock.Unlock()
	}
}

// incr 模拟redis incr操作
// 基于RWMutex实现串行
func (rl *MemoryRateLimiter) incr(ctx context.Context, key string, expireAt time.Time) int {
	rl.lock.Lock()
	defer rl.lock.Unlock()

	var current int
	if entry, ok := rl.data[key]; ok {
		if entry.expireAt.After(time.Now()) {
			// 没有过期
			current = entry.value
		}
	}
	current++ // 当前值+1
	rl.data[key] = entry{value: current, expireAt: expireAt}
	return current
}

// incr 模拟redis decr操作
// 基于RWMutex实现串行
func (rl *MemoryRateLimiter) decr(ctx context.Context, key string) int {
	rl.lock.Lock()
	defer rl.lock.Unlock()

	var current int
	if v, ok := rl.data[key]; ok {
		if v.expireAt.After(time.Now()) {
			// 没有过期
			current = v.value
			current--
			rl.data[key] = entry{value: current, expireAt: v.expireAt}
		}
	}
	// 如果过期了，直接返回0, 防止减到0以下
	return current
}

func (rl *MemoryRateLimiter) Allow(ctx context.Context, key string, limit int) bool {
	total := rl.incr(ctx, key, time.Now().Add(time.Hour))

	return total <= limit
}

func (rl *MemoryRateLimiter) Release(ctx context.Context, key string) {
	rl.decr(ctx, key)
}

// RedisRateLimiter 基于redis的并发控制器
type RedisRateLimiter struct {
	*redis.Client
}

func NewRedisRateLimiter(client *redis.Client) RateLimiter {
	return &RedisRateLimiter{Client: client}
}

func (rl *RedisRateLimiter) Allow(ctx context.Context, key string, limit int) bool {
	total, err := rl.Incr(ctx, key).Result()
	if err != nil {
		return false
	}
	rl.Expire(ctx, key, time.Hour)

	return total <= int64(limit)
}

func (rl *RedisRateLimiter) Release(ctx context.Context, key string) {
	rl.Decr(ctx, key)
}
