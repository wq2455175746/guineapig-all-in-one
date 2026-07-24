import axios from 'axios'

// 创建 axios 实例
const instance = axios.create({
  withCredentials: true
})

// 请求拦截器：自动注入管理后台 Token
instance.interceptors.request.use(
  config => {
    // 从 localStorage 获取 admin token，优先使用
    const adminToken = localStorage.getItem('admin_token') || import.meta.env.VITE_ADMIN_TOKEN || 'guineapig-admin-dev-token'
    if (adminToken) {
      config.headers['X-Admin-Token'] = adminToken
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

// 响应拦截器
// instance.interceptors.response.use(
//   response => response,
//   error => {
//     if (error.response?.status === 401) {
//       // 跳转到auth/login并带redirectUrl
//       const loginUrl = `${API_ENDPOINTS.AUTH.LOGIN}?redirectUrl=${encodeURIComponent(window.location.href)}`
//       window.location.href = loginUrl
//       return Promise.reject('未登录')
//     }
//     return Promise.reject(error)
//   }
// )

export default instance 