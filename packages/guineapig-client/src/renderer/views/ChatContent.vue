<template>
  <main class="chat-main">
    <!-- 当前会话标题 -->
    <div v-if="selectedTitle" class="chat-header">
      <i class="pi pi-comment" style="font-size: 14px; color: #999; margin-right: 8px"></i>
      <span class="chat-header-title">{{ selectedTitle }}</span>
    </div>

    <!-- 消息展示区 -->
    <div class="chat-messages" ref="scrollContainer">
      <div v-if="messages.length === 0" class="welcome-message">
        <i class="pi pi-comments" style="font-size: 48px; color: #d0d5dd; margin-bottom: 16px"></i>
        <p class="placeholder-text">有什么可以帮助你的？</p>
      </div>
      <div v-else class="message-list">
        <div v-for="msg in messages" :key="msg.messageId" class="message-item"
          :class="msg.role === 'user' ? 'message-user' : 'message-assistant'">
          <div class="message-bubble">
            <div class="message-content" v-html="renderMarkdown(msg.content)" @click="handleContentClick"></div>
            <div v-if="msg.attachments && msg.attachments.length > 0" class="message-attachments">
              <template v-for="att in msg.attachments" :key="att.url">
                <div v-if="att.type === 'audio'" class="attachment-audio" @click="handlePlayAudio(att)">
                  <i class="pi pi-volume-up"></i>
                  <span class="attachment-audio-label">{{ att.name || '语音' }}</span>
                </div>
                <img v-else-if="att.type === 'image' || /\.(png|jpe?g|gif|webp|svg)$/i.test(att.name)"
                  :src="att.url" :alt="att.name" class="attachment-image" @click="handlePreviewImage(att.url)" />
                <div v-else class="attachment-tag">
                  <i class="pi pi-paperclip"></i>
                  <span class="attachment-name">{{ att.name }}</span>
                  <span v-if="att.size" class="attachment-size">({{ (att.size / 1024).toFixed(1) }}KB)</span>
                </div>
              </template>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 语音输入按钮 -->
    <div class="voice-btn-row" v-if="recorderState !== 'idle'">
      <button v-if="recorderState === 'requesting' || recorderState === 'encoding'"
        class="voice-btn voice-btn-disabled" disabled>
        <i class="pi pi-spin pi-spinner"></i>
      </button>
      <button v-else-if="recorderState === 'recording'" class="voice-btn voice-btn-recording" @click="startRecord">
        <span class="recording-dot"></span>
        <span class="recording-duration">{{ duration }}"</span>
      </button>
      <button v-else-if="recorderState === 'done'" class="voice-btn voice-btn-done" v-tooltip.top="'录音完成'"
        @click="resetRecorder">
        <i class="pi pi-check"></i>
      </button>
      <button v-else-if="recorderState === 'error'" class="voice-btn voice-btn-error" v-tooltip.top="errorMessage"
        @click="resetRecorder">
        <i class="pi pi-exclamation-triangle"></i>
      </button>
    </div>
    <div class="voice-btn-row voice-btn-row-idle" v-else>
      <button class="voice-btn voice-btn-idle" v-tooltip.top="'语音输入'" @click="startRecord">
        <i class="pi pi-microphone"></i>
      </button>
    </div>

    <!-- 已选文件标签行 -->
    <div class="file-tags-row" v-if="localEmbeddedFileTags.length > 0">
      <span v-for="tag in localEmbeddedFileTags" :key="tag.id" class="file-tag">
        <i class="pi pi-file"></i>
        @{{ tag.name }}
        <i class="pi pi-times tag-remove" @click="removeTag(tag.id)"></i>
      </span>
    </div>

    <!-- 输入区 -->
    <div class="chat-input-area">
      <div class="input-wrapper">
        <textarea v-model="inputMessage" placeholder="发送消息..." rows="1" @keydown.enter.prevent="handleSend"
          class="chat-textarea"></textarea>
        <div class="input-actions">
          <div class="input-toolbar">
            <Select :modelValue="selectedModel" @update:modelValue="(val: number) => $emit('update:selectedModel', val)" :options="modelOptions" optionLabel="model_name" optionValue="id"
              placeholder="选择模型" class="model-select" size="small" :disabled="modelOptions.length === 0" />
            <button class="action-btn" v-tooltip.top="'新建会话'" @click="$emit('new-session')">
              <i class="pi pi-plus"></i>
            </button>
            <button class="action-btn" v-tooltip.top="'文件选择'" @click="toggleFilePopover($event)">
              <i class="pi pi-paperclip"></i>
            </button>
            <button class="action-btn" :class="{ 'action-btn-active': webSearchEnabled }" v-tooltip.top="'网络搜索'"
              @click="$emit('toggle-web-search')">
              <i class="pi pi-globe"></i>
            </button>
            <button class="action-btn" :class="{ 'action-btn-active': agentMode }" v-tooltip.top="'Agent模式'"
              @click="$emit('toggle-agent-mode')">
              <i class="pi pi-shield"></i>
            </button>
          </div>
          <button class="action-btn send-btn"
            :class="{ 'action-btn-active': !!inputMessage.trim() && modelOptions.length > 0 }"
            :disabled="!inputMessage.trim() || modelOptions.length === 0"
            v-tooltip.top="modelOptions.length === 0 ? '请先在「我的资源」中配置 AI 模型' : ''" @click="handleSend">
            <i class="pi pi-send"></i>
          </button>
        </div>
      </div>
    </div>

    <!-- 文件选择 Popover -->
    <Popover ref="filePopover">
      <div class="file-popover-content">
        <Button label="上传文件" icon="pi pi-upload" severity="secondary" size="small" text @click="handleOpenFileManagement" />
        <Button label="选择文件" icon="pi pi-check-circle" severity="secondary" size="small" text
          @click="handleOpenEmbeddedFileDialog" />
      </div>
    </Popover>

    <!-- 已嵌入文件选择对话框 -->
    <Dialog v-model:visible="showEmbeddedFileDialog" header="选择知识库文件" modal :draggable="false"
      :style="{ width: '400px' }">
      <div style="display: flex; flex-direction: column; gap: 16px;">
        <div class="field">
          <label class="field-label">搜索已嵌入的文件</label>
        </div>
        <div class="field">
          <MultiSelect v-model="selectedEmbeddedFileIds" :options="embeddedFileOptions" optionLabel="name" optionValue="id"
            filter :filterFields="['name']" class="field-input" size="small" placeholder="搜索已嵌入的文件..."
            :virtualScrollerOptions="{ itemSize: 40 }" @filter="onEmbeddedFileFilter" />
        </div>
        <div class="dialog-actions">
          <Button label="取消" severity="secondary" @click="showEmbeddedFileDialog = false" />
          <Button label="确认" @click="confirmEmbeddedFiles" :disabled="selectedEmbeddedFileIds.length === 0" />
        </div>
      </div>
    </Dialog>

    <!-- Skill Command 对话框 -->
    <Dialog :visible="showCommandDialog" @update:visible="(v: boolean) => { if (!v) $emit('cancel-commands') }" header="待执行的命令" modal :draggable="false" :style="{ width: '640px' }">
      <div class="command-dialog-body">
        <div v-for="(cmd, i) in pendingCommands" :key="i" class="command-item p-mb-2" :class="'risk-' + cmd.risk">
          <div class="command-item-header">
            <Tag :value="cmd.type" severity="warn" />
            <span class="command-description">{{ cmd.description }}</span>
            <Tag :value="riskLabel(cmd.risk)" :severity="riskSeverity(cmd.risk)" />
          </div>
          <code class="command-code">{{ cmd.command }}</code>
          <div v-if="commandResults[i]" class="command-result"
            :class="{ success: commandResults[i].result.exitCode === 0, error: commandResults[i].result.exitCode !== 0 }">
            <div v-if="commandResults[i].result.stdout" class="result-block">
              <pre>{{ commandResults[i].result.stdout }}</pre>
            </div>
            <div v-if="commandResults[i].result.stderr" class="result-block result-stderr">
              <pre>{{ commandResults[i].result.stderr }}</pre>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <Button v-if="!isExecutingCommands" label="取消" severity="secondary" @click="$emit('cancel-commands')" />
        <Button v-if="!isExecutingCommands" label="允许执行" @click="$emit('execute-commands')" severity="contrast"
          :class="{ 'p-button-danger': hasHighRiskCommands }" />
        <Button v-else label="执行中..." disabled />
      </template>
    </Dialog>
  </main>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import Select from 'primevue/select'
