package utils

import (
	"context"
	"github.com/google/uuid"
	"github.com/labstack/echo/v4"
	"strings"
)

func UUID() string {
	uid := uuid.New().String()
	return strings.ReplaceAll(uid, "-", "")
}

func NewContext(e echo.Context) context.Context {
	// 从请求 context 派生，保证客户端断开/超时能向下游（DB/Redis/HTTP）传播取消
	ctx := e.Request().Context()

	// 保留 requestId 供日志链路追踪
	if requestId := e.Get("requestId"); requestId != nil {
		ctx = context.WithValue(ctx, "requestId", requestId)
	}

	return ctx
}

// BackendContext 复制一个context,设置永不过期
func BackendContext(src context.Context) context.Context {
	return context.Background()
}
