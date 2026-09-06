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
              <span class="filter-label">记忆类型：</span>
              <Select v-model="filterMemType" :options="memTypeOptions" optionValue="value" optionLabel="label"
                placeholder="全部类型" showClear style="width: 140px" @change="onFilterChange" />
            </div>
          </div>
          <div class="search-area">
            <IconField>
              <InputIcon class="pi pi-search" />
              <InputText v-model="searchQuery" placeholder="搜索记忆名称..." @keydown.enter="handleSearch" />
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
          <Column field="id" header="记忆ID" headerStyle="min-width: 70px" />
          <Column field="name" header="记忆名">
            <template #body="{ data }">
              <span v-tooltip.top="data.name"
                style="max-width: 150px; display: inline-block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{{ data.name }}</span>
            </template>
          </Column>
          <Column header="记忆类型">
            <template #body="{ data }">
              <Tag :value="memTypeLabel(data.mem_type)" :severity="memTypeSeverity(data.mem_type)" />
            </template>
          </Column>
          <Column header="用户">
            <template #body="{ data }">
              <span>{{ getUserLabel(data.user_id) }}</span>
            </template>
          </Column>
          <Column header="时间范围">
            <template #body="{ data }">
              <div style="font-size: 12px;">
                <div>{{ formatTime(data.time_range_start_at) }}</div>
                <div v-if="data.time_range_end_at" style="color: #999;">~ {{ formatTime(data.time_range_end_at) }}</div>
              </div>
            </template>
          </Column>
          <Column field="source_msg_count" header="归纳消息数" />
          <Column header="活跃">
            <template #body="{ data }">
              <Tag :value="data.is_active === 1 ? '是' : '否'"
                :severity="data.is_active === 1 ? 'success' : 'secondary'" />
            </template>
          </Column>
          <Column header="置信度">
            <template #body="{ data }">
              <span>{{ data.confidence_score != null ? data.confidence_score : '-' }}</span>
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
          <template #empty>
            <div style="text-align: center; padding: 40px 0; color: #999; font-size: 14px;">暂无数据</div>
          </template>
        </DataTable>

        <!-- 详情对话框 -->
        <Dialog v-model:visible="detailVisible" :header="'记忆详情 - ' + (detailItem?.name || '')" :modal="true"
          :style="{ width: '700px' }" :draggable="false" maximizable>
          <div v-if="detailItem" class="detail-content">
            <div class="detail-fields">
              <div class="detail-row">
                <span class="detail-label">记忆名</span>
                <span class="detail-value">{{ detailItem.name }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">记忆类型</span>
                <span class="detail-value">{{ memTypeLabel(detailItem.mem_type) }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">用户ID</span>
                <span class="detail-value">{{ detailItem.user_id }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">开始时间</span>
                <span class="detail-value">{{ formatTime(detailItem.time_range_start_at) || '-' }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">结束时间</span>
                <span class="detail-value">{{ formatTime(detailItem.time_range_end_at) || '-' }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">消息数</span>
                <span class="detail-value">{{ detailItem.source_msg_count || 0 }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">版本</span>
                <span class="detail-value">{{ detailItem.version || 1 }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">活跃</span>
                <span class="detail-value">{{ detailItem.is_active === 1 ? '是' : '否' }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">置信度</span>
                <span class="detail-value">{{ detailItem.confidence_score != null ? detailItem.confidence_score : '-' }}</span>
              </div>
            </div>
            <Divider />
            <div class="mem-content">
              <h4 class="section-title">记忆内容</h4>
              <div class="mem-markdown">{{ detailItem.mem }}</div>
            </div>
          </div>
        </Dialog>
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
import Dialog from 'primevue/dialog'
import Divider from 'primevue/divider'
import Select from 'primevue/select'
import { API_ENDPOINTS } from '@/config/api'
import request from '@/config/axios'
import { useUserOptions } from '@/composables/useUserOptions'

const toast = useToast()

// Filters
const filterUserId = ref(null)
const filterMemType = ref(null)
const { userOptions, userMap, loadUsers } = useUserOptions()

const memTypeOptions = [
  { label: '日度摘要', value: 'daily_summary' },
  { label: '主题摘要', value: 'topic_summary' },
  { label: '关键事实', value: 'key_fact' },
  { label: '用户偏好', value: 'preference' },
]

function getUserLabel(userId) {
  return userMap.value[userId] || `用户#${userId}`
}

function memTypeLabel(type) {
  const map = { daily_summary: '日度摘要', topic_summary: '主题摘要', key_fact: '关键事实', preference: '用户偏好' }
  return map[type] || type
}

function memTypeSeverity(type) {
  const map = { daily_summary: 'info', topic_summary: 'warn', key_fact: 'success', preference: 'contrast' }
  return map[type] || 'secondary'
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
    if (searchQuery.value.trim()) params.keywords = searchQuery.value.trim()

    const res = await request.get(API_ENDPOINTS.MEMORY.LIST, { params })
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

// ========== Detail ==========
const detailVisible = ref(false)
const detailItem = ref(null)
const detailLoading = ref(false)

async function viewDetail(data) {
  detailLoading.value = true
  try {
    const res = await request.get(API_ENDPOINTS.MEMORY.GET, { params: { id: data.id } })
    if (res.data?.code === 0 && res.data?.result) {
      detailItem.value = res.data.result
    } else {
      detailItem.value = data
    }
  } catch {
    detailItem.value = data
  } finally {
    detailLoading.value = false
    detailVisible.value = true
  }
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
  padding: 0 4px;
}

.detail-fields {
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
}

.mem-content {
  margin-top: 4px;
}

.section-title {
  font-size: 14px;
  color: #333;
  margin: 0 0 8px 0;
}

.mem-markdown {
  font-size: 13px;
  color: #555;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  background: #f8f9fa;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid #eee;
  max-height: 400px;
  overflow-y: auto;
}
</style>
