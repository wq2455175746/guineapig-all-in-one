package service

import (
	"context"
	"guineapig/internal/model"
	"guineapig/pkg/plugin"
	"guineapig/pkg/plugin/logger"
	"strconv"
	"strings"

	"github.com/hibiken/asynq"
)

const (
	// OtelSyncTaskType Asynq 任务类型名称
	OtelSyncTaskType = "otel:sync"
	otelRedisPrefix  = "otel:metrics:"
)

// SyncOtelMetrics 从 Redis Hash + Set 读取指标数据并同步到 MySQL（UPSERT）。
// 指标值存储在 Hash (HINCRBY)，conversation_ids 存储在 Set (SADD)。
// 不删除 Redis key，由 2 天 TTL 自动过期。
func SyncOtelMetrics(ctx context.Context) error {
	rdb := plugin.GetClient()

	// 扫描所有匹配的 key
	iter := rdb.Scan(ctx, 0, otelRedisPrefix+"*", 100).Iterator()

	syncedCount := 0
	for iter.Next(ctx) {
		key := iter.Val()

		// 跳过 :conversations Set key（SCAN 模式 otel:metrics:* 也会匹配到它）
		if strings.HasSuffix(key, ":conversations") {
			continue
		}

		// HGETALL 读取所有字段
		result, err := rdb.HGetAll(ctx, key).Result()
		if err != nil {
			logger.Errorf("[OtelSync] HGETALL 失败: key=%s, err=%v", key, err)
			continue
		}

		if len(result) == 0 {
			continue
		}

		// 解析 key: otel:metrics:{stat_date}:{user_id}
		parts := strings.SplitN(key, ":", 4)
		if len(parts) < 4 {
			logger.Warnf("[OtelSync] 无效的 key 格式: %s", key)
			continue
		}
		statDate := parts[2]
		userId := parseInt64(parts[3])
		if userId <= 0 {
			continue
		}

		// 从 Redis Set 读取 conversation IDs（aiagent 使用 SADD 写入）
		convSetKey := key + ":conversations"
		convIDStrs, err := rdb.SMembers(ctx, convSetKey).Result()
		var conversationIDs []int64
		if err == nil {
			for _, s := range convIDStrs {
				if id, e := strconv.ParseInt(s, 10, 64); e == nil {
					conversationIDs = append(conversationIDs, id)
				}
			}
		}

		// 遍历指标字段，逐条 UPSERT
		metricFields := []string{
			"input_token",
			"output_token",
			"request_count",
			"agent_mode_count",
			"web_search_count",
			"rag_count",
		}

		for _, field := range metricFields {
			val := result[field]
			if val == "" || val == "0" {
				continue
			}
			count := parseInt64(val)
			if count <= 0 {
				continue
			}
			if err := model.MChatOtel.UpsertCount(ctx, userId, field, statDate, "metric", count, conversationIDs); err != nil {
				logger.Errorf("[OtelSync] upsert 失败: key=%s, field=%s, err=%v", key, field, err)
				continue
			}
			syncedCount++
		}

		logger.Infof("[OtelSync] 同步完成: key=%s", key)
	}

	if err := iter.Err(); err != nil {
		logger.Errorf("[OtelSync] SCAN 迭代失败: %v", err)
		return err
	}

	if syncedCount > 0 {
		logger.Infof("[OtelSync] 本轮同步完成: 共写入 %d 条记录", syncedCount)
	}
	return nil
}

// HandleOtelSyncTask Asynq 任务处理器 — 由 Asynq Server 在消费任务时调用
func HandleOtelSyncTask(ctx context.Context, t *asynq.Task) error {
	logger.Infof("[OtelSync] Asynq 任务开始执行")
	if err := SyncOtelMetrics(ctx); err != nil {
		logger.Errorf("[OtelSync] Asynq 任务执行失败: %v", err)
		return err
	}
	logger.Infof("[OtelSync] Asynq 任务执行完成")
	return nil
}

func parseInt64(s string) int64 {
	var n int64
	for _, c := range s {
		if c >= '0' && c <= '9' {
			n = n*10 + int64(c-'0')
		} else {
			break
		}
	}
	return n
}
