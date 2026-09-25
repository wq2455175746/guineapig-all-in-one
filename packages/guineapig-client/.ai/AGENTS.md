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
| Electron 主进程 | `src/main/index.ts` | 窗口管理、系统托盘、全局快捷键、IPC handlers、命令白名单、MCP fetch、日志 |
| 主进程日志 | `src/main/logger.ts` | 统一 logger（日志写入 userData/logs） |
| preload 桥接 | `src/preload/index.ts` | contextBridge + ipcRenderer.invoke，暴露 `window.electronAPI` |
| 渲染进程（聊天 UI） | `src/renderer/` | 聊天界面、录音、播放（`App.vue` / `views/` / `router/`） |
| Overlay 系统页面 | `src/renderer-overlay/` | 独立小窗口页面：系统设置 / 资源管理 / 头像 / 记忆等 |
| 渲染进程类型声明 | `src/renderer/vite-env.d.ts` | `Window.electronAPI` 全量类型（新增 IPC 必须同步扩展） |
| 音频录制 | `src/audio/recorder-worklet.js` + `src/composables/` | AudioWorklet 录制封装 |
| RSA 加密 | `src/utils/rsa.ts` | 登录等敏感字段公钥加密 |
| API 调用 | `src/renderer/api.ts` | Axios 封装，调用 Backend |

## Architecture Rules

1. **客户端不直接调用 AIAgent**: 所有请求通过 Backend 中转
2. **音频文件通过 S3**: 不直接传输音频给 Backend，使用 S3 presigned URL
3. **Electron 安全**: 使用 contextBridge + preload，不开启 nodeIntegration，渲染进程仅能调用白名单 IPC

## 命令白名单（execute-command）

- 常量 `DEFAULT_ALLOWED_COMMAND_BINARIES`（`src/main/index.ts`）为内置默认白名单：开发命令 + 系统只读/打开命令 + 文件操作类（mkdir/cp/mv/rm/touch/printf/chmod/sed/tar）
- **配置副本优先于代码默认**：启动时 `loadCommandWhitelist()` 从 `userData/command-whitelist.json` 加载；文件存在则用之而非代码默认（首次启动自动生成副本）。**改代码默认时必须同步更新已有 userData 副本**（或经设置页"恢复默认→保存"），否则"修了没生效"
- `execute-command` handler：`spawn(shell:false)`，二进制必须过 `isAllowedBinary`（白名单按 basename 匹配，允许 `/usr/bin/open` 这类路径限定调用），参数逐个过 `SAFE_ARG_TOKEN` 正则（ASCII 安全字符 + 任意非 ASCII，**拒 shell 重定向/管道等元字符**——`echo x > file` 这类命令会被拒，技能需用 python3/node/cp/printf 直接写文件），cwd 限定 userData/skills 下，risk 非 low 弹二次确认
- **页面管理**：系统设置 Overlay → 命令白名单 Tab（`src/renderer-overlay/views/CommandWhitelistTab.vue`），IPC `get-command-whitelist` / `set-command-whitelist`；主进程 `sanitizeCommandBinaries()` 清洗（trim/小写/去重/拒空白与 shell 元字符），`persistCommandWhitelist()` 写 JSON + 更新内存 Set 立即生效，空列表回退默认

## 日志规范（logger + 渲染进程转发）

- 统一 logger：`userData/temp/logs/` 每日 error/info/debug 三文件；系统设置→本地日志 页可查看/删除/导出
- **关键 handler 必须补日志**：入口记 info（参数摘要）、拒绝路径记 error（白名单/cwd/参数非法/越界读取/openExternal）、完成记 info（exit/字节数）；命令 stdout/stderr 用 `truncate(s, 500)` 截断落盘
- `attachRendererLogging(win)` 已挂到每个窗口：转发 did-fail-load / render-process-gone / unresponsive / renderer console warning&error
- **Electron 42 的 `console-message` 用新 API**：`on('console-message', (details) => ...)`，level/message/lineNumber/sourceId 直挂 details，level 为 'info'|'warning'|'error'|'debug'（旧 `(event, level, message, ...)` 签名已弃用）

## IPC 扩展约定

新增 IPC 的固定三步（缺一即类型/运行时出错）：
1. `src/main/index.ts` 注册 `ipcMain.handle(...)`
2. `src/preload/index.ts` 用 `ipcRenderer.invoke` 暴露方法
3. `src/renderer/vite-env.d.ts` 扩展 `Window.electronAPI` 类型

## 构建与校验

```bash
# 无 lint 脚本；类型检查 + 构建
npx vue-tsc --noEmit
npm run build          # vue-tsc && vite build（含 electron 主进程 + preload + renderer + overlay）
npm run electron:build # 完整打包 electron-builder

# 项目级验证（含 harness 完整性）
make validate
```

注意：
- 主进程是 ESM（`"type": "module"`），任何 CJS/原生依赖（adm-zip/archiver/node-machine-id）必须加进 `vite.config.ts` 主进程 `rollupOptions.external`；按子路径导入的包（`@modelcontextprotocol/sdk`）必须用正则 `^/包名/` 而非精确字符串
- electron 插件 outDir `dist/electron` 不自动清空，手动改过外部依赖后需清理残留 chunk