import Dialog from 'primevue/dialog'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import Popover from 'primevue/popover'
import MultiSelect from 'primevue/multiselect'
import { useRecorder } from '@/composables/useRecorder'
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: false
})

function renderMarkdown(content: string): string {
  if (!content) return ''
  return md.render(content.trim()).trim()
}

function handleContentClick(event: MouseEvent) {
  const target = event.target as HTMLElement
  const anchor = target.closest('a')
  if (anchor && anchor.href) {
    const href = anchor.href
    // 跳过空链接和页面内锚点
    if (!href || href === '#' || href.startsWith('javascript:')) return
    event.preventDefault()
    if (window.electronAPI?.openExternal) {
      window.electronAPI.openExternal(href).catch((err: Error) => {
        console.warn('[ChatContent] 打开外部链接失败:', href, err.message)
        toast.add({
          severity: 'warn',
          summary: '无法打开链接',
          detail: '当前系统没有找到可以打开此链接的应用',
          life: 4000
        })
      })
    }
  }
}

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

const props = defineProps<{
  messages: ChatMessage[]
  selectedTitle: string
  isStreaming: boolean
  selectedModel: number | null
  modelOptions: { id: number; model_name: string }[]
  webSearchEnabled: boolean
  agentMode: boolean
  showCommandDialog: boolean
  pendingCommands: CommandItem[]
  commandResults: { cmd: CommandItem; result: CommandResult }[]
  isExecutingCommands: boolean
  hasHighRiskCommands: boolean
}>()

