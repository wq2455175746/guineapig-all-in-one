<template>
  <div class="resource-body">
    <Card>
      <template #content>
        <div class="table-toolbar">
          <Button label="添加模型" icon="pi pi-plus" severity="secondary" raised size="small" @click="openAddDialog" />
          <div class="search-area">
            <IconField>
              <InputIcon class="pi pi-search" />
              <InputText v-model="searchQuery" placeholder="搜索URL或模型..." @keydown.enter="handleSearch" />
            </IconField>
            <Button icon="pi pi-refresh" severity="secondary" raised size="small" @click="fetchList" />
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
          <Column field="provider_code" header="供应商"></Column>
          <Column field="api_url" header="URL"></Column>
          <Column field="api_key" header="API Key"></Column>
          <Column field="model_name" header="模型"></Column>
          <Column field="model_type" header="模型类型"></Column>
          <Column header="连通状态">
            <template #body="{ data }">
              <div style="display: flex; align-items: center; gap: 4px;">
                <i v-if="data.established === 1" class="pi pi-check-circle"
                  style="color: #22c55e; font-size: 14px;"></i>
                <i v-else class="pi pi-minus-circle" style="color: #d0d5dd; font-size: 14px;"></i>
                <span :style="{ color: data.established === 1 ? '#22c55e' : '#999', fontSize: '13px' }">
                  {{ data.established === 1 ? '已连通' : '未测试' }}
                </span>
              </div>
            </template>
          </Column>
          <Column header="状态">
            <template #body="{ data }">
              <Tag :value="data.status ? '启用' : '禁用'" :severity="data.status ? 'success' : 'danger'" />
            </template>
          </Column>
          <Column headerStyle="text-align: right">
            <template #header>
              <span style="display: flex; justify-content: flex-end; width: 100%;">操作</span>
            </template>
            <template #body="{ data }">
              <div class="action-buttons">
                <Button icon="pi pi-pencil" rounded severity="secondary" v-tooltip.top="'编辑'"
                  @click="openEditDialog(data)" />
                <Button icon="pi pi-send" rounded severity="secondary" v-tooltip.top="'测试连接'"
                  @click="handleTestConnection(data)" />
                <Button icon="pi pi-trash" rounded severity="danger" v-tooltip.top="'删除'"
                  @click="confirmDelete($event, data)" />
              </div>
            </template>
          </Column>
        </DataTable>
      </template>
    </Card>

    <!-- 添加/编辑 对话框 -->
    <Dialog v-model:visible="dialogVisible" :header="dialogTitle" :modal="true" :style="{ width: '1280px' }"
      :draggable="false">
      <div class="dialog-form">
        <div class="form-row">
          <div class="field">
            <label class="field-label">供应商</label>
            <Select v-model="formData.provider_code" :options="vendorOptions" placeholder="选择供应商" class="field-input" />
          </div>
          <div class="field">
            <label class="field-label">模型类型</label>
            <Select v-model="formData.model_type" :options="modelTypeOptions" placeholder="选择模型类型"
              class="field-input" />
          </div>
        </div>
        <div class="form-row">
          <div class="field">
            <label class="field-label">URL</label>
            <InputText v-model="formData.api_url" placeholder="请输入API地址" class="field-input" />
          </div>
          <div class="field">
            <label class="field-label">模型名称</label>
            <InputText v-model="formData.model_name" placeholder="请输入模型名称" class="field-input" />
          </div>
        </div>
        <div class="form-row">
          <div class="field">
            <label class="field-label">API Key</label>
            <div v-if="!changingApiKey" class="api-key-row">
              <InputText :value="'••••••••'" disabled class="field-input" />
              <Button label="更换密钥" severity="secondary" size="small" @click="startChangeApiKey" />
            </div>
            <div v-else class="api-key-row">
              <InputText ref="apiKeyInputRef" v-model="formData.api_key" placeholder="输入新的API Key"
                class="field-input" />
              <Button icon="pi pi-times" rounded severity="secondary" @click="cancelChangeApiKey"
                v-tooltip.top="'取消修改'" />
            </div>
          </div>
          <div class="field">
            <label class="field-label">状态</label>
            <div class="field-switch">
              <InputSwitch v-model="formData.status" />
              <span class="switch-label">{{ formData.status ? '启用' : '禁用' }}</span>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <div class="dialog-footer">
          <Button label="测试连接" icon="pi pi-send" severity="secondary" outlined size="small" @click="testConnection"
            :loading="testingConnection" :disabled="!formData.api_url || !formData.model_name" />
          <div class="dialog-footer-right">
            <Button label="取消" severity="secondary" outlined @click="dialogVisible = false" />
            <Button label="确定" severity="contrast" @click="submitDialog" :loading="submitting" />
          </div>
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import { useConfirm } from 'primevue/useconfirm'
import { useToast } from 'primevue/usetoast'
import { encryptApiKey } from '../../utils/rsa'
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
import InputSwitch from 'primevue/inputswitch'

