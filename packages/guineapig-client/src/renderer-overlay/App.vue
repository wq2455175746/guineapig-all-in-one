<template>
  <div class="overlay-container">
    <!-- 顶部关闭栏 -->
    <div class="top-bar">
      <div class="top-bar-left">
        <i :class="iconClass" class="page-icon"></i>
        <span class="page-title">{{ pageTitle }}</span>
      </div>
      <button class="close-btn" @click="closeWindow">
        <i class="pi pi-times"></i>
      </button>
    </div>

    <!-- 内容区 -->
    <div class="content-area">
      <AvatarPage v-if="page === 'avatar'" />
      <AICapabilitiesPage v-else-if="page === 'ai-capabilities'" />
      <ResourcePage v-else-if="page === 'my-resources'" />
      <MemoryPage v-else-if="page === 'memory'" />
      <SystemSettingsPage v-else-if="page === 'system-settings'" />
      <div v-else class="placeholder">
        <p class="placeholder-text">暂时未实现</p>
      </div>

      <ConfirmPopup />
    </div>
    <Toast />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ConfirmPopup from 'primevue/confirmpopup'
import Toast from 'primevue/toast'
import AvatarPage from './views/AvatarPage.vue'
import AICapabilitiesPage from './views/AICapabilitiesPage.vue'
import ResourcePage from './views/ResourcePage.vue'
import MemoryPage from './views/MemoryPage.vue'
import SystemSettingsPage from './views/SystemSettingsPage.vue'

const page = new URLSearchParams(window.location.search).get('page') || 'unknown'

const pageConfig: Record<string, { title: string; icon: string }> = {
  'avatar': { title: '个人信息', icon: 'pi pi-user' },
  'chat-history': { title: '对话历史', icon: 'pi pi-history' },
  'ai-capabilities': { title: 'AI能力', icon: 'pi pi-bolt' },
  'my-resources': { title: '我的资源', icon: 'pi pi-folder' },
  'memory': { title: '记忆', icon: 'pi pi-database' },
  'notification-channels': { title: '通知渠道', icon: 'pi pi-bell' },
  'system-settings': { title: '系统设置', icon: 'pi pi-cog' }
}

const pageTitle = computed(() => pageConfig[page]?.title || page)
const iconClass = computed(() => pageConfig[page]?.icon || 'pi pi-question')

function closeWindow() {
  if (window.electronAPI?.closeCurrentWindow) {
    window.electronAPI.closeCurrentWindow()
  }
}
</script>

<style scoped>
.overlay-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: #fff;
  overflow: hidden;
}

/* ========== 顶部关闭栏 ========== */
.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 52px;
  padding: 0 16px;
  border-bottom: 1px solid #eee;
  flex-shrink: 0;
}

.top-bar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.page-icon {
  font-size: 1.1rem;
  color: #666;
}

.page-title {
  font-size: 15px;
  font-weight: 500;
  color: #333;
}

.close-btn {
  width: 36px;
  height: 36px;
  border: none;
  background: transparent;
  border-radius: 8px;
  cursor: pointer;
  color: #999;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.15s ease;
  font-size: 1.1rem;
}

.close-btn:hover {
  color: #333;
  background: #f5f5f5;
}

/* ========== 内容区 ========== */
.content-area {
  flex: 1;
  display: flex;
  background: #f5f5f5;
  overflow: hidden;
}

.placeholder {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.placeholder-text {
  font-size: 18px;
  color: #999;
  margin: 0;
}
</style>
