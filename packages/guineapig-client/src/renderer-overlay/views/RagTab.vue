<template>
  <div class="rag-layout">
    <!-- 顶部工具栏 -->
    <div class="rag-toolbar">
      <div class="rag-toolbar-left">
        <Button label="添加知识库" icon="pi pi-plus" severity="secondary" raised size="small"
          @click="openAddDialog" />
      </div>
      <div class="search-area">
        <IconField>
          <InputIcon class="pi pi-search" />
          <InputText v-model="searchQuery" placeholder="搜索知识库名称或描述..." @keydown.enter="handleSearch" />
        </IconField>
        <Button icon="pi pi-refresh" severity="secondary" raised size="small" @click="fetchList"
          :loading="loading" />
      </div>
    </div>

    <!-- 卡片列表 -->
    <DataView :value="items" layout="grid" paginator :rows="pageSize" :rowsPerPageOptions="[10, 20, 50]"
      :totalRecords="total" :lazy="true" @page="onPage" dataKey="id" class="rag-dataview" :loading="loading">
      <template #grid="slotProps">
        <div class="rag-grid">
          <div v-for="item in slotProps.items" :key="item.id" class="rag-card">
            <!-- 名称 -->
            <div class="rag-card-name">{{ item.name }}</div>

            <!-- 描述 -->
            <div class="rag-card-desc" v-tooltip.top="item.rag_desc || '暂无描述'">
              {{ item.rag_desc || '暂无描述' }}
            </div>

            <!-- 参数 -->
            <div class="rag-card-meta">
              <div class="meta-row">
                <span class="meta-label">分段大小</span>
                <span class="meta-value">{{ item.chunk_size }}</span>
              </div>
              <div class="meta-row">
                <span class="meta-label">重叠大小</span>
                <span class="meta-value">{{ item.overlap_size }}</span>
              </div>
              <div class="meta-row">
                <span class="meta-label">嵌入维度</span>
                <span class="meta-value">{{ item.dimension_size }}</span>
              </div>
              <div class="meta-row">
                <span class="meta-label">嵌入模型</span>
                <span class="meta-value">{{ item.embedding_model_name }}</span>
              </div>
              <div class="meta-row">
                <span class="meta-label">Reranker</span>
                <span class="meta-value">{{ item.reranker_model_name }}</span>
              </div>
              <div class="meta-row">
                <span class="meta-label">文档数</span>
                <span class="meta-value">{{ item.doc_count }}</span>
              </div>
            </div>

            <!-- 操作按钮 -->
            <div class="rag-card-actions">
              <Button icon="pi pi-pencil" severity="secondary" rounded size="small" v-tooltip.top="'编辑'"
                @click="openEditDialog(item)" />
              <Button icon="pi pi-trash" severity="danger" rounded size="small" v-tooltip.top="'删除'"
                :disabled="item.doc_count > 0 || isRagInUse(item)" @click="confirmDelete($event, item)" />
            </div>
          </div>
        </div>
      </template>
      <template #empty>
        <div class="empty-state">
          <i class="pi pi-database" style="font-size: 48px; color: #d0d5dd; margin-bottom: 16px"></i>
          <p class="empty-text">{{ loading ? '加载中...' : '暂无知识库，点击上方按钮添加' }}</p>
        </div>
      </template>
    </DataView>

    <!-- 添加对话框 -->
    <Dialog v-model:visible="addDialogVisible" header="添加知识库" :modal="true" :style="{ width: '1280px' }"
      :draggable="false">
      <div class="dialog-form">
        <div class="form-row">
          <div class="field">
            <label class="field-label">知识库名称 <span style="color:red">*</span></label>
            <InputText v-model="addForm.name" placeholder="字母、数字、下划线，数字不能开头" class="field-input"
              @input="validateName" />
            <small v-if="nameError" style="color:red">{{ nameError }}</small>
          </div>
          <div class="field">
            <label class="field-label">知识库描述</label>
            <InputText v-model="addForm.rag_desc" placeholder="知识库描述（选填）" class="field-input" />
          </div>
        </div>
        <div class="form-row">
          <div class="field">
            <label class="field-label">分段大小</label>
            <InputNumber v-model="addForm.chunk_size" :min="1" :max="10000" class="field-input" />
          </div>
          <div class="field">
            <label class="field-label">重叠大小</label>
            <InputNumber v-model="addForm.overlap_size" :min="0" :max="1000" class="field-input" />
          </div>
        </div>
        <div class="form-row">
          <div class="field">
            <label class="field-label">嵌入维度</label>
            <InputNumber v-model="addForm.dimension_size" :min="1" :max="10000" class="field-input" />
          </div>
          <div class="field">
            <label class="field-label">嵌入模型 <span style="color:red">*</span></label>
            <Select v-model="addForm.embedding_model_id" :options="embeddingOptions" optionLabel="model_name"
              optionValue="id" placeholder="选择嵌入模型" class="field-input" :loading="embeddingLoading" />
          </div>
        </div>
        <div class="form-row">
          <div class="field">
            <label class="field-label">Reranker 模型 <span style="color:red">*</span></label>
            <Select v-model="addForm.reranker_model_id" :options="rerankerOptions" optionLabel="model_name"
              optionValue="id" placeholder="选择 Reranker 模型" class="field-input" :loading="rerankerLoading" />
          </div>
        </div>
        <div class="dialog-actions">
          <Button label="取消" severity="secondary" outlined @click="addDialogVisible = false" />
          <Button label="确定" @click="handleAdd" :loading="addLoading" :disabled="!!nameError || !addForm.name" />
        </div>
      </div>
    </Dialog>

    <!-- 编辑对话框 -->
    <Dialog v-model:visible="editDialogVisible" header="编辑知识库" :modal="true" :style="{ width: '600px' }"
      :draggable="false">
      <div class="dialog-form">
        <div class="form-row">
          <div class="field">
            <label class="field-label">知识库名称</label>
            <InputText :value="editForm.name" disabled class="field-input" />
          </div>
        </div>
        <div class="form-row">
          <div class="field">
            <label class="field-label">知识库描述</label>
            <InputText v-model="editForm.rag_desc" placeholder="修改知识库描述" class="field-input" />
          </div>
        </div>
        <div class="form-row">
          <div class="field">
            <label class="field-label">分段大小</label>
            <InputText :value="String(editForm.chunk_size)" disabled class="field-input" />
          </div>
          <div class="field">
            <label class="field-label">重叠大小</label>
            <InputText :value="String(editForm.overlap_size)" disabled class="field-input" />
          </div>
        </div>
        <div class="form-row">
          <div class="field">
            <label class="field-label">嵌入模型</label>
            <InputText :value="editForm.embedding_model_name" disabled class="field-input" />
          </div>
          <div class="field">
            <label class="field-label">Reranker 模型</label>
            <InputText :value="editForm.reranker_model_name" disabled class="field-input" />
          </div>
        </div>
        <div class="dialog-actions">
          <Button label="取消" severity="secondary" outlined @click="editDialogVisible = false" />
          <Button label="保存" @click="handleUpdate" severity="contrast" :loading="updateLoading" />
        </div>
      </div>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import DataView from 'primevue/dataview'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import InputNumber from 'primevue/inputnumber'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import Select from 'primevue/select'
