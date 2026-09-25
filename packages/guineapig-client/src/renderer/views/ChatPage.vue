<template>
  <div class="chat-layout">
    <!-- 左侧菜单 — 图标模式 -->
    <aside class="sidebar">
      <div class="sidebar-logo" v-tooltip.right="'头像'" @click="openOverlay('avatar')">
        <img src="/logo.svg" alt="logo" style="width: 56px; height: 56px; cursor: pointer" />
      </div>

      <nav class="sidebar-nav">
        <button class="nav-item nav-item-active" v-tooltip.right="'对话'">
          <i class="pi pi-comments nav-icon"></i>
        </button>
        <div class="nav-divider"></div>
        <button v-for="item in overlayItems" :key="item.key" class="nav-item" v-tooltip.right="item.label"
          @click="openOverlay(item.key)">
          <i :class="item.icon" class="nav-icon"></i>
        </button>
      </nav>

      <div class="sidebar-footer">
        <button class="nav-item" v-tooltip.right="'系统设置'" @click="openOverlay('system-settings')">
          <i class="pi pi-cog nav-icon"></i>
        </button>
      </div>
    </aside>

    <!-- 主体内容区 -->
    <div class="chat-body">
      <!-- 左侧：对话历史栏 -->
      <ConversationHistory :conversations="conversations" :selectedId="selectedId" :hasMore="hasMoreConversations"
        :loading="loadingConversations" @select="selectConversation" @load-more="fetchConversations" />

      <!-- 右侧：对话聊天框 -->
      <ChatContent :messages="messages" :selectedTitle="selectedTitle" :isStreaming="isStreaming"
        :selectedModel="selectedModel" :modelOptions="modelOptions" :webSearchEnabled="webSearchEnabled"
        :agentMode="agentMode" :showCommandDialog="showCommandDialog" :pendingCommands="pendingCommands"
        :commandResults="commandResults" :isExecutingCommands="isExecutingCommands"
        :hasHighRiskCommands="hasHighRiskCommands" @send="handleSend" @voice-sent="handleVoiceSent"
        @update:selectedModel="(id: number) => selectedModel = Number(id)" @toggle-web-search="toggleWebSearch"
        @new-session="newSession" @execute-commands="executeCommands" @cancel-commands="cancelCommands"
        @toggle-agent-mode="toggleAgentMode" />
    </div>

    <!-- Agent HITL 干预组件 -->
    <HITLIntervention
      :visible="showHITL"
      :steps="agentSteps"
      :agent-status="agentStatus"
      :current-step-id="currentStepId"
      :agent-summary="agentSummary"
      @confirm-plan="handleAgentConfirmPlan"
      @cancel-plan="handleAgentCancelPlan"
      @skip-step="handleAgentSkipStep"
      @modify-step="handleAgentModifyStep"
      @intervene="handleAgentIntervene"
      @delegate-result="handleAgentDelegateResult"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useToast } from 'primevue/usetoast'
import ConversationHistory from './ConversationHistory.vue'
import ChatContent from './ChatContent.vue'
import HITLIntervention from './HITLIntervention.vue'
import type { AgentStep, AgentStatus, AgentSummary } from './HITLIntervention.vue'

const router = useRouter()
const toast = useToast()

function getDeviceId(): string {
  return localStorage.getItem('device_id') || 'unknown'
}

// ========== 侧边栏 ==========
const overlayItems = [
  { key: 'ai-capabilities', label: 'AI能力', icon: 'pi pi-bolt' },
  { key: 'my-resources', label: '我的资源', icon: 'pi pi-folder' },
  { key: 'memory', label: '记忆', icon: 'pi pi-database' }
]

function openOverlay(page: string) {
  if (window.electronAPI?.openOverlayWindow) {
    window.electronAPI.openOverlayWindow(page)
  }
}

function handleLogout() {
  localStorage.removeItem('api_key')
  router.push({ name: 'Login' })
}

// ========== 网络搜索 ==========
const webSearchEnabled = ref(localStorage.getItem('webSearchEnabled') === 'true')

function toggleWebSearch() {
  webSearchEnabled.value = !webSearchEnabled.value
  localStorage.setItem('webSearchEnabled', String(webSearchEnabled.value))
}