const emit = defineEmits<{
  send: [text: string, attachments: { id: number; name: string }[]]
  'voice-sent': [recordingInfo: any, embeddedFiles: { id: number; name: string }[]]
  'update:selectedModel': [id: number]
  'toggle-web-search': []
  'new-session': []
  'execute-commands': []
  'cancel-commands': []
  'open-overlay': [page: string]
  'toggle-agent-mode': []
}>()

// ========== 对话输入 ==========
const inputMessage = ref('')
const scrollContainer = ref<HTMLElement | null>(null)

// ========== 语音输入 ==========
const {
  state: recorderState,
  duration,
  recordedFilePath,
  errorMessage,
  recordingInfo,
  startRecording,
  stopRecording,
  reset: resetRecorder,
} = useRecorder()

function startRecord() {
  startRecording()
}

// 录音完成后自动发送
watch(() => recorderState.value, (newState) => {
  if (newState === 'done' && recordingInfo.value) {
    // 发送前保存当前文件标签引用并清除
    const files = [...localEmbeddedFileTags.value]
    localEmbeddedFileTags.value = []
    selectedEmbeddedFileIds.value = []
    emit('voice-sent', recordingInfo.value, files)
    resetRecorder()
  }
})

// ========== 文本发送 ==========
function handleSend() {
  const text = inputMessage.value.trim()
  if (!text) return

  const attachments = [...localEmbeddedFileTags.value]
  inputMessage.value = ''
  localEmbeddedFileTags.value = []
  selectedEmbeddedFileIds.value = []

  emit('send', text, attachments)
}

// ========== 音频播放 ==========
import { useToast } from 'primevue/usetoast'
const toast = useToast()
let audioPlayer: HTMLAudioElement | null = null

