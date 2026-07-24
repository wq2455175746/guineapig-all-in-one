// 全局 fetch 拦截器
// 1. 为所有 API 请求注入 device_id, user_id, request_id 请求头
// 2. 捕获 401 响应并自动跳转到登录页
;(() => {
  const { fetch: originalFetch } = window

  // 生成 request_id（UUID v4），降级到 Math.random
  function generateRequestId(): string {
    try {
      return crypto.randomUUID()
    } catch {
      // 降级方案
      return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
        const r = (Math.random() * 16) | 0
        return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16)
      })
    }
  }

  window.fetch = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    // 判断是否为登录请求，登录请求跳过 401 拦截
    const urlStr = typeof input === 'string' ? input : (input instanceof URL ? input.href : input.url)
    const isLoginRequest = urlStr.includes('/client/login')

    // 只在 /api/v1/ 路径的请求注入 header
    const isApiRequest = urlStr.includes('/api/v1/')

    const headers = new Headers(init?.headers)

    // 注入三个请求头
    if (isApiRequest) {
      headers.set('X-Device-Id', localStorage.getItem('device_id') || 'unknown')
      headers.set('X-User-Id', localStorage.getItem('user_id') || '')
      headers.set('X-Request-Id', generateRequestId())
    }

    return originalFetch(input, { ...init, headers }).then(response => {
      if (response.status === 401 && !isLoginRequest) {
        // 清除认证数据
        localStorage.removeItem('user_email')
        localStorage.removeItem('user_id')
        localStorage.removeItem('device_id')
        localStorage.removeItem('api_key')

        // 跳转到登录页（hash 路由模式）
        window.location.hash = '#/login'
      }
      return response
    })
  }
})()
