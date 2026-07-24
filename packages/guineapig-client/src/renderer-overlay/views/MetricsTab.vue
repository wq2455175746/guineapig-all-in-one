<template>
  <div class="resource-body">
    <Card>
      <template #content>
        <!-- 工具栏 -->
        <div class="table-toolbar">
          <div class="toolbar-left"></div>
          <div class="search-area">
            <IconField>
              <InputIcon class="pi pi-search" />
              <InputText v-model="searchQuery" placeholder="搜索指标名..." @keydown.enter="handleSearch" />
            </IconField>
            <Button icon="pi pi-refresh" severity="secondary" raised size="small" @click="fetchList" />
          </div>
        </div>

        <!-- 指标列表 -->
        <DataTable :value="items" size="small" paginator :rows="pageSize" :rowsPerPageOptions="[10, 20, 50]"
          :totalRecords="total" :lazy="true" @page="onPage" currentPageReportTemplate="共 {totalRecords} 条"
          tableStyle="min-width: 50rem" :loading="loading">

          <template #empty>
            <div style="text-align: center; padding: 40px 0; color: #999; font-size: 14px;">暂无数据</div>
          </template>

          <Column header="序号">
            <template #body="{ data }">
              {{ items.indexOf(data) + 1 + (pageNum - 1) * pageSize }}
            </template>
          </Column>
          <Column field="type" header="类型" style="width: 100px">
            <template #body="{ data }">
              <Tag :value="typeLabel(data.type)" :severity="typeSeverity(data.type)" />
            </template>
          </Column>
          <Column field="name" header="指标名">
            <template #body="{ data }">
              <span v-tooltip.top="data.name">{{ data.name }}</span>
            </template>
          </Column>

          <Column header="Label" style="width: 100px">
            <template #body="{ data }">
              <span class="json-cell">{{ data.otel_label || '-' }}</span>
            </template>
          </Column>
          <Column header="指标值" style="width: 150px">
            <template #body="{ data }">
              <span class="json-cell">{{ data.otel_value || '-' }}</span>
            </template>
          </Column>

          <Column field="created_at" header="创建时间" style="width: 200px">
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
                <Button icon="pi pi-eye" rounded severity="secondary" v-tooltip.top="'查看'" @click="viewDetail(data)" />
                <Button icon="pi pi-trash" rounded severity="danger" v-tooltip.top="'删除'"
                  @click="confirmDelete($event, data)" />
              </div>
            </template>
          </Column>
        </DataTable>
      </template>
    </Card>

    <!-- 指标详情对话框 -->
    <Dialog v-model:visible="detailDialogVisible" :header="'指标详情 - ' + (detailItem?.name || '')" :modal="true"
      :style="{ width: '700px' }" :draggable="false" maximizable>
      <div v-if="detailItem" class="detail-content">
        <div class="detail-fields">
          <div class="detail-row">
            <span class="detail-label">指标名</span>
            <span class="detail-value">{{ detailItem.name }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">类型</span>
            <span class="detail-value">{{ typeLabel(detailItem.type) }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">对话ID</span>
            <span class="detail-value">{{ detailItem.conversation_id }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">统计日期</span>
            <span class="detail-value">{{ detailItem.stat_date || '-' }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">创建时间</span>
            <span class="detail-value">{{ formatTime(detailItem.created_at) }}</span>
          </div>
        </div>

        <!-- Label 内容 -->
        <div class="data-section" v-if="detailItem.otel_label">
          <h4 class="section-title">Label</h4>
          <div class="json-block">{{ formatJSON(detailItem.otel_label) }}</div>
        </div>

        <!-- 指标值内容 -->
        <div class="data-section" v-if="detailItem.otel_value">
          <h4 class="section-title">指标值</h4>
          <div class="json-block">{{ formatJSON(detailItem.otel_value) }}</div>
        </div>
      </div>
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

interface OtelItem {
  id: number
  name: string
  user_id: number
  conversation_id: number
  stat_date: string
  type: string
  otel_value: string
  otel_label: string
  created_by: string
  created_at: string
  updated_at: string
}

const confirm = useConfirm()
const toast = useToast()

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:6880'
const userId = localStorage.getItem('user_id') || ''

// ========== 状态 ==========
const items = ref<OtelItem[]>([])
const total = ref(0)
const pageSize = ref(10)
const pageNum = ref(1)
const loading = ref(false)
const searchQuery = ref('')

// ========== 详情弹窗 ==========
const detailDialogVisible = ref(false)
const detailItem = ref<OtelItem | null>(null)

// ========== 类型标签 ==========
const typeMap: Record<string, string> = {
  metric: '指标',
  log: '日志',
  trace: '链路',
  other: '其他',
}

function typeLabel(t: string): string {
  return typeMap[t] || t
}

function typeSeverity(t: string): string {
  const map: Record<string, string> = {
    metric: 'info',
    log: 'warn',
    trace: 'contrast',
    other: 'secondary',
  }
  return map[t] || 'secondary'
}

// ========== 格式化 ==========
function formatTime(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const h = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  return `${y}-${m}-${day} ${h}:${min}`
}

function formatJSON(s: string): string {
  if (!s) return '-'
  try {
    return JSON.stringify(JSON.parse(s), null, 2)
  } catch {
    return s
  }
}

// ========== 数据加载 ==========
async function fetchList() {
  loading.value = true
  try {
    const params = new URLSearchParams({
      user_id: userId,
      pageSize: String(pageSize.value),
      pageNum: String(pageNum.value),
    })
    if (searchQuery.value.trim()) {
      params.set('keywords', searchQuery.value.trim())
    }

    const res = await fetch(`${API_BASE_URL}/api/v1/otel/list?${params}`)
    const data = await res.json()

    if (data.code !== 0) {
      toast.add({ severity: 'error', summary: '加载失败', detail: data.message, life: 3000 })
      return
    }

    items.value = data.result.items || []
    total.value = data.result.total || 0
  } catch (err) {
    toast.add({ severity: 'error', summary: '请求失败', detail: String(err), life: 3000 })
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

// ========== 搜索 ==========
function handleSearch() {
  pageNum.value = 1
  fetchList()
}

function onPage(event: any) {
  pageNum.value = event.page + 1
  pageSize.value = event.rows
  fetchList()
}

// ========== 查看详情 ==========
function viewDetail(data: OtelItem) {
  detailItem.value = data
  detailDialogVisible.value = true
}

// ========== 删除 ==========
async function handleDelete(data: OtelItem) {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/otel/delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: data.id, user_id: userId }),
    })
    const result = await res.json()

    if (result.code !== 0) {
      toast.add({ severity: 'error', summary: '删除失败', detail: result.message, life: 3000 })
      return
    }

    toast.add({ severity: 'success', summary: '删除成功', detail: `${data.name} 已删除`, life: 2000 })
    fetchList()
  } catch (err) {
    toast.add({ severity: 'error', summary: '删除失败', detail: String(err), life: 3000 })
  }
}

function confirmDelete(event: MouseEvent, data: OtelItem) {
  confirm.require({
    target: event.currentTarget as HTMLElement,
    message: `确定要删除指标 "${data.name}" 吗？`,
    icon: 'pi pi-exclamation-triangle',
    rejectProps: {
      label: '取消',
      severity: 'secondary',
      outlined: true,
    },
    acceptProps: {
      label: '删除',
      severity: 'danger',
    },
    accept: () => handleDelete(data),
  })
}

// ========== 初始化 ==========
onMounted(() => {
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

/* ========== 工具栏 ========== */
.table-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  gap: 12px;
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

/* ========== 操作按钮 ========== */
.action-buttons {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
}

/* ========== JSON 单元格 ========== */
.json-cell {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: inline-block;
  font-family: monospace;
  font-size: 12px;
  color: #666;
}

/* ========== 详情对话框 ========== */
.detail-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-fields {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.detail-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.detail-label {
  font-size: 13px;
  font-weight: 500;
  color: #666;
  min-width: 80px;
  flex-shrink: 0;
}

.detail-value {
  font-size: 14px;
  color: #333;
}

.data-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  margin: 0;
}

.json-block {
  background: #f5f5f5;
  border-radius: 8px;
  padding: 16px;
  font-family: monospace;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  color: #333;
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid #eee;
}
</style>