// ========== 消息列表 ==========
interface AttachmentItem {
  id?: number
  type: string
  url: string
  name: string
  size: number
  localPath?: string
}

interface ChatMessage {
  messageId: number
  conversationId: number
  its: number
  userId: number
  deviceId: string
  role: string
  content: string
  attachments?: AttachmentItem[]
}

const messages = ref<ChatMessage[]>([])
const scrollContainer = ref<HTMLElement | null>(null)

// WebSocket
const isStreaming = ref(false)
let ws: WebSocket | null = null
let wsReconnectAttempts = 0
let currentConvId = 0
let currentAssistantId = 0

// ========== Agent 状态 ==========
const agentMode = ref(localStorage.getItem('agentMode') === 'true')
const showHITL = ref(false)
const agentSteps = ref<AgentStep[]>([])
const agentStatus = ref<AgentStatus>('idle')
const currentStepId = ref('')
const agentSummary = ref<AgentSummary | null>(null)
const pendingAgentConvId = ref(0)
const pendingAgentMsgId = ref(0)

function toggleAgentMode() {
  agentMode.value = !agentMode.value
  localStorage.setItem('agentMode', String(agentMode.value))
  if (!agentMode.value) {
    // 关闭 Agent 模式时重置状态
    showHITL.value = false
    agentStatus.value = 'idle'
    agentSteps.value = []
    currentStepId.value = ''
    agentSummary.value = null
  }
}

// Skill Command 状态
interface CommandItem {
  type: string
  command: string
  description: string
  risk: string
}

interface CommandResult {
  stdout: string
  stderr: string
  exitCode: number
}

const pendingCommands = ref<CommandItem[]>([])
const showCommandDialog = ref(false)
const commandResults = ref<{ cmd: CommandItem; result: CommandResult }[]>([])
const isExecutingCommands = ref(false)
let pendingConvId = 0
const hasHighRiskCommands = computed(() =>
  pendingCommands.value.some(c => c.risk === 'high')
)

// 最近一次已执行并回传结果的命令签名（防循环弹窗：LLM 对同一命令反复生成时不再弹框）
let lastExecutedCommandsSig = ''

function commandsSignature(cmds: CommandItem[]): string {
  return JSON.stringify(cmds.map((c) => ({ type: c.type, command: c.command, cwd: c.cwd || '' })))
}

function shouldShowCommandDialog(cmds: CommandItem[]): boolean {
  if (!cmds || cmds.length === 0) return false
  if (commandsSignature(cmds) === lastExecutedCommandsSig) return false
  return true
}

// ========== WebSocket 连接管理 ==========
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:6880'

function getWsAuthToken(): string {
  // 使用服务端签发的 HMAC 会话 Token 作为 WS 握手凭据，不再以裸 user_id 标识身份
  return localStorage.getItem('user_token') || ''
}

function connectWebSocket(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      resolve()
      return
    }

    const wsHost = API_BASE_URL.replace(/^http/, 'ws')
    const url = `${wsHost}/api/v1/chat/ws?token=${encodeURIComponent(getWsAuthToken())}`
    ws = new WebSocket(url)

    ws.onopen = () => {
      wsReconnectAttempts = 0
      resolve()
    }

    ws.onmessage = (event) => {
      try {
        const env = JSON.parse(event.data)
        handleWSMessage(env)
      } catch { /* skip */ }
    }

    ws.onerror = () => {
      // 不输出 err 对象，避免 ErrorEvent.message 包含带 token 的连接 URL
      console.error('WS 连接失败')
      reject(new Error('WebSocket 连接失败'))
    }

    ws.onclose = () => {
      ws = null
      if (wsReconnectAttempts < 5) {
        const delay = Math.min(1000 * Math.pow(2, wsReconnectAttempts), 30000)
        wsReconnectAttempts++
        setTimeout(() => connectWebSocket().catch(() => { }), delay)
      }
    }
  })
}

function sendWSMessage(type: string, payload: Record<string, unknown>, meta?: Record<string, unknown>) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    console.warn('WS 未连接，无法发送消息')
    return
  }
  ws.send(JSON.stringify({
    type,
    from: 'client',
    to: 'backend',
    payload,
    meta: meta || {},
  }))
}

