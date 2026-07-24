package service

import (
	"context"
	"guineapig/config"
	"guineapig/internal/response"

	"github.com/hibiken/asynq"
)

// schedulerTaskDescriptions 已知调度任务的中文描述（与 main.go 中注册的任务对应）
var schedulerTaskDescriptions = map[string]string{
	OtelSyncTaskType:         "同步 Redis OTel 指标数据到 MySQL",
	MemorySummarizeTaskType:  "每日记忆归纳，遍历所有用户执行昨日记忆归纳",
}

// ListSchedulerEntries 从 Redis 读取 Asynq Scheduler 的定时调度任务
func ListSchedulerEntries(ctx context.Context) (*response.SchedulerListResponse, error) {
	conf := config.Global
	inspector := asynq.NewInspector(asynq.RedisClientOpt{
		Addr:     conf.Redis.Addr,
		Password: conf.Redis.Password,
		DB:       conf.Redis.Db,
	})
	defer inspector.Close()

	entries, err := inspector.SchedulerEntries()
	if err != nil {
		return nil, err
	}

	resItems := make([]response.SchedulerEntryItem, 0, len(entries))
	for _, e := range entries {
		taskType := e.Task.Type()
		nextStr := ""
		if !e.Next.IsZero() {
			nextStr = e.Next.Format("2006-01-02 15:04:05")
		}
		prevStr := ""
		if !e.Prev.IsZero() {
			prevStr = e.Prev.Format("2006-01-02 15:04:05")
		}
		desc := schedulerTaskDescriptions[taskType]
		if desc == "" {
			desc = taskType
		}

		resItems = append(resItems, response.SchedulerEntryItem{
			ID:          e.ID,
			TaskType:    taskType,
			Spec:        e.Spec,
			NextEnqueue: nextStr,
			PrevEnqueue: prevStr,
			Description: desc,
		})
	}

	return &response.SchedulerListResponse{
		Entries: resItems,
	}, nil
}
