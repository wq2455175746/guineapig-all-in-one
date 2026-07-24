<template>
  <div class="capabilities-body">
    <!-- 工具栏 -->
    <div class="mcp-toolbar">
      <div class="mcp-toolbar-left">
        <Button label="添加 MCP" icon="pi pi-plus" severity="secondary" raised size="small" @click="openAddMcpDialog" />
      </div>
      <div class="mcp-toolbar-right">
        <IconField>
          <InputIcon class="pi pi-search" />
          <InputText v-model="mcpSearchQuery" placeholder="搜索 MCP 名称..." size="small" />
        </IconField>
        <Button icon="pi pi-refresh" severity="secondary" raised size="small" @click="fetchMcpList"
          :loading="mcpLoading" />
      </div>
    </div>

    <!-- MCP 卡片列表 -->
    <DataView :value="filteredMcpItems" layout="grid" paginator :rows="10" :rowsPerPageOptions="[10, 20, 50]"
      dataKey="id" class="mcp-dataview">
      <template #grid="slotProps">
        <div class="mcp-grid">
          <div v-for="item in slotProps.items" :key="item.id" class="mcp-card">
            <div class="mcp-card-header">
              <div class="mcp-card-name">{{ item.name }}</div>
              <Tag :value="mcpTypeLabel(item.type)" :severity="mcpTypeSeverity(item.type)" class="mcp-type-tag" />
            </div>
            <div class="mcp-card-desc">{{ item.description || '无描述' }}</div>
            <div class="mcp-card-meta">
              <div class="meta-row">
                <span class="meta-label">状态</span>
                <span class="meta-value" :class="{ active: item.status }">
                  {{ item.status ? '已启用' : '已禁用' }}
                </span>
              </div>
              <div class="meta-row" v-if="item.type === 'stdio'">
                <span class="meta-label">命令</span>
                <span class="meta-value mono">{{ item.command }}</span>
              </div>
              <div class="meta-row" v-else>
                <span class="meta-label">URL</span>
                <span class="meta-value mono">{{ item.url }}</span>
              </div>
            </div>
            <div class="mcp-card-actions">
              <Button icon="pi pi-eye" severity="secondary" rounded size="small" v-tooltip.top="'查看资源'"
                @click="openMcpResourceView(item)" />
              <Button icon="pi pi-pencil" severity="secondary" rounded size="small" v-tooltip.top="'编辑'"
                @click="openEditMcpDialog(item)" />
              <Button icon="pi pi-trash" severity="danger" rounded size="small" v-tooltip.top="'删除'"
                @click="confirmDeleteMcp($event, item)" />
            </div>
          </div>
        </div>
      </template>
      <template #empty>
        <div class="empty-state">
          <i class="pi pi-puzzle" style="font-size: 48px; color: #d0d5dd; margin-bottom: 16px"></i>
          <p class="empty-text">{{ mcpLoading ? '加载中...' : '暂无 MCP，点击「添加 MCP」开始' }}</p>
        </div>
      </template>
    </DataView>
  </div>

  <!-- 添加/编辑 MCP Dialog — Splitter 布局 -->
  <Dialog v-model:visible="mcpDialogVisible" :header="mcpDialogMode === 'add' ? '添加 MCP' : '编辑 MCP'" :modal="true"
    :closable="true" :style="{ width: '1280px' }" :draggable="false" @update:visible="onMcpDialogClose">
    <Splitter class="mcp-dialog-splitter">
      <SplitterPanel :size="25" :minSize="20">
        <ScrollPanel style="height: 800px" class="mcp-form-scroll">
          <div class="mcp-form">

            <div class="field-row">
              <label class="field-label">类型 <span class="required">*</span></label>
              <Select v-model="mcpForm.type" :options="mcpTypeOptions" optionLabel="label" optionValue="value"
                class="field-input" />
            </div>

            <div class="field-row">
              <label class="field-label">名称 <span class="required">*</span></label>
              <InputText v-model="mcpForm.name" placeholder="MCP 名称" class="field-input" />
            </div>

            <div class="field-row">
              <label class="field-label">描述</label>
              <Textarea v-model="mcpForm.description" placeholder="描述" rows="3" class="field-input" autoResize />
            </div>

            <!-- Stdio 字段 -->
            <template v-if="mcpForm.type === 'stdio'">
              <div class="field-row">
                <label class="field-label">命令 <span class="required">*</span></label>
                <InputText v-model="mcpForm.command" placeholder="如 npx" class="field-input" />
              </div>
              <div class="field-row">
                <label class="field-label">参数</label>
                <Textarea v-model="mcpForm.args"
                  placeholder="每行一个，如&#10;-y&#10;@modelcontextprotocol/server-filesystem&#10;/path" rows="3"
                  class="field-input" autoResize />
              </div>
              <div class="field-row">
                <label class="field-label">环境变量</label>
                <Textarea v-model="mcpForm.env_vars" placeholder="KEY=VALUE&#10;每行一个" rows="2" class="field-input"
                  autoResize />
                <small class="field-hint">key=value 每行一个</small>
              </div>
            </template>

            <!-- SSE / Streamable HTTP 字段 -->
            <template v-else>
              <div class="field-row">
                <label class="field-label">URL <span class="required">*</span></label>
                <InputText v-model="mcpForm.url" placeholder="如 http://localhost:3000/mcp" class="field-input" />
              </div>
              <div class="field-row">
                <label class="field-label">Headers</label>
                <Textarea v-model="mcpForm.headers" placeholder="key:value&#10;每行一个" rows="3" class="field-input"
                  autoResize />
                <small class="field-hint">key:value 每行一个</small>
              </div>
            </template>

            <div class="field-row">
              <label class="field-label">超时(s)</label>
              <InputNumber v-model="mcpForm.timeout" placeholder="60" class="field-input" :min="30" :max="180" />
            </div>

            <div class="field-row">
              <label class="field-label">状态</label>
              <div class="field-switch">
                <InputSwitch v-model="mcpForm.status" />
                <span class="switch-label">{{ mcpForm.status ? '启用' : '禁用' }}</span>
              </div>
            </div>


          </div>
        </ScrollPanel>
      </SplitterPanel>
      <SplitterPanel :size="75" :minSize="50">
        <ScrollPanel style="height: 800px" class="mcp-tools-scroll">
          <div v-if="mcpFetchedTools.length === 0 && !mcpFetching" class="mcp-tools-empty">
            <i class="pi pi-arrow-left" style="font-size: 24px; color: #ccc"></i>
            <p class="empty-hint">点击左侧「获取资源」按钮获取 MCP 工具列表</p>
          </div>
          <div v-else class="mcp-tools-list">
            <div class="tools-header">
              <span class="tools-count">工具 ({{ mcpFetchedTools.length }})</span>
            </div>
            <div v-for="tool in mcpFetchedTools" :key="tool.name" class="mcp-tool-item">
              <div class="tool-item-header">
                <span class="tool-name">{{ tool.name }}</span>
                <InputSwitch v-model="tool._enabled" />
              </div>
              <div class="tool-desc">{{ tool.description || '无描述' }}</div>
              <div v-if="tool.input_schema?.properties" class="tool-params">
                <div v-for="(prop, pName) in tool.input_schema.properties" :key="pName as string"
                  class="tool-param-row">
                  <span class="param-name">{{ pName as string }}</span>
                  <span class="param-type">({{ (prop as any).type || 'any' }})</span>
                  <span class="param-desc">{{ (prop as any).description || '' }}</span>
                </div>
              </div>
            </div>
            <!-- Resources 摘要 -->
            <div v-if="mcpFetchedResources.length > 0" class="tools-section-divider"></div>
            <div v-if="mcpFetchedResources.length > 0" class="tools-header">
              <span class="tools-count">资源 ({{ mcpFetchedResources.length }})</span>
            </div>
            <!-- Prompts 摘要 -->
            <div v-if="mcpFetchedPrompts.length > 0" class="tools-section-divider"></div>
            <div v-if="mcpFetchedPrompts.length > 0" class="tools-header">
              <span class="tools-count">Prompts ({{ mcpFetchedPrompts.length }})</span>
            </div>
          </div>
        </ScrollPanel>
      </SplitterPanel>
    </Splitter>
    <template #footer>
      <!-- 获取资源按钮 -->
      <div class="field-row ">
        <Button label="获取资源" icon="pi pi-cloud-download" size="small" severity="secondary"
          @click="handleFetchMcpResources" :loading="mcpFetching"
          :disabled="!mcpForm.name || !mcpForm.command && !mcpForm.url" class="fetch-btn" />
        <Message v-if="mcpFetchError" severity="error" :closable="false" class="fetch-error-msg">
          {{ mcpFetchError }}
        </Message>
      </div>
      <Button label="取消" severity="secondary" @click="mcpDialogVisible = false" size="small" />
      <Button label="确定" @click="submitMcpDialog" :loading="mcpSubmitting" :disabled="!mcpToolsFetched"
        size="small" severity="contrast"/>
    </template>
  </Dialog>

  <!-- 查看资源 Dialog -->
  <Dialog v-model:visible="mcpResourceViewVisible" :header="'资源查看 - ' + (mcpResourceViewData?.name || '')"
    :modal="true" :closable="true" :style="{ width: '800px' }" :draggable="false">
    <div v-if="mcpResourceViewData?.mcp_tools" class="resource-view-content">
      <div class="tools-header">
        <span class="tools-count">工具</span>
      </div>
      <div v-for="tool in parsedViewTools" :key="tool.name" class="mcp-tool-item view-only">
        <div class="tool-item-header">
          <span class="tool-name">{{ tool.name }}</span>
        </div>
        <div class="tool-desc">{{ tool.description || '无描述' }}</div>
        <div v-if="tool.input_schema?.properties" class="tool-params">
          <div v-for="(prop, pName) in tool.input_schema.properties" :key="pName as string"
            class="tool-param-row">
            <span class="param-name">{{ pName as string }}</span>
            <span class="param-type">({{ (prop as any).type || 'any' }})</span>
            <span class="param-desc">{{ (prop as any).description || '' }}</span>
          </div>
        </div>
      </div>
    </div>
    <div v-else class="resource-view-empty">
      <p>暂无资源数据</p>
    </div>
    <template #footer>
      <Button label="关闭" severity="secondary" @click="mcpResourceViewVisible = false" />
    </template>
  </Dialog>
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
import Dialog from 'primevue/dialog'
import Splitter from 'primevue/splitter'
import SplitterPanel from 'primevue/splitterpanel'
import ScrollPanel from 'primevue/scrollpanel'
import Select from 'primevue/select'
import Textarea from 'primevue/textarea'
import InputNumber from 'primevue/inputnumber'
import Message from 'primevue/message'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:6880'
const userId = localStorage.getItem('user_id') || ''

