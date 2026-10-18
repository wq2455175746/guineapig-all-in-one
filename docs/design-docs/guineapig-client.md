# GuineaPig Client Design (Electron)

## Metadata
- **Status**: implemented (updated to match current code)
- **Created**: 2026-05-21
- **Updated**: 2026-10-17
- **Package**: guineapig-client
- **Tech**: Electron 42, Vue 3.5, TypeScript, PrimeVue 4, AudioWorklet + lamejs, MCP SDK

> 说明：本文替换早期"Electron + Vue + Web Audio（Pinia/ffmpeg）"的草稿设计，描述**当前代码**实现。

## Overview

guineapig-client 是桌面客户端：语音录制、对话交互、以及 **client 端能力执行**
（CLI / Skill / stdio-MCP）。技术要点：

- TypeScript + Electron 42 + Vue 3.5 + PrimeVue 4（Aura）
- **无 Pinia**、**无 ffmpeg**；MP3 由 **lamejs** 在渲染进程内编码
- 录音使用 **AudioWorklet**（非废弃的 ScriptProcessor）

## Architecture

```
Electron App
├── Main Process (src/main/index.ts)
│   ├── Window / overlay window management
│   ├── IPC handlers (contextBridge 契约)
│   ├── MCP client pool (stdio / sse / streamable-http)
│   ├── Local command execution (whitelist + confirmation)
│   ├── Skill zip download & extraction (adm-zip)
│   └── Log / file read-write
├── Preload (src/preload/index.ts)  — 暴露 window.electronAPI
├── Renderer — 主窗口 (src/renderer, index.html)
│   └── Login / Chat / ConversationHistory / HITLIntervention
└── Renderer — 浮层窗口 (src/renderer-overlay, overlay.html)
    └── McpTab / SkillTab / RagTab / FileManagementTab / MemoryTab /
        MetricsTab / AIConfigTab / SystemSettingsPage / BotChannelTab /
        LocalLogTab / CommandWhitelistTab / ...
```

## Source Structure

```
src/
├── main/index.ts            # 主进程（窗口、IPC、MCP、命令执行、日志打包）
├── main/logger.ts           # 文件日志 → userData/temp/logs
├── preload/index.ts         # contextBridge: window.electronAPI
├── audio/recorder-worklet.js# AudioWorkletProcessor，回传 Float32 PCM
├── composables/
│   ├── useRecorder.ts       # 录音状态机 + PCM 累积 + S3 上传
│   └── mp3Encoder.ts        # lamejs MP3 编码（mono 44.1k 128kbps）
├── utils/rsa.ts             # jsencrypt RSA 加密
├── renderer/                # 主窗口 (index.html)
│   ├── main.ts, App.vue, api.ts, router/index.ts
│   └── views/ LoginPage, ChatPage, ChatContent, ConversationHistory, HITLIntervention
└── renderer-overlay/        # 浮层窗口 (overlay.html)
    ├── main.ts, App.vue
    └── views/ McpTab, SkillTab, RagTab, FileManagementTab, MemoryTab, MetricsTab,
               AIConfigTab, SystemSettingsPage, BotChannelTab, BotChannelDialog,
               LocalLogTab, ChatHistoryTab, CommandWhitelistTab, ResourcePage,
               AICapabilitiesPage, AvatarPage, MemoryPage
```

主窗口与浮层窗口为**两个独立渲染进程**（Vite 两个 build input：`index.html` 与 `overlay.html`）。

## Voice Recording

1. `getUserMedia` 采集麦克风 → `AudioContext` + `AudioWorkletNode`
2. `recorder-worklet.js` 逐 quantum 回传 Float32 PCM
3. `useRecorder.ts` 累积 PCM，达到 `MAX_DURATION = 10s` 自动停止
4. `mp3Encoder.ts` 经 `public/lame.min.js`（lamejs）将 PCM 编码为 MP3
5. 先经 IPC 保存到本地 `userData/temp/{YYYYMMDD}/{hash}.mp3`
6. 向后端申请 presigned URL 并 `PUT` 上传到 S3

## Voice Playback

1. 音/视频资源经后端 presigned URL 从 S3 获取
2. 本地文件经 IPC `read-local-file` 读回（限制在 `userData` 内）
3. 使用 HTML5 Audio / Web Audio 播放，支持对话消息逐条播放

## Chat & Transport

- **WebSocket**：`/api/v1/chat/ws?token=<user_token>`（http→ws），信封 `{ type, from, to, payload, meta }`，指数退避重连
- **HTTP fetch**：`src/renderer/api.ts` 包装 `window.fetch`，对 `/api/v1/` 请求注入：
  - `X-Device-Id`、`X-User-Id`、`X-User-Token`、`X-Request-Id`
  - 401 时清除本地登录态并跳转 `#/login`
- 路由使用 **hash history**（`/login`、`/chat`），以 `localStorage.user_email` 守卫

## Login & Security

- `LoginPage.vue`：获取机器码（IPC `getMachineId`）→ 用 RSA 公钥加密 API Key（`utils/rsa.ts`，jsencrypt）
  → `POST /api/v1/client/login` `{ api_key, device_id }`
- 成功后仅保存 `user_token` / `user_email` / `user_id` / `device_id`（不保存明文 API Key）
- 公钥来源：打包资源 `resources/public/public.key`，dev 下 `fetch('/public.key')`

## Client-Side Capability Execution (Trust Boundary)

当后端 SSE 下发 `chat.agent_delegate`（`execution_location=client`）时，客户端执行并回填结果：

- `cli` → `electronAPI.executeCommand`（主进程 `spawn`，cwd 限 `userData/skills`，命令白名单 + 参数校验 + 高风险二次确认 + 超时）
- `mcp_*` → `electronAPI.callMcpTool`（主进程 MCP SDK 连接池：stdio / sse / streamable-http）
- `skill` → 客户端 Skill 下载/解压（adm-zip，路径穿越防护）
- 结果通过 `delegate-result` 回传后端

命令白名单持久化在 `userData/command-whitelist.json`，可在"系统设置 → 命令白名单"编辑。

## Overlay Window

`overlay.html` → `renderer-overlay/main.ts`，用于浮层弹窗（头像、AI 能力、资源、记忆、系统设置等）。
主进程 `open-overlay-window` IPC 按 `?page=` 打开并聚焦对应页面。

## Key Dependencies

- `electron` 42, `electron-builder` 26
- `vue` 3.5, `vue-router` 4 (hash), `primevue` 4 + `@primevue/themes` (Aura)
- `@modelcontextprotocol/sdk`（MCP client）
- `lamejs`（MP3 编码）、`jsencrypt`（RSA）
- `adm-zip`、`archiver`、`node-machine-id`、`markdown-it`、`echarts`

## Dev / Build

```bash
npm run electron:dev     # 开发（Vite，README 使用端口 5174）
npm run build            # vue-tsc && vite build
npm run electron:build   # electron-builder 打包安装包
```
