<template>
  <div class="bot-channel-layout">
    <!-- 平台绑定卡片列表 -->
    <div class="channel-list">
      <div v-for="item in bindings" :key="item.platform" class="channel-card"
        :class="{ 'channel-card--empty': !item.bound }">
        <!-- 平台图标和名称 -->
        <div class="channel-header">
          <i :class="platformIcon(item.platform)" class="channel-icon"></i>
          <span class="channel-name">{{ platformLabel(item.platform) }}</span>
        </div>

        <!-- 已绑定状态 -->
        <template v-if="item.bound">
          <div class="channel-info">
            <div class="info-row">
              <span class="info-label">AppID</span>
              <span class="info-value">{{ item.app_id }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">状态</span>
              <Tag :value="statusLabel(item.bot_status)" :severity="statusSeverity(item.bot_status)" />
            </div>
            <div class="info-row" v-if="item.bot_name">
              <span class="info-label">备注</span>
              <span class="info-value">{{ item.bot_name }}</span>
            </div>
          </div>
          <div class="channel-actions">
            <Button label="重新绑定" size="small" severity="secondary" outlined
              @click="handleRebind(item.platform)" />
            <Button label="解除绑定" size="small" severity="danger" outlined
              @click="confirmUnbind($event, item)" />
          </div>
        </template>

        <!-- 未绑定状态 -->
        <template v-else>
          <div class="channel-empty">
            <span class="empty-text">暂未绑定</span>
          </div>
          <div class="channel-actions">
            <Button label="绑定" size="small" severity="contrast" @click="handleBind(item.platform)" />
          </div>
        </template>
      </div>
    </div>

    <!-- 绑定/重新绑定对话框 -->
    <BotChannelDialog ref="dialogRef" @bound="fetchBindInfo" />

    <!-- 全局确认弹窗 -->
    <ConfirmPopup />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import ConfirmPopup from 'primevue/confirmpopup'
import BotChannelDialog from './BotChannelDialog.vue'

const confirm = useConfirm()
const toast = useToast()

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:6880'
const userId = localStorage.getItem('user_id') || ''

interface BindingInfo {
  id: number
  user_id: number
  platform: string
  app_id: string
  app_secret: string
  bot_status: number
  bot_name: string
  tenant_key: string
  description: string
  created_at: string
}

interface ChannelItem {
  platform: string
  bound: boolean
  app_id: string
  bot_status: number
  bot_name: string
}

const allPlatforms = ['feishu', 'wechat', 'dingtalk']

const bindings = ref<ChannelItem[]>([])
const dialogRef = ref<InstanceType<typeof BotChannelDialog> | null>(null)

const platformLabels: Record<string, string> = {
  feishu: '飞书',
  wechat: '企业微信',
  dingtalk: '钉钉',
}

const platformIcons: Record<string, string> = {
  feishu: 'pi pi-book',
  wechat: 'pi pi-comments',
  dingtalk: 'pi pi-flag',
}

function platformLabel(p: string): string {
  return platformLabels[p] || p
}

function platformIcon(p: string): string {
  return platformIcons[p] || 'pi pi-question'
}

function statusLabel(status: number): string {
  switch (status) {
    case 1: return '已连接'
    case 2: return '连接失败'
    default: return '未连接'
  }
}

function statusSeverity(status: number): string {
  switch (status) {
    case 1: return 'success'
    case 2: return 'danger'
    default: return 'secondary'
  }
}

async function fetchBindInfo() {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/bot/info?user_id=${userId}`)
    const data = await res.json()
    const items: BindingInfo[] = data.result || []

    bindings.value = allPlatforms.map(platform => {
      const found = items.find(i => i.platform === platform)
      return {
        platform,
        bound: !!found,
        app_id: found?.app_id || '',
        bot_status: found?.bot_status ?? 0,
        bot_name: found?.bot_name || '',
      }
    })
  } catch {
    // 初始化空状态
    bindings.value = allPlatforms.map(platform => ({
      platform,
      bound: false,
      app_id: '',
      bot_status: 0,
      bot_name: '',
    }))
  }
}

function handleBind(platform: string) {
  dialogRef.value?.open(platform)
}

function handleRebind(platform: string) {
  dialogRef.value?.open(platform)
}

function confirmUnbind(event: MouseEvent, item: ChannelItem) {
  confirm.require({
    target: event.currentTarget as HTMLElement,
    message: `确定要解除 ${platformLabel(item.platform)} 的绑定吗？`,
    icon: 'pi pi-exclamation-triangle',
    rejectProps: { label: '取消', severity: 'secondary', outlined: true },
    acceptProps: { label: '解除', severity: 'danger' },
    accept: async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/v1/bot/unbind`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ user_id: userId, platform: item.platform }),
        })
        const data = await res.json()
        if (data.code !== 0) {
          toast.add({ severity: 'error', summary: '解绑失败', detail: data.detail || data.message, life: 3000 })
          return
        }
        toast.add({ severity: 'success', summary: '解绑成功', detail: `${platformLabel(item.platform)} 已解绑`, life: 2000 })
        fetchBindInfo()
      } catch (err: any) {
        toast.add({ severity: 'error', summary: '网络错误', detail: err.message, life: 3000 })
      }
    },
  })
}

onMounted(() => {
  fetchBindInfo()
})
</script>

<style scoped>
.bot-channel-layout {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px 0;
  height: 100%;
  overflow: auto;
}

.channel-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 0 16px;
}

.channel-card {
  background: #fff;
  border: 1px solid #eee;
  border-radius: 10px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  transition: box-shadow 0.15s ease;
}

.channel-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.channel-card--empty {
  opacity: 0.7;
}

.channel-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.channel-icon {
  font-size: 1.4rem;
  color: #555;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f5f5;
  border-radius: 8px;
}

.channel-name {
  font-size: 15px;
  font-weight: 600;
  color: #333;
}

.channel-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 0;
  border-top: 1px solid #f5f5f5;
}

.info-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.info-label {
  font-size: 12px;
  color: #999;
  min-width: 50px;
  flex-shrink: 0;
}

.info-value {
  font-size: 12px;
  color: #555;
}

.channel-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8px 0;
}

.empty-text {
  font-size: 13px;
  color: #bbb;
}

.channel-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 4px;
  border-top: 1px solid #f5f5f5;
}
</style>
