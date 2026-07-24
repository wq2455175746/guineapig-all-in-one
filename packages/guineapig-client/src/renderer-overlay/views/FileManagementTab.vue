<template>
  <div class="resource-body">
    <Card>
      <template #content>
        <!-- 文件管理工具栏 -->
        <div class="file-table-toolbar">
          <div class="file-toolbar-left">
            <Button label="上传文件" icon="pi pi-upload" severity="secondary" raised size="small" @click="handleUpload"
              :loading="uploading" />
          </div>
          <div class="search-area">
            <SelectButton v-model="embedFilter" :options="embedFilterOptions" optionLabel="label" optionValue="value"
              size="small" />
            <Select v-model="fileTypeFilter" :options="fileTypeOptions" placeholder="文件类型" showClear size="small" />
            <IconField>
              <InputIcon class="pi pi-search" />
              <InputText v-model="fileSearchQuery" placeholder="搜索文件名..." @keydown.enter="handleFileSearch" />
            </IconField>
            <Button icon="pi pi-refresh" severity="secondary" raised size="small" @click="fetchFileList" />
          </div>
        </div>

        <!-- 文件列表 -->
        <DataTable :value="fileItems" size="small" paginator :rows="filePageSize" :rowsPerPageOptions="[10, 20, 50]"
          :totalRecords="fileTotal" :lazy="true" @page="onFilePage" currentPageReportTemplate="共 {totalRecords} 条"
          tableStyle="min-width: 50rem" :loading="fileLoading">
          <Column header="序号">
            <template #body="{ data }">
              {{ fileItems.indexOf(data) + 1 + (filePageNum - 1) * filePageSize }}
            </template>
          </Column>
          <Column field="name" header="文件名">
            <template #body="{ data }">
              <span class="file-name-cell" v-tooltip.top="data.name">{{ data.name }}</span>
            </template>
          </Column>
          <Column field="file_url" header="文件URL">
            <template #body="{ data }">
              <span class="url-cell" v-tooltip.top="data.file_url">{{ data.file_url }}</span>
            </template>
          </Column>
          <Column field="file_md5" header="MD5"></Column>
          <Column field="file_size" header="大小">
            <template #body="{ data }">
              {{ formatFileSize(data.file_size) }}
            </template>
          </Column>
          <Column field="file_type" header="类型">
            <template #body="{ data }">
              <Tag :value="fileTypeLabel(data.file_type)" :severity="fileTypeSeverity(data.file_type)" />
            </template>
          </Column>
          <Column header="是否嵌入">
            <template #body="{ data }">
              <template v-if="data.is_embedded === 1">
                <Tag value="已嵌入" severity="success" />
              </template>
              <template v-else-if="data.is_embedded === 2">
                <Tag :value="`嵌入中 ${getEmbeddingProcess(data)}%`" severity="warn" />
              </template>
              <template v-else-if="data.is_embedded === 9">
                <Tag value="嵌入失败" severity="danger" v-tooltip.top="getEmbeddingError(data)" />
              </template>
              <template v-else>
                <Tag value="未嵌入" severity="secondary" />
              </template>
            </template>
          </Column>
          <Column field="created_at" header="上传时间"></Column>
          <Column headerStyle="text-align: right">
            <template #header>
              <span style="display: flex; justify-content: flex-end; width: 100%;">操作</span>
            </template>
            <template #body="{ data }">
              <div class="action-buttons">
                <Button icon="pi pi-microchip" rounded severity="secondary" v-tooltip.top="'嵌入'"
                  :disabled="!canEmbed(data.file_type) || data.is_embedded === 1 || data.is_embedded === 2"
                  @click="handleEmbed(data)" />
                <Button icon="pi pi-download" rounded severity="secondary" v-tooltip.top="'下载'"
                  @click="handleDownload(data)" />
                <Button icon="pi pi-trash" rounded severity="danger" v-tooltip.top="'删除'"
                  @click="confirmDeleteFile($event, data)" />
              </div>  
            </template>
          </Column>
        </DataTable>

        <!-- 隐藏文件选择器 -->
        <input ref="fileInputRef" type="file" style="display:none" @change="onFileSelected" />

        <!-- 嵌入知识库选择对话框 -->
        <Dialog v-model:visible="embedDialogVisible" header="选择知识库" :modal="true" :style="{ width: '400px' }"
          :draggable="false">
          <div style="display: flex; flex-direction: column; gap: 16px;">
            <div class="field">
              <label class="field-label">选择要嵌入的知识库</label>
            </div>
            <div class="field">
              <Select v-model="selectedRagId" :options="ragList" optionLabel="name" optionValue="id" size="small"
                placeholder="请选择知识库" class="field-input" :loading="ragLoading" />
            </div>
            <div class="dialog-actions">
              <Button label="取消" severity="secondary" outlined @click="embedDialogVisible = false" />
              <Button label="开始嵌入" @click="confirmEmbed" :loading="embeddingLoading" severity="contrast" 
                :disabled="!selectedRagId" />
            </div>
          </div>
        </Dialog>
      </template>
    </Card>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
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
import Select from 'primevue/select'
import SelectButton from 'primevue/selectbutton'
import Dialog from 'primevue/dialog'