const confirm = useConfirm()
const toast = useToast()

// ========== MCP 类型 ==========
interface McpItem {
  id: number
  user_id: number
  name: string
  type: string
  description: string
  mcp_body: string
  command: string
  args: string
  url: string
  headers: string
  env_vars: string
  timeout: number
  status: boolean
  mcp_tools?: string
  mcp_resources?: string
  mcp_prompt?: string
  created_at: string
  updated_at: string
}

const mcpTypeOptions = [
  { label: 'Stdio', value: 'stdio' },
  { label: 'SSE', value: 'sse' },
  { label: 'Streamable HTTP', value: 'streamablehttp' },
]

function mcpTypeLabel(type: string): string {
  const map: Record<string, string> = { stdio: 'Stdio', sse: 'SSE', streamablehttp: 'Streamable HTTP' }
  return map[type] || type
}

function mcpTypeSeverity(type: string): string {
  const map: Record<string, string> = { stdio: 'info', sse: 'warn', streamablehttp: 'success' }
  return map[type] || 'info'
}

// ========== MCP 状态 ==========
const mcpItems = ref<McpItem[]>([])
const mcpLoading = ref(false)
const mcpSearchQuery = ref('')

const filteredMcpItems = computed(() => {
  const q = mcpSearchQuery.value.trim().toLowerCase()
  if (!q) return mcpItems.value
  return mcpItems.value.filter(item => item.name.toLowerCase().includes(q))
})