function handlePlayAudio(att: AttachmentItem) {
  if (audioPlayer) {
    audioPlayer.pause()
    audioPlayer = null
  }

  async function play() {
    try {
      let audioUrl: string
      if (att.localPath && window.electronAPI?.readLocalFile) {
        const buffer = await window.electronAPI.readLocalFile(att.localPath)
        const blob = new Blob([buffer], { type: 'audio/mpeg' })
        audioUrl = URL.createObjectURL(blob)
      } else {
        toast.add({ severity: 'error', summary: '播放失败', detail: '本地音频文件不存在', life: 3000 })
        return
      }

      audioPlayer = new Audio(audioUrl)
      audioPlayer.onended = () => URL.revokeObjectURL(audioUrl)
      audioPlayer.onerror = () => {
        URL.revokeObjectURL(audioUrl)
        toast.add({ severity: 'error', summary: '播放失败', detail: '无法播放此音频', life: 3000 })
      }
      await audioPlayer.play()
    } catch (err) {
      console.error('播放音频失败:', err)
      toast.add({ severity: 'error', summary: '播放失败', detail: '无法播放此音频', life: 3000 })
    }
  }
  play()
}

function handlePreviewImage(url: string) {
  if (window.electronAPI?.openOverlayWindow) {
    window.electronAPI.openOverlayWindow('image-preview', { url })
  } else {
    window.open(url, '_blank')
  }
}

// ========== 文件附件 ==========
const filePopover = ref<InstanceType<typeof Popover> | null>(null)
const showEmbeddedFileDialog = ref(false)
const selectedEmbeddedFileIds = ref<number[]>([])
const embeddedFileOptions = ref<{ id: number; name: string }[]>([])
const localEmbeddedFileTags = ref<{ id: number; name: string }[]>([])
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:6880'

function toggleFilePopover(event: MouseEvent) {
  filePopover.value?.toggle(event)
}

function handleOpenFileManagement() {
  filePopover.value?.hide()
  window.electronAPI?.openOverlayWindow('my-resources', 'tab=knowledge-base')
}

async function fetchEmbeddedFiles(keywords?: string) {
  const userId = localStorage.getItem('user_id')
  if (!userId) return
  let url = `${API_BASE_URL}/api/v1/file/list?user_id=${userId}&is_embedded=1&pageSize=50`
  if (keywords) url += `&keywords=${encodeURIComponent(keywords)}`
  try {
    const res = await fetch(url)
    const data = await res.json()
    if (data.code === 0 && data.result) {
      embeddedFileOptions.value = (data.result.items || []).map((f: any) => ({
        id: f.id,
        name: f.name,
      }))
    }
  } catch (err) {
    console.error('获取已嵌入文件列表失败:', err)
  }
}

function handleOpenEmbeddedFileDialog() {
  filePopover.value?.hide()
  showEmbeddedFileDialog.value = true
  fetchEmbeddedFiles()
}

function onEmbeddedFileFilter(event: any) {
  const filterValue = event.value
  if (filterValue && filterValue.length > 0) {
    fetchEmbeddedFiles(filterValue)
  } else {
    fetchEmbeddedFiles()
  }
}

function confirmEmbeddedFiles() {
  showEmbeddedFileDialog.value = false
  localEmbeddedFileTags.value = embeddedFileOptions.value.filter(
    (f) => selectedEmbeddedFileIds.value.includes(f.id)
  )
  filePopover.value?.hide()
}

function removeTag(id: number) {
  localEmbeddedFileTags.value = localEmbeddedFileTags.value.filter(t => t.id !== id)
  selectedEmbeddedFileIds.value = selectedEmbeddedFileIds.value.filter(fid => fid !== id)
}

// ========== Command Dialog ==========
function riskLabel(risk: string): string {
  const map: Record<string, string> = { low: '低风险', medium: '中风险', high: '高风险' }
  return map[risk] || risk
}

function riskSeverity(risk: string): string {
  const map: Record<string, string> = { low: 'success', medium: 'warn', high: 'danger' }
  return map[risk] || 'info'
}

// ========== 自动滚动 ==========
watch(() => props.messages.map(m => m.content + m.messageId).join('|'), () => {
  nextTick(() => {
    if (scrollContainer.value) {
      scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight
    }
  })
})
</script>

<style scoped>
.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 8px;
}

.field-input {
  width: 100%;
}