const confirm = useConfirm()
const toast = useToast()

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:6880'
const userId = localStorage.getItem('user_id') || ''

const fileTypeOptions = ['txt', 'markdown', 'html', 'pdf', 'mp3', 'img', 'other']
const embedFilterOptions = [
  { label: '全部', value: -1 },
  { label: '普通', value: 0 },
  { label: '已嵌入', value: 1 }
]

const fileTypeLabels: Record<number, string> = {
  0: 'TXT', 1: 'MARKDOWN', 2: 'HTML', 3: 'PDF', 4: 'MP3', 5: 'IMG', 99: 'OTHER'
}

const fileTypeMapToInt: Record<string, number> = {
  txt: 0, markdown: 1, html: 2, pdf: 3, mp3: 4, img: 5, other: 99
}

interface FileItem {
  id: number
  user_id: number
  name: string
  file_desc: string
  file_url: string
  file_size: number
  file_md5: string
  file_type: number
  is_embedded: number
  storage_type: number
  embedding_config: string
  created_at: string
  updated_at: string
}

const fileTypeFilter = ref<string>('')
const embedFilter = ref<number>(-1)
const fileSearchQuery = ref('')
const fileItems = ref<FileItem[]>([])
const fileTotal = ref(0)
const fileLoading = ref(false)
const filePageSize = ref(10)
const filePageNum = ref(1)
const fileInputRef = ref<HTMLInputElement | null>(null)

// ========== 嵌入相关 ==========
const embedDialogVisible = ref(false)
const selectedRagId = ref<number | null>(null)
const embeddingLoading = ref(false)
const embeddingTarget = ref<FileItem | null>(null)
const ragList = ref<RagItem[]>([])
const ragLoading = ref(false)

interface RagItem {
  id: number
  user_id: number
  name: string
  rag_desc: string
}

const uploading = ref(false)

async function fetchFileList() {
  fileLoading.value = true
  try {
    const params = new URLSearchParams({
      user_id: String(userId),
      pageSize: String(filePageSize.value),
      pageNum: String(filePageNum.value)
    })
    if (fileSearchQuery.value.trim()) {
      params.set('keywords', fileSearchQuery.value.trim())
    }
    if (fileTypeFilter.value) {
      const typeInt = fileTypeMapToInt[fileTypeFilter.value]
      if (typeInt !== undefined) {
        params.set('file_type', String(typeInt))
      }
    }
    params.set('is_embedded', String(embedFilter.value))

    const res = await fetch(`${API_BASE_URL}/api/v1/file/list?${params}`)
    const data = await res.json()
    if (data.code !== 0) {
      toast.add({ severity: 'error', summary: '加载失败', detail: data.message, life: 3000 })
      return
    }
    fileItems.value = data.result.items || []
    fileTotal.value = data.result.total || 0
  } catch (err) {
    toast.add({ severity: 'error', summary: '请求失败', detail: String(err), life: 3000 })
  } finally {
    fileLoading.value = false
  }
}