// ========== WS 消息处理器 ==========
function findAssistantMsg(convId: number): ChatMessage | undefined {
  for (let i = messages.value.length - 1; i >= 0; i--) {
    if (messages.value[i].role === 'assistant' && messages.value[i].conversationId === convId) {
      return messages.value[i]
    }
  }
  return undefined
}

function extractContentFromRawSSE(text: string): string | null {
  if (text.startsWith('data: ')) {
    try {
      const parsed = JSON.parse(text.slice(6))
      return parsed.content || null
    } catch { /* ignore */ }
  }
  return null
}

function handleWSMessage(env: any) {
  switch (env.type) {
    case 'chat.send_ack': {
      const convId = env.meta?.conversation_id || env.payload?.conversation_id || 0
      const msgId = env.meta?.message_id || env.payload?.message_id || 0
      const msgs = messages.value
      const lastUserIdx = msgs.length - 1
      const lastMsg = msgs[lastUserIdx]

      if (lastMsg && lastMsg.role === 'user') {
        if (msgId > 0) {
          lastMsg.messageId = msgId
        }
        lastMsg.conversationId = convId
        // 回填 ASR 转写文本与附件（保留本地播放路径）
        if (env.payload?.content) {
          lastMsg.content = env.payload.content
        }
        if (Array.isArray(env.payload?.attachments) && env.payload.attachments.length > 0) {
          lastMsg.attachments = env.payload.attachments.map((att: any) => ({
            id: att.id != null ? Number(att.id) : undefined,
            type: att.type,
            url: att.url,
            name: att.name,
            size: Number(att.size || 0),
            localPath: att.localPath || (lastMsg.attachments || []).find((l: AttachmentItem) => l.url === att.url)?.localPath,
          }))
        }
      }

      currentConvId = convId
      currentAssistantId = 0

      // Agent 模式记录会话/消息 ID
      if (agentMode.value && convId > 0) {
        pendingAgentConvId.value = convId
        pendingAgentMsgId.value = msgId
      }

      if (!selectedId.value && convId > 0) {
        selectedId.value = Number(convId)
        cursor.value = ''
        conversations.value = []
        fetchConversations()
      }

      const placeholder: ChatMessage = {
        messageId: 0,
        conversationId: convId,
        its: Date.now(),
        userId: 0,
        deviceId: '',
        role: 'assistant',
        content: '',
      }
      messages.value.push(placeholder)
      isStreaming.value = true
      break
    }

    case 'chat.content': {
      let text = env.payload?.content
      if (!text && typeof env.payload === 'string') {
        text = extractContentFromRawSSE(env.payload)
      }
      if (!text && typeof env.data === 'string') {
        text = extractContentFromRawSSE(env.data)
      }
      if (!text) break

      const target = findAssistantMsg(currentConvId)
      if (target) {
        target.content += text
      }
      break
    }

    case 'chat.command': {
      const commands = env.payload?.commands || []
      if (shouldShowCommandDialog(commands)) {
        pendingCommands.value = commands
        commandResults.value = []
        showCommandDialog.value = true
        pendingConvId = currentConvId
      }
      break
    }

    case 'chat.done': {
      if (agentMode.value && env.payload?.agent_result) {
        isStreaming.value = false
        if (agentStatus.value === 'executing' || agentStatus.value === 'awaiting_client') {
          agentStatus.value = 'completed'
        } else if (agentStatus.value === 'planning') {
          // reject/fallback/clarify — 没有进入 SSE 流,关闭 HITL
          showHITL.value = false
          agentStatus.value = 'idle'
          currentConvId = 0
        }
        break
      }

      const target = findAssistantMsg(currentConvId)
      if (target) {
        target.messageId = env.meta?.message_id || target.messageId
        if (env.payload?.full_content) {
          target.content = env.payload.full_content
        }
        if (env.payload?.commands && env.payload.commands.length > 0 && !showCommandDialog.value && shouldShowCommandDialog(env.payload.commands)) {
          pendingCommands.value = env.payload.commands
          commandResults.value = []
          showCommandDialog.value = true
          pendingConvId = currentConvId
        }
      }
      isStreaming.value = false
      currentConvId = 0
      break
    }

    case 'chat.error': {
      const errMsg = env.payload?.error || '未知错误'
      console.error('AI 回复出错:', errMsg)
      toast.add({ severity: 'error', summary: 'AI 回复失败', detail: errMsg, life: 5000 })

      if (agentMode.value) {
        agentStatus.value = 'failed'
        showHITL.value = false
        isStreaming.value = false
        break
      }

      const target = findAssistantMsg(currentConvId)
      if (target && target.content === '') {
        const idx = messages.value.indexOf(target)
        if (idx !== -1) messages.value.splice(idx, 1)
      }
      isStreaming.value = false
      currentConvId = 0
      break
    }

    // ════════════════════════════════════════════
    // Agent 事件处理
    // ════════════════════════════════════════════
    case 'chat.agent_rejected': {
      // 任务被拒绝 — 关闭 HITL + toast 通知
      showHITL.value = false
      agentStatus.value = 'idle'
      const reason = env.payload?.reason || '无法执行此任务'
      toast.add({ severity: 'warn', summary: '无法执行', detail: reason, life: 6000 })
      break
    }

    case 'chat.agent_plan': {
      const payload = env.payload || {}
      const steps: AgentStep[] = (payload.steps || []).map((s: any) => ({
        step_id: s.step_id || '',
        capability: s.capability || '',
        action: s.action || '',
        status: 'pending',
        execution_location: s.execution_location || 'server',
        params: s.params || {},
        depends_on: s.depends_on || [],
      }))
      agentSteps.value = steps
      agentStatus.value = 'awaiting_confirmation'
      currentStepId.value = ''
      showHITL.value = true
      break
    }

    case 'chat.agent_step_started': {
      const stepId = env.payload?.step_id || ''
      currentStepId.value = stepId
      updateAgentStepStatus(stepId, 'running')
      if (agentStatus.value !== 'paused' && agentStatus.value !== 'awaiting_client') {
        agentStatus.value = 'executing'
      }
      break
    }

    case 'chat.agent_step_completed': {
      const sId = env.payload?.step_id || ''
      updateAgentStepStatus(sId, 'completed', {
        result_summary: env.payload?.result_summary || '',
        duration_ms: env.payload?.duration_ms || 0,
      })
      if (currentStepId.value === sId) {
        currentStepId.value = ''
      }
      break
    }

    case 'chat.agent_step_failed': {
      const fsId = env.payload?.step_id || ''
      updateAgentStepStatus(fsId, 'failed', {
        error: env.payload?.error || '未知错误',
        duration_ms: env.payload?.duration_ms || 0,
      })
      if (currentStepId.value === fsId) {
        currentStepId.value = ''
      }
      break
    }

    case 'chat.agent_delegate': {
      const delId = env.payload?.step_id || ''
      updateAgentStepStatus(delId, 'awaiting_client', {
        params: env.payload?.params || {},
      })
      agentStatus.value = 'awaiting_client'
      showHITL.value = true
      break
    }

    case 'chat.agent_execution_complete': {
      const payload = env.payload || {}
      agentStatus.value = (payload.status === 'success' || payload.status === 'completed' || payload.status === 'rejected') ? (payload.status === 'rejected' ? 'idle' : 'completed') : 'failed'
      agentSummary.value = {
        total_steps: payload.total_steps || 0,
        completed_steps: payload.completed_steps || 0,
        duration_ms: payload.duration_ms || 0,
        status: payload.status || '',
      }
      isStreaming.value = false
      // 执行完成后关闭 HITL 面板，回到主对话
      showHITL.value = false
      break
    }

    case 'chat.agent_error': {
      const errMsg = env.payload?.error || 'Agent 执行出错'
      toast.add({ severity: 'error', summary: 'Agent 错误', detail: errMsg, life: 5000 })
      agentStatus.value = 'failed'
      isStreaming.value = false
      break
    }

    case 'chat.agent_log': {
      // 日志仅做调试用，可选添加到对应 step
      break
    }

    case 'chat.agent_awaiting_confirmation': {
      const payload = env.payload || {}
      const confSteps: AgentStep[] = (payload.steps || []).map((s: any) => ({
        step_id: s.step_id || '',
        capability: s.capability || '',
        action: s.action || '',
        status: 'pending' as const,
        execution_location: s.execution_location || 'server',
        params: s.params || {},
        depends_on: s.depends_on || [],
      }))
      agentSteps.value = confSteps
      agentStatus.value = 'awaiting_confirmation'
      showHITL.value = true
      break
    }

    // ════════════════════════════════════════════

    case 'pong':
      break
  }
}

