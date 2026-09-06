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
            <IconField>
              <InputIcon class="pi pi-search" />
              <InputText v-model="searchQuery" placeholder="搜索模型名称..." @keydown.enter="handleSearch" />
            </IconField>
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
          <Column field="id" header="模型ID" headerStyle="min-width: 70px" />
          <Column field="model_name" header="模型名称" />
          <Column field="model_code" header="模型代码" />
          <Column field="provider_code" header="提供商">
            <template #body="{ data }">
              <Tag :value="data.provider_code || '-'" :severity="providerSeverity(data.provider_code)" />
            </template>
          </Column>
          <Column field="model_type" header="模型类型" />
          <Column field="api_url" header="API地址">
            <template #body="{ data }">
              <span v-tooltip.top="data.api_url"
                style="max-width: 200px; display: inline-block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{{ data.api_url }}</span>
            </template>
          </Column>
          <Column header="状态">
            <template #body="{ data }">
              <Tag :value="data.status === 1 ? '启用' : '禁用'" :severity="data.status === 1 ? 'success' : 'danger'" />
            </template>
          </Column>
          <Column header="默认">
            <template #body="{ data }">
              <Tag :value="data.established === 1 ? '是' : '否'" :severity="data.established === 1 ? 'info' : 'secondary'" />
            </template>
          </Column>
          <Column header="用户">
            <template #body="{ data }">
              <span>{{ getUserLabel(data.user_id) }}</span>
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
        <Dialog v-model:visible="detailVisible" header="模型详情" :modal="true" :style="{ width: '600px' }"
          :draggable="false">
          <div v-if="detailItem" class="detail-content">
            <div class="detail-row">
              <span class="detail-label">模型ID</span>
              <span class="detail-value">{{ detailItem.id }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">模型名称</span>
              <span class="detail-value">{{ detailItem.model_name }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">模型代码</span>
              <span class="detail-value">{{ detailItem.model_code || '-' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">提供商</span>
              <span class="detail-value">{{ detailItem.provider_code || '-' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">模型类型</span>
              <span class="detail-value">{{ detailItem.model_type || '-' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">API地址</span>
              <span class="detail-value detail-url">{{ detailItem.api_url || '-' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">API Key</span>
              <span class="detail-value">{{ maskApiKey(detailItem.api_key) }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">状态</span>
              <span class="detail-value">
                <Tag :value="detailItem.status === 1 ? '启用' : '禁用'" :severity="detailItem.status === 1 ? 'success' : 'danger'" />
              </span>
            </div>
            <div class="detail-row">
              <span class="detail-label">默认</span>
              <span class="detail-value">{{ detailItem.established === 1 ? '是' : '否' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">用户ID</span>
              <span class="detail-value">{{ detailItem.user_id }}</span>
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
import InputText from 'primevue/inputtext'
import Button from 'primevue/button'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import Tag from 'primevue/tag'
import Dialog from 'primevue/dialog'
import Select from 'primevue/select'
import { API_ENDPOINTS } from '@/config/api'
import { usePagedList } from '@/composables/usePagedList'
import { useUserOptions } from '@/composables/useUserOptions'

const filterUserId = ref(null)
const { userOptions, userMap, loadUsers } = useUserOptions()

function getUserLabel(userId) {
  return userMap.value[userId] || `用户#${userId}`
}

function providerSeverity(code) {
  const map = { deepseek: 'info', openai: 'success', azure: 'warn', ollama: 'contrast' }
  return map[code] || null
}

function maskApiKey(key) {
  if (!key) return '-'
  if (key.length <= 8) return '***'
  return key.substring(0, 4) + '****' + key.substring(key.length - 4)
}

// ========== List ==========
const { items, total, loading, pageSize, pageNum, searchQuery, fetchList, handleSearch, onPage, onFilterChange } =
  usePagedList(API_ENDPOINTS.AIMODEL.LIST, { filters: [{ key: 'user_id', value: filterUserId }] })

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

.search-area :deep(.p-inputtext) {
  font-size: 14px;
  padding: 10px 12px 10px 36px;
  width: 260px;
  border-radius: 8px;
  border: 1px solid #e5e5e5;
  transition: all 0.15s ease;
  background: #f8f9fa;
}

.search-area :deep(.p-inputtext:hover) {
  border-color: #ccc;
  background: #fff;
}

.search-area :deep(.p-inputtext:focus) {
  border-color: #333;
  box-shadow: none;
  background: #fff;
}

.search-area :deep(.p-inputicon) {
  font-size: 14px;
  color: #999;
  left: 12px;
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

.detail-url {
  color: #409eff;
}
</style>