function handleFileSearch() {
  filePageNum.value = 1
  fetchFileList()
}

function onFilePage(event: any) {
  filePageNum.value = event.page + 1
  filePageSize.value = event.rows
  fetchFileList()
}

watch(fileTypeFilter, () => {
  filePageNum.value = 1
  fetchFileList()
})
watch(embedFilter, () => {
  filePageNum.value = 1
  fetchFileList()
})

function handleUpload() {
  fileInputRef.value?.click()
}

async function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  uploading.value = true
  try {
    // 1. 获取预签名上传 URL
    const presignRes = await fetch(
      `${API_BASE_URL}/api/v1/file/presigned-upload-url?user_id=${userId}&filename=${encodeURIComponent(file.name)}`
    )
    const presignData = await presignRes.json()
    if (presignData.code !== 0) {
      toast.add({ severity: 'error', summary: '获取上传地址失败', detail: presignData.message, life: 3000 })
      return
    }
    const { url: uploadURL, key: fileKey } = presignData.result

    // 2. 文件直传到 S3
    const uploadRes = await fetch(uploadURL, { method: 'PUT', body: file })
    if (!uploadRes.ok) {
      toast.add({ severity: 'error', summary: '上传失败', detail: '文件上传到存储服务失败', life: 3000 })
      return
    }

    // 从 S3 响应中取 ETag 作为文件 MD5 值
    const etag = uploadRes.headers.get('ETag') || ''
    const fileMd5 = etag.replace(/^"/, '').replace(/"$/, '')

    // 3. 创建文件记录
    const createRes = await fetch(`${API_BASE_URL}/api/v1/file/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        name: file.name,
        file_url: fileKey,
        file_type: detectFileType(file.name),
        file_size: file.size,
        file_md5: fileMd5,
        storage_type: 0
      })
    })
    const createData = await createRes.json()
    if (createData.code !== 0) {
      toast.add({ severity: 'error', summary: '保存记录失败', detail: createData.message, life: 3000 })
      return
    }

    toast.add({ severity: 'success', summary: '上传成功', detail: `文件「${file.name}」已上传`, life: 3000 })
    fetchFileList()
  } catch (err) {
    toast.add({ severity: 'error', summary: '上传失败', detail: String(err), life: 3000 })
  } finally {
    uploading.value = false
    input.value = ''
  }
}

function detectFileType(filename: string): number {
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  const map: Record<string, number> = {
    txt: 0, md: 1, markdown: 1, html: 2, htm: 2,
    pdf: 3, mp3: 4, wav: 4, ogg: 4, flac: 4,
    png: 5, jpg: 5, jpeg: 5, gif: 5, svg: 5, webp: 5, bmp: 5, ico: 5
  }
  return map[ext] ?? 99
}

function formatFileSize(bytes: number): string {
  if (!bytes) return '-'
  if (bytes >= 1024 * 1024) {
    return (bytes / (1024 * 1024)).toFixed(2) + ' MB'
  } else if (bytes >= 1024) {
    return (bytes / 1024).toFixed(2) + ' KB'
  }
  return bytes + ' B'
}

function fileTypeLabel(type: number): string {
  return fileTypeLabels[type] || 'OTHER'
}

function fileTypeSeverity(type: number): string {
  const map: Record<number, string> = {
    0: 'info', 1: 'info', 2: 'warn', 3: 'danger', 4: 'success', 5: 'contrast', 99: 'secondary'
  }
  return map[type] || 'secondary'
}

function canEmbed(fileType: number): boolean {
  return fileType === 0 || fileType === 1 || fileType === 2
}

function handleEmbed(data: FileItem) {
  embeddingTarget.value = data
  selectedRagId.value = null
  embedDialogVisible.value = true
  fetchRagList()
}

interface EmbeddingConfig {
  embedding_process: number
  res_rag_id: number
  task_id: string
  error?: string
}

// 解析 embedding_config JSON
function parseEmbeddingConfig(config: string): EmbeddingConfig | null {
  if (!config) return null
  try {
    return JSON.parse(config)
  } catch {
    return null
  }
}

// 获取嵌入进度
function getEmbeddingProcess(data: FileItem): number {
  const config = parseEmbeddingConfig(data.embedding_config)
  return config?.embedding_process ?? 0
}

// 获取嵌入错误信息
function getEmbeddingError(data: FileItem): string {
  const config = parseEmbeddingConfig(data.embedding_config)
  return config?.error ?? '嵌入失败'
}

// 预加载知识库列表
async function fetchRagList() {
  ragLoading.value = true
  try {
    const params = new URLSearchParams({ user_id: String(userId), pageSize: '999', pageNum: '1' })
    const res = await fetch(`${API_BASE_URL}/api/v1/rag/list?${params}`)
    const data = await res.json()
    if (data.code === 0) {
      ragList.value = data.result.items || []
    }
  } catch (err) {
    console.warn('加载知识库列表失败:', err)
  } finally {
    ragLoading.value = false
  }
}

async function confirmEmbed() {
  if (!selectedRagId.value || !embeddingTarget.value) return
  embeddingLoading.value = true
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/file/embed`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_id: String(embeddingTarget.value.id),
        res_rag_id: String(selectedRagId.value),
      }),
    })
    const data = await res.json()
    if (data.code === 0) {
      toast.add({ severity: 'success', summary: '嵌入任务已提交', detail: `文件「${embeddingTarget.value.name}」正在嵌入`, life: 3000 })
      embedDialogVisible.value = false
      await fetchFileList()
    } else {
      toast.add({ severity: 'error', summary: '提交失败', detail: data.message, life: 3000 })
    }
  } catch (err) {
    toast.add({ severity: 'error', summary: '请求失败', detail: String(err), life: 3000 })
  } finally {
    embeddingLoading.value = false
  }
}