// ========== MCP Dialog 状态 ==========
const mcpDialogVisible = ref(false)
const mcpDialogMode = ref<'add' | 'edit'>('add')
const mcpSubmitting = ref(false)
const mcpEditId = ref<number | null>(null)

const mcpForm = ref({
  name: '',
  type: 'stdio',
  description: '',
  command: '',
  args: '',
  url: '',
  headers: '',
  env_vars: '',
  timeout: 60,
  status: true,
})

// ========== MCP 资源获取状态 ==========
const mcpFetchedTools = ref<McpToolInfo[]>([])
const mcpFetchedResources = ref<McpResourceInfo[]>([])
const mcpFetchedPrompts = ref<McpPromptInfo[]>([])
const mcpFetching = ref(false)
const mcpFetchError = ref('')
const mcpToolsFetched = ref(false)

// ========== MCP 资源查看 Dialog ==========
const mcpResourceViewVisible = ref(false)
const mcpResourceViewData = ref<McpItem | null>(null)

const parsedViewTools = computed(() => {
  if (!mcpResourceViewData.value?.mcp_tools) return []
  try {
    return JSON.parse(mcpResourceViewData.value.mcp_tools) as McpToolInfo[]
  } catch { return [] }
})

// ========== MCP CRUD ==========
async function fetchMcpList() {
  mcpLoading.value = true
  try {
    const params = new URLSearchParams({ user_id: String(userId) })
    const res = await fetch(`${API_BASE_URL}/api/v1/mcp/list?${params}`)
    const body = await res.json()
    if (body.code === 0 && body.result) {
      mcpItems.value = (body.result.items || []).map((item: any) => {
        const { command, url } = extractMcpBodyFields(item.type, item.mcp_body)
        return {
          ...item,
          command,
          url,
          status: item.status === 1 || item.status === true,
          mcp_tools: item.mcp_tools || item._mcp_tools || '',
          mcp_resources: item.mcp_resources || item._mcp_resources || '',
          mcp_prompt: item.mcp_prompt || item._mcp_prompt || '',
        }
      })
    } else {
      toast.add({ severity: 'error', summary: '加载失败', detail: body.message || '请求异常', life: 3000 })
    }
  } catch (e: any) {
    toast.add({ severity: 'error', summary: '网络错误', detail: e.message, life: 3000 })
  } finally {
    mcpLoading.value = false
  }
}

