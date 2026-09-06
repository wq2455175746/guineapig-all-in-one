import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import ConversationMgr from '../views/ConversationMgr.vue'
import UserList from '../views/UserList.vue'
import UserFileMgr from '../views/UserFileMgr.vue'
import ModelMgr from '../views/ModelMgr.vue'
import SkillMgr from '../views/SkillMgr.vue'
import McpMgr from '../views/McpMgr.vue'
import UserMemoryMgr from '../views/UserMemoryMgr.vue'
import InfoChannelMgr from '../views/InfoChannelMgr.vue'
import ScheduledTaskMgr from '../views/ScheduledTaskMgr.vue'
import PermissionMgr from '../views/PermissionMgr.vue'
import RoleMgr from '../views/RoleMgr.vue'
import RegisterPage from '../views/RegisterPage.vue'
import Layout from '../components/Layout.vue'
import PlaceholderView from '../components/PlaceholderView.vue'

const routes = [
  {
    path: '/register',
    name: 'register',
    component: RegisterPage,
    meta: { title: '用户注册' }
  },
  {
    path: '/',
    component: Layout,
    children: [
      { path: '', redirect: '/dashboard' },
      { path: 'dashboard', component: Dashboard, meta: { title: 'Dashboard' } },
      { path: 'conversationMgr', component: ConversationMgr, meta: { title: '对话管理' } },
      { path: 'userList', component: UserList, meta: { title: '用户管理' } },
      { path: 'userFileMgr', component: UserFileMgr, meta: { title: '用户文件' } },
      { path: 'modelMgr', component: ModelMgr, meta: { title: '模型管理' } },
      { path: 'skillMgr', component: SkillMgr, meta: { title: 'Skill 管理' } },
      { path: 'mcpMgr', component: McpMgr, meta: { title: 'MCP 管理' } },
      { path: 'userMemoryMgr', component: UserMemoryMgr, meta: { title: '用户记忆' } },
      { path: 'infoChannelMgr', component: InfoChannelMgr, meta: { title: '信息渠道' } },
      { path: 'scheduledTaskMgr', component: ScheduledTaskMgr, meta: { title: '定时任务' } },
      { path: 'permissionMgr', component: PermissionMgr, meta: { title: '权限管理' } },
      { path: 'roleMgr', component: RoleMgr, meta: { title: '角色管理' } },
      { path: ':pathMatch(.*)*', component: PlaceholderView, meta: { title: '页面不存在' } }
    ]
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach(to => {
  const token = localStorage.getItem('admin_token') || import.meta.env.VITE_ADMIN_TOKEN
  if (!token && to.path !== '/register') {
    return '/register'
  }
  return true
})

router.afterEach(to => {
  document.title = to.meta?.title || 'guinea-pig'
})

export default router