const confirm = useConfirm()
const toast = useToast()

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:6880'
const userId = localStorage.getItem('user_id') || ''

// ========== 数据类型 ==========
interface AiModelItem {
  id: number
  model_name: string
  api_url: string
  provider_code: string
  model_type: string
  api_key?: string
  status: number
  established: number
}

// ========== API请求 ==========
async function fetchList() {
  loading.value = true
  try {
    const params = new URLSearchParams({
      user_id: String(userId),
      pageSize: String(pageSize.value),
      pageNum: String(pageNum.value)
    })
    if (searchQuery.value.trim()) {
      params.set('keywords', searchQuery.value.trim())
    }
    const res = await fetch(`${API_BASE_URL}/api/v1/aimodel/list?${params}`)
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

async function createModel(): Promise<boolean> {
  try {
    const encryptedKey = await encryptApiKey(formData.api_key)
    const res = await fetch(`${API_BASE_URL}/api/v1/aimodel/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        model_name: formData.model_name,
        api_url: formData.api_url,
        api_key: encryptedKey,
        provider_code: formData.provider_code,
        model_type: formData.model_type,
        status: formData.status ? 1 : 0
      })
    })
    const data = await res.json()
    if (data.code !== 0) {
      toast.add({ severity: 'error', summary: '添加失败', detail: data.message, life: 3000 })
      return false
    }
    return true
  } catch (err) {
    toast.add({ severity: 'error', summary: '请求失败', detail: String(err), life: 3000 })
    return false
  }
}

async function updateModel(): Promise<boolean> {
  try {
    const body: Record<string, any> = {
      id: editingId.value,
      user_id: userId,
      model_name: formData.model_name,
      api_url: formData.api_url,
      provider_code: formData.provider_code,
      model_type: formData.model_type,
      status: formData.status ? 1 : 0
    }
    if (changingApiKey.value && formData.api_key) {
      body.api_key = await encryptApiKey(formData.api_key)
    }
    const res = await fetch(`${API_BASE_URL}/api/v1/aimodel/update`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
    const data = await res.json()
    if (data.code !== 0) {
      toast.add({ severity: 'error', summary: '更新失败', detail: data.message, life: 3000 })
      return false
    }
    return true
  } catch (err) {
    toast.add({ severity: 'error', summary: '请求失败', detail: String(err), life: 3000 })
    return false
  }
}

async function deleteModel(id: number): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/aimodel/delete`, {
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

// ========== 状态 ==========
const items = ref<AiModelItem[]>([])
const total = ref(0)
const pageSize = ref(10)
const pageNum = ref(1)
const loading = ref(false)

// ========== 搜索 ==========
const searchQuery = ref('')

function handleSearch() {
  pageNum.value = 1
  fetchList()
}

function onPage(event: any) {
  pageNum.value = event.page + 1
  pageSize.value = event.rows
  fetchList()
}

// ========== 供应商/类型选项 ==========
const vendorOptions = ['OpenAI', 'DeepSeek', 'Anthropic', 'Qwen', 'Ollama', 'Vllm', 'Other']
const modelTypeOptions = ['LLM', 'OCR', 'EMBEDDING', 'RERANKER', 'OTHER']

// ========== 添加/编辑对话框 ==========
const dialogVisible = ref(false)
const dialogMode = ref<'add' | 'edit'>('add')
const editingId = ref<number>(0)
const submitting = ref(false)
const testingConnection = ref(false)
const changingApiKey = ref(false)
const apiKeyInputRef = ref<HTMLInputElement | null>(null)

const defaultForm = () => ({
  provider_code: '',
  api_url: '',
  model_name: '',
  model_type: '',
  api_key: '',
  status: true
})

const formData = reactive(defaultForm())

const dialogTitle = computed(() =>
  dialogMode.value === 'add' ? '添加模型' : '修改模型')

function openAddDialog() {
  dialogMode.value = 'add'
  editingId.value = 0
  Object.assign(formData, defaultForm())
  dialogVisible.value = true
}

function openEditDialog(data: AiModelItem) {
  dialogMode.value = 'edit'
  editingId.value = data.id
  changingApiKey.value = false
  Object.assign(formData, {
    provider_code: data.provider_code,
    api_url: data.api_url,
    model_name: data.model_name,
    model_type: data.model_type,
    api_key: '',
    status: data.status === 1
  })
  dialogVisible.value = true
}

function startChangeApiKey() {
  changingApiKey.value = true
  formData.api_key = ''
  nextTick(() => {
    apiKeyInputRef.value?.focus()
  })
}

function cancelChangeApiKey() {
  changingApiKey.value = false
  formData.api_key = ''
}

async function testConnection(): Promise<void> {
  if (!formData.api_url || !formData.model_name) {
    toast.add({ severity: 'warn', summary: '请填写URL和模型名称', detail: '测试连接需要URL和模型名称', life: 2000 })
    return
  }

  testingConnection.value = true
  try {
    const body: Record<string, any> = {
      api_url: formData.api_url,
      model_name: formData.model_name,
      provider_code: formData.provider_code,
      model_type: formData.model_type
    }

    if (dialogMode.value === 'edit' && !changingApiKey.value && !formData.api_key) {
      body.id = editingId.value
      body.user_id = userId
    } else {
      body.api_key = await encryptApiKey(formData.api_key)
    }

    const res = await fetch(`${API_BASE_URL}/api/v1/aimodel/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    })
    const data = await res.json()
    if (data.code !== 0) {
      toast.add({ severity: 'error', summary: '测试失败', detail: data.message, life: 3000 })
      return
    }
    if (data.result?.connected) {
      toast.add({ severity: 'success', summary: '连接成功', detail: '模型可以正常连通', life: 3000 })
    } else {
      toast.add({ severity: 'error', summary: '连接失败', detail: data.result?.message || '未知错误', life: 3000 })
    }
  } catch (err) {
    toast.add({ severity: 'error', summary: '请求失败', detail: String(err), life: 3000 })
  } finally {
    testingConnection.value = false
  }
}

async function submitDialog() {
  if (!formData.provider_code || !formData.api_url || !formData.model_name) {
    toast.add({ severity: 'warn', summary: '请填写必填字段', detail: '供应商、URL、模型为必填项', life: 2000 })
    return
  }

  submitting.value = true
  let success = false
  if (dialogMode.value === 'add') {
    success = await createModel()
  } else {
    success = await updateModel()
  }
  submitting.value = false

  if (success) {
    dialogVisible.value = false
    fetchList()
  }
}

// ========== 删除确认 ==========
function confirmDelete(event: MouseEvent, data: AiModelItem) {
  confirm.require({
    target: event.currentTarget as HTMLElement,
    message: '确定要删除该模型配置吗？',
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
      const ok = await deleteModel(data.id)
      if (ok) fetchList()
    }
  })
}

// ========== 其他操作 ==========
async function handleTestConnection(data: AiModelItem) {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/aimodel/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: data.id,
        user_id: userId,
        api_url: data.api_url,
        model_name: data.model_name,
        provider_code: data.provider_code,
        model_type: data.model_type
      })
    })
    const r = await res.json()
    if (r.code !== 0) {
      toast.add({ severity: 'error', summary: '测试失败', detail: r.message, life: 3000 })
      return
    }
    if (r.result?.connected) {
      toast.add({ severity: 'success', summary: '连接成功', detail: '模型可以正常连通', life: 3000 })
      const updateRes = await fetch(`${API_BASE_URL}/api/v1/aimodel/updateEstablished`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: data.id, user_id: userId, established: 1 })
      })
      const updateData = await updateRes.json()
      if (updateData.code === 0) {
        fetchList()
      }
    } else {
      toast.add({ severity: 'error', summary: '连接失败', detail: r.result?.message || '未知错误', life: 3000 })
    }
  } catch (err) {
    toast.add({ severity: 'error', summary: '请求失败', detail: String(err), life: 3000 })
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

/* ========== 对话框表单 ========== */
.dialog-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 8px 0;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 14px;
  font-weight: 500;
  color: #333;
}

.field-input {
  width: 100%;
}

.field-switch {
  display: flex;
  align-items: center;
  gap: 10px;
}

.switch-label {
  font-size: 14px;
  color: #666;
}

/* ========== API密钥字段 ========== */
.api-key-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.api-key-row .field-input {
  flex: 1;
}

/* ========== 双列布局 ========== */
.form-row {
  display: flex;
  gap: 16px;
}

.form-row .field {
  flex: 1;
  min-width: 0;
}

/* ========== 对话框底部 ========== */
.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.dialog-footer-right {
  display: flex;
  gap: 8px;
}
</style>
