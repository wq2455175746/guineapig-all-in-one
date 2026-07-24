import { createRouter, createWebHashHistory } from 'vue-router'
import LoginPage from '../views/LoginPage.vue'
import ChatPage from '../views/ChatPage.vue'

const routes = [
  {
    path: '/',
    redirect: '/chat'
  },
  {
    path: '/login',
    name: 'Login',
    component: LoginPage
  },
  {
    path: '/chat',
    name: 'Chat',
    component: ChatPage,
    meta: { requiresAuth: true }
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

// 路由守卫：检查本地是否有 API 密钥，没有则跳转到登录页
router.beforeEach((to, _from, next) => {
  const userEmail = localStorage.getItem('user_email')

  if (to.meta.requiresAuth) {
    if (userEmail) {
      next()
    } else {
      next({ name: 'Login' })
    }
  } else if (to.name === 'Login' && userEmail) {
    // 已登录用户访问登录页，重定向到聊天页
    next({ name: 'Chat' })
  } else {
    next()
  }
})

export default router
