/**
 * 录音 AudioWorklet 处理器（在音频渲染线程上运行，不阻塞 UI 线程）
 *
 * 替代已废弃的 ScriptProcessorNode。每个 render quantum（默认 128 帧）
 * 将单声道 Float32Array PCM 数据通过 port.postMessage 回传主线程，
 * 由 useRecorder.ts 累积后交给 MP3 编码器。
 *
 * 数据格式与原 ScriptProcessorNode 完全一致：Float32Array（-1 ~ 1）数组。
 * 采样率 = AudioContext 的采样率（通常 44100 或 48000）。
 *
 * 注意：此文件为纯 JS，通过 `?raw` 导入并以 Blob URL 形式传给
 * audioWorklet.addModule()，避免 Electron 生产环境 file:// 页面无法 fetch 的问题。
 */
class RecorderWorkletProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0]
    const channel = input && input[0]
    if (channel) {
      // 复制一份再转移，避免持有音频引擎内部复用/重写的 buffer
      const buffer = new Float32Array(channel.length)
      buffer.set(channel)
      this.port.postMessage(buffer, [buffer.buffer])
    }
    return true
  }
}

registerProcessor('recorder-worklet-processor', RecorderWorkletProcessor)