function resetMcpForm() {
  mcpForm.value = {
    name: '',
    type: 'stdio',
    description: '',
    command: '',
    args: '',
    url: '',
    headers: '',
    env_vars: '',
    timeout: 30000,
    status: true,
  }
  mcpFetchedTools.value = []
  mcpFetchedResources.value = []
  mcpFetchedPrompts.value = []
  mcpFetchError.value = ''
  mcpToolsFetched.value = false
  mcpEditId.value = null
}

function openAddMcpDialog() {
  resetMcpForm()
  mcpDialogMode.value = 'add'
  mcpDialogVisible.value = true
}

function openEditMcpDialog(item: McpItem) {
  resetMcpForm()
  mcpDialogMode.value = 'edit'
  mcpEditId.value = item.id
  mcpForm.value = {
    name: item.name,
    type: item.type,
    description: item.description,
    command: '',
    args: '',
    url: '',
    headers: '',
    env_vars: '',
    timeout: item.timeout || 30000,
    status: item.status,
  }
  // 从 mcp_body 解析 command/args/url/headers/env_vars
  parseMcpBodyToForm(item.type, item.mcp_body)
  // 加载已有 tools 数据
  if (item.mcp_tools) {
    try {
      const parsed = JSON.parse(item.mcp_tools) as McpToolInfo[]
      mcpFetchedTools.value = parsed.map(t => ({ ...t, _enabled: t._enabled !== false }))
      mcpToolsFetched.value = true
    } catch {
      mcpFetchedTools.value = []
    }
  }
  if (item.mcp_resources) {
    try {
      mcpFetchedResources.value = JSON.parse(item.mcp_resources)
    } catch { mcpFetchedResources.value = [] }
  }
  if (item.mcp_prompt) {
    try {
      mcpFetchedPrompts.value = JSON.parse(item.mcp_prompt)
    } catch { mcpFetchedPrompts.value = [] }
  }
  mcpDialogVisible.value = true
}