import Dialog from 'primevue/dialog'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:6880'
const userId = localStorage.getItem('user_id') || ''

const confirm = useConfirm()
const toast = useToast()

// ========== 数据类型 ==========
interface RagItem {
  id: number
  user_id: number
  name: string
  rag_desc: string
  chunk_size: number
  overlap_size: number
  dimension_size: number
  embedding_model_id: number
  embedding_model_name: string
  reranker_model_id: number
  reranker_model_name: string
  doc_count: number
  rag_metadata: string
  created_at: string
  updated_at: string
}

interface AiModelOption {
  id: number
  model_name: string
}

// ========== 列表加载 ==========
const items = ref<RagItem[]>([])
const loading = ref(false)
const total = ref(0)
const pageNum = ref(1)
const pageSize = ref(10)

onMounted(() => {
  fetchList()
})

async function fetchList() {
  loading.value = true
  try {
    const params = new URLSearchParams({
      user_id: String(userId),
      pageNum: String(pageNum.value),
      pageSize: String(pageSize.value),
    })
    if (searchQuery.value.trim()) {
      params.set('keywords', searchQuery.value.trim())
    }
    const res = await fetch(`${API_BASE_URL}/api/v1/rag/list?${params}`)
    const body = await res.json()
    if (body.code === 0 && body.result) {
      items.value = body.result.items || []
      total.value = body.result.total || 0
    } else {
      toast.add({ severity: 'error', summary: '加载失败', detail: body.message || '请求异常', life: 3000 })
    }
  } catch (e: any) {
    toast.add({ severity: 'error', summary: '网络错误', detail: e.message, life: 3000 })
  } finally {
    loading.value = false
  }
}

