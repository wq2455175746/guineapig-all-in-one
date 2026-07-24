<template>
  <div class="skill-layout">
    <!-- 顶部工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <Button label="上传 Skill" icon="pi pi-upload" severity="secondary" raised size="small" @click="handleUploadClick"
          :loading="uploading" />
      </div>
      <div class="search-area">
        <IconField>
          <InputIcon class="pi pi-search" />
          <InputText v-model="searchQuery" placeholder="搜索 Skill 名称或描述..." @keydown.enter="handleSearch" />
        </IconField>
        <Button icon="pi pi-refresh" severity="secondary" raised size="small" @click="fetchList"
          :loading="loading" />
      </div>
    </div>

    <!-- 隐藏文件选择器 -->
    <input ref="fileInputRef" type="file" accept=".zip" style="display:none" @change="onFileSelected" />

    <!-- 底部：内容区 -->
    <DataView :value="filteredItems" layout="grid" paginator :rows="10" :rowsPerPageOptions="[10, 20, 50]"
      dataKey="id" class="skill-dataview">
      <template #grid="slotProps">
        <div class="skill-grid">
          <div v-for="item in slotProps.items" :key="item.id" class="skill-card">
            <!-- 名称 -->
            <div class="skill-card-name">{{ item.name }}</div>

            <!-- 描述 -->
            <div class="skill-card-desc" :class="{ expanded: expandedDesc[item.id] }"
              v-tooltip.top="item.description" @click="toggleDesc(item.id)">
              {{ item.description }}
            </div>

            <!-- 状态 -->
            <div class="skill-card-status">
              <span class="status-label" :class="{ active: item.status }">
                {{ item.status ? '已启用' : '已禁用' }}
              </span>
              <InputSwitch :modelValue="item.status" @update:modelValue="toggleStatus(item)"
                class="status-switch" />
            </div>

            <!-- 文件统计 -->
            <div class="skill-card-file">
              <span class="file-label">文件统计</span>
              <div class="file-tags">
                <Tag :value="`scripts ${fileScriptCount(item)}`" severity="info" class="file-tag"
                  v-if="fileScriptCount(item) > 0" />
                <Tag :value="`refs ${fileRefCount(item)}`" severity="warn" class="file-tag"
                  v-if="fileRefCount(item) > 0" />
                <Tag :value="`assets ${fileAssetCount(item)}`" severity="success" class="file-tag"
                  v-if="fileAssetCount(item) > 0" />
                <Tag :value="`others ${fileOtherCount(item)}`" severity="secondary" class="file-tag"
                  v-if="fileOtherCount(item) > 0" />
              </div>
            </div>

            <!-- 元数据 -->
            <div class="skill-card-meta">
              <div class="meta-row">
                <span class="meta-label">版本</span>
                <span class="meta-value">{{ item.skill_version || itemMeta(item, 'version') }}</span>
              </div>
              <div class="meta-row">
                <span class="meta-label">文件</span>
                <span class="meta-value">{{ itemMeta(item, 'file_count') }} 个 / {{ formatSize(itemMeta(item,
                  'total_size')) }}</span>
              </div>
              <div class="meta-row">
                <span class="meta-label">上传时间</span>
                <span class="meta-value">{{ item.created_at?.substring(0, 10) }}</span>
              </div>
            </div>

            <!-- 操作按钮 -->
            <div class="skill-card-actions">
              <Button icon="pi pi-download" severity="secondary" rounded size="small" v-tooltip.top="'下载'"
                @click="handleDownload(item)" />
              <Button icon="pi pi-trash" severity="danger" rounded size="small" v-tooltip.top="'删除'"
                @click="confirmDelete($event, item)" />
            </div>
          </div>
        </div>
      </template>
      <template #empty>
        <div class="empty-state">
          <i class="pi pi-box" style="font-size: 48px; color: #d0d5dd; margin-bottom: 16px"></i>
          <p class="empty-text">{{ loading ? '加载中...' : '暂无 Skill，请上传一个 ZIP 文件' }}</p>
        </div>
      </template>
    </DataView>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import DataView from 'primevue/dataview'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import InputSwitch from 'primevue/inputswitch'
import Tag from 'primevue/tag'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:6880'
const userId = localStorage.getItem('user_id') || ''

const confirm = useConfirm()
const toast = useToast()

const loading = ref(false)
const uploading = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

// ========== 数据类型 ==========
interface SkillItem {
  id: number
  user_id: number
  name: string
  description: string
  skill_version: string
  zip_url: string
  file_stat: string   // JSON string
  metadata: string    // JSON string
  status: boolean     // UI 层用 boolean，API 收发时转换 0|1
  created_at: string
  updated_at: string
}

const items = ref<SkillItem[]>([])

// ========== 列表加载 ==========
onMounted(() => {
  fetchList()
})