function onMcpDialogClose() {
  // 不需要额外操作
}

function buildMcpToolsJson(): string {
  return JSON.stringify(mcpFetchedTools.value.map(t => ({
    name: t.name,
    description: t.description,
    input_schema: t.input_schema,
    _enabled: t._enabled !== false,
  })))
}

/**
 * 将 form 中的 command/args/url/headers/env_vars 封装为 mcp_body JSON
 */
function buildMcpBody(): string {
  const f = mcpForm.value
  if (f.type === 'stdio') {
    const body: Record<string, any> = { command: f.command }
    const args = f.args.split('\n').map(s => s.trim()).filter(Boolean)
    if (args.length) body.args = args
    const env: Record<string, string> = {}
    f.env_vars.split('\n').forEach(line => {
      const idx = line.indexOf('=')
      if (idx > 0) {
        env[line.substring(0, idx).trim()] = line.substring(idx + 1).trim()
      }
    })
    if (Object.keys(env).length) body.env = env
    return JSON.stringify(body)
  }
  // sse / streamable-http
  const body: Record<string, any> = { url: f.url }
  const headers: Record<string, string> = {}
  f.headers.split('\n').forEach(line => {
    const idx = line.indexOf(':')
    if (idx > 0) {
      headers[line.substring(0, idx).trim()] = line.substring(idx + 1).trim()
    }
  })
  if (Object.keys(headers).length) body.headers = headers
  return JSON.stringify(body)
}

/**
 * 从 mcp_body JSON 中提取 command/args/url/headers/env_vars 到 form
 */
function parseMcpBodyToForm(type: string, mcpBody: string) {
  if (!mcpBody) return
  try {
    const parsed = JSON.parse(mcpBody)
    if (type === 'stdio') {
      mcpForm.value.command = parsed.command || ''
      mcpForm.value.args = Array.isArray(parsed.args) ? parsed.args.join('\n') : ''
      if (parsed.env) {
        mcpForm.value.env_vars = Object.entries(parsed.env as Record<string, string>)
          .map(([k, v]) => `${k}=${v}`).join('\n')
      }
    } else {
      mcpForm.value.url = parsed.url || ''
      if (parsed.headers) {
        mcpForm.value.headers = Object.entries(parsed.headers as Record<string, string>)
          .map(([k, v]) => `${k}:${v}`).join('\n')
      }
    }
  } catch { /* ignore parse error */ }
}

/**
 * 从 mcp_body JSON 中提取 command/url 用于列表展示
 */
function extractMcpBodyFields(type: string, mcpBody: string): { command?: string; url?: string } {
  if (!mcpBody) return {}
  try {
    const parsed = JSON.parse(mcpBody)
    if (type === 'stdio') {
      return { command: parsed.command || '' }
    }
    return { url: parsed.url || '' }
  } catch {
    return {}
  }
}

