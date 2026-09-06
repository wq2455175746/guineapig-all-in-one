package plugin

import (
	"context"
	"fmt"
	"github.com/redis/go-redis/extra/redisotel/v9"
	"github.com/redis/go-redis/v9"
	"guineapig/config"
	"guineapig/pkg/plugin/logger"
	"strings"
	"time"
)

var rdb *redis.Client

func SetupRedis(conf config.Redis) {
	rdb = NewRedisClient(conf)

	// Enable tracing instrumentation.
	if err := redisotel.InstrumentTracing(rdb); err != nil {
		panic(err)
	}
	pong, err := rdb.Ping(context.Background()).Result()
	if err != nil {
		panic(fmt.Sprintf("连接 Redis 失败: %v", err))
	}
	// 预期输出: PONG
	logger.Infof("Redis 连接成功: %s", pong)
}

func NewRedisClient(conf config.Redis) *redis.Client {
	var client *redis.Client
	if strings.Contains(conf.Addr, ",") {
		nodes := strings.Split(conf.Addr, ",")
		client = redis.NewFailoverClient(&redis.FailoverOptions{
			MasterName:       conf.MasterName,
			SentinelAddrs:    nodes,
			SentinelPassword: conf.SentinelPassword,
			Password:         conf.Password,
		})

		return client
	} else {
		client = redis.NewClient(&redis.Options{
			Addr:            conf.Addr,
			Password:        conf.Password,
			DB:              conf.Db,
			PoolSize:        10,
			DisableIdentity: true,
		})

		return client
	}
}

func GetClient() *redis.Client {
	return rdb
}

func Set(ctx context.Context, key string, value interface{}, expiration time.Duration) (string, error) {
	return rdb.Set(ctx, key, value, expiration).Result()
}

func Get(ctx context.Context, key string) (string, error) {
	return rdb.Get(ctx, key).Result()
}

// AcquireLock 获取锁
func AcquireLock(ctx context.Context, key string, ttl time.Duration) (bool, error) {
	// 使用 SETNX 尝试设置锁，并指定过期时间
	success, err := rdb.SetNX(ctx, key, "locked", ttl).Result()
	if err != nil {
		return false, err
	}

	return success, nil
}

// ReleaseLock 释放分布式锁
func ReleaseLock(ctx context.Context, key string) {
	_, err := rdb.Del(ctx, key).Result()
	if err != nil {
		logger.ErrorReqIdf(ctx, "Error releasing lock: %v", err)
	}
}
