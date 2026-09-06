<template>
  <div class="resource-body">
    <Card>
      <template #content>
        <div class="toolbar">
          <div class="toolbar-left">
            <div class="filter-item">
              <span class="filter-label">用户：</span>
              <Select v-model="filterUserId" :options="userOptions" optionValue="id" optionLabel="label"
                placeholder="全部用户" showClear filter style="width: 200px" @change="onFilterChange" />
            </div>
          </div>
          <div class="search-area">
            <Button icon="pi pi-refresh" severity="secondary" raised size="small" @click="fetchList" :loading="loading" />
          </div>
        </div>

        <DataTable :value="items" size="small" paginator :rows="pageSize" :rowsPerPageOptions="[10, 20, 50]"
          :totalRecords="total" :lazy="true" @page="onPage" currentPageReportTemplate="共 {totalRecords} 条"
          tableStyle="min-width: 60rem" :loading="loading">
          <Column header="序号">
            <template #body="{ index }">
              {{ index + 1 + (pageNum - 1) * pageSize }}
            </template>
          </Column>
          <Column field="id" header="绑定ID" headerStyle="min-width: 70px" />
          <Column header="用户">
            <template #body="{ data }">
              <span>{{ getUserLabel(data.user_id) }}</span>
            </template>
          </Column>
          <Column header="平台">
            <template #body="{ data }">
              <Tag :value="platformLabel(data.platform)" :severity="platformSeverity(data.platform)" />
            </template>
          </Column>
          <Column field="app_id" header="AppID" />
          <Column field="bot_name" header="Bot名称" />
          <Column header="连接状态">
            <template #body="{ data }">
              <Tag :value="statusLabel(data.bot_status)" :severity="statusSeverity(data.bot_status)" />
            </template>
          </Column>
          <Column field="created_at" header="创建时间">
            <template #body="{ data }">
              {{ formatTime(data.created_at) }}
            </template>
          </Column>
          <Column headerStyle="text-align: right">
            <template #header>
              <span style="display: flex; justify-content: flex-end; width: 100%;">操作</span>
            </template>
            <template #body="{ data }">
              <div class="action-buttons">
                <Button icon="pi pi-eye" rounded severity="secondary" v-tooltip.top="'查看详情'"
                  @click="viewDetail(data)" />
              </div>
            </template>
          </Column>
        </DataTable>

        <!-- 详情对话框 -->
        <Dialog v-model:visible="detailVisible" header="Bot 绑定详情" :modal="true" :style="{ width: '600px' }"
          :draggable="false">
          <div v-if="detailItem" class="detail-content">
            <div class="detail-row">
              <span class="detail-label">绑定ID</span>
              <span class="detail-value">{{ detailItem.id }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">用户ID</span>
              <span class="detail-value">{{ detailItem.user_id }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">平台</span>
              <span class="detail-value">{{ platformLabel(detailItem.platform) }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">AppID</span>
              <span class="detail-value">{{ detailItem.app_id }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">AppSecret</span>
              <span class="detail-value">***</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Bot名称</span>
              <span class="detail-value">{{ detailItem.bot_name || '-' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">租户Key</span>
              <span class="detail-value">{{ detailItem.tenant_key || '-' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">连接状态</span>
              <span class="detail-value">
                <Tag :value="statusLabel(detailItem.bot_status)" :severity="statusSeverity(detailItem.bot_status)" />
              </span>
            </div>
            <div class="detail-row">
              <span class="detail-label">备注</span>
              <span class="detail-value">{{ detailItem.description || '-' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">创建时间</span>
              <span class="detail-value">{{ formatTime(detailItem.created_at) }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">更新时间</span>
              <span class="detail-value">{{ formatTime(detailItem.updated_at) }}</span>
            </div>
          </div>
        </Dialog>
      </template>
    </Card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import Card from 'primevue/card'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import Dialog from 'primevue/dialog'
import Select from 'primevue/select'
import { API_ENDPOINTS } from '@/config/api'
import { usePagedList } from '@/composables/usePagedList'
import { useUserOptions } from '@/composables/useUserOptions'
import { formatTime } from '@/utils/format'

// ========== User Filter ==========
const filterUserId = ref(null)
const { userOptions, userMap, loadUsers } = useUserOptions()

function getUserLabel(userId) {
  return userMap.value[userId] || `用户#${userId}`
}

// ========== Bot Helpers ==========
function platformLabel(platform) {
  const map = { feishu: '飞书', wechat: '企业微信', dingtalk: '钉钉' }
  return map[platform] || platform
}

function platformSeverity(platform) {
  const map = { feishu: 'info', wechat: 'success', dingtalk: 'warn' }
  return map[platform] || null
}

function statusLabel(status) {
  switch (status) {
    case 1: return '已连接'
    case 2: return '错误'
    default: return '未连接'
  }
}

function statusSeverity(status) {
  switch (status) {
    case 1: return 'success'
    case 2: return 'warn'
    default: return 'danger'
  }
}

// ========== List ==========
const { items, total, loading, pageSize, pageNum, fetchList, onPage, onFilterChange } =
  usePagedList(API_ENDPOINTS.BOT.LIST, { filters: [{ key: 'user_id', value: filterUserId }] })

// ========== Detail ==========
const detailVisible = ref(false)
const detailItem = ref(null)

function viewDetail(data) {
  detailItem.value = data
  detailVisible.value = true
}

onMounted(() => {
  loadUsers()
  fetchList()
})
</script>

<style scoped>
.resource-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 0;
  overflow: auto;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  gap: 12px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.filter-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.filter-label {
  white-space: nowrap;
  font-size: 14px;
  color: #606266;
}

.search-area {
  display: flex;
  align-items: center;
  gap: 8px;
}

.action-buttons {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
}

.detail-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.detail-row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.detail-label {
  font-size: 13px;
  color: #999;
  min-width: 80px;
  flex-shrink: 0;
  padding-top: 2px;
}

.detail-value {
  font-size: 13px;
  color: #333;
  word-break: break-all;
}
</style>
