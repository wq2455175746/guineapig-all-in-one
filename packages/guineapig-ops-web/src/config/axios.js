import axios from 'axios'
import ToastEventBus from 'primevue/toasteventbus'

// 创建 axios 实例
const instance = axios.create({
  withCredentials: true
})

// 请求拦截器：自动注入管理后台 Token
instance.interceptors.request.use(
  config => {
    // 从 localStorage 获取 admin token，优先使用；否则从环境变量读取
    const adminToken = localStorage.getItem('admin_token') || import.meta.env.VITE_ADMIN_TOKEN
    if (adminToken) {
      config.headers['X-Admin-Token'] = adminToken
    } else {
      console.warn('[axios] 未配置 admin token，请在 .env 中设置 VITE_ADMIN_TOKEN')
    }
    return config
  },
  error => Promise.reject(error)
)

// 请求拦截器
// instance.interceptors.request.use(
//   config => {
//     // 自动为auth/login接口拼接redirectUrl参数
//     if (config.url === API_ENDPOINTS.AUTH.LOGIN) {
//       if (!config.params) config.params = {}
//       config.params.redirectUrl = window.location.href
//     }
//     return config
//   },
//   error => Promise.reject(error)
// )

// 响应拦截器：业务错误（code !== 0）统一 toast；HTTP 401 清理 token 并跳转登录页。
// 注意：不改变响应结构，视图仍然读取 res.data.code/result/message，避免大规模改动。
instance.interceptors.response.use(
  response => {
    const data = response.data
    if (data && typeof data === 'object' && data.code !== undefined && data.code !== 0) {
      ToastEventBus.emit('add', {
        severity: 'error',
        summary: '请求失败',
        detail: data.message || `错误码 ${data.code}`,
        life: 3000
      })
    }
    return response
  },
  error => {
    if (error.response?.status === 401) {
      localStorage.removeItem('admin_token')
      window.location.href = '/register'
    }
    return Promise.reject(error)
  }
)

export default instance 