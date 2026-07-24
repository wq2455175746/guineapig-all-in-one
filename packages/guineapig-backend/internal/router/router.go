package router

import (
	"guineapig/internal/router/aimodel"
	botRouter "guineapig/internal/router/bot"
	"guineapig/internal/router/chat"
	fileRouter "guineapig/internal/router/file"
	"guineapig/internal/router/mcp"
	memoryRouter "guineapig/internal/router/memory"
	"guineapig/internal/router/otel"
	ragRouter "guineapig/internal/router/rag"
	schedulerRouter "guineapig/internal/router/scheduler"
	"guineapig/internal/router/skill"
	"guineapig/internal/router/user"

	"github.com/labstack/echo/v4"
)

func init() {
	// 用户相关
	AddGetRouter("/users", user.ListUser)
	AddGetRouter("/user/search", user.SearchUser)
	AddGetRouter("/user/decryptUserInfo", user.DecryptUserInfo)
	AddPostRouter("/client/login", user.ClientLogin)
	AddPostRouter("/client/register", user.Register)

	// AI模型相关
	AddPostRouter("/aimodel/create", aimodel.Create)
	AddPostRouter("/aimodel/update", aimodel.Update)
	AddPostRouter("/aimodel/delete", aimodel.Delete)
	AddPostRouter("/aimodel/updateEstablished", aimodel.UpdateEstablished)
	AddGetRouter("/aimodel/list", aimodel.List)
	AddGetRouter("/aimodel/options", aimodel.Options)
	AddPostRouter("/aimodel/test", aimodel.TestConnection)
	AddGetRouter("/aimodel/presigned-upload-url", aimodel.PresignedUploadURL)
	AddGetRouter("/aimodel/presigned-download-url", aimodel.PresignedDownloadURL)
	AddGetRouter("/aimodel/options-by-type", aimodel.OptionsByType)

	// 聊天相关
	AddGetRouter("/chat/ws", chat.WebSocketHandler)
	AddPostRouter("/chat/send", chat.SendChatMessage)
	AddGetRouter("/chat/conversations", chat.ListConversations)
	AddGetRouter("/chat/messages", chat.ListMessages)
	AddGetRouter("/chat/conversation-history", chat.ListConversationHistory)

	// 记忆相关
	AddGetRouter("/memory/list", memoryRouter.List)
	AddGetRouter("/memory/get", memoryRouter.Get)
	AddPostRouter("/memory/delete", memoryRouter.Delete)
	AddPostRouter("/memory/summarize", memoryRouter.Summarize)
	AddPostRouter("/memory/update-content", memoryRouter.UpdateContent)

	// Skill 相关
	AddGetRouter("/skill/presigned-upload-url", skill.PresignedUploadURL)
	AddPostRouter("/skill/create", skill.Create)
	AddPostRouter("/skill/update", skill.Update)
	AddPostRouter("/skill/delete", skill.Delete)
	AddGetRouter("/skill/list", skill.List)

	// MCP 相关
	AddPostRouter("/mcp/create", mcp.Create)
	AddPostRouter("/mcp/update", mcp.Update)
	AddPostRouter("/mcp/delete", mcp.Delete)
	AddGetRouter("/mcp/list", mcp.List)

	// 文件管理相关
	AddGetRouter("/file/presigned-upload-url", fileRouter.PresignedUploadURL)
	AddGetRouter("/file/presigned-download-url", fileRouter.PresignedDownloadURL)
	AddGetRouter("/file/list", fileRouter.List)
	AddPostRouter("/file/create", fileRouter.Create)
	AddPostRouter("/file/update", fileRouter.Update)
	AddPostRouter("/file/delete", fileRouter.Delete)
	AddPostRouter("/file/embed", fileRouter.Embed)
	AddPostRouter("/file/embed-progress", fileRouter.EmbedProgress)

	// RAG 知识库相关
	AddPostRouter("/rag/create", ragRouter.Create)
	AddPostRouter("/rag/update", ragRouter.Update)
	AddPostRouter("/rag/delete", ragRouter.Delete)
	AddGetRouter("/rag/list", ragRouter.List)

	// 可观察指标相关
	AddGetRouter("/otel/list", otel.List)
	AddPostRouter("/otel/delete", otel.Delete)
	AddGetRouter("/otel/chart/data", otel.ChartData)

	// IM Bot 绑定管理
	AddPostRouter("/bot/bind", botRouter.Bind)
	AddPostRouter("/bot/unbind", botRouter.Unbind)
	AddGetRouter("/bot/info", botRouter.Info)
}