function onPage(event: any) {
  pageNum.value = Math.floor(event.first / event.rows) + 1
  pageSize.value = event.rows
  fetchList()
}

// ========== 搜索 ==========
const searchQuery = ref('')

function handleSearch() {
  pageNum.value = 1
  fetchList()
}

// ========== 模型选项加载 ==========
const embeddingOptions = ref<AiModelOption[]>([])
const rerankerOptions = ref<AiModelOption[]>([])
const embeddingLoading = ref(false)
const rerankerLoading = ref(false)

async function loadModelOptions() {
  embeddingLoading.value = true
  rerankerLoading.value = true
  try {
    const [embedRes, rerankRes] = await Promise.all([
      fetch(`${API_BASE_URL}/api/v1/aimodel/options-by-type?user_id=${userId}&model_type=EMBEDDING`),
      fetch(`${API_BASE_URL}/api/v1/aimodel/options-by-type?user_id=${userId}&model_type=RERANKER`),
    ])
    const embedBody = await embedRes.json()
    const rerankBody = await rerankRes.json()
    if (embedBody.code === 0) embeddingOptions.value = embedBody.result || []
    if (rerankBody.code === 0) rerankerOptions.value = rerankBody.result || []
  } catch (e: any) {
    console.warn('加载模型选项失败:', e)
  } finally {
    embeddingLoading.value = false
    rerankerLoading.value = false
  }
}

// ========== 添加对话框 ==========
const addDialogVisible = ref(false)
const addLoading = ref(false)
const nameError = ref('')

const addForm = ref({
  name: '',
  rag_desc: '',
  chunk_size: 500,
  overlap_size: 50,
  dimension_size: 1024,
  embedding_model_id: null as number | null,
  reranker_model_id: null as number | null,
})

function validateName() {
  const v = addForm.value.name
  if (!v) {
    nameError.value = ''
    return
  }
  if (/^\d/.test(v)) {
    nameError.value = '名称不能以数字开头'
    return
  }
  if (!/^[a-zA-Z0-9_]+$/.test(v)) {
    nameError.value = '只能包含字母、数字、下划线'
    return
  }
  nameError.value = ''
}

function openAddDialog() {
  addForm.value = { name: '', rag_desc: '', chunk_size: 500, overlap_size: 50, dimension_size: 1024, embedding_model_id: null, reranker_model_id: null }
  nameError.value = ''
  loadModelOptions()
  addDialogVisible.value = true
}

