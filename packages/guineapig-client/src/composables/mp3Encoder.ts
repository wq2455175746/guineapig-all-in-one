/**
 * 编码 PCM 音频数据为 MP3 格式
 * 使用 lame.min.js 完整 bundle（通过 script 标签加载，避免 Vite CJS 兼容问题）
 */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let Mp3Encoder: any = null
let loadingPromise: Promise<void> | null = null

async function ensureLoaded(): Promise<void> {
  if (Mp3Encoder) return
  if (loadingPromise) return loadingPromise

  loadingPromise = new Promise<void>((resolve, reject) => {
    // 先检查是否已全局加载
    const g = globalThis as unknown as { lamejs?: { Mp3Encoder: unknown } }
    if (g.lamejs?.Mp3Encoder) {
      Mp3Encoder = g.lamejs.Mp3Encoder
      resolve()
      return
    }

    // 动态加载 lame.min.js 脚本
    const script = document.createElement('script')
    script.src = './lame.min.js'
    script.onload = () => {
      if (g.lamejs?.Mp3Encoder) {
        Mp3Encoder = g.lamejs.Mp3Encoder
        resolve()
      } else {
        reject(new Error('lamejs 加载成功但 Mp3Encoder 未找到'))
      }
    }
    script.onerror = () => {
      reject(new Error('lame.min.js 脚本加载失败'))
    }
    document.head.appendChild(script)
  })

  return loadingPromise
}

function float32ToInt16(float32: Float32Array): Int16Array {
  const int16 = new Int16Array(float32.length)
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]))
    int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF
  }
  return int16
}

export async function encodePcmToMp3(pcmBuffers: Float32Array[]): Promise<Uint8Array> {
  await ensureLoaded()

  // 合并所有 PCM 缓冲区
  const totalLength = pcmBuffers.reduce((acc, buf) => acc + buf.length, 0)
  const allSamples = new Float32Array(totalLength)
  let offset = 0
  for (const buf of pcmBuffers) {
    allSamples.set(buf, offset)
    offset += buf.length
  }

  // 转换为 Int16
  const samples = float32ToInt16(allSamples)

  // 编码为 MP3（单声道，44.1kHz，128kbps）
  const encoder = new Mp3Encoder(1, 44100, 128)

  const mp3Chunks: Uint8Array[] = []
  const chunkSize = 1152
  for (let i = 0; i < samples.length; i += chunkSize) {
    const chunk = samples.subarray(i, Math.min(i + chunkSize, samples.length))
    const encoded = encoder.encodeBuffer(chunk, chunk)
    if (encoded && encoded.length > 0) {
      mp3Chunks.push(new Uint8Array(encoded))
    }
  }

  const flushed = encoder.flush()
  if (flushed && flushed.length > 0) {
    mp3Chunks.push(new Uint8Array(flushed))
  }

  // 合并所有 MP3 块
  const totalSize = mp3Chunks.reduce((acc, c) => acc + c.length, 0)
  const mp3Data = new Uint8Array(totalSize)
  let mp3Offset = 0
  for (const chunk of mp3Chunks) {
    mp3Data.set(chunk, mp3Offset)
    mp3Offset += chunk.length
  }

  return mp3Data
}
