<!--
  HITLIntervention.vue — Human-in-the-Loop 人工干预组件

  @用途: AI Agent 执行过程中的步骤展示与人工干预
  @设计: 独立组件，Props/Events 驱动，后续可转换为 A2UI 动态表单

  TODO-A2UI: 这是一个自包含的 A2UI 候选组件。
  转换要点:
  1. steps 数据模型 → JSON Schema definition
  2. 按钮操作 (confirm/skip/modify/cancel) → A2UI Action schema
  3. 状态图标 + 颜色映射 → A2UI Visual theme config
  4. 整体布局为: header + progress bar + step list + action bar

  @props:
  - visible: boolean — 是否显示
  - steps: AgentStep[] — 步骤列表
  - agentStatus: 'idle' | 'planning' | 'executing' | 'awaiting_client' | 'completed' | 'failed' | 'intervened'
  - currentStepId: string — 当前执行步骤 ID
  - agentSummary: { total_steps, completed_steps, duration_ms, status } | null

  @emits:
  - confirm-plan: 用户确认执行计划
  - cancel-plan: 用户取消计划
  - close: 关闭弹窗（仅隐藏面板，不终止服务端任务）
  - terminate: 终止请求（关闭面板并取消服务端任务）
  - skip-step(stepId): 跳过指定步骤
  - modify-step(stepId, params): 修改步骤参数
  - intervene(action): 总体干预动作 (pause / resume / cancel-all)
  - delegate-result(stepId, capability, result, error): 客户端执行结果回传
-->

