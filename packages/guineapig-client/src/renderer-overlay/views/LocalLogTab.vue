<template>
  <div class="resource-body">
    <Card>
      <template #content>
        <!-- 工具栏 -->
        <div class="table-toolbar">
          <div class="toolbar-left">
            <Button label="打包下载" icon="pi pi-download" severity="secondary" raised size="small"
              @click="openZipDialog" />
          </div>
          <div class="search-area">
            <IconField>
              <InputIcon class="pi pi-search" />
              <InputText v-model="searchQuery" placeholder="搜索文件名..." @keydown.enter="handleSearch" />
            </IconField>
            <Button icon="pi pi-refresh" severity="secondary" raised size="small" @click="fetchList" />
          </div>
        </div>

        <!-- 日志列表 -->
        <DataTable :value="items" size="small" paginator :rows="pageSize" :rowsPerPageOptions="[10, 20, 50]"
          :totalRecords="total" :lazy="true" @page="onPage" currentPageReportTemplate="共 {totalRecords} 条"
          tableStyle="min-width: 50rem" :loading="loading">

          <Column header="序号">
            <template #body="{ data }">
              {{ items.indexOf(data) + 1 + (pageNum - 1) * pageSize }}
            </template>
          </Column>
          <Column field="name" header="日志文件名">
            <template #body="{ data }">
              <span class="file-name-cell" v-tooltip.top="data.name">{{ data.name }}</span>
            </template>
          </Column>
          <Column header="文件大小">
            <template #body="{ data }">
              {{ formatFileSize(data.size) }}
            </template>
          </Column>
          <Column field="created_at" header="创建日期">
            <template #body="{ data }">
              {{ formatDate(data.created_at) }}
            </template>
          </Column>
          <Column headerStyle="text-align: right">
            <template #header>
              <span style="display: flex; justify-content: flex-end; width: 100%;">操作</span>
            </template>
            <template #body="{ data }">
              <div class="action-buttons">
                <Button icon="pi pi-eye" rounded severity="secondary" v-tooltip.top="'查看'"
                  @click="handleView(data)" />
                <Button icon="pi pi-trash" rounded severity="danger" v-tooltip.top="'删除'"
                  @click="confirmDelete($event, data)" />
              </div>
            </template>
          </Column>
        </DataTable>
      </template>
    </Card>

    <!-- 日期范围选择弹窗 -->
    <Dialog v-model:visible="showDatePicker" header="选择日期范围" :modal="true" :style="{ width: '500px' }"
      :draggable="false" :closable="true">
      <div class="dialog-body">
        <label class="date-range-label">日期范围</label>
        <DatePicker v-model="zipDateRange" selectionMode="range" dateFormat="yy-mm-dd"
          placeholder="点击选择日期范围" class="date-range-input" />
      </div>
      <template #footer>
        <Button label="取消" severity="secondary" outlined @click="showDatePicker = false" />
        <Button label="确认下载" severity="contrast" @click="handleZipDownload" :loading="zipping"
          :disabled="!zipDateRange || !zipDateRange[0] || !zipDateRange[1]" />
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
import Dialog from 'primevue/dialog'
import DatePicker from 'primevue/datepicker'

const confirm = useConfirm()
const toast = useToast()

// ========== 日期工具 ==========
function formatDate(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const h = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  return `${y}-${m}-${day} ${h}:${min}`
}

function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const k = 1024
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  const size = (bytes / Math.pow(k, i)).toFixed(i > 0 ? 1 : 0)
  return `${size} ${units[i]}`
}

function dateToStr(d: Date | null): string {
  if (!d) return ''
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}${m}${day}`
}

// ========== 状态 ==========
const items = ref<LogFileItem[]>([])
const total = ref(0)
const pageSize = ref(10)
const pageNum = ref(1)
const loading = ref(false)
const zipping = ref(false)
const searchQuery = ref('')

// 打包下载弹窗
const showDatePicker = ref(false)
const zipDateRange = ref<Date[] | null>(null)

// ========== 数据加载 ==========
async function fetchList() {
  loading.value = true
  try {
    const files = await window.electronAPI.getLogFiles(searchQuery.value.trim() || undefined)

    // 前端分页
    total.value = files.length
    const start = (pageNum.value - 1) * pageSize.value
    const end = start + pageSize.value
    items.value = files.slice(start, end)
  } catch (err) {
    toast.add({ severity: 'error', summary: '加载失败', detail: String(err), life: 3000 })
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

// ========== 查看（系统默认编辑器打开） ==========
async function handleView(data: LogFileItem) {
  try {
    await window.electronAPI.openLogFile(data.name)
  } catch (err) {
    toast.add({ severity: 'error', summary: '打开失败', detail: String(err), life: 3000 })
  }
}

// ========== 删除 ==========
async function handleDelete(data: LogFileItem) {
  try {
    const ok = await window.electronAPI.deleteLogFile(data.name)
    if (ok) {
      toast.add({ severity: 'success', summary: '删除成功', detail: `${data.name} 已删除`, life: 2000 })
      fetchList()
    } else {
      toast.add({ severity: 'error', summary: '删除失败', detail: '文件不存在', life: 3000 })
    }
  } catch (err) {
    toast.add({ severity: 'error', summary: '删除失败', detail: String(err), life: 3000 })
  }
}

function confirmDelete(event: MouseEvent, data: LogFileItem) {
  confirm.require({
    target: event.currentTarget as HTMLElement,
    message: `确定要删除日志文件 "${data.name}" 吗？`,
    icon: 'pi pi-exclamation-triangle',
    rejectProps: {
      label: '取消',
      severity: 'secondary',
      outlined: true
    },
    acceptProps: {
      label: '删除',
      severity: 'danger'
    },
    accept: () => handleDelete(data)
  })
}

// ========== 打包下载 ==========
function openZipDialog() {
  const today = new Date()
  zipDateRange.value = [today, today]
  showDatePicker.value = true
}

async function handleZipDownload() {
  if (!zipDateRange.value || !zipDateRange.value[0] || !zipDateRange.value[1]) {
    toast.add({ severity: 'warn', summary: '请选择完整日期范围', detail: '需要选择开始和结束日期', life: 3000 })
    return
  }

  const startStr = dateToStr(zipDateRange.value[0])
  const endStr = dateToStr(zipDateRange.value[1])

  if (startStr > endStr) {
    toast.add({ severity: 'warn', summary: '日期范围错误', detail: '开始日期不能晚于结束日期', life: 3000 })
    return
  }

  zipping.value = true
  try {
    const result = await window.electronAPI.zipAndDownloadLogs({
      startDate: startStr,
      endDate: endStr,
      keyword: searchQuery.value.trim() || undefined,
    })
    if (result.cancelled) return
    showDatePicker.value = false
    zipDateRange.value = null
    toast.add({
      severity: 'success',
      summary: '下载完成',
      detail: `已打包 ${result.count} 个日志文件`,
      life: 3000,
    })
  } catch (err) {
    toast.add({ severity: 'error', summary: '打包失败', detail: String(err), life: 3000 })
  } finally {
    zipping.value = false
  }
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

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
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

/* ========== 操作按钮组 ========== */
.action-buttons {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
}

/* ========== 文件名 ========== */
.file-name-cell {
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: inline-block;
}

/* ========== 打包下载弹窗 ========== */
.dialog-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 0;
}

.date-range-label {
  font-size: 14px;
  font-weight: 500;
  color: #333;
}

.date-range-input {
  width: 100%;
}
</style>
