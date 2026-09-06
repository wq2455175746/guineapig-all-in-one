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
              <InputText v-model="searchQuery" placeholder="搜索Skill名称..." @keydown.enter="handleSearch" />
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
          <Column field="id" header="Skill ID" headerStyle="min-width: 70px" />
          <Column field="name" header="名称" />
          <Column field="description" header="描述">
            <template #body="{ data }">
              <span v-tooltip.top="data.description"
                style="max-width: 200px; display: inline-block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{{ data.description || '-' }}</span>
            </template>
          </Column>
          <Column field="skill_version" header="版本" />
          <Column header="状态">
            <template #body="{ data }">
              <Tag :value="data.status === 1 ? '启用' : '禁用'" :severity="data.status === 1 ? 'success' : 'danger'" />
            </template>
          </Column>
          <Column header="用户">
            <template #body="{ data }">
              <span>{{ getUserLabel(data.user_id) }}</span>
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
        <Dialog v-model:visible="detailVisible" header="Skill 详情" :modal="true" :style="{ width: '700px' }"
          :draggable="false" maximizable>
          <div v-if="detailItem" class="detail-content">
            <div class="detail-row">
              <span class="detail-label">ID</span>
              <span class="detail-value">{{ detailItem.id }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">名称</span>
              <span class="detail-value">{{ detailItem.name }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">描述</span>
              <span class="detail-value">{{ detailItem.description || '-' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">版本</span>
              <span class="detail-value">{{ detailItem.skill_version || '1.0.0' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">Zip URL</span>
              <span class="detail-value detail-url">{{ detailItem.zip_url || '-' }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">用户ID</span>
              <span class="detail-value">{{ detailItem.user_id }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">状态</span>
              <span class="detail-value">
                <Tag :value="detailItem.status === 1 ? '启用' : '禁用'"
                  :severity="detailItem.status === 1 ? 'success' : 'danger'" />
              </span>
            </div>
            <Divider />
            <div class="detail-section">
              <h4 class="section-title">文件统计 (file_stat)</h4>
              <pre class="json-block">{{ formatJson(detailItem.file_stat) }}</pre>
            </div>
            <div class="detail-section">
              <h4 class="section-title">元数据 (metadata)</h4>
              <pre class="json-block">{{ formatJson(detailItem.metadata) }}</pre>
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
import Divider from 'primevue/divider'
import Select from 'primevue/select'
import { API_ENDPOINTS } from '@/config/api'
import { usePagedList } from '@/composables/usePagedList'
import { useUserOptions } from '@/composables/useUserOptions'
import { formatTime } from '@/utils/format'

const filterUserId = ref(null)
const { userOptions, userMap, loadUsers } = useUserOptions()

function getUserLabel(userId) {
  return userMap.value[userId] || `用户#${userId}`
}

function formatJson(str) {
  if (!str) return '(空)'
  try {
    return JSON.stringify(JSON.parse(str), null, 2)
  } catch {
    return str
  }
}

// ========== List ==========
const { items, total, loading, pageSize, pageNum, searchQuery, fetchList, handleSearch, onPage, onFilterChange } =
  usePagedList(API_ENDPOINTS.SKILL.LIST, { filters: [{ key: 'user_id', value: filterUserId }] })

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
  gap: 8px;
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

.detail-section {
  margin-top: 8px;
}

.section-title {
  font-size: 14px;
  color: #333;
  margin: 0 0 8px 0;
}

.json-block {
  background: #f8f9fa;
  border: 1px solid #eee;
  border-radius: 8px;
  padding: 12px;
  font-size: 12px;
  line-height: 1.5;
  color: #555;
  max-height: 300px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
