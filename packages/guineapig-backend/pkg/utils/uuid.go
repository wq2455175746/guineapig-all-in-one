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
	// 从 echo.Context 获取 requestId
	requestId := e.Get("requestId")

	// 创建一个新的 context，并将 requestId 放入其中
	ctx := context.WithValue(context.Background(), "requestId", requestId)

	return ctx
}

// BackendContext 复制一个context,设置永不过期
func BackendContext(src context.Context) context.Context {
	return context.Background()
}
