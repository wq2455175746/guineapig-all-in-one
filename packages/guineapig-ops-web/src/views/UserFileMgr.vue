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
            <div class="filter-item">
              <span class="filter-label">文件类型：</span>
              <Select v-model="filterFileType" :options="fileTypeOptions" optionValue="value" optionLabel="label"
                placeholder="全部类型" showClear style="width: 140px" @change="onFilterChange" />
            </div>
          </div>
          <div class="search-area">
            <IconField>
              <InputIcon class="pi pi-search" />
              <InputText v-model="searchQuery" placeholder="搜索文件名..." @keydown.enter="handleSearch" />
            </IconField>
            <Button icon="pi pi-refresh" severity="secondary" raised size="small" @click="fetchList" :loading="loading" />
          </div>
        </div>

        <DataTable :value="items" size="small" paginator :rows="pageSize" :rowsPerPageOptions="[10, 20, 50]"
          :totalRecords="total" :lazy="true" @page="onPage" currentPageReportTemplate="共 {totalRecords} 条"
          tableStyle="min-width: 60rem" :loading="loading">
          <Column header="序号">
            <template #body="{ data }">
              {{ items.indexOf(data) + 1 + (pageNum - 1) * pageSize }}
            </template>
          </Column>
          <Column field="id" header="文件ID" headerStyle="min-width: 70px" />
          <Column field="name" header="文件名">
            <template #body="{ data }">
              <span v-tooltip.top="data.name"
                style="max-width: 200px; display: inline-block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{{ data.name }}</span>
            </template>
          </Column>
          <Column field="file_desc" header="描述">
            <template #body="{ data }">
              <span v-tooltip.top="data.file_desc">{{ data.file_desc || '-' }}</span>
            </template>
          </Column>
          <Column header="文件类型">
            <template #body="{ data }">
              <Tag :value="fileTypeLabel(data.file_type)" :severity="fileTypeSeverity(data.file_type)" />
            </template>
          </Column>
          <Column header="嵌入状态">
            <template #body="{ data }">
              <Tag :value="embedLabel(data.is_embedded)" :severity="embedSeverity(data.is_embedded)" />
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
        </DataTable>
      </template>
    </Card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useToast } from 'primevue/usetoast'
import Card from 'primevue/card'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import InputText from 'primevue/inputtext'
import Button from 'primevue/button'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import Tag from 'primevue/tag'
import Select from 'primevue/select'
import { API_ENDPOINTS } from '@/config/api'
import request from '@/config/axios'
import { useUserOptions } from '@/composables/useUserOptions'

const toast = useToast()

// ========== Filters ==========
const filterUserId = ref(null)
const filterFileType = ref(null)
const { userOptions, userMap, loadUsers } = useUserOptions()

const fileTypeOptions = [
  { label: 'TXT', value: 0 },
  { label: 'Markdown', value: 1 },
  { label: 'HTML', value: 2 },
  { label: 'PDF', value: 3 },
  { label: 'MP3', value: 4 },
  { label: '图片', value: 5 },
  { label: '其他', value: 99 },
]

function getUserLabel(userId) {
  return userMap.value[userId] || `用户#${userId}`
}

function fileTypeLabel(type) {
  const map = { 0: 'TXT', 1: 'Markdown', 2: 'HTML', 3: 'PDF', 4: 'MP3', 5: '图片', 99: '其他' }
  return map[type] || '其他'
}

function fileTypeSeverity(type) {
  const map = { 0: 'info', 1: 'success', 2: 'warn', 3: 'danger', 4: 'secondary', 5: 'contrast', 99: null }
  return map[type] || null
}

function embedLabel(val) {
  const map = { 0: '未嵌入', 1: '已嵌入', 2: '嵌入中', 9: '失败' }
  return map[val] || '未知'
}

function embedSeverity(val) {
  const map = { 0: 'secondary', 1: 'success', 2: 'warn', 9: 'danger' }
  return map[val] || null
}

// ========== List ==========
const items = ref([])
const total = ref(0)
const loading = ref(false)
const pageSize = ref(10)
const pageNum = ref(1)
const searchQuery = ref('')

async function fetchList() {
  loading.value = true
  try {
    const params = { pageSize: pageSize.value, pageNum: pageNum.value }
    if (filterUserId.value) params.user_id = filterUserId.value
    if (filterFileType.value !== null && filterFileType.value !== undefined) params.file_type = filterFileType.value
    if (searchQuery.value.trim()) params.keywords = searchQuery.value.trim()

    const res = await request.get(API_ENDPOINTS.FILE.LIST, { params })
    if (res.data?.code !== 0) {
      toast.add({ severity: 'error', summary: '加载失败', detail: res.data?.message, life: 3000 })
      return
    }
    items.value = res.data.result?.items || []
    total.value = res.data.result?.total || 0
  } catch (err) {
    toast.add({ severity: 'error', summary: '请求失败', detail: String(err), life: 3000 })
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pageNum.value = 1
  fetchList()
}

function onPage(event) {
  pageNum.value = event.page + 1
  pageSize.value = event.rows
  fetchList()
}

function onFilterChange() {
  pageNum.value = 1
  fetchList()
}

function formatTime(t) {
  if (!t) return '-'
  return t.substring(0, 16).replace('T', ' ')
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
</style>
