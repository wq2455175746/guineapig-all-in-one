package middleware

import (
	"net/http"
	"strconv"
	"strings"

	"github.com/labstack/echo/v4"
	"github.com/spf13/cast"
	"guineapig/config"
	"guineapig/internal/model"
)

type AuthErrorResponse struct {
	Code      int    `json:"code"`
	Message   string `json:"message"`
	Detail    string `json:"detail"`
	RequestId string `json:"requestId"`
}

// Auth 接口鉴权中间件
// 对于 /api/v1/ 路径：检查 X-User-Id 对应的用户是否存在
// 对于 /admin/api/v1/ 路径：检查 X-Admin-Token 是否匹配配置中的管理后台 Token
// 对于 /inner/api/v1/ 路径：跳过鉴权（内部服务调用）
// 跳过公开路径：/client/login, /client/register, /chat/ws 等
func Auth() echo.MiddlewareFunc {
	skipPaths := map[string]bool{
		"/api/v1/client/login":    true,
		"/api/v1/client/register": true,
		"/api/v1/chat/ws":         true,
	}

	adminToken := config.Global.Admin.Token

	return func(next echo.HandlerFunc) echo.HandlerFunc {
		return func(c echo.Context) error {
			// 跳过 OPTIONS 预检请求
			if c.Request().Method == http.MethodOptions {
				return next(c)
			}

			requestId := cast.ToString(c.Get("requestId"))
			authErr := func(detail string) error {
				return c.JSON(http.StatusUnauthorized, AuthErrorResponse{
					Code:      http.StatusUnauthorized,
					Message:   "未授权",
					Detail:    detail,
					RequestId: requestId,
				})
			}

			path := c.Path()

			// 跳过公开路径
			if skipPaths[path] {
				return next(c)
			}

			// 管理后台路由鉴权：检查 X-Admin-Token
			if strings.HasPrefix(path, "/admin/api/v1/") {
				token := c.Request().Header.Get("X-Admin-Token")
				if token == "" {
					return authErr("缺少管理后台 Token")
				}
				if adminToken == "" {
					return authErr("管理后台 Token 未配置")
				}
				if token != adminToken {
					return authErr("管理后台 Token 无效")
				}
				return next(c)
			}

			// 内部服务路由（/inner/api/v1/）：跳过鉴权
			if strings.HasPrefix(path, "/inner/api/v1/") {
				return next(c)
			}

			// 普通客户端鉴权：检查 X-User-Id
			userIDStr := c.Request().Header.Get("X-User-Id")
			if userIDStr == "" {
				return authErr("缺少用户标识")
			}

			userID, err := strconv.ParseInt(userIDStr, 10, 64)
			if err != nil {
				return authErr("无效的用户标识")
			}

			// 校验用户是否存在
			user, err := model.MUser.FindById(c.Request().Context(), userID)
			if err != nil {
				return c.JSON(http.StatusInternalServerError, AuthErrorResponse{
					Code:      http.StatusInternalServerError,
					Message:   "系统错误",
					Detail:    "验证用户信息失败",
					RequestId: requestId,
				})
			}

			if user == nil {
				return authErr("用户不存在或未登录")
			}

			return next(c)
		}
	}
}