async function fetchList() {
  loading.value = true
  try {
    const params = new URLSearchParams({ user_id: String(userId) })
    const res = await fetch(`${API_BASE_URL}/api/v1/skill/list?${params}`)
    const body = await res.json()
    if (body.code === 0 && body.result) {
      items.value = (body.result.items || []).map((item: any) => ({
        ...item,
        status: item.status === 1 || item.status === true,
      }))
    } else {
      toast.add({ severity: 'error', summary: '加载失败', detail: body.message || '请求异常', life: 3000 })
    }
  } catch (e: any) {
    toast.add({ severity: 'error', summary: '网络错误', detail: e.message, life: 3000 })
  } finally {
    loading.value = false
  }
}

// ========== 搜索 ==========
const searchQuery = ref('')

function handleSearch() {
  // DataView 已通过计算属性 filteredItems 实时过滤
}

const filteredItems = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return items.value
  return items.value.filter(item =>
    item.name.toLowerCase().includes(q) || item.description.toLowerCase().includes(q)
  )
})

// ========== 描述展开/收起 ==========
const expandedDesc = ref<Record<number, boolean>>({})

function toggleDesc(id: number) {
  expandedDesc.value[id] = !expandedDesc.value[id]
}

// ========== 文件统计展示 ==========
function fileScriptCount(item: SkillItem): number {
  try {
    const fs = JSON.parse(item.file_stat)
    return fs.scripts?.length || 0
  } catch { return 0 }
}
function fileRefCount(item: SkillItem): number {
  try {
    const fs = JSON.parse(item.file_stat)
    return fs.references?.length || 0
  } catch { return 0 }
}
function fileAssetCount(item: SkillItem): number {
  try {
    const fs = JSON.parse(item.file_stat)
    return fs.assets?.length || 0
  } catch { return 0 }
}
function fileOtherCount(item: SkillItem): number {
  try {
    const fs = JSON.parse(item.file_stat)
    return fs.others?.length || 0
  } catch { return 0 }
}
function itemMeta(item: SkillItem, key: string): string {
  try {
    const m = JSON.parse(item.metadata)
    return m[key] ?? '—'
  } catch { return '—' }
}
function formatSize(sizeStr: string): string {
  const size = parseInt(sizeStr)
  if (isNaN(size)) return '—'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

// ========== 文件上传 ==========
function handleUploadClick() {
  fileInputRef.value?.click()
}

async function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  // 校验文件类型
  if (!file.name.toLowerCase().endsWith('.zip')) {
    toast.add({ severity: 'error', summary: '上传失败', detail: '仅支持 .zip 格式文件', life: 3000 }); (input.value = '')
    return
  }

  // 校验文件大小
  const maxSize = 10 * 1024 * 1024 // 10MB
  if (file.size > maxSize) {
    toast.add({ severity: 'error', summary: '上传失败', detail: '文件大小不能超过 10MB', life: 3000 }); (input.value = '')
    return
  }

  const skillName = file.name.replace(/\.zip$/i, '')
  uploading.value = true

  try {
    // Step 1: 获取预签名上传 URL
    const uploadParams = new URLSearchParams({
      user_id: String(userId),
      filename: skillName,
    })
    const uploadRes = await fetch(`${API_BASE_URL}/api/v1/skill/presigned-upload-url?${uploadParams}`)
    const uploadBody = await uploadRes.json()
    if (uploadBody.code !== 0 || !uploadBody.result) {
      toast.add({ severity: 'error', summary: '上传失败', detail: '获取上传地址失败', life: 3000 })
      return
    }
    const { url: presignedUrl, key: zipKey } = uploadBody.result

    // Step 2: 上传文件到 S3
    const s3Res = await fetch(presignedUrl, {
      method: 'PUT',
      body: file,
      headers: { 'Content-Type': 'application/zip' },
    })
    if (!s3Res.ok) {
      toast.add({ severity: 'error', summary: '上传失败', detail: '文件上传到存储服务失败', life: 3000 })
      return
    }

    // Step 3: 通知后端创建 Skill
    const createRes = await fetch(`${API_BASE_URL}/api/v1/skill/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: userId, zip_key: zipKey }),
    })
    const createBody = await createRes.json()
    if (createBody.code !== 0) {
      toast.add({ severity: 'error', summary: '创建失败', detail: createBody.detail || createBody.message, life: 3000 })
      return
    }

    toast.add({ severity: 'success', summary: '上传成功', detail: `${file.name} 已上传并解析`, life: 3000 })
    await fetchList()

    // 下载并解压到本地 userData/skills/{skillName}/
    try {
      const presignedRes = await fetch(
        `${API_BASE_URL}/api/v1/aimodel/presigned-download-url?key=${encodeURIComponent(zipKey)}`
      )
      const presignedBody = await presignedRes.json()
      if (presignedBody.code === 0 && presignedBody.result?.url) {
        await window.electronAPI.downloadAndExtractSkill({
          url: presignedBody.result.url,
          skillName: skillName,
        })
      }
    } catch (extractErr: any) {
      // 本地解压失败不影响主流程，仅警告
      console.warn('本地 Skill 解压失败:', extractErr)
    }
  } catch (e: any) {
    toast.add({ severity: 'error', summary: '上传异常', detail: e.message, life: 3000 })
  } finally {
    uploading.value = false
    input.value = ''
  }
}

// ========== 状态切换 ==========
async function toggleStatus(item: SkillItem) {
  const newStatus = !item.status
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/skill/update`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: item.id, user_id: userId, status: newStatus ? 1 : 0 }),
    })
    const body = await res.json()
    if (body.code !== 0) {
      toast.add({ severity: 'error', summary: '更新失败', detail: body.detail || body.message, life: 3000 })
      return
    }
    item.status = newStatus
    toast.add({
      severity: newStatus ? 'success' : 'warn',
      summary: newStatus ? '已启用' : '已禁用',
      detail: `${item.name} 状态已更新`,
      life: 2000,
    })
  } catch (e: any) {
    toast.add({ severity: 'error', summary: '网络错误', detail: e.message, life: 3000 })
  }
}

