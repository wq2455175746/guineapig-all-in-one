# GuineaPig Client Design (Electron)

## Metadata
- **Status**: draft
- **Created**: 2026-05-21
- **Package**: guineapig-client
- **Tech**: Electron, Vue 3, Web Audio API

## Overview
guineapig-client 是桌面客户端，提供语音录制、音频播放、对话交互界面。MVP 阶段为非实时语音对话。

## Architecture

```
Electron App
├── Main Process (Node.js)
│   ├── Window management
│   ├── System tray
│   ├── Global shortcuts
│   └── Auto-updater
├── Renderer Process (Vue 3)
│   ├── Chat UI
│   ├── Voice recorder
│   ├── Audio player
│   └── Settings
└── Preload Script
    └── IPC bridge (main <-> renderer)
```

## Core Features

### Voice Recording
1. 用户点击/按住录音键
2. Web Audio API 捕获麦克风音频
3. 编码为 MP3 格式 (使用 ffmpeg.js 或本地 ffmpeg)
4. 限制录音时长 10 秒
5. 上传到 S3 (presigned URL)

### Voice Playback
1. 从 S3 下载 AI 回复音频 (presigned URL)
2. 使用 Web Audio API 或 HTML5 Audio 播放
3. 支持分段播放 (长内容分 100 段)
4. 显示播放进度

### Chat UI
1. 对话气泡 (用户/AI)
2. 语音消息波形显示
3. 文本转写显示 (ASR 结果)
4. 多会话切换

## State Flow

```
[Idle] -> [Recording] -> [Uploading] -> [Processing] -> [Playing] -> [Idle]
  ^                                                                  |
  └──────────────────────────────────────────────────────────────────┘
```

## Key Dependencies
- `electron` (desktop shell)
- `vue` 3.x (UI)
- `pinia` (state)
- `lamejs` or `ffmpeg.wasm` (MP3 encoding)
- `howler.js` or native Audio API (playback)
- `axios` (HTTP client)

## System Tray
- 显示 GuineaPig 图标
- 快捷操作: 开始录音、打开窗口、退出
- 通知: 新回复、定时提醒

## Global Shortcuts
- `Ctrl+Shift+G`: 开始/停止录音
- `Ctrl+Shift+H`: 显示/隐藏窗口