.chat-main {
  flex: 1;
  min-width: 0;
  background: #fff;
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-header {
  display: flex;
  align-items: center;
  padding: 14px 24px;
  border-bottom: 1px solid #f0f0f0;
  flex-shrink: 0;
}

.chat-header-title {
  font-size: 15px;
  font-weight: 600;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.chat-messages:has(.welcome-message) {
  align-items: center;
  justify-content: center;
}

.welcome-message {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.placeholder-text {
  font-size: 18px;
  color: #999;
  margin: 0;
}

.chat-input-area {
  padding: 12px 16px 16px;
  flex-shrink: 0;
}

.input-wrapper {
  width: 100%;
  display: flex;
  flex-direction: column;
  background: #f5f5f5;
  border: 1px solid #e5e5e5;
  border-radius: 12px;
  padding: 8px 8px 4px 16px;
  transition: border-color 0.15s ease;
  box-sizing: border-box;
}

.input-wrapper:focus-within {
  border-color: #333;
  background: #fff;
}

.chat-textarea {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  font-size: 14px;
  line-height: 1.5;
  resize: none;
  color: #333;
  font-family: inherit;
  max-height: 120px;
  height: 80px;
}

.chat-textarea::placeholder {
  color: #aaa;
}

.input-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 4px;
}

.input-toolbar {
  display: flex;
  align-items: center;
  gap: 2px;
}

.action-btn {
  width: 40px;
  height: 40px;
  border: none;
  background: transparent;
  border-radius: 8px;
  cursor: pointer;
  color: #999;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.15s ease;
}

.action-btn:hover {
  color: #555;
  background: #f0f0f0;
}

.action-btn-active {
  color: #333;
  background: #e8e8e8;
}

.action-btn i {
  font-size: 15px;
}

.send-btn {
  color: #ccc;
  cursor: not-allowed;
}

.send-btn.action-btn-active {
  color: #fff;
  background: #333;
  cursor: pointer;
}

.send-btn.action-btn-active:hover {
  background: #555;
}

.model-select {
  width: 140px;
  height: 32px;
  margin-right: 4px;
}

.model-select :deep(.p-select-label) {
  font-size: 13px;
  padding: 0 8px;
}

.model-select :deep(.p-select-dropdown) {
  width: 24px;
}

.file-tags-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 0 16px;
  flex-shrink: 0;
}

.file-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background: #e8f4ff;
  border-radius: 4px;
  font-size: 12px;
  color: #333;
  user-select: none;
}

.tag-remove {
  cursor: pointer;
  font-size: 10px;
  opacity: 0.6;
  transition: opacity 0.15s;
}

.tag-remove:hover {
  opacity: 1;
}

.file-popover-content {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.embedded-file-dialog-body {
  min-height: 200px;
}

.voice-btn-row {
  display: flex;
  justify-content: center;
  padding-bottom: 6px;
}

.voice-btn-row-idle {
  padding-bottom: 0;
}

.voice-btn {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 18px;
}

.voice-btn-idle {
  color: #999;
  background: transparent;
}

.voice-btn-idle:hover {
  color: #666;
  background: #f0f0f0;
}

.voice-btn-disabled {
  cursor: not-allowed;
  opacity: 0.6;
  color: #999;
  background: #f5f5f5;
}

.voice-btn-recording {
  background: #07c160;
  color: #fff;
  gap: 2px;
  animation: voice-pulse 1.2s ease-in-out infinite;
  cursor: pointer;
}

.voice-btn-recording:hover {
  background: #06ad56;
}

@keyframes voice-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(7, 193, 96, 0.5); }
  50% { box-shadow: 0 0 0 10px rgba(7, 193, 96, 0); }
}

.recording-dot {
  width: 8px;
  height: 8px;
  background: #fff;
  border-radius: 50%;
  animation: dot-pulse 1s ease-in-out infinite;
}

@keyframes dot-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(0.8); }
}

.recording-duration {
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.voice-btn-done {
  background: #07c160;
  color: #fff;
}

.voice-btn-done:hover {
  background: #06ad56;
  color: #fff;
}

.voice-btn-error {
  background: #e74c3c;
  color: #fff;
}

.voice-btn-error:hover {
  background: #c0392b;
  color: #fff;
}

.message-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  width: 100%;
}

.message-item {
  display: flex;
  flex-direction: column;
}

.message-user {
  align-items: flex-end;
}

.message-assistant {
  align-items: flex-start;
}

