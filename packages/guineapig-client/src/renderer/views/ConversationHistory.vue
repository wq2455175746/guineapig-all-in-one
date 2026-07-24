<template>
  <aside class="history-panel">
    <div class="history-header">
      <IconField>
        <InputIcon class="pi pi-search" />
        <InputText v-model="searchQuery" placeholder="搜索对话..." />
      </IconField>
    </div>

    <VirtualScroller v-if="displayItems.length > 0" :items="displayItems" :itemSize="64" :delay="10" lazy
      class="history-list">
      <template #item="{ item, options }">
        <div class="history-item" :class="{ 'history-item-active': selectedId === item.id }"
          :style="{ height: options.itemSize + 'px' }" @click="$emit('select', item)">
          <div class="history-item-icon">
            <i class="pi pi-comment"></i>
          </div>
          <div class="history-item-body">
            <div class="history-item-summary">{{ truncate(item.lastMessagePreview || item.title, 14) }}</div>
            <div class="history-item-time">{{ formatTimeStr(item.updatedAt) }}</div>
          </div>
        </div>
      </template>
    </VirtualScroller>

    <div v-else class="history-empty">
      <i class="pi pi-inbox" style="font-size: 32px; color: #d0d5dd; margin-bottom: 8px"></i>
      <p class="placeholder-text">{{ searchQuery ? '没有匹配的对话' : '暂无对话记录' }}</p>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import InputText from 'primevue/inputtext'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import VirtualScroller from 'primevue/virtualscroller'

interface ChatHistoryItem {
  id: number
  title: string
  modelId: number
  messageCount: number
  status: string
  lastMessagePreview: string
  startAt: string
  endAt: string | null
  createdAt: string
  updatedAt: string
}

const props = defineProps<{
  conversations: ChatHistoryItem[]
  selectedId: number | null
  hasMore: boolean
  loading: boolean
}>()

const emit = defineEmits<{
  select: [item: ChatHistoryItem]
  'new-session': []
  'load-more': []
}>()

const searchQuery = ref('')

const displayItems = computed(() => {
  if (!searchQuery.value.trim()) return props.conversations
  const q = searchQuery.value.toLowerCase()
  return props.conversations.filter(
    item =>
      item.title.toLowerCase().includes(q) ||
      item.lastMessagePreview.toLowerCase().includes(q)
  )
})

function formatTimeStr(isoStr: string): string {
  if (!isoStr) return ''
  const date = new Date(isoStr)
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  const h = String(date.getHours()).padStart(2, '0')
  const min = String(date.getMinutes()).padStart(2, '0')
  const s = String(date.getSeconds()).padStart(2, '0')
  return `${y}-${m}-${d} ${h}:${min}:${s}`
}

function truncate(text: string, max: number): string {
  return text.length > max ? text.slice(0, max) + '...' : text
}

// Infinite scroll with IntersectionObserver
let scrollObserver: IntersectionObserver | null = null

function setupHistoryScroll() {
  const historyScrollEl = document.querySelector('.history-list')
  if (!historyScrollEl) return

  const sentinel = document.createElement('div')
  sentinel.className = 'scroll-sentinel'
  sentinel.style.height = '1px'
  historyScrollEl.parentElement?.appendChild(sentinel)

  scrollObserver = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && props.hasMore && !props.loading) {
      emit('load-more')
    }
  }, { root: historyScrollEl.parentElement, threshold: 0.1 })
  scrollObserver.observe(sentinel)
}

onMounted(() => {
  setTimeout(setupHistoryScroll, 500)
})

onUnmounted(() => {
  if (scrollObserver) {
    scrollObserver.disconnect()
  }
})
</script>

<style scoped>
.history-panel {
  width: 320px;
  min-width: 320px;
  background: #fff;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.history-header {
  padding: 16px 16px 12px;
  flex-shrink: 0;
}

.history-header :deep(.p-inputtext) {
  font-size: 13px;
  padding: 8px 10px;
  background: #f5f5f5;
  border: 1px solid transparent;
  border-radius: 8px;
  width: 100%;
  transition: all 0.15s ease;
}

.history-header :deep(.p-inputtext:hover) {
  background: #eee;
}

.history-header :deep(.p-inputtext:focus) {
  background: #fff;
  border-color: #333;
  box-shadow: none;
}

.history-header :deep(.p-inputicon) {
  font-size: 13px;
  color: #999;
}

.history-header :deep(.p-icon-field) {
  width: 100%;
}

.history-list {
  flex: 1;
  padding: 0 8px 8px;
}

.history-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  cursor: pointer;
  border-radius: 8px;
  transition: background 0.15s ease;
  margin: 2px 0;
}

.history-item:hover {
  background: #ededf1;
}

.history-item-active {
  background: #ededf1 !important;
}

.history-item-icon {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #666;
  font-size: 14px;
  margin-top: 1px;
}

.history-item-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.history-item-summary {
  font-size: 13px;
  color: #333;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-all;
}

.history-item-time {
  font-size: 11px;
  color: #b0b0b0;
}

.history-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 16px;
}

.history-empty .placeholder-text {
  font-size: 14px;
  color: #b0b0b0;
}
</style>