// ========== 文本发送（ChatContent emit 处理）==========
async function handleSend(text: string, embeddedFiles: { id: number; name: string }[]) {
  const userId = localStorage.getItem('user_id') || ''
  if (!userId) return

  const attachments: Record<string, unknown>[] = embeddedFiles.map(tag => ({
    id: tag.id,
    type: 'embedded_file',
    url: '',
    name: tag.name,
    size: 0,
  }))

  messages.value.push({
    messageId: 0,
    conversationId: String(selectedId.value || 0),
    its: Date.now(),
    userId: 0,
    deviceId: getDeviceId(),
    role: 'user',
    content: text,
  })

  try {
    await connectWebSocket()
  } catch {
    toast.add({ severity: 'error', summary: '连接失败', detail: '无法连接到服务器', life: 3000 })
    return
  }

  if (agentMode.value) {
    // Agent 模式
    showHITL.value = true
    agentStatus.value = 'planning'
    agentSteps.value = []
    currentStepId.value = ''

    sendWSMessage('chat.agent_send', {
      reqMsgType: 0,
      userId,
      deviceId: getDeviceId(),
      modelId: String(selectedModel.value || 0),
      conversationId: String(selectedId.value || 0),
      startAt: Date.now(),
      content: text,
      attachments,
      webSearchEnabled: webSearchEnabled.value,
      agent_mode: true,
      mcp_servers: [],
      skills: [],
    })
  } else {
    // 普通对话模式
    sendWSMessage('chat.send', {
      reqMsgType: 0,
      userId,
      deviceId: getDeviceId(),
      modelId: String(selectedModel.value || 0),
      conversationId: String(selectedId.value || 0),
      startAt: Date.now(),
      content: text,
      attachments,
      webSearchEnabled: webSearchEnabled.value,
    })
  }
}