async function submitMcpDialog() {
  const f = mcpForm.value
  if (!f.name) {
    toast.add({ severity: 'warn', summary: '请输入名称', life: 2000 })
    return
  }
  if (f.type === 'stdio' && !f.command) {
    toast.add({ severity: 'warn', summary: '请输入命令', life: 2000 })
    return
  }
  if (f.type !== 'stdio' && !f.url) {
    toast.add({ severity: 'warn', summary: '请输入 URL', life: 2000 })
    return
  }

  mcpSubmitting.value = true
  try {
    const body: any = {
      user_id: userId,
      name: f.name,
      type: f.type,
      description: f.description,
      mcp_body: buildMcpBody(),
      timeout: f.timeout,
      status: f.status ? 1 : 0,
      mcp_tools: buildMcpToolsJson(),
      mcp_resources: JSON.stringify(mcpFetchedResources.value),
      mcp_prompt: JSON.stringify(mcpFetchedPrompts.value),
    }

    let res
    if (mcpDialogMode.value === 'add') {
      res = await fetch(`${API_BASE_URL}/api/v1/mcp/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
    } else {
      body.id = mcpEditId.value
      res = await fetch(`${API_BASE_URL}/api/v1/mcp/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
    }

    const result = await res!.json()
    if (result.code !== 0) {
      toast.add({ severity: 'error', summary: '保存失败', detail: result.detail || result.message, life: 3000 })
      return
    }

    toast.add({ severity: 'success', summary: '保存成功', life: 2000 })
    mcpDialogVisible.value = false
    await fetchMcpList()
  } catch (e: any) {
    toast.add({ severity: 'error', summary: '网络错误', detail: e.message, life: 3000 })
  } finally {
    mcpSubmitting.value = false
  }
}

// ========== MCP 获取资源 ==========
async function handleFetchMcpResources() {
  const f = mcpForm.value
  if (!f.name) {
    toast.add({ severity: 'warn', summary: '请先输入名称', life: 2000 })
    return
  }
  if (f.type === 'stdio' && !f.command) {
    toast.add({ severity: 'warn', summary: '请输入命令', life: 2000 })
    return
  }
  if (f.type !== 'stdio' && !f.url) {
    toast.add({ severity: 'warn', summary: '请输入 URL', life: 2000 })
    return
  }

  mcpFetching.value = true
  mcpFetchError.value = ''
  try {
    const result = await window.electronAPI.fetchMcpResources({
      type: f.type as 'stdio' | 'sse' | 'streamablehttp',
      command: f.command || undefined,
      args: f.args || undefined,
      url: f.url || undefined,
      headers: f.headers || undefined,
      env_vars: f.env_vars || undefined,
      timeout: f.timeout || 30000,
    })

    mcpFetchedTools.value = (result.tools || []).map(t => ({ ...t, _enabled: true }))
    mcpFetchedResources.value = result.resources || []
    mcpFetchedPrompts.value = result.prompts || []
    mcpToolsFetched.value = true

    toast.add({ severity: 'success', summary: '获取成功', detail: `获取到 ${result.tools.length} 个工具`, life: 3000 })
  } catch (e: any) {
    mcpFetchError.value = e.message
    toast.add({ severity: 'error', summary: '获取失败', detail: e.message, life: 5000 })
  } finally {
    mcpFetching.value = false
  }
}

// ========== MCP 查看资源 ==========
function openMcpResourceView(item: McpItem) {
  mcpResourceViewData.value = item
  mcpResourceViewVisible.value = true
}

// ========== MCP 删除 ==========
function confirmDeleteMcp(event: MouseEvent, item: McpItem) {
  confirm.require({
    target: event.currentTarget as HTMLElement,
    message: `确定要删除 MCP「${item.name}」吗？`,
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
        const res = await fetch(`${API_BASE_URL}/api/v1/mcp/delete`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: item.id, user_id: userId }),
        })
        const body = await res.json()
        if (body.code !== 0) {
          toast.add({ severity: 'error', summary: '删除失败', detail: body.detail || body.message, life: 3000 })
          return
        }
        mcpItems.value = mcpItems.value.filter(i => i.id !== item.id)
        toast.add({ severity: 'success', summary: '删除成功', detail: `${item.name} 已删除`, life: 2000 })
      } catch (e: any) {
        toast.add({ severity: 'error', summary: '网络错误', detail: e.message, life: 3000 })
      }
    },
  })
}