<template>
  <div v-if="visible" class="hitl-overlay">
    <div class="hitl-panel">
      <!-- ══════ Header ══════ -->
      <div class="hitl-header">
        <div class="hitl-title-row">
          <i class="pi pi-shield hitl-icon"></i>
          <span class="hitl-title">Agent 任务执行</span>
          <span :class="['hitl-status-badge', `hitl-status--${agentStatus}`]">
            {{ statusLabel }}
          </span>
          <Button icon="pi pi-times" class="p-button-rounded p-button-text p-button-sm hitl-close-btn"
            aria-label="关闭弹窗" @click="$emit('close')" />
        </div>
        <div v-if="agentSummary" class="hitl-summary-row">
          <span class="hitl-stat">
            步骤 {{ agentSummary.completed_steps || 0 }} / {{ agentSummary.total_steps || 0 }}
          </span>
          <span v-if="agentSummary.duration_ms" class="hitl-stat">
            耗时 {{ formatDuration(agentSummary.duration_ms) }}
          </span>
          <span v-if="agentSummary.status === 'completed'" class="hitl-stat hitl-stat--success">
            已完成
          </span>
        </div>
      </div>

      <!-- ══════ Progress Bar ══════ -->
      <div class="hitl-progress-bar">
        <div class="hitl-progress-fill" :style="{ width: progressPercent + '%' }" :class="progressClass"></div>
      </div>

      <!-- ══════ Step List ══════ -->
      <div class="hitl-step-list">
        <div v-for="step in steps" :key="step.step_id" :class="[
          'hitl-step-item',
          `hitl-step--${step.status}`,
          { 'hitl-step--active': step.step_id === currentStepId }
        ]">
          <!-- 状态图标 -->
          <div class="hitl-step-status-icon">
            <i v-if="step.status === 'running' || step.step_id === currentStepId" class="pi pi-spin pi-spinner"></i>
            <i v-else-if="step.status === 'completed'" class="pi pi-check-circle hitl-color--success"></i>
            <i v-else-if="step.status === 'failed'" class="pi pi-times-circle hitl-color--danger"></i>
            <i v-else-if="step.status === 'skipped'" class="pi pi-forward hitl-color--warning"></i>
            <i v-else-if="step.status === 'awaiting_client'" class="pi pi-send hitl-color--info"></i>
            <i v-else class="pi pi-circle-off"></i>
          </div>

          <!-- 步骤内容 -->
          <div class="hitl-step-body">
            <div class="hitl-step-header-row">
              <span class="hitl-step-id">{{ step.step_id }}</span>
              <span class="hitl-step-capability">{{ step.capability }}</span>
              <span class="hitl-step-location" :class="`hitl-loc--${step.execution_location || 'server'}`">
                {{ step.execution_location === 'client' ? '🖥客户端' : '☁️服务端' }}
              </span>
              <span v-if="step.duration_ms" class="hitl-step-duration">
                {{ formatDuration(step.duration_ms) }}
              </span>
            </div>
            <div class="hitl-step-action">{{ step.action }}</div>
            <div v-if="step.error" class="hitl-step-error">{{ step.error }}</div>
            <div v-if="step.result_summary" class="hitl-step-result">
              <span class="hitl-result-label">结果:</span> {{ truncateText(step.result_summary, 150) }}
            </div>

            <!-- 客户端步骤的操作按钮 -->
            <div v-if="step.status === 'awaiting_client'" class="hitl-step-client-actions">
              <Button label="执行" icon="pi pi-play" size="small" class="p-button-sm p-button-success"
                @click="handleDelegate(step)" />
              <Button label="跳过" icon="pi pi-forward" size="small" class="p-button-sm p-button-warning"
                @click="$emit('skip-step', step.step_id)" />
              <Button v-if="step.params && Object.keys(step.params).length" label="修改参数" icon="pi pi-pencil"
                size="small" class="p-button-sm p-button-outlined" @click="showModifyDialog(step)" />
            </div>
          </div>
        </div>
      </div>

      <!-- ══════ Empty State ══════ -->
      <div v-if="!steps.length && agentStatus !== 'completed'" class="hitl-empty-state">
        <i class="pi pi-spin pi-spinner" style="font-size: 2rem; color: #999;"></i>
        <p>{{ agentStatus === 'planning' ? '正在分析意图并生成执行计划...' : '等待任务开始...' }}</p>
      </div>

      <!-- ══════ Intervention Action Bar ══════ -->
      <div class="hitl-action-bar">
        <!-- 左侧: 计划确认按钮 -->
        <div class="hitl-action-left">
          <Button v-if="agentStatus === 'awaiting_confirmation' || agentStatus === 'planning'" label="确认执行"
            icon="pi pi-check" severity="contrast" raised :disabled="!steps.length" @click="$emit('confirm-plan')" />
          <Button v-if="agentStatus === 'awaiting_confirmation' || agentStatus === 'planning'" label="取消任务"
            icon="pi pi-times" severity="secondary" outlined raised @click="$emit('cancel-plan')" />
          <Button v-if="isActiveState" label="终止请求" icon="pi pi-stop-circle" severity="danger"
            outlined raised @click="$emit('terminate')" />
        </div>
        <!-- 右侧: 执行中控制 -->
        <div class="hitl-action-right">
          <Button v-if="agentStatus === 'executing'" label="暂停" icon="pi pi-pause"
            severity="warning" outlined @click="$emit('intervene', 'pause')" />
          <Button v-if="agentStatus === 'paused'" label="继续" icon="pi pi-play"
            severity="success" outlined @click="$emit('intervene', 'resume')" />
          <Button v-if="isExecutingOrPaused" label="中断全部" icon="pi pi-stop" severity="danger"
            outlined @click="$emit('intervene', 'cancel-all')" />
        </div>
      </div>
    </div>

    <!-- ══════ 参数修改对话框 (A2UI 候选) ══════ -->
    <!-- TODO-A2UI: 此对话框应转换为 A2UI DynamicForm 渲染 -->
    <Dialog v-model:visible="modifyDialogVisible" header="修改步骤参数" :modal="true" :style="{ width: '450px' }">
      <div v-if="modifyTarget" class="hitl-modify-form">
        <div class="hitl-modify-field">
          <label>步骤 ID: {{ modifyTarget.step_id }}</label>
        </div>
        <div class="hitl-modify-field">
          <label>能力: {{ modifyTarget.capability }}</label>
        </div>
        <div class="hitl-modify-field">
          <label>操作: {{ modifyTarget.action }}</label>
        </div>
        <div v-for="(value, key) in modifyTarget.params" :key="key" class="hitl-modify-field">
          <label :for="'param-' + key">{{ key }}</label>
          <InputText :id="'param-' + key" :model-value="String(value)" class="p-inputtext-sm w-full"
            @update:model-value="(v: string) => updateModifyParam(key, v)" />
        </div>
      </div>
      <template #footer>
        <Button label="取消" severity="secondary" outlined @click="modifyDialogVisible = false" />
        <Button label="确认修改" severity="contrast" @click="confirmModify()" />
      </template>
    </Dialog>

    <!-- ══════ MCP 工具执行确认对话框 ══════ -->
    <Dialog v-model:visible="mcpConfirmVisible" header="确认执行 MCP 工具" :modal="true" :style="{ width: '520px' }">
      <div v-if="mcpConfirmStep" class="hitl-modify-form">
        <div class="hitl-modify-field">
          <label>能力: {{ mcpConfirmStep.capability }}</label>
        </div>
        <div class="hitl-modify-field">
          <label>Server: {{ mcpConfirmStep.params?.server_name || '-' }}</label>
        </div>
        <div class="hitl-modify-field">
          <label>工具: {{ mcpConfirmStep.params?.tool }}</label>
        </div>
        <div class="hitl-modify-field">
          <label>参数:</label>
          <pre class="hitl-mcp-args">{{ formatJson(mcpConfirmStep.params?.arguments) }}</pre>
        </div>
        <div v-if="mcpConfirmStep.action" class="hitl-modify-field">
          <label>操作说明: {{ mcpConfirmStep.action }}</label>
        </div>
      </div>
      <template #footer>
        <Button label="取消" severity="secondary" outlined @click="cancelMcpConfirm()" />
        <Button label="确认执行" severity="contrast" @click="confirmMcpExecute()" />
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'