// ========== 语音发送 ==========
import type { RecordingInfo } from '@/composables/useRecorder'

function handleVoiceSent(recordingInfo: RecordingInfo, embeddedFiles: { id: number; name: string }[]) {
  const userId = localStorage.getItem('user_id') || ''
  if (!userId) return

  const allAttachments: AttachmentItem[] = [{
    type: 'audio',
    url: recordingInfo.key,
    name: recordingInfo.name,
    size: recordingInfo.size,
    localPath: recordingInfo.localPath || undefined,
  }]
  for (const tag of embeddedFiles) {
    allAttachments.push({
      id: tag.id,
      type: 'embedded_file',
      url: '',
      name: tag.name,
      size: 0,
    })
  }

  connectWebSocket().then(() => {
    sendWSMessage('chat.send', {
      reqMsgType: 1,
      userId,
      deviceId: getDeviceId(),
      modelId: String(selectedModel.value || 0),
      conversationId: String(selectedId.value || 0),
      startAt: Date.now(),
      content: '',
      attachments: allAttachments,
      webSearchEnabled: webSearchEnabled.value,
    })

    messages.value.push({
      messageId: 0,
      conversationId: String(selectedId.value || 0),
      its: Date.now(),
      userId: 0,
      deviceId: getDeviceId(),
      role: 'user',
      content: '',
      attachments: allAttachments,
    })
  }).catch(() => {
    toast.add({ severity: 'error', summary: '连接失败', detail: '无法发送消息', life: 3000 })
  })
}

// ========== 对话历史 ==========
interface ChatHistoryItem {
  id: number
  title: string
  modelId: number
  messageCount: number
  status: string
  lastMessagePreview: string
  startAt: string
  endAt: string | null
  createdAt: string
  updatedAt: string
}

const conversations = ref<ChatHistoryItem[]>([])
const cursor = ref<string | null>(null)
const hasMoreConversations = ref(false)
const loadingConversations = ref(false)
const loadingMessages = ref(false)

