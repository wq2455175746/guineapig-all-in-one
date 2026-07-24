<template>
  <div class="resource-body">
    <Card>
      <template #content>
        <div class="toolbar">
          <div class="toolbar-left">
            <Button icon="pi pi-book" label="归纳记忆" severity="secondary" raised size="small"
              @click="showDatePicker = true" :loading="summarizing" />
          </div>
          <div class="search-area">
            <IconField>
              <InputIcon class="pi pi-search" />
              <InputText v-model="searchQuery" placeholder="搜索记忆名称或类型..." @keydown.enter="handleSearch" />
            </IconField>
            <Button icon="pi pi-refresh" severity="secondary" raised size="small" @click="fetchList"
              :loading="loading" />
          </div>
        </div>

        <DataTable :value="items" size="small" paginator :rows="pageSize" :rowsPerPageOptions="[10, 20, 50]"
          :totalRecords="total" :lazy="true" @page="onPage" currentPageReportTemplate="共 {totalRecords} 条"
          tableStyle="min-width: 50rem" :loading="loading">
          <Column header="序号">
            <template #body="{ data }">
              {{ items.indexOf(data) + 1 + (pageNum - 1) * pageSize }}
            </template>
          </Column>
          <Column field="name" header="记忆名">
            <template #body="{ data }">
              <span v-tooltip.top="data.name"
                style="max-width: 150px; display: inline-block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{{
                data.name }}</span>
            </template>
          </Column>
          <Column field="mem_type" header="记忆类型">
            <template #body="{ data }">
              <Tag :value="memTypeLabel(data.mem_type)" :severity="memTypeSeverity(data.mem_type)" />
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
          <Column field="source_msg_count" header="归纳消息条数"></Column>
          <Column headerStyle="text-align: right">
            <template #header>
              <span style="display: flex; justify-content: flex-end; width: 100%;">操作</span>
            </template>
            <template #body="{ data }">
              <div class="action-buttons">
                <Button icon="pi pi-eye" rounded severity="secondary" v-tooltip.top="'查看'" @click="viewDetail(data)" />
                <Button icon="pi pi-trash" rounded severity="danger" v-tooltip.top="'删除'"
                  @click="confirmDelete($event, data)" />
              </div>
            </template>
          </Column>
          <template #empty>
            <div style="text-align: center; padding: 40px 0; color: #999; font-size: 14px;">暂无数据</div>
          </template>
        </DataTable>

        <!-- 查看详情对话框 -->
        <Dialog v-model:visible="detailDialogVisible" :header="'记忆详情 - ' + (detailItem?.name || '')" :modal="true"
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
                <span class="detail-label">开始时间</span>
                <span class="detail-value">{{ formatTime(detailItem.time_range_start_at) || '-' }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">结束时间</span>
                <span class="detail-value">{{ formatTime(detailItem.time_range_end_at) || '-' }}</span>
              </div>
            </div>
            <Divider />
            <div class="mem-content">
              <h4 class="mem-content-title">记忆内容</h4>
              <div class="mem-markdown">{{ detailItem.mem }}</div>
            </div>
          </div>
        </Dialog>
      </template>
    </Card>

    <!-- 归纳记忆日期选择 -->
    <Dialog v-model:visible="showDatePicker" header="选择归纳日期" :modal="true" :style="{ width: '360px' }"
      :draggable="false" :closable="true">
      <div class="datepicker-wrapper">
        <DatePicker v-model="summarizeDate" :maxDate="maxDate" dateFormat="yy-mm-dd" placeholder="选择日期" />
      </div>
      <template #footer>
        <Button label="取消" severity="secondary" outlined @click="showDatePicker = false" />
        <Button label="确认归纳" severity="contrast" @click="submitSummarize" :loading="summarizing" />
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useConfirm } from 'primevue/useconfirm'
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
import DatePicker from 'primevue/datepicker'

const confirm = useConfirm()
const toast = useToast()

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:6880'
const userId = localStorage.getItem('user_id') || ''

// ========== 记忆列表 ==========
interface MemoryItem {
  id: number
  name: string
  user_id: number
  mem_type: string
  time_range_start_at: string | null
  time_range_end_at: string | null
  source_msg_count: number
  mem: string
  version: number
  is_active: number
  created_at: string
  updated_at: string
}

const items = ref<MemoryItem[]>([])
const total = ref(0)
const loading = ref(false)
const pageSize = ref(10)
const pageNum = ref(1)
const searchQuery = ref('')

const showDatePicker = ref(false)
const summarizing = ref(false)
const summarizeDate = ref<Date | null>(null)

// 最大可选日期：昨天
const maxDate = ref(new Date(new Date().setDate(new Date().getDate() - 1)))

