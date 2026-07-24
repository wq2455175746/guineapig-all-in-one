import { ref } from 'vue'
import { useToast } from 'primevue/usetoast'
import { encodePcmToMp3 } from './mp3Encoder'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:6880'

export type RecorderState = 'idle' | 'requesting' | 'recording' | 'encoding' | 'done' | 'error'

export interface RecordingInfo {
  key: string
  name: string
  size: number
  localPath: string  // 本地缓存文件的绝对路径
}

// 计算 SHA-256 哈希，取前 16 位 hex 作为文件名
async function hashData(data: Uint8Array): Promise<string> {
  const hashBuffer = await crypto.subtle.digest('SHA-256', data)
  const hashArray = Array.from(new Uint8Array(hashBuffer))
  return hashArray.slice(0, 8).map(b => b.toString(16).padStart(2, '0')).join('')
}

function getDateDir(): string {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}${m}${day}`
}

const MAX_DURATION = 10 // seconds

export function useRecorder() {
  const toast = useToast()
  const state = ref<RecorderState>('idle')
  const duration = ref(0)
  const recordedFilePath = ref<string | null>(null)
  const errorMessage = ref('')
  const recordingInfo = ref<RecordingInfo | null>(null)

  let mediaStream: MediaStream | null = null
  let audioContext: AudioContext | null = null
  let scriptNode: ScriptProcessorNode | null = null
  let pcmBuffers: Float32Array[] = []
  let startTime = 0
  let durationTimer: ReturnType<typeof setInterval> | null = null
  let autoStopTimer: ReturnType<typeof setTimeout> | null = null

  function cleanupTimers() {
    if (durationTimer !== null) {
      clearInterval(durationTimer)
      durationTimer = null
    }
    if (autoStopTimer !== null) {
      clearTimeout(autoStopTimer)
      autoStopTimer = null
    }
  }

  function cleanupAudio() {
    if (scriptNode !== null) {
      scriptNode.disconnect()
      scriptNode = null
    }
    if (audioContext !== null) {
      audioContext.close().catch(() => {})
      audioContext = null
    }
    if (mediaStream !== null) {
      mediaStream.getTracks().forEach(track => track.stop())
      mediaStream = null
    }
  }

  async function startRecording() {
    if (state.value === 'recording') {
      stopRecording()
      return
    }

    state.value = 'requesting'
    errorMessage.value = ''
    recordedFilePath.value = null
    pcmBuffers = []

    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch (err: unknown) {
      state.value = 'error'
      if (err instanceof DOMException && (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError')) {
        errorMessage.value = '请在系统设置中允许麦克风权限'
      } else {
        errorMessage.value = '无法访问麦克风'
      }
      return
    }

    try {
      audioContext = new AudioContext()
      const source = audioContext.createMediaStreamSource(mediaStream)

      const bufferSize = 4096
      scriptNode = audioContext.createScriptProcessor(bufferSize, 1, 1)

      scriptNode.onaudioprocess = (event) => {
        const input = event.inputBuffer.getChannelData(0)
        pcmBuffers.push(new Float32Array(input))
      }

      source.connect(scriptNode)
      scriptNode.connect(audioContext.destination)

      state.value = 'recording'
      startTime = Date.now()
      duration.value = 0

      durationTimer = setInterval(() => {
        const elapsed = Math.floor((Date.now() - startTime) / 1000)
        duration.value = elapsed
        if (elapsed >= MAX_DURATION) {
          stopRecording()
        }
      }, 200)

      autoStopTimer = setTimeout(() => {
        if (state.value === 'recording') {
          stopRecording()
        }
      }, MAX_DURATION * 1000)
    } catch {
      cleanupAudio()
      state.value = 'error'
      errorMessage.value = '初始化录音失败'
    }
  }

  function stopRecording() {
    if (state.value !== 'recording') return

    state.value = 'encoding'
    cleanupTimers()
    cleanupAudio()

    encodeToMp3()
  }

  async function uploadToS3(mp3Data: Uint8Array, fileHash: string): Promise<void> {
    const userId = localStorage.getItem('user_id')
    if (!userId) {
      throw new Error('用户未登录')
    }

    const dateDir = getDateDir()
    const filename = `${fileHash}.mp3`

    // 先保存本地缓存
    const filePath = await window.electronAPI.saveTempFile({
      buffer: mp3Data.buffer as ArrayBuffer,
      filename,
      dateDir
    })

    // 获取预签名上传 URL（用 hash 做文件名）
    const presignRes = await fetch(
      `${API_BASE_URL}/api/v1/aimodel/presigned-upload-url?user_id=${encodeURIComponent(userId)}&filename=${encodeURIComponent(fileHash)}`
    )
    const presignData = await presignRes.json()
    if (presignData.code !== 0) {
      throw new Error(presignData.message || '获取上传地址失败')
    }

    const { url, key } = presignData.result

    // 上传 MP3 到 S3
    const uploadRes = await fetch(url, {
      method: 'PUT',
      headers: { 'Content-Type': 'audio/mpeg' },
      body: mp3Data
    })

    if (!uploadRes.ok) {
      throw new Error(`S3 上传失败，HTTP ${uploadRes.status}`)
    }

    // 保存附件信息（含本地路径）
    recordedFilePath.value = filePath
    recordingInfo.value = { key, name: filename, size: mp3Data.length, localPath: filePath }
  }

  async function encodeToMp3() {
    try {
      const mp3Data = await encodePcmToMp3(pcmBuffers)
      pcmBuffers = []

      // 计算文件哈希作为唯一文件名
      const fileHash = await hashData(mp3Data)

      // 上传到 S3（会同时保存本地缓存）
      try {
        await uploadToS3(mp3Data, fileHash)
      } catch (uploadErr) {
        const msg = uploadErr instanceof Error ? uploadErr.message : 'S3 上传失败'
        toast.add({ severity: 'error', summary: '上传失败', detail: msg, life: 3000 })
      }

      state.value = 'done'
    } catch (err: unknown) {
      errorMessage.value = err instanceof Error ? err.message : 'MP3 编码失败'
      state.value = 'error'
    }
  }

  function reset() {
    cleanupTimers()
    cleanupAudio()
    state.value = 'idle'
    duration.value = 0
    recordedFilePath.value = null
    errorMessage.value = ''
    recordingInfo.value = null
    pcmBuffers = []
  }

  return {
    state,
    duration,
    recordedFilePath,
    errorMessage,
    recordingInfo,
    startRecording,
    stopRecording,
    reset
  }
}
