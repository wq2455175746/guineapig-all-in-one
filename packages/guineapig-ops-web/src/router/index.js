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

export default [
  {
    path: '/register',
    name: 'register',
    component: RegisterPage
  },
  {
    path: '/',
    component: Layout,
    children: [
      { path: '', redirect: '/dashboard' },
      { path: 'dashboard', component: Dashboard },
      { path: 'conversationMgr', component: ConversationMgr },
      { path: 'userList', component: UserList },
      { path: 'userFileMgr', component: UserFileMgr },
      { path: 'modelMgr', component: ModelMgr },
      { path: 'skillMgr', component: SkillMgr },
      { path: 'mcpMgr', component: McpMgr },
      { path: 'userMemoryMgr', component: UserMemoryMgr },
      { path: 'infoChannelMgr', component: InfoChannelMgr },
      { path: 'scheduledTaskMgr', component: ScheduledTaskMgr },
      { path: 'permissionMgr', component: PermissionMgr },
      { path: 'roleMgr', component: RoleMgr },
    ]
  }
]