async function fetchConversations() {
  const userId = localStorage.getItem('user_id')
  if (!userId) return
  if (loadingConversations.value) return

  loadingConversations.value = true
  try {
    let url = `${API_BASE_URL}/api/v1/chat/conversations?user_id=${userId}&limit=20`
    if (cursor.value) url += `&cursor=${encodeURIComponent(cursor.value)}`
    const res = await fetch(url)
    const data = await res.json()
    if (data.code === 0 && data.result) {
      const items = data.result.items || []
      const existingIds = new Set(conversations.value.map(c => c.id))
      const newItems = items.filter((item: ChatHistoryItem) => !existingIds.has(item.id))
      conversations.value.push(...newItems)
      hasMoreConversations.value = data.result.hasMore
      cursor.value = data.result.nextCursor || null
    }
  } catch (err) {
    console.error('获取会话列表失败:', err)
  } finally {
    loadingConversations.value = false
  }
}

async function fetchMessages(conversationId: number) {
  if (loadingMessages.value) return
  loadingMessages.value = true
  try {
    const userId = localStorage.getItem('user_id')
    const res = await fetch(`${API_BASE_URL}/api/v1/chat/messages?conversation_id=${conversationId}&limit=100&user_id=${userId || ''}`)
    const data = await res.json()
    if (data.code === 0 && data.result) {
      messages.value = (data.result.items || []).map((item: any) => {
        let attachments: AttachmentItem[] = []
        if (item.attachments) {
          try {
            attachments = typeof item.attachments === 'string'
              ? JSON.parse(item.attachments)
              : item.attachments
          } catch { /* ignore */ }
        }
        return {
          messageId: item.id,
          conversationId: item.conversationId,
          its: new Date(item.createdAt).getTime(),
          userId: 0,
          deviceId: '',
          role: item.role,
          content: item.content,
          attachments,
        } as ChatMessage
      }).sort((a, b) => a.messageId - b.messageId)
    }
  } catch (err) {
    console.error('获取消息列表失败:', err)
  } finally {
    loadingMessages.value = false
  }
}

const selectedId = ref<number | null>(null)
const selectedTitle = ref('新对话')

function selectConversation(item: ChatHistoryItem) {
  selectedId.value = Number(item.id)
  selectedTitle.value = item.title
  fetchMessages(item.id)
}

function newSession() {
  selectedId.value = null
  selectedTitle.value = '新对话'
  messages.value = []
}

// ========== 模型选择 ==========
interface ModelOption {
  id: number
  model_name: string
}

const modelOptions = ref<ModelOption[]>([])
const selectedModel = ref<number | null>(null)

