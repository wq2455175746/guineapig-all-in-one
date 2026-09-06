package chat

import (
	"fmt"
	"net/http"

	"guineapig/config"
	"guineapig/internal/service"
	"guineapig/pkg/auth"
	"guineapig/pkg/plugin/logger"

	"github.com/gorilla/websocket"
	"github.com/labstack/echo/v4"
)

var upgrader = websocket.Upgrader{
	ReadBufferSize:  4096,
	WriteBufferSize: 4096,
	// CheckOrigin 校验请求来源：仅允许白名单来源，不再允许任意跨域握手
	CheckOrigin: func(r *http.Request) bool {
		origin := r.Header.Get("Origin")
		if origin == "" {
			// 非浏览器客户端（桌面应用/脚本）不携带 Origin，允许连接
			return true
		}
		switch origin {
		case "http://guineapig-client.local:5174",
			"http://guineapig-ops-web.local:5173",
			"http://localhost:5174",
			"http://localhost:5173":
			return true
		}
		return false
	},
}

// WebSocketHandler 处理 WebSocket 升级和会话管理
func WebSocketHandler(e echo.Context) error {
	token := e.QueryParam("token")
	if token == "" {
		return e.String(401, "缺少 token 参数")
	}

	// 使用与服务端会话 Token 相同的 HMAC 签名校验，替代裸 user_id 解析
	userID, err := auth.ParseUserToken(config.Global.JwtSecret, token)
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