onMounted(() => {
  fetchMcpList()
})
</script>

<style scoped>
.capabilities-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 16px 0;
  gap: 16px;
  overflow: auto;
}

/* ========== MCP 布局 ========== */
.mcp-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 16px;
  margin-bottom: 4px;
}

.mcp-toolbar-left {
  display: flex;
  gap: 8px;
}

.mcp-toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.mcp-dataview {
  flex: 1;
  padding: 12px;
}

.mcp-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  padding: 14px;
}

.mcp-card {
  background: #fff;
  border: 1px solid #eee;
  border-radius: 10px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: box-shadow 0.15s ease;
}

.mcp-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.mcp-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.mcp-card-name {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mcp-type-tag {
  flex-shrink: 0;
}

.mcp-card-desc {
  font-size: 12px;
  color: #888;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 36px;
}

.mcp-card-meta {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px 0;
  border-top: 1px solid #f0f0f0;
}

.mcp-card-meta .meta-value.active {
  color: #22c55e;
  font-weight: 500;
}

.mcp-card-meta .meta-value.mono {
  font-family: monospace;
  font-size: 11px;
  max-width: 160px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.mcp-card-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  padding-top: 4px;
  border-top: 1px solid #f0f0f0;
}

/* ========== MCP Dialog Splitter ========== */
.mcp-dialog-splitter {
  min-height: 480px;
}

.mcp-form-scroll {
  padding: 8px;
}

.mcp-tools-scroll {
  padding: 8px;
}

.mcp-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 4px;
}

.field-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-label {
  font-size: 12px;
  font-weight: 500;
  color: #555;
}

.field-label .required {
  color: #e24c4c;
}

.field-input {
  width: 100%;
}

.field-hint {
  font-size: 11px;
  color: #999;
}

.field-switch {
  display: flex;
  align-items: center;
  gap: 8px;
}

.switch-label {
  font-size: 12px;
  color: #666;
}

.mcp-fetch-row {
  margin-top: 8px;
  gap: 8px;
}

.fetch-btn {
  width: 100%;
}

.fetch-error-msg {
  font-size: 12px;
}

/* ========== MCP 工具列表 ========== */
.mcp-tools-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 12px;
  color: #999;
}

.empty-hint {
  font-size: 14px;
  color: #bbb;
  margin: 0;
}

.mcp-tools-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tools-header {
  padding: 6px 0;
  border-bottom: 1px solid #eee;
  margin-bottom: 4px;
}

.tools-count {
  font-size: 13px;
  font-weight: 600;
  color: #555;
}

.tools-section-divider {
  height: 1px;
  background: #e0e0e0;
  margin: 8px 0;
}

.mcp-tool-item {
  background: #f9f9f9;
  border: 1px solid #eee;
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.mcp-tool-item.view-only {
  background: #fff;
  border-color: #e5e5e5;
}

.tool-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.tool-name {
  font-size: 13px;
  font-weight: 600;
  color: #333;
  font-family: monospace;
}

.tool-desc {
  font-size: 12px;
  color: #888;
  line-height: 1.4;
}

.tool-params {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding-left: 12px;
  border-left: 2px solid #e0e0e0;
}

.tool-param-row {
  font-size: 11px;
  line-height: 1.5;
}

.param-name {
  color: #333;
  font-weight: 500;
  font-family: monospace;
}

.param-type {
  color: #888;
  margin-left: 4px;
}

.param-desc {
  color: #999;
  margin-left: 6px;
}

/* ========== MCP 资源查看 ========== */
.resource-view-content {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 500px;
  overflow-y: auto;
}

.resource-view-empty {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 60px 0;
  color: #999;
  font-size: 14px;
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
