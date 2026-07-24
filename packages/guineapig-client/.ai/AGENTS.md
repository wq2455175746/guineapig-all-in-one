# guineapig-client AI Agent Guide

## Quick Start

```bash
# Read project-level rules first
cat ../../.ai/AGENTS.md
cat ../../docs/ARCHITECTURE.md
cat ../../docs/design-docs/guineapig-client.md
```

## Module Map

| 任务 | 位置 | 说明 |
|-----|------|------|
| Electron 主进程 | `electron/` | 窗口管理、系统托盘、全局快捷键 |
| Vue 渲染进程 | `src/` | 聊天界面、录音、播放 |
| IPC 通信 | `preload/` | 主进程与渲染进程桥梁 |
| 音频录制 | `src/composables/useRecorder.js` | Web Audio API 封装 |
| 音频播放 | `src/composables/usePlayer.js` | 音频播放封装 |
| API 调用 | `src/api/` | Axios 封装，调用 Backend |

## Architecture Rules

1. **客户端不直接调用 AIAgent**: 所有请求通过 Backend 中转
2. **音频文件通过 S3**: 不直接传输音频给 Backend，使用 S3 presigned URL
3. **Electron 安全**: 使用 contextBridge + preload，不开启 nodeIntegration

## Key Patterns

### Vue Composables (录音示例)
```js
// src/composables/useRecorder.js
export function useRecorder() {
  const isRecording = ref(false)
  const audioBlob = ref(null)

  async function startRecording() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    // ... MediaRecorder setup, max 10s
  }

  return { isRecording, audioBlob, startRecording, stopRecording }
}
```

### IPC 通信
```js
// preload/index.js
contextBridge.exposeInMainWorld('electronAPI', {
  minimize: () => ipcRenderer.send('window:minimize'),
  close: () => ipcRenderer.send('window:close'),
})
```

### API 调用格式
```js
// src/api/task.js
import request from './index'

export function submitTask(data) {
  return request.post('/api/v1/tasks', data)
  // data: { user_id, s3_path, task_id }
}
```

## Voice Dialogue Flow (Client Side)

```
1. 用户点击/按住录音按钮
2. useRecorder 录制音频 (max 10s)
3. 编码为 MP3 (ffmpeg.wasm)
4. 上传到 S3 (presigned URL from Backend)
5. POST /api/v1/tasks 提交任务
6. 轮询任务状态 / SSE 等待结果
7. 下载 AI 回复音频 from S3
8. usePlayer 播放音频
9. 显示文本转写
```

## Before Committing

```bash
npm run lint
npm run build
```