async function handleAdd() {
  if (!addForm.value.name || nameError.value) return
  if (!addForm.value.embedding_model_id || !addForm.value.reranker_model_id) {
    toast.add({ severity: 'warn', summary: '请选择', detail: '请选择嵌入模型和 Reranker 模型', life: 3000 })
    return
  }

  addLoading.value = true
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/rag/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        name: addForm.value.name,
        rag_desc: addForm.value.rag_desc,
        chunk_size: addForm.value.chunk_size,
        overlap_size: addForm.value.overlap_size,
        dimension_size: addForm.value.dimension_size,
        embedding_model_id: addForm.value.embedding_model_id,
        reranker_model_id: addForm.value.reranker_model_id,
      }),
    })
    const body = await res.json()
    if (body.code !== 0) {
      toast.add({ severity: 'error', summary: '创建失败', detail: body.detail || body.message, life: 3000 })
      return
    }
    toast.add({ severity: 'success', summary: '创建成功', detail: `知识库「${addForm.value.name}」已创建`, life: 2000 })
    addDialogVisible.value = false
    pageNum.value = 1
    await fetchList()
  } catch (e: any) {
    toast.add({ severity: 'error', summary: '网络错误', detail: e.message, life: 3000 })
  } finally {
    addLoading.value = false
  }
}

// ========== 编辑对话框 ==========
const editDialogVisible = ref(false)
const updateLoading = ref(false)
const editForm = ref({
  id: 0,
  name: '',
  rag_desc: '',
  chunk_size: 0,
  overlap_size: 0,
  dimension_size: 0,
  embedding_model_name: '',
  reranker_model_name: '',
})

function openEditDialog(item: RagItem) {
  editForm.value = {
    id: item.id,
    name: item.name,
    rag_desc: item.rag_desc,
    chunk_size: item.chunk_size,
    overlap_size: item.overlap_size,
    dimension_size: item.dimension_size,
    embedding_model_name: item.embedding_model_name,
    reranker_model_name: item.reranker_model_name,
  }
  editDialogVisible.value = true
}

async function handleUpdate() {
  updateLoading.value = true
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/rag/update`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: editForm.value.id,
        user_id: userId,
        rag_desc: editForm.value.rag_desc,
      }),
    })
    const body = await res.json()
    if (body.code !== 0) {
      toast.add({ severity: 'error', summary: '更新失败', detail: body.detail || body.message, life: 3000 })
      return
    }
    toast.add({ severity: 'success', summary: '更新成功', detail: '描述已更新', life: 2000 })
    editDialogVisible.value = false
    await fetchList()
  } catch (e: any) {
    toast.add({ severity: 'error', summary: '网络错误', detail: e.message, life: 3000 })
  } finally {
    updateLoading.value = false
  }
}

// ========== is_used 检查 ==========
function isRagInUse(item: RagItem): boolean {
  if (!item.rag_metadata) return false
  try {
    const meta = JSON.parse(item.rag_metadata)
    return meta.is_used === true
  } catch {
    return false
  }
}

// ========== 删除 ==========
function confirmDelete(event: MouseEvent, item: RagItem) {
  confirm.require({
    target: event.currentTarget as HTMLElement,
    message: `确定要删除知识库「${item.name}」吗？`,
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
        const res = await fetch(`${API_BASE_URL}/api/v1/rag/delete`, {
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
        total.value--
        toast.add({ severity: 'success', summary: '删除成功', detail: `${item.name} 已删除`, life: 2000 })
      } catch (e: any) {
        toast.add({ severity: 'error', summary: '网络错误', detail: e.message, life: 3000 })
      }
    },
  })
}
</script>

<style scoped>
.rag-layout {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px 0;
  height: 100%;
  overflow: auto;
}

.rag-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 16px;
}

.rag-toolbar-left {
  display: flex;
  gap: 8px;
}

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

/* ========== DataView ========== */
.rag-dataview {
  flex: 1;
  padding: 12px;
}

.rag-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  padding: 14px;
}

.rag-card {
  background: #fff;
  border: 1px solid #eee;
  border-radius: 10px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: box-shadow 0.15s ease;
}

.rag-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.rag-card-name {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rag-card-desc {
  font-size: 12px;
  color: #888;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 36px;
}

/* 参数信息 */
.rag-card-meta {
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
.rag-card-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  padding-top: 4px;
  border-top: 1px solid #f0f0f0;
}

/* ========== 对话框表单 ========== */
.dialog-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-row {
  display: flex;
  gap: 16px;
}

.field {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 13px;
  font-weight: 500;
  color: #333;
}

.field-input {
  width: 100%;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 8px;
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