type Router struct {
	Method   string
	Path     string
	HandleFn echo.HandlerFunc
}

var routers []Router

func Register(srv *echo.Echo) {
	for _, r := range routers {
		srv.Add(r.Method, r.Path, r.HandleFn)
	}
}

func addRouter(method, path string, fn echo.HandlerFunc) {
	routers = append(routers, Router{
		Method:   method,
		Path:     "/api/v1" + path,
		HandleFn: fn,
	})
}

// addAdminRouter 注册运营管理后台 API，路径前缀为 /admin/api/v1
func addAdminRouter(method, path string, fn echo.HandlerFunc) {
	routers = append(routers, Router{
		Method:   method,
		Path:     "/admin/api/v1" + path,
		HandleFn: fn,
	})
}

// addInnerRouter 注册内部服务调用 API（供 aiagent 回调），路径前缀为 /inner/api/v1，无需鉴权
func addInnerRouter(method, path string, fn echo.HandlerFunc) {
	routers = append(routers, Router{
		Method:   method,
		Path:     "/inner/api/v1" + path,
		HandleFn: fn,
	})
}

// 注册所有运营管理后台 API 路由
func registerAdminRoutes() {
	// 用户管理
	addAdminRouter(echo.GET, "/users", user.ListUser)
	addAdminRouter(echo.GET, "/user/search", user.SearchUser)
	addAdminRouter(echo.GET, "/user/decryptUserInfo", user.DecryptUserInfo)

	// 模型管理
	addAdminRouter(echo.GET, "/aimodel/list", aimodel.List)

	// 文件管理
	addAdminRouter(echo.GET, "/file/list", fileRouter.List)

	// Skill 管理
	addAdminRouter(echo.GET, "/skill/list", skill.List)

	// MCP 管理
	addAdminRouter(echo.GET, "/mcp/list", mcp.List)

	// 记忆管理
	addAdminRouter(echo.GET, "/memory/list", memoryRouter.List)
	addAdminRouter(echo.GET, "/memory/get", memoryRouter.Get)

	// 对话管理
	addAdminRouter(echo.GET, "/chat/conversation-history", chat.ListConversationHistory)
	addAdminRouter(echo.GET, "/chat/messages", chat.ListMessages)

	// 可观察指标
	addAdminRouter(echo.GET, "/otel/list", otel.List)
	addAdminRouter(echo.GET, "/otel/chart/data", otel.ChartData)

	// 定时任务调度
	addAdminRouter(echo.GET, "/task-scheduler/list", schedulerRouter.List)

	// IM Bot 绑定管理
	addAdminRouter(echo.GET, "/bot/list", botRouter.AdminList)
}

// registerInnerRoutes 注册内部服务调用 API（供 aiagent 回调），路径前缀为 /inner/api/v1
func registerInnerRoutes() {
	// 文件嵌入进度回调
	addInnerRouter(echo.POST, "/file/embed-progress", fileRouter.EmbedProgress)

	// 记忆内容更新回调
	addInnerRouter(echo.POST, "/memory/update-content", memoryRouter.UpdateContent)
}

func init() {
	registerAdminRoutes()
	registerInnerRoutes()
}

func AddGetRouter(path string, fn echo.HandlerFunc) {
	addRouter(echo.GET, path, fn)
}

func AddPostRouter(path string, fn echo.HandlerFunc) {
	addRouter(echo.POST, path, fn)
}

func AddPutRouter(path string, fn echo.HandlerFunc) {
	addRouter(echo.PUT, path, fn)
}

func AddDeleteRouter(path string, fn echo.HandlerFunc) {
	addRouter(echo.DELETE, path, fn)
}
