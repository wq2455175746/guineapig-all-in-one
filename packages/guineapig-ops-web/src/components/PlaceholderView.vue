<template>
  <div class="placeholder-view">
    <div class="placeholder-content">
      <i class="pi pi-clock placeholder-icon"></i>
      <h2>{{ title || '功能开发中' }}</h2>
      <p>待实现</p>
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: {
    type: String,
    default: ''
  }
})
</script>

<style scoped>
.placeholder-view {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 400px;
}
.placeholder-content {
  text-align: center;
  color: #909399;
}
.placeholder-icon {
  font-size: 64px;
  margin-bottom: 16px;
}
.placeholder-content h2 {
  font-size: 20px;
  color: #606266;
  margin: 0 0 8px 0;
  font-weight: 500;
}
.placeholder-content p {
  font-size: 14px;
  margin: 0;
}
</style>