// ═══════════════════════════════════════════
// 类型定义 — 后续可转为 A2UI JSON Schema
// ═══════════════════════════════════════════

/**
 * TODO-A2UI: 此 interface 可直接映射为 JSON Schema:
 * {
 *   "type": "object",
 *   "properties": {
 *     "step_id": { "type": "string" },
 *     "capability": { "type": "string" },
 *     "action": { "type": "string" },
 *     "status": { "type": "string", "enum": ["pending","running","completed","failed","skipped","awaiting_client"] },
 *     "execution_location": { "type": "string", "enum": ["server","client"] },
 *     "duration_ms": { "type": "integer" },
 *     "result_summary": { "type": "string" },
 *     "error": { "type": "string" },
 *     "params": { "type": "object" },
 *     "requires_confirmation": { "type": "boolean" }
 *   }
 * }
 */
export interface AgentStep {
  step_id: string
  capability: string
  action: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'skipped' | 'awaiting_client'
  execution_location?: 'server' | 'client'
  duration_ms?: number
  result_summary?: string
  error?: string
  params?: Record<string, any>
  depends_on?: string[]
  output_key?: string
  requires_confirmation?: boolean
  max_retries?: number
  timeout_seconds?: number
}

export type AgentStatus = 'idle' | 'planning' | 'awaiting_confirmation' | 'executing' | 'paused' | 'awaiting_client' | 'completed' | 'failed' | 'intervened'

export interface AgentSummary {
  total_steps: number
  completed_steps: number
  duration_ms: number
  status: string
}

// ═══════════════════════════════════════════
// Props
// ═══════════════════════════════════════════

const props = withDefaults(defineProps<{
  visible: boolean
  steps?: AgentStep[]
  agentStatus?: AgentStatus
  currentStepId?: string
  agentSummary?: AgentSummary | null
}>(), {
  steps: () => [],
  agentStatus: 'idle',
  currentStepId: '',
  agentSummary: null,
})