async function fetchModelOptions() {
  const userId = localStorage.getItem('user_id')
  if (!userId) return
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/aimodel/options-by-type?user_id=${userId}&model_type=LLM`)
    const data = await res.json()
    if (data.code === 0) {
      modelOptions.value = data.result || []
      if (modelOptions.value.length > 0) {
        selectedModel.value = Number(modelOptions.value[0].id)
      }
    }
  } catch (err) {
    console.error('获取模型列表失败:', err)
  }
}

// ========== Command 执行 ==========
async function executeCommands() {
  isExecutingCommands.value = true
  commandResults.value = []

  for (let i = 0; i < pendingCommands.value.length; i++) {
    const cmd = pendingCommands.value[i]
    try {
      if (window.electronAPI?.executeCommand) {
        const result = await window.electronAPI.executeCommand({ ...cmd })
        commandResults.value[i] = { cmd, result }
      }
    } catch (e: any) {
      commandResults.value[i] = {
        cmd,
        result: { stdout: '', stderr: e.message || String(e), exitCode: -1 }
      }
    }
  }

  isExecutingCommands.value = false
  showCommandDialog.value = false
  // 记录已执行命令签名，后端若把同一命令结果回传触发 LLM 再次生成相同命令时不再弹窗
  lastExecutedCommandsSig = commandsSignature(pendingCommands.value)

  const results = commandResults.value.map((cr) => ({
    index: commandResults.value.indexOf(cr),
    stdout: cr.result.stdout || '',
    stderr: cr.result.stderr || '',
    exitCode: cr.result.exitCode,
  }))

  if (ws && ws.readyState === WebSocket.OPEN && pendingConvId > 0) {
    sendWSMessage('chat.command_result', { results }, {
      conversation_id: pendingConvId,
    })
  } else if (pendingConvId > 0) {
    console.warn('WS 未连接，fallback 到 HTTP POST /chat/command-result')
    try {
      const userId = localStorage.getItem('user_id') || '0'
      await fetch(`${API_BASE_URL}/api/v1/chat/command-result`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conversation_id: pendingConvId,
          results,
          meta: { user_id: userId },
        }),
      })
    } catch (e) {
      console.error('HTTP command-result fallback 失败:', e)
    }
  } else {
    console.warn('WS 未连接且无有效会话ID，command result 无法回传')
  }
}

function cancelCommands() {
  showCommandDialog.value = false
  pendingCommands.value = []
  commandResults.value = []
}

// ========== Agent 事件处理 ==========

function updateAgentStepStatus(stepId: string, status: AgentStep['status'], extra?: Partial<AgentStep>) {
  const idx = agentSteps.value.findIndex(s => s.step_id === stepId)
  if (idx !== -1) {
    agentSteps.value[idx] = { ...agentSteps.value[idx], ...extra, status }
  }
}

function handleAgentConfirmPlan() {
  if (pendingAgentConvId.value > 0 && pendingAgentMsgId.value > 0) {
    sendWSMessage('chat.agent_confirm', {}, {
      conversation_id: pendingAgentConvId.value,
      message_id: pendingAgentMsgId.value,
    })
  }
  agentStatus.value = 'executing'
}

function handleAgentCancelPlan() {
  showHITL.value = false
  agentStatus.value = 'intervened'
  if (pendingAgentConvId.value > 0) {
    sendWSMessage('chat.agent_cancel', {}, {
      conversation_id: pendingAgentConvId.value,
    })
  }
  isStreaming.value = false
}

function handleAgentSkipStep(stepId: string) {
  updateAgentStepStatus(stepId, 'skipped')
  sendWSMessage('chat.agent_skip_step', { step_id: stepId }, {
    conversation_id: pendingAgentConvId.value,
  })
}

function handleAgentModifyStep(stepId: string, params: Record<string, any>) {
  sendWSMessage('chat.agent_modify_step', {
    step_id: stepId,
    params,
  }, {
    conversation_id: pendingAgentConvId.value,
  })
}

function handleAgentIntervene(action: string) {
  if (action === 'cancel-all') {
    showHITL.value = false
    agentStatus.value = 'intervened'
    isStreaming.value = false
  } else if (action === 'pause') {
    agentStatus.value = 'paused'
  } else if (action === 'resume') {
    agentStatus.value = 'executing'
  }
  sendWSMessage('chat.agent_intervene', { action }, {
    conversation_id: pendingAgentConvId.value,
  })
}

function handleAgentDelegateResult(stepId: string, capability: string, result: Record<string, any> | null, error: string) {
  updateAgentStepStatus(stepId, 'completed', {
    result_summary: result ? JSON.stringify(result).slice(0, 200) : '',
  })
  sendWSMessage('chat.agent_delegate_result', {
    step_id: stepId,
    capability,
    result,
    error,
  }, {
    conversation_id: pendingAgentConvId.value,
  })
}

// ========== 初始化 ==========
onMounted(() => {
  fetchModelOptions()
  fetchConversations()
})

onUnmounted(() => {
  if (ws) {
    ws.close()
    ws = null
  }
})
</script>

<style scoped>
.chat-layout {
  display: flex;
  height: 100vh;
  background: #f5f5f5;
  overflow: hidden;
}

.chat-body {
  display: flex;
  gap: 12px;
  padding: 12px;
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.sidebar {
  width: 72px;
  background: #fff;
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  overflow: hidden;
}

.sidebar-logo {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 0;
  gap: 2px;
  flex: 1;
  width: 100%;
  overflow: hidden;
}

.nav-divider {
  width: 32px;
  height: 1px;
  background: #eee;
  margin: 6px 0;
}

.sidebar-footer {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 0;
  width: 100%;
}

.nav-item {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  border: none;
  background: transparent;
  border-radius: 10px;
  cursor: pointer;
  color: #999;
  transition: all 0.15s ease;
  padding: 0;
}

.nav-item:hover {
  color: #555;
  background: #f5f5f5;
}

.nav-item-active {
  color: #fff !important;
  background: #333 !important;
}

.nav-item-active:hover {
  color: #fff !important;
  background: #333 !important;
}

.nav-item-logout:hover {
  color: #e74c3c !important;
}

.nav-icon {
  font-size: 1.25rem;
}
</style>
