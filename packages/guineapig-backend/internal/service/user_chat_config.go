package service

import (
	"context"
	"fmt"
	"strconv"

	"guineapig/pkg/plugin"
	"guineapig/pkg/plugin/logger"
)

// Redis 用户聊天配置 key 前缀：chat:config:{user_id}
// 存储用户最近一次从 client 端发送 chat 时的参数：
//   - model_id            (string: int64)
//   - web_search_enabled  (string: "true"/"false")
//   - agent_mode_enabled  (string: "true"/"false")
//
// 无 TTL，每次 client 发起 chat 时更新覆盖。
// Feishu 等外部渠道读取此配置以使用用户最新选择的模型和参数。
const redisKeyUserChatConfig = "chat:config:%d"

// SetUserChatConfig 保存用户聊天配置到 Redis Hash。
func SetUserChatConfig(ctx context.Context, userID int64, modelID int64, webSearchEnabled, agentModeEnabled bool) error {
	if userID <= 0 {
		return nil
	}

	rdb := plugin.GetClient()
	key := fmt.Sprintf(redisKeyUserChatConfig, userID)

	err := rdb.HSet(ctx, key,
		"model_id", strconv.FormatInt(modelID, 10),
		"web_search_enabled", fmt.Sprintf("%t", webSearchEnabled),
		"agent_mode_enabled", fmt.Sprintf("%t", agentModeEnabled),
	).Err()
	if err != nil {
		logger.Warnf("[UserChatConfig] HSet 失败: user_id=%d, err=%v", userID, err)
		return err
	}
	return nil
}

// GetUserChatConfig 读取用户聊天配置。
// Redis 中无记录或解析失败时返回零值（modelID=0, webSearchEnabled=false, agentModeEnabled=false），
// 调用方应据此降级为默认行为。
func GetUserChatConfig(ctx context.Context, userID int64) (modelID int64, webSearchEnabled, agentModeEnabled bool) {
	if userID <= 0 {
		return 0, false, false
	}

	rdb := plugin.GetClient()
	key := fmt.Sprintf(redisKeyUserChatConfig, userID)

	result, err := rdb.HGetAll(ctx, key).Result()
	if err != nil {
		logger.Warnf("[UserChatConfig] HGetAll 失败: user_id=%d, err=%v", userID, err)
		return 0, false, false
	}
	if len(result) == 0 {
		return 0, false, false
	}

	if v, ok := result["model_id"]; ok {
		if id, err := strconv.ParseInt(v, 10, 64); err == nil && id > 0 {
			modelID = id
		}
	}
	if v, ok := result["web_search_enabled"]; ok {
		webSearchEnabled = v == "true"
	}
	if v, ok := result["agent_mode_enabled"]; ok {
		agentModeEnabled = v == "true"
	}

	return modelID, webSearchEnabled, agentModeEnabled
}