async function handleDownload(data: FileItem) {
  try {
    const res = await fetch(
      `${API_BASE_URL}/api/v1/file/presigned-download-url?key=${encodeURIComponent(data.file_url)}`
    )
    const json = await res.json()
    if (json.code !== 0) {
      toast.add({ severity: 'error', summary: '获取下载链接失败', detail: json.message, life: 3000 })
      return
    }
    window.open(json.result.url, '_blank')
  } catch (err) {
    toast.add({ severity: 'error', summary: '下载失败', detail: String(err), life: 3000 })
  }
}

async function deleteFileRecord(id: number): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/file/delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, user_id: userId })
    })
    const data = await res.json()
    if (data.code !== 0) {
      toast.add({ severity: 'error', summary: '删除失败', detail: data.message, life: 3000 })
      return false
    }
    return true
  } catch (err) {
    toast.add({ severity: 'error', summary: '请求失败', detail: String(err), life: 3000 })
    return false
  }
}

function confirmDeleteFile(event: MouseEvent, data: FileItem) {
  confirm.require({
    target: event.currentTarget as HTMLElement,
    message: `确定要删除文件「${data.name}」吗？`,
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
    accept: async () => {
      const ok = await deleteFileRecord(data.id)
      if (ok) {
        toast.add({ severity: 'success', summary: '已删除', detail: `文件「${data.name}」已删除`, life: 2000 })
        fetchFileList()
      }
    }
  })
}

// 组件挂载时加载列表
fetchFileList()
</script>

<style scoped>

.field-input {
  width: 100%;
}


.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 8px;
}

.resource-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 16px 0;
  gap: 16px;
  overflow: auto;
}

/* ========== 文件管理工具栏 ========== */
.file-table-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  gap: 12px;
}

.file-toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.file-toolbar-left :deep(.p-selectbutton) {
  display: flex;
  align-items: center;
}

.file-toolbar-left :deep(.p-selectbutton .p-button) {
  padding-top: 8px;
  padding-bottom: 8px;
}

/* ========== 搜索 ========== */
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

/* ========== 文件名/URL 截断 ========== */
.file-name-cell,
.url-cell {
  display: inline-block;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