// ═══════════════════════════════════════════
// Emits
// ═══════════════════════════════════════════

const emit = defineEmits<{
  'confirm-plan': []
  'cancel-plan': []
  'close': []
  'terminate': []
  'skip-step': [stepId: string]
  'modify-step': [stepId: string, params: Record<string, any>]
  'intervene': [action: string]
  'delegate-result': [stepId: string, capability: string, result: Record<string, any> | null, error: string]
}>()

// ═══════════════════════════════════════════
// Computed
// ═══════════════════════════════════════════

const isExecutingOrPaused = computed(() =>
  props.agentStatus === 'executing' || props.agentStatus === 'paused'
)

/** 任务仍在进行中（可终止）的状态 */
const isActiveState = computed(() =>
  ['planning', 'awaiting_confirmation', 'executing', 'paused', 'awaiting_client'].includes(
    props.agentStatus
  )
)

const statusLabel = computed(() => {
  const labels: Record<string, string> = {
    idle: '待机',
    planning: '规划中',
    awaiting_confirmation: '待确认',
    executing: '执行中',
    paused: '已暂停',
    awaiting_client: '等待客户端',
    completed: '已完成',
    failed: '已失败',
    intervened: '已干预',
  }
  return labels[props.agentStatus] || props.agentStatus
})

const progressPercent = computed(() => {
  const total = props.agentSummary?.total_steps || props.steps.length || 1
  const completed = props.steps.filter(s =>
    s.status === 'completed' || s.status === 'skipped'
  ).length
  return Math.round((completed / total) * 100)
})

const progressClass = computed(() => {
  if (props.agentStatus === 'failed' || props.agentStatus === 'intervened') return 'hitl-progress--failed'
  if (props.agentStatus === 'completed') return 'hitl-progress--completed'
  return ''
})

// ═══════════════════════════════════════════
// 参数修改对话框
// ═══════════════════════════════════════════

const modifyDialogVisible = ref(false)
const modifyTarget = ref<AgentStep | null>(null)
const modifyParams = ref<Record<string, any>>({})

function showModifyDialog(step: AgentStep) {
  modifyTarget.value = step
  modifyParams.value = { ...(step.params || {}) }
  modifyDialogVisible.value = true
}

function updateModifyParam(key: string, value: string) {
  modifyParams.value[key] = value
}

function confirmModify() {
  if (modifyTarget.value) {
    emit('modify-step', modifyTarget.value.step_id, modifyParams.value)
  }
  modifyDialogVisible.value = false
}

// ═══════════════════════════════════════════
// 客户端执行委托
// ═══════════════════════════════════════════

const mcpConfirmVisible = ref(false)
const mcpConfirmStep = ref<AgentStep | null>(null)

async function handleDelegate(step: AgentStep) {
  try {
    // MCP 工具调用：先弹出确认对话框，用户确认后才真正执行
    if (step.capability.startsWith('mcp_') && step.params?.tool) {
      mcpConfirmStep.value = step
      mcpConfirmVisible.value = true
      return
    }
    await executeDelegate(step)
  } catch (e: any) {
    const errMsg = e?.message || String(e)
    emit('delegate-result', step.step_id, step.capability, { status: 'error', error: errMsg }, errMsg)
  }
}

/** 用户确认执行 MCP 工具 */
async function confirmMcpExecute() {
  const step = mcpConfirmStep.value
  mcpConfirmVisible.value = false
  mcpConfirmStep.value = null
  if (!step) return
  try {
    await executeDelegate(step)
  } catch (e: any) {
    const errMsg = e?.message || String(e)
    emit('delegate-result', step.step_id, step.capability, { status: 'error', error: errMsg }, errMsg)
  }
}

/** 用户取消执行 MCP 工具 */
function cancelMcpConfirm() {
  const step = mcpConfirmStep.value
  mcpConfirmVisible.value = false
  mcpConfirmStep.value = null
  if (!step) return
  const errMsg = '用户取消执行 MCP 工具'
  emit('delegate-result', step.step_id, step.capability, { status: 'error', error: errMsg }, errMsg)
}

