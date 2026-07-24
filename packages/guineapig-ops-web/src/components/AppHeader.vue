<template>
  <header class="app-header">
    <div class="header-left">
      <img src="/logo.svg" alt="logo" class="logo" />
      <span class="system-title">guinea-pig</span>
    </div>
    <div class="header-right">
      <Badge :value="notificationCount" :hidden="notificationCount === 0" class="notification-badge">
        <i class="pi pi-bell notification-icon" style="font-size: 1.2rem;"></i>
      </Badge>
      <slot name="right"></slot>
    </div>
  </header>
</template>

<script setup>
import { ref } from 'vue'
import Badge from 'primevue/badge'

const notificationCount = ref(0)
</script>

<style scoped>
.app-header {
  width: 100vw;
  min-width: 0;
  left: 0;
  top: 0;
  position: relative;
  height: 56px;
  background: #232533;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 32px;
  box-sizing: border-box;
  color: #fff;
  font-size: 18px;
  font-weight: 500;
}
.header-left {
  display: flex;
  align-items: center;
}
.logo {
  height: 32px;
  margin-right: 12px;
}
.system-title {
  font-size: 20px;
  font-weight: bold;
  letter-spacing: 1px;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 20px;
}
.notification-icon {
  color: #fff;
  cursor: pointer;
  transition: color 0.2s;
  display: flex;
  align-items: center;
}
.notification-icon:hover {
  color: #409eff;
}
.notification-badge {
  line-height: 1;
}
</style>
