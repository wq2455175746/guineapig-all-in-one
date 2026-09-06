package middleware

import (
	"crypto/subtle"
	"net/http"
	"strings"

	"github.com/labstack/echo/v4"
	"github.com/spf13/cast"
	"guineapig/config"
	"guineapig/internal/model"
	"guineapig/pkg/auth"
)

type AuthErrorResponse struct {
	Code      int    `json:"code"`
	Message   string `json:"message"`
	Detail    string `json:"detail"`
	RequestId string `json:"requestId"`
}

// 鉴权上下文 Key
const (
	ContextRoleKey   = "authRole"
	ContextUserIDKey = "authUserId"
)

// 鉴权角色
const (
	RoleAdmin = "admin"
	RoleUser  = "user"
	RoleInner = "inner"
)

// Auth 接口鉴权中间件
//   - /api/v1/*          ：校验 HMAC 签名用户会话 Token（X-User-Token 或 Authorization: Bearer），
//     从 Token 推导 caller identity，X-User-Id 不再作为可信身份。
//   - /admin/api/v1/*    ：校验 X-Admin-Token 是否匹配配置中的管理后台 Token。
//   - /inner/api/v1/*    ：校验 X-Inner-Token 是否匹配配置中的内部服务 Token。
//   - 公开路径（/client/login、/client/register）：跳过鉴权。
//   - /chat/ws：跳过 header 鉴权，Token 由 WebSocket 握手参数校验（见 chat.WebSocketHandler）。
func Auth() echo.MiddlewareFunc {
	skipPaths := map[string]bool{
		"/api/v1/client/login":    true,
		"/api/v1/client/register": true,
		"/api/v1/chat/ws":         true,
	}

	adminToken := config.Global.Admin.Token
	innerToken := config.Global.Inner.Token

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
				if subtle.ConstantTimeCompare([]byte(token), []byte(adminToken)) != 1 {
					return authErr("管理后台 Token 无效")
				}
				c.Set(ContextRoleKey, RoleAdmin)
				return next(c)
			}

			// 内部服务路由（/inner/api/v1/）：校验共享内部 Token
			if strings.HasPrefix(path, "/inner/api/v1/") {
				token := c.Request().Header.Get("X-Inner-Token")
				if token == "" {
					return authErr("缺少内部服务 Token")
				}
				if innerToken == "" {
					return authErr("内部服务 Token 未配置")
				}
				if subtle.ConstantTimeCompare([]byte(token), []byte(innerToken)) != 1 {
					return authErr("内部服务 Token 无效")
				}
				c.Set(ContextRoleKey, RoleInner)
				return next(c)
			}

			// 普通客户端鉴权：校验 HMAC 签名用户会话 Token
			token := c.Request().Header.Get("X-User-Token")
			if token == "" {
				authz := c.Request().Header.Get("Authorization")
				if strings.HasPrefix(authz, "Bearer ") {
					token = strings.TrimPrefix(authz, "Bearer ")
				}
			}
			if token == "" {
				return authErr("缺少用户 Token")
			}

			userID, err := auth.ParseUserToken(config.Global.JwtSecret, token)
			if err != nil {
				return authErr("用户 Token 无效或已过期")
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

			c.Set(ContextRoleKey, RoleUser)
			c.Set(ContextUserIDKey, userID)
			return next(c)
		}
	}
}

// CurrentUserID 返回当前会话的 caller userID。
// 仅用户会话返回 >0 的值；admin / inner 会话返回 0。
func CurrentUserID(c echo.Context) int64 {
	uid, _ := c.Get(ContextUserIDKey).(int64)
	return uid
}

// IsAdminSession 判断当前会话是否为管理后台会话。
func IsAdminSession(c echo.Context) bool {
	return c.Get(ContextRoleKey) == RoleAdmin
}

// BindRequester 将请求中的 userId 覆盖为 Token 推导的 caller identity。
// 仅对用户会话生效；admin / inner 会话保留调用方传入的 userId。
// 用于杜绝客户端伪造他人 user_id 的 IDOR。
func BindRequester(c echo.Context, userId *int64) {
	if uid := CurrentUserID(c); uid > 0 {
		*userId = uid
	}
}