/** 实际执行委托步骤（cli / skill / mcp / 其他） */
async function executeDelegate(step: AgentStep) {
  let result: Record<string, any> = {}
  if (step.capability === 'cli') {
    const command = step.params?.command || step.action
    if (window.electronAPI?.executeCommand) {
      const execResult = await window.electronAPI.executeCommand({ command, description: step.action })
      result = execResult
    } else {
      result = { stdout: 'Electron IPC 不可用', stderr: '', exitCode: -1 }
    }
  } else if (step.capability === 'skill') {
    result = { note: 'Skill 执行需要 Skill Service 支持', status: 'pending' }
  } else if (step.capability.startsWith('mcp_') && step.params?.tool) {
    // MCP 工具调用：使用 aiagent 注入的连接参数（含 stdio command/args/env）执行
    // 注意：step.params 来自 Vue reactive 数组，Proxy 无法被 Electron IPC 结构化克隆，
    // 必须先深拷贝为纯 JSON 再传给主进程，否则会抛 "An object could not be cloned."
    const p = toPlain(step.params)
    console.warn('[HITL] 下发 MCP 工具调用参数:', JSON.stringify({
      capability: step.capability,
      server_name: p.server_name,
      transport_type: p.transport_type,
      command: p.command,
      args: p.args,
      env: p.env,
      mcp_url: p.mcp_url,
      headers: p.headers,
      tool: p.tool,
      arguments: p.arguments,
      timeout: p.timeout,
    }))
    const callResult = await window.electronAPI.callMcpTool({
      type: p.transport_type || 'stdio',
      server_name: p.server_name,
      command: p.command,
      args: p.args,
      env: p.env,
      url: p.mcp_url,
      headers: p.headers,
      tool: p.tool,
      arguments: p.arguments || {},
      timeout: p.timeout || 30000,
    })
    result = {
      status: callResult.isError ? 'error' : 'completed',
      isError: callResult.isError,
      result: callResult.result,
      content: callResult.content,
      note: `MCP 工具 '${step.capability}' 执行完成`,
    }
  } else {
    // 其他客户端能力（无 MCP 工具参数）
    result = { note: `客户端能力 '${step.capability}' 执行`, status: 'delegated' }
  }

  const error = result.error || (result.exitCode !== undefined && result.exitCode !== 0 ? `退出码: ${result.exitCode}` : '')
  emit('delegate-result', step.step_id, step.capability, result, error || '')
}

// ═══════════════════════════════════════════
// 工具函数
// ═══════════════════════════════════════════

function formatJson(value: any): string {
  if (value === undefined || value === null) return '-'
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

/** 深拷贝为纯 JSON 对象（剥离 Vue reactive Proxy，否则 IPC 结构化克隆会抛 DataCloneError） */
function toPlain<T>(value: T): T {
  if (value === null || typeof value !== 'object') return value
  return JSON.parse(JSON.stringify(value))
}

function formatDuration(ms: number): string {
  if (!ms) return ''
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  const m = Math.floor(ms / 60000)
  const s = Math.round((ms % 60000) / 1000)
  return `${m}m${s}s`
}

function truncateText(text: string, maxLen: number): string {
  if (!text) return ''
  return text.length <= maxLen ? text : text.slice(0, maxLen) + '...'
}
</script>

<style scoped>
.hitl-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.hitl-panel {
  background: #fff;
  border-radius: 12px;
  width: 680px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.18);
  overflow: hidden;
}

.hitl-header {
  padding: 16px 20px 12px;
  border-bottom: 1px solid #eee;
}

.hitl-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.hitl-icon {
  font-size: 1.2rem;
  color: #6366f1;
}

.hitl-title {
  font-weight: 600;
  font-size: 1rem;
  color: #333;
  flex: 1;
}

