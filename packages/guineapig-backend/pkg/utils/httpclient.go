package utils

import (
	"net"
	"net/http"
	"time"

	"guineapig/config"
)

// sharedHTTPTransport 全局共享的 HTTP transport（连接池复用）。
// 所有出站 HTTP 请求共用同一 transport，避免每个请求新建连接导致的
// TIME_WAIT 堆积与 TLS/握手开销；各调用方通过 NewHTTPClient 自设超时。
var sharedHTTPTransport = &http.Transport{
	Proxy: http.ProxyFromEnvironment,
	DialContext: (&net.Dialer{
		Timeout:   10 * time.Second,
		KeepAlive: 30 * time.Second,
	}).DialContext,
	ForceAttemptHTTP2:     true,
	MaxIdleConns:          100,
	MaxIdleConnsPerHost:   10,
	IdleConnTimeout:       90 * time.Second,
	TLSHandshakeTimeout:   10 * time.Second,
	ExpectContinueTimeout: 1 * time.Second,
}

// NewHTTPClient 创建复用共享连接池的 http.Client。
// timeout 为该调用方整次请求的超时（含响应体读取）；流式 SSE 调用请按需传大超时，
// 非流式调用建议使用 HTTPRequestTimeout 等常量。
func NewHTTPClient(timeout time.Duration) *http.Client {
	return &http.Client{
		Transport: sharedHTTPTransport,
		Timeout:   timeout,
	}
}

// AttachAiAgentAuth 为发往 guineapig-aiagent 的出站请求附加管理令牌头。
// aiagent 的鉴权中间件为 fail-closed：除白名单外的所有接口都要求 X-Admin-Token，
// 缺失即 401。这里从 config.Global.Admin.Token 读取（config.yaml admin.token ← ADMIN_TOKEN），
// 与 docker-compose 中 aiagent 的 ADMIN_TOKEN 保持同值，从而恢复 backend→aiagent 运行时链路。
func AttachAiAgentAuth(req *http.Request) {
	if token := config.Global.Admin.Token; token != "" {
		req.Header.Set("X-Admin-Token", token)
	}
}
