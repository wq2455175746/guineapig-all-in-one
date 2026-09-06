<template>
  <AppHeader>
    <template #right>
      <div v-if="user" style="display: inline-flex; align-items: center;">
        <Button
          icon="pi pi-user"
          class="user-avatar-btn"
          rounded
          @click="toggleUserMenu"
          v-tooltip.left="user.name || 'admin'"
        />
        <Menu ref="userMenuRef" :model="userMenuItems" :popup="true" />
      </div>
    </template>
  </AppHeader>
  <div class="layout-container">
    <aside class="sidebar">
      <Menu :model="menuItems" class="sidebar-menu w-full">
        <template #start>
          <span class="sidebar-header-text">导航菜单</span>
        </template>
        <template #submenulabel="{ item }">
          <span class="sidebar-group-label">{{ item.label }}</span>
        </template>
        <template #item="{ item, props }">
          <a
            v-ripple
            class="flex items-center sidebar-item-link"
            :class="{ 'sidebar-item-active': isActive(item) }"
            v-bind="props.action"
            @click="item.command"
          >
            <span :class="item.icon" class="sidebar-item-icon" />
            <span class="sidebar-item-label">{{ item.label }}</span>
          </a>
        </template>
        <template #end>
          <!-- <div class="sidebar-footer">
            <span class="text-sm text-muted-color">guinea-pig v0.0.0</span>
          </div> -->
        </template>
      </Menu>
    </aside>
    <main class="main-content">
      <router-view />
    </main>
  </div>
  <Toast />
</template>

<script setup>
import AppHeader from './AppHeader.vue'
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import Menu from 'primevue/menu'
import Button from 'primevue/button'
import Toast from 'primevue/toast'

const router = useRouter()
const route = useRoute()
const user = ref({ name: 'admin' })

function isActive(item) {
  return route.path === item.route
}

const menuItems = ref([
  {
    label: '主菜单',
    items: [
      { label: 'Dashboard', icon: 'pi pi-chart-bar', command: () => router.push('/dashboard'), route: '/dashboard' },
      { label: '对话管理', icon: 'pi pi-comments', command: () => router.push('/conversationMgr'), route: '/conversationMgr' },
      { label: '用户管理', icon: 'pi pi-users', command: () => router.push('/userList'), route: '/userList' },
    ]
  },
  {
    label: '资源管理',
    items: [
      { label: '用户文件', icon: 'pi pi-file', command: () => router.push('/userFileMgr'), route: '/userFileMgr' },
      { label: '模型', icon: 'pi pi-cog', command: () => router.push('/modelMgr'), route: '/modelMgr' },
      { label: 'Skill', icon: 'pi pi-bolt', command: () => router.push('/skillMgr'), route: '/skillMgr' },
      { label: 'MCP', icon: 'pi pi-plug', command: () => router.push('/mcpMgr'), route: '/mcpMgr' },
      { label: '用户记忆', icon: 'pi pi-database', command: () => router.push('/userMemoryMgr'), route: '/userMemoryMgr' },
      { label: '信息渠道', icon: 'pi pi-share-alt', command: () => router.push('/infoChannelMgr'), route: '/infoChannelMgr' },
    ]
  },
  {
    label: '系统管理',
    items: [
      { label: '定时任务', icon: 'pi pi-clock', command: () => router.push('/scheduledTaskMgr'), route: '/scheduledTaskMgr' },
      { label: '权限管理', icon: 'pi pi-lock', command: () => router.push('/permissionMgr'), route: '/permissionMgr' },
      { label: '角色管理', icon: 'pi pi-users', command: () => router.push('/roleMgr'), route: '/roleMgr' },
    ]
  }
])

const userMenuRef = ref()
const userMenuItems = ref([
  { label: '你好, admin', disabled: true },
  { separator: true },
  {
    label: '个人设置',
    icon: 'pi pi-cog',
    command: () => router.push('/settings')
  },
  {
    label: '退出登录',
    icon: 'pi pi-sign-out',
    command: () => handleLogout()
  }
])

function toggleUserMenu(event) {
  userMenuRef.value.toggle(event)
}

function handleLogout() {
  localStorage.removeItem('admin_token')
  router.push('/register')
}
</script>

<style>
.layout-container {
  display: flex;
  flex: 1;
  min-height: 0;
  width: 100vw;
}
.sidebar {
  width: 260px;
  min-width: 260px;
  border-right: 1px solid #e4e7ed;
  height: calc(100vh - 56px);
  overflow-y: auto;
  box-sizing: border-box;
  background: #fff;
}
.sidebar-menu {
  width: 100%;
  border: none !important;
  padding: 0;
}

/* Sidebar header in #start slot */
.sidebar-header-text {
  display: block;
  padding: 16px 20px 8px;
  font-size: 14px;
  font-weight: 600;
  color: #1a1a2e;
  letter-spacing: 0.5px;
}

/* Submenu group labels */
.sidebar-group-label {
  display: block;
  padding: 12px 20px 4px;
  font-size: 11px;
  font-weight: 700;
  color: #409eff;
  text-transform: uppercase;
  letter-spacing: 1px;
}

/* Menu item link */
.sidebar-item-link {
  padding: 10px 20px !important;
  margin: 2px 8px;
  border-radius: 6px;
  cursor: pointer;
  text-decoration: none;
  transition: background-color 0.15s, color 0.15s;
  color: #4a4a5a;
}
.sidebar-item-link:hover {
  background-color: #f0f6ff !important;
  color: #409eff !important;
}
.sidebar-item-active {
  background-color: #e8f2ff !important;
  color: #409eff !important;
  font-weight: 600;
}

/* Menu item icon */
.sidebar-item-icon {
  margin-right: 10px;
  font-size: 1.1rem;
  width: 20px;
  text-align: center;
}

/* Menu item label */
.sidebar-item-label {
  font-size: 14px;
}

/* Sidebar footer */
.sidebar-footer {
  padding: 12px 20px;
  border-top: 1px solid #eee;
  margin-top: 8px;
  text-align: center;
}

.main-content {
  flex: 1;
  background: #f5f7fa;
  padding: 20px;
  overflow-y: auto;
  min-width: 0;
}
.user-avatar-btn {
  background: linear-gradient(135deg, rgb(168, 191, 213) 60%, rgb(103, 170, 242) 100%) !important;
  border: 2px solid #fff !important;
  box-shadow: 0 2px 8px rgba(14, 119, 224, 0.15) !important;
  width: 32px;
  height: 32px;
  color: #fff !important;
  transition: box-shadow 0.2s;
}
.user-avatar-btn:hover {
  box-shadow: 0 4px 16px rgba(64,158,255,0.25) !important;
  background: linear-gradient(135deg, #66b1ff 60%, #409eff 100%) !important;
}
</style>