.message-bubble {
  max-width: 80%;
  padding: 10px 14px;
  border-radius: 12px;
  background: #f5f5f5;
  color: #333;
  font-size: 14px;
  line-height: 1.5;
  word-break: break-word;
}

.message-user .message-bubble {
  background: #f5f5f5;
  color: #060606;
}

/* Markdown 渲染样式 — 紧凑排版 */
.message-content :deep(p) {
  margin: 0;
  line-height: 1.6;
  min-height: 0;
}

.message-content :deep(a) {
  color: #1677ff;
  text-decoration: underline;
  cursor: pointer;
}

.message-content :deep(a:hover) {
  opacity: 0.8;
}

.message-content :deep(code) {
  background: rgba(0,0,0,0.06);
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 13px;
  font-family: 'SF Mono', Monaco, 'Cascadia Code', monospace;
}

.message-content :deep(pre) {
  background: #f6f8fa;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  padding: 12px 14px;
  overflow-x: auto;
  margin: 8px 0;
}

.message-content :deep(pre code) {
  background: none;
  padding: 0;
  border-radius: 0;
  font-size: 13px;
}

.message-content :deep(ul),
.message-content :deep(ol) {
  margin: 4px 0;
  padding-left: 20px;
}

.message-content :deep(li) {
  margin: 2px 0;
  line-height: 1.5;
}

.message-content :deep(strong) {
  font-weight: 600;
}

.message-content :deep(blockquote) {
  margin: 6px 0;
  padding: 4px 12px;
  border-left: 3px solid #e0e0e0;
  color: #666;
}

.message-content :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
  font-size: 13px;
}

.message-content :deep(th),
.message-content :deep(td) {
  border: 1px solid #e0e0e0;
  padding: 6px 10px;
  text-align: left;
}

.message-content :deep(th) {
  background: #fafafa;
  font-weight: 600;
}

.message-content :deep(hr) {
  border: none;
  border-top: 1px solid #e0e0e0;
  margin: 12px 0;
}

.message-attachments {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.2);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.message-user .message-attachments {
  border-top-color: rgba(255, 255, 255, 0.2);
}

.message-assistant .message-attachments {
  border-top-color: #e0e0e0;
}

.attachment-audio {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.06);
  cursor: pointer;
  transition: background 0.15s;
  font-size: 13px;
  user-select: none;
}

.attachment-audio:hover {
  background: rgba(0, 0, 0, 0.1);
}

.attachment-audio i {
  font-size: 18px;
}

.attachment-audio-label {
  opacity: 0.85;
}

.attachment-image {
  max-width: 240px;
  max-height: 240px;
  border-radius: 8px;
  cursor: pointer;
  object-fit: cover;
  transition: opacity 0.15s;
}

.attachment-image:hover {
  opacity: 0.85;
}

.attachment-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  font-size: 12px;
  opacity: 0.85;
}

.attachment-name {
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.attachment-size {
  opacity: 0.7;
}

.command-dialog-body {
  max-height: 400px;
  overflow-y: auto;
  gap: 16px;
}

.command-item {
  border: 1px solid var(--surface-border);
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 8px;
}

.command-item.risk-low {
  border-left: 3px solid var(--green-500);
}

.command-item.risk-medium {
  border-left: 3px solid var(--yellow-500);
}

.command-item.risk-high {
  border-left: 3px solid var(--red-500);
}

.command-item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.command-description {
  flex: 1;
  font-weight: 500;
  font-size: 14px;
}

.command-code {
  display: block;
  padding: 6px 10px;
  background: var(--surface-ground);
  border-radius: 4px;
  font-size: 13px;
  word-break: break-all;
  overflow-x: auto;
}

.command-result {
  margin-top: 8px;
}

.command-result.success pre {
  color: var(--green-600);
}

.command-result.error pre {
  color: var(--red-600);
}

.result-block {
  margin-top: 4px;
}

.result-stderr {
  opacity: 0.85;
}

.command-result pre {
  margin: 0;
  font-size: 12px;
  max-height: 120px;
  overflow-y: auto;
  white-space: pre-wrap;
}
</style>