// ========== 下载（通过预签名 URL） ==========
async function handleDownload(item: SkillItem) {
  if (!item.zip_url) {
    toast.add({ severity: 'warn', summary: '下载失败', detail: '文件地址不可用', life: 2000 })
    return
  }
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/aimodel/presigned-download-url?key=${encodeURIComponent(item.zip_url)}`)
    const body = await res.json()
    if (body.code === 0 && body.result?.url) {
      window.open(body.result.url, '_blank')
    } else {
      toast.add({ severity: 'error', summary: '下载失败', detail: '获取下载链接失败', life: 3000 })
    }
  } catch (e: any) {
    toast.add({ severity: 'error', summary: '网络错误', detail: e.message, life: 3000 })
  }
}

// ========== 删除确认 ==========
function confirmDelete(event: MouseEvent, item: SkillItem) {
  confirm.require({
    target: event.currentTarget as HTMLElement,
    message: `确定要删除 Skill「${item.name}」吗？`,
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
    accept: async () => {
      try {
        const res = await fetch(`${API_BASE_URL}/api/v1/skill/delete`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: item.id, user_id: userId }),
        })
        const body = await res.json()
        if (body.code !== 0) {
          toast.add({ severity: 'error', summary: '删除失败', detail: body.detail || body.message, life: 3000 })
          return
        }
        items.value = items.value.filter(i => i.id !== item.id)
        toast.add({ severity: 'success', summary: '删除成功', detail: `${item.name} 已删除`, life: 2000 })
      } catch (e: any) {
        toast.add({ severity: 'error', summary: '网络错误', detail: e.message, life: 3000 })
      }
    },
  })
}
</script>

<style scoped>
.skill-layout {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px 0;
  height: 100%;
  overflow: auto;
}

/* ========== 工具栏 ========== */
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  gap: 12px;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* ========== 搜索 ========== */
.search-area {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.search-area :deep(.p-inputtext) {
  font-size: 14px;
  padding: 10px 12px 10px 36px;
  width: 280px;
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

/* ========== DataView 网格 ========== */
.skill-dataview {
  flex: 1;
  padding: 12px 12px 12px 12px;
}

.skill-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  padding: 14px;
}

.skill-card {
  background: #fff;
  border: 1px solid #eee;
  border-radius: 10px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: box-shadow 0.15s ease;
}

.skill-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

/* 名称 */
.skill-card-name {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 描述 */
.skill-card-desc {
  font-size: 12px;
  color: #888;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 36px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.skill-card-desc:hover {
  color: #555;
}

.skill-card-desc.expanded {
  display: block;
  -webkit-line-clamp: unset;
  overflow: visible;
  color: #555;
}

/* 状态 */
.skill-card-status {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.status-label {
  font-size: 12px;
  color: #999;
}

.status-label.active {
  color: #22c55e;
  font-weight: 500;
}

.status-switch :deep(.p-inputswitch-slider) {
  width: 32px;
  height: 18px;
}

.status-switch :deep(.p-inputswitch-slider::before) {
  width: 14px;
  height: 14px;
}

/* 文件统计 */
.skill-card-file {
  display: flex;
  align-items: center;
  gap: 6px;
}

.file-label {
  font-size: 12px;
  color: #999;
}

.file-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.file-tag {
  font-size: 11px;
}

/* 元数据 */
.skill-card-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px 0;
  border-top: 1px solid #f0f0f0;
}

.meta-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.meta-label {
  font-size: 11px;
  color: #aaa;
}

.meta-value {
  font-size: 11px;
  color: #666;
}

/* 操作按钮 */
.skill-card-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  padding-top: 4px;
  border-top: 1px solid #f0f0f0;
}

/* ========== 空状态 ========== */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 0;
}

.empty-text {
  font-size: 16px;
  color: #999;
  margin: 0;
}
</style>