async function fetchList() {
  loading.value = true
  try {
    const params = new URLSearchParams({
      user_id: String(userId),
      pageSize: String(pageSize.value),
      pageNum: String(pageNum.value),
    })
    if (searchQuery.value.trim()) {
      params.set('keywords', searchQuery.value.trim())
    }
    const res = await fetch(`${API_BASE_URL}/api/v1/memory/list?${params}`)
    const data = await res.json()
    if (data.code !== 0) {
      toast.add({ severity: 'error', summary: '加载失败', detail: data.message, life: 3000 })
      return
    }
    items.value = data.result.items || []
    total.value = data.result.total || 0
  } catch (err) {
    toast.add({ severity: 'error', summary: '请求失败', detail: String(err), life: 3000 })
  } finally {
    loading.value = false
  }
}

async function submitSummarize() {
  if (!summarizeDate.value) {
    toast.add({ severity: 'warn', summary: '请选择日期', life: 2000 })
    return
  }

  summarizing.value = true
  try {
    const year = summarizeDate.value.getFullYear()
    const month = String(summarizeDate.value.getMonth() + 1).padStart(2, '0')
    const day = String(summarizeDate.value.getDate()).padStart(2, '0')
    const dateStr = `${year}-${month}-${day}`

    const res = await fetch(`${API_BASE_URL}/api/v1/memory/summarize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: String(userId), date: dateStr }),
    })
    const body = await res.json()
    if (body.code !== 0) {
      toast.add({ severity: 'error', summary: '归纳失败', detail: body.message, life: 3000 })
      return
    }
    toast.add({ severity: 'success', summary: '记忆归纳任务已提交', life: 2000 })
    showDatePicker.value = false
    fetchList()
  } catch (err) {
    toast.add({ severity: 'error', summary: '请求失败', detail: String(err), life: 3000 })
  } finally {
    summarizing.value = false
  }
}

function handleSearch() {
  pageNum.value = 1
  fetchList()
}

function onPage(event: any) {
  pageNum.value = event.page + 1
  pageSize.value = event.rows
  fetchList()
}

function formatTime(t: string | null): string {
  if (!t) return '-'
  return t.substring(0, 16).replace('T', ' ')
}

function memTypeLabel(type: string): string {
  const map: Record<string, string> = {
    'daily_summary': '日度摘要',
    'topic_summary': '主题摘要',
    'key_fact': '关键事实',
    'preference': '用户偏好',
  }
  return map[type] || type
}

function memTypeSeverity(type: string): string {
  const map: Record<string, string> = {
    'daily_summary': 'info',
    'topic_summary': 'warn',
    'key_fact': 'success',
    'preference': 'contrast',
  }
  return map[type] || 'secondary'
}

// ========== 查看详情 ==========
const detailDialogVisible = ref(false)
const detailItem = ref<MemoryItem | null>(null)
const detailLoading = ref(false)

async function viewDetail(data: MemoryItem) {
  detailLoading.value = true
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/memory/get?id=${data.id}`)
    const body = await res.json()
    if (body.code === 0 && body.result) {
      detailItem.value = body.result
    } else {
      detailItem.value = data
    }
  } catch {
    detailItem.value = data
  } finally {
    detailLoading.value = false
    detailDialogVisible.value = true
  }
}

// ========== 删除 ==========
function confirmDelete(event: MouseEvent, data: MemoryItem) {
  confirm.require({
    target: event.currentTarget as HTMLElement,
    message: `确定要删除记忆「${data.name}」吗？`,
    icon: 'pi pi-exclamation-triangle',
    rejectProps: { label: '取消', severity: 'secondary', outlined: true },
    acceptProps: { label: '删除', severity: 'danger' },
    accept: async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/v1/memory/delete`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: data.id, user_id: userId }),
        })
        const body = await res.json()
        if (body.code !== 0) {
          toast.add({ severity: 'error', summary: '删除失败', detail: body.message, life: 3000 })
          return
        }
        toast.add({ severity: 'success', summary: '删除成功', detail: `记忆「${data.name}」已删除`, life: 2000 })
        fetchList()
      } catch (err) {
        toast.add({ severity: 'error', summary: '请求失败', detail: String(err), life: 3000 })
      }
    },
  })
}

onMounted(() => {
  const yesterday = new Date()
  yesterday.setDate(yesterday.getDate() - 1)
  summarizeDate.value = yesterday
  fetchList()
})
</script>

<style scoped>
.resource-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 16px 0;
  gap: 16px;
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
  align-items: center;
}

.detail-label {
  font-size: 13px;
  color: #999;
  min-width: 80px;
  flex-shrink: 0;
}

.detail-value {
  font-size: 13px;
  color: #333;
}

.mem-content {
  margin-top: 4px;
}

.mem-content-title {
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

.datepicker-wrapper {
  display: flex;
  justify-content: center;
  padding: 16px 0;
}
</style>
