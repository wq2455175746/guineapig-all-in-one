package chat

import (
	"fmt"
	"net/http"
	"strconv"
	"strings"

	"guineapig/internal/service"
	"guineapig/pkg/plugin/logger"

	"github.com/gorilla/websocket"
	"github.com/labstack/echo/v4"
)

var upgrader = websocket.Upgrader{
	ReadBufferSize:  4096,
	WriteBufferSize: 4096,
	CheckOrigin: func(r *http.Request) bool {
		return true // 开发阶段允许所有来源
	},
}

// WebSocketHandler 处理 WebSocket 升级和会话管理
func WebSocketHandler(e echo.Context) error {
	token := e.QueryParam("token")
	if token == "" {
		return e.String(401, "缺少 token 参数")
	}

	userID, err := parseToken(token)
	if err != nil {
		return e.String(401, fmt.Sprintf("token 无效: %v", err))
	}

	conn, err := upgrader.Upgrade(e.Response(), e.Request(), nil)
	if err != nil {
		logger.Errorf("[WS] 升级失败: user_id=%d, err=%v", userID, err)
		return err
	}

	hub := service.GetHub()
	hub.ServeWS(conn, userID)
	return nil
}

// parseToken 从 token 中解析 user_id
// token 格式可以是纯 user_id 数字，或 "user_{id}" 格式
// 生产环境应接入 JWT 验证
func parseToken(token string) (int64, error) {
	if id, err := strconv.ParseInt(token, 10, 64); err == nil && id > 0 {
		return id, nil
	}

	parts := strings.SplitN(token, "_", 2)
	if len(parts) == 2 && parts[0] == "user" {
		if id, err := strconv.ParseInt(parts[1], 10, 64); err == nil && id > 0 {
			return id, nil
		}
	}

	return 0, fmt.Errorf("无效的 token 格式: %s", token)
}
