package server

import (
	"context"
	"errors"
	"fmt"
	gdMid "guineapig/pkg/middleware"
	"guineapig/pkg/plugin/logger"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/labstack/echo/v4"
	"github.com/labstack/echo/v4/middleware"
)

type EchoServer struct {
	*echo.Echo
}

func NewServer(debug bool) *EchoServer {
	e := echo.New()
	e.Debug = debug

	e.Use(gdMid.RequestId)
	e.Use(gdMid.RateLimit())
	e.Use(middleware.Logger())
	e.Use(middleware.Recover())
	//e.Use(middleware.CORSWithConfig(middleware.CORSConfig{
	//	AllowOrigins:     strings.Split(config.Global.CorsHosts, ","),
	//	AllowCredentials: true,
	//	AllowHeaders:     append([]string{"Origin", "Content-Type", "Accept", "Authorization"}, strings.Split(config.Global.CorsHeaders, ",")...),
	//	AllowMethods:     []string{echo.GET, echo.POST, echo.PUT, echo.DELETE, echo.OPTIONS},
	//}))
	e.Use(middleware.CORSWithConfig(middleware.CORSConfig{
		// 1. 允许访问本后端的前端域名白名单
		AllowOrigins: []string{"http://guineapig-ops-web.local:5173", "http://guineapig-client.local:5174"},
		// 2. 是否允许跨域请求携带 Cookie、Token 凭证
		AllowCredentials: true,
		// 3. 前端请求里允许携带的自定义请求头白名单
		AllowHeaders: []string{"Origin", "Content-Type", "Accept", "Authorization", "X-Device-Id", "X-User-Id", "X-User-Token", "X-Request-Id", "X-Admin-Token", "X-Inner-Token"},
		// 4. 允许前端发起的 HTTP 请求方法
		AllowMethods: []string{echo.GET, echo.POST, echo.PUT, echo.DELETE, echo.OPTIONS},
	}))
	// 健康检查端点（需要在 Auth 中间件之前注册，避免鉴权）
	e.GET("/health", func(c echo.Context) error {
		return c.JSON(http.StatusOK, map[string]any{
			"status": "ok",
			"time":   time.Now().Unix(),
		})
	})
	e.GET("/api/v1/health", func(c echo.Context) error {
		return c.JSON(http.StatusOK, map[string]any{
			"status": "ok",
			"time":   time.Now().Unix(),
		})
	})
	e.Use(gdMid.Auth())
	// 企业微信登录 https://developer.work.weixin.qq.com/community/article/detail?content_id=16265336773389953164
	return &EchoServer{
		e,
	}
}

func (s *EchoServer) Run(port int) {
	go func() {
		if err := s.Start(fmt.Sprintf(":%d", port)); err != nil && !errors.Is(err, http.ErrServerClosed) {
			logger.Errorf("echo server error: %v", err)
		}
	}()

	// 信号监听已在 main.go 中统一处理
	// 等待信号通过单独的 goroutine 通知
	<-s.shutdownCh()
}

func (s *EchoServer) RunAsync(port int) chan struct{} {
	done := make(chan struct{})
	go func() {
		// 无论 Start 返回错误还是被正常关闭，都保证 close(done)，避免调用方死锁
		defer close(done)
		if err := s.Start(fmt.Sprintf(":%d", port)); err != nil && !errors.Is(err, http.ErrServerClosed) {
			logger.Errorf("echo server error: %v", err)
		}
	}()
	return done
}

func (s *EchoServer) ShutdownEcho() {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := s.Shutdown(ctx); err != nil {
		logger.Infof("echo shutdown error: %v", err)
	}
}

func (s *EchoServer) shutdownCh() chan struct{} {
	ch := make(chan struct{})
	go func() {
		quit := make(chan os.Signal, 1)
		signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
		<-quit
		logger.Infof("Shutting down...")
		close(ch)
	}()
	return ch
}