.hitl-status-badge {
  font-size: 0.75rem;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 500;
}

.hitl-status--planning {
  background: #e0e7ff;
  color: #4338ca;
}

.hitl-status--awaiting_confirmation {
  background: #fef9c3;
  color: #a16207;
}

.hitl-status--executing {
  background: #dbeafe;
  color: #1d4ed8;
}

.hitl-status--paused {
  background: #f3e8ff;
  color: #7c3aed;
}

.hitl-status--awaiting_client {
  background: #fff7ed;
  color: #c2410c;
}

.hitl-status--completed {
  background: #dcfce7;
  color: #16a34a;
}

.hitl-status--failed {
  background: #fee2e2;
  color: #dc2626;
}

.hitl-summary-row {
  display: flex;
  gap: 16px;
  font-size: 0.8rem;
  color: #666;
}

.hitl-stat--success {
  color: #16a34a;
  font-weight: 500;
}

.hitl-progress-bar {
  height: 4px;
  background: #e5e7eb;
  margin: 0 20px;
  border-radius: 2px;
}

.hitl-progress-fill {
  height: 100%;
  background: #6366f1;
  border-radius: 2px;
  transition: width 0.3s ease;
}

.hitl-progress--completed {
  background: #22c55e;
}

.hitl-progress--failed {
  background: #ef4444;
}

.hitl-step-list {
  flex: 1;
  overflow-y: auto;
  padding: 12px 20px;
}

.hitl-step-item {
  display: flex;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  margin-bottom: 4px;
  transition: background 0.15s;
}

.hitl-step-item:hover {
  background: #f9fafb;
}

.hitl-step--active {
  background: #eef2ff;
}

.hitl-step--completed {
  opacity: 0.75;
}

.hitl-step--failed {
  background: #fef2f2;
}

.hitl-step--awaiting_client {
  background: #fff7ed;
  border: 1px solid #fed7aa;
}

.hitl-step-status-icon {
  width: 24px;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding-top: 3px;
  font-size: 1rem;
}

.hitl-step-body {
  flex: 1;
  min-width: 0;
}

.hitl-step-header-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 2px;
}

.hitl-step-id {
  font-weight: 600;
  font-size: 0.8rem;
  color: #555;
  min-width: 28px;
}

.hitl-step-capability {
  font-size: 0.78rem;
  color: #6366f1;
  background: #eef2ff;
  padding: 0 6px;
  border-radius: 4px;
}

.hitl-step-location {
  font-size: 0.7rem;
  color: #888;
}

.hitl-step-duration {
  font-size: 0.7rem;
  color: #999;
  margin-left: auto;
}

.hitl-step-action {
  font-size: 0.85rem;
  color: #444;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.hitl-step-error {
  font-size: 0.78rem;
  color: #dc2626;
  margin-top: 2px;
}

.hitl-step-result {
  font-size: 0.78rem;
  color: #16a34a;
  margin-top: 2px;
}

.hitl-result-label {
  font-weight: 500;
  color: #555;
}

.hitl-step-client-actions {
  display: flex;
  gap: 6px;
  margin-top: 6px;
}

.hitl-empty-state {
  padding: 40px 20px;
  text-align: center;
  color: #999;
  font-size: 0.9rem;
}

.hitl-action-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  border-top: 1px solid #eee;
  gap: 8px;
}

.hitl-action-left,
.hitl-action-right {
  display: flex;
  gap: 8px;
}

.hitl-modify-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.hitl-modify-field label {
  font-size: 0.8rem;
  color: #666;
  display: block;
  margin-bottom: 2px;
}

.hitl-mcp-args {
  background: #f5f5f5;
  border: 1px solid #e5e5e5;
  border-radius: 6px;
  padding: 8px;
  font-size: 0.8rem;
  max-height: 220px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.color--success {
  color: #22c55e;
}

.color--danger {
  color: #ef4444;
}

.color--warning {
  color: #f59e0b;
}

.color--info {
  color: #3b82f6;
}
</style>
