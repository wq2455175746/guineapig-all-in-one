/**
 * Electron 主进程入口文件
 */

import { app, BrowserWindow, ipcMain, dialog, globalShortcut, shell } from 'electron'
import path from 'path'
import fs from 'fs'
import { fileURLToPath } from 'url'
import { spawn } from 'child_process'
import machineIdPkg from 'node-machine-id'
import AdmZip from 'adm-zip'
const { machineId } = machineIdPkg
import { createWriteStream } from 'fs'
import { logger } from './logger'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged

/**
 * 允许通过 shell.openExternal 打开的协议白名单
 * 拒绝 file: / javascript: / data: 等危险协议
 */
const ALLOWED_EXTERNAL_PROTOCOLS = new Set(['https:', 'http:', 'amapuri:'])

/** execute-command 允许执行的已知二进制（首 token） */
const DEFAULT_ALLOWED_COMMAND_BINARIES = [
  // 开发/脚本类（原有）
  'npx', 'npm', 'node', 'python', 'python3', 'pip', 'pip3',
  // 系统只读/打开类（LLM 生成命令常用，无破坏性副作用）
  'open', 'xdg-open', 'ls', 'cat', 'pwd', 'echo', 'which', 'head', 'tail', 'grep',
  // 文件操作类（cwd 已限制在 userData/skills 内，shell:false + 参数安全校验兜底）
  'mkdir', 'cp', 'mv', 'rm', 'touch', 'printf', 'chmod', 'sed', 'tar',
]

const CONFIG_FILE_NAME = 'command-whitelist.json'

/** 当前生效的命令白名单（可配置，从 userData/command-whitelist.json 加载） */
let allowedCommandBinaries: Set<string> = new Set(DEFAULT_ALLOWED_COMMAND_BINARIES)

/**
 * 加载命令白名单配置。
 * 优先读取 userData/command-whitelist.json；文件缺失/损坏时写入默认配置并使用内置默认。
 * 配置结构: { "allowedBinaries": ["open", "node", ...] }
 */
function loadCommandWhitelist(): void {
  const configPath = path.join(app.getPath('userData'), CONFIG_FILE_NAME)
  const defaultConfig = { allowedBinaries: DEFAULT_ALLOWED_COMMAND_BINARIES }
  try {
    if (fs.existsSync(configPath)) {
      const raw = JSON.parse(fs.readFileSync(configPath, 'utf-8'))
      const list = Array.isArray(raw?.allowedBinaries)
        ? raw.allowedBinaries.filter((b: unknown) => typeof b === 'string' && b.trim())
        : []
      if (list.length > 0) {
        allowedCommandBinaries = new Set(list.map((b: string) => b.toLowerCase()))
        logger.info(`[CommandWhitelist] 已从配置加载: ${list.length} 项 | ${configPath}`)
        return
      }
    }
    // 缺失或内容无效 → 写默认配置（供用户编辑），使用内置默认
    fs.mkdirSync(app.getPath('userData'), { recursive: true })
    fs.writeFileSync(configPath, JSON.stringify(defaultConfig, null, 2), 'utf-8')
    allowedCommandBinaries = new Set(DEFAULT_ALLOWED_COMMAND_BINARIES)
    logger.info(`[CommandWhitelist] 已生成默认配置: ${configPath}`)
  } catch (e) {
    logger.error(`[CommandWhitelist] 加载配置失败，使用内置默认: ${e}`)
    allowedCommandBinaries = new Set(DEFAULT_ALLOWED_COMMAND_BINARIES)
  }
}

/** 白名单二进制名校验：仅允许安全字符（无空白、无 shell 元字符） */
const SAFE_BINARY_NAME = /^[A-Za-z0-9_./:@+=~-]+$/u

/**
 * 清洗命令白名单：trim、小写、去重、丢弃空项与非法项，最多保留 200 项。
 * 与 loadCommandWhitelist 的语义保持一致。
 */
function sanitizeCommandBinaries(raw: unknown): string[] {
  if (!Array.isArray(raw)) return []
  const seen = new Set<string>()
  const result: string[] = []
  for (const item of raw.slice(0, 200)) {
    if (typeof item !== 'string') continue
    const b = item.trim().toLowerCase()
    if (!b || !SAFE_BINARY_NAME.test(b) || seen.has(b)) continue
    seen.add(b)
    result.push(b)
  }
  return result
}

/**
 * 持久化命令白名单：写入 userData/command-whitelist.json 并更新内存 Set。
 * 空列表视为无效 → 回退到内置默认白名单（避免完全失去保护）。
 */
function persistCommandWhitelist(list: unknown): string[] {
  const clean = sanitizeCommandBinaries(list)
  const saved = clean.length > 0 ? clean : DEFAULT_ALLOWED_COMMAND_BINARIES
  const configPath = path.join(app.getPath('userData'), CONFIG_FILE_NAME)
  fs.mkdirSync(app.getPath('userData'), { recursive: true })
  fs.writeFileSync(configPath, JSON.stringify({ allowedBinaries: saved }, null, 2), 'utf-8')
  allowedCommandBinaries = new Set(saved)
  logger.info(`[CommandWhitelist] 白名单已更新: ${saved.length} 项`)
  return saved
}

// ==================== 命令白名单 IPC ====================

/** 获取当前生效的命令白名单及内置默认（供系统设置页展示/恢复默认） */
ipcMain.handle('get-command-whitelist', () => ({
  allowedBinaries: Array.from(allowedCommandBinaries),
  defaults: DEFAULT_ALLOWED_COMMAND_BINARIES,
}))

/** 保存命令白名单（系统设置页），立即生效并持久化到 userData/command-whitelist.json */
ipcMain.handle('set-command-whitelist', (_event, payload: { allowedBinaries?: unknown }) => {
  const saved = persistCommandWhitelist(payload?.allowedBinaries)
  return { allowedBinaries: saved, defaults: DEFAULT_ALLOWED_COMMAND_BINARIES }
})

/** 命令参数合法字符集：ASCII 安全字符 + 任意非 ASCII（中文文件名等），拒绝 shell 元字符 / 注入 */
const SAFE_ARG_TOKEN = /^(?:[A-Za-z0-9_./:@+=~-]|[\u{0080}-\u{10FFFF}])+$/u

function isAllowedExternalUrl(rawUrl: string): boolean {
  try {
    return ALLOWED_EXTERNAL_PROTOCOLS.has(new URL(rawUrl).protocol)
  } catch {
    return false
  }
}

function isAllowedInternalUrl(rawUrl: string): boolean {
  try {
    const url = new URL(rawUrl)
    if (isDev) {
      return url.origin === new URL(getDevServerUrl()).origin
    }
    if (url.protocol === 'file:') {
      const rendererDir = path.resolve(__dirname, '../renderer')
      const resolved = path.resolve(decodeURIComponent(url.pathname))
      return resolved === rendererDir || resolved.startsWith(rendererDir + path.sep)
    }
    return false
  } catch {
    return false
  }
}

/**
 * 窗口安全防护：拦截 window.open / 站外导航
 * 允许的 http(s)/自定义协议改走系统默认浏览器，其余一律 deny
 */
function attachWindowSecurity(win: BrowserWindow): void {
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (isAllowedExternalUrl(url)) {
      logger.info(`[Security] window.open 转交系统浏览器: ${url}`)
      shell.openExternal(url).catch(() => {})
    } else {
      logger.error(`[Security] window.open 已拦截: ${url}`)
    }
    return { action: 'deny' }
  })

  win.webContents.on('will-navigate', (event, url) => {
    if (!isAllowedInternalUrl(url)) {
      event.preventDefault()
      if (isAllowedExternalUrl(url)) {
        logger.info(`[Security] 站外导航转交系统浏览器: ${url}`)
        shell.openExternal(url).catch(() => {})
      } else {
        logger.error(`[Security] 非法导航已拦截: ${url}`)
      }
    }
  })
}

/**
 * 将渲染进程关键事件转发到主进程文件日志
 * 覆盖：加载失败 / 渲染进程崩溃 / 无响应 / console warning & error
 */
function attachRendererLogging(win: BrowserWindow): void {
  win.webContents.on('did-fail-load', (_e, errorCode, errorDescription, validatedURL) => {
    logger.error(`[Renderer] 加载失败: ${errorCode} ${errorDescription} | ${validatedURL}`)
  })
  win.webContents.on('render-process-gone', (_e, details) => {
    logger.error(`[Renderer] 渲染进程退出: ${details.reason} | exitCode=${details.exitCode}`)
  })
  win.webContents.on('unresponsive', () => {
    logger.error('[Renderer] 渲染进程无响应')
  })
  win.webContents.on('console-message', (details) => {
    // 新 API：details 为 Event<WebContentsConsoleMessageEventParams>，参数直接挂在对象上
    // level: 'verbose' | 'info' | 'warning' | 'error' — 只转发 warning/error，避免刷屏
    if (details.level === 'error' || details.level === 'warning') {
      const tag = `[Renderer:${path.basename(details.sourceId || '')}]`
      const line = ` (line ${details.lineNumber})`
      if (details.level === 'error') {
        logger.error(`${tag} ${details.message}${line}`)
      } else {
        logger.info(`${tag} ${details.message}${line}`)
      }
    }
  })
}

let mainWindow: BrowserWindow | null = null

const overlayWindows: Map<string, BrowserWindow> = new Map()

function getDevServerUrl(): string {
  return process.env.VITE_DEV_SERVER_URL || 'http://guineapig-client.local:5174'
}

/**
 * 创建主窗口 — 对话页（默认渲染进程）
 */
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,

    webPreferences: {
      preload: path.join(__dirname, 'preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    },

    frame: true,
    show: false,
    backgroundColor: '#ffffff',
    title: 'guineapig-client'
  })

  attachWindowSecurity(mainWindow)
  attachRendererLogging(mainWindow)

  if (isDev) {
    mainWindow.loadURL(getDevServerUrl())
    // 可选：自动打开开发者工具（调试用）
    mainWindow.webContents.openDevTools()
  } else {
    mainWindow.loadFile(path.join(__dirname, '../renderer/index.html'))
  }

  mainWindow.once('ready-to-show', () => {
    logger.info('[Window] 主窗口就绪')
    mainWindow?.maximize()
    mainWindow?.show()
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })
}

const pageTitles: Record<string, string> = {
  'avatar': '头像',
  'chat-history': '对话历史',
  'ai-capabilities': 'AI能力',
  'my-resources': '我的资源',
  'notification-channels': '通知渠道',
  'system-settings': '系统设置'
}

/**
 * 创建覆盖窗口（独立渲染进程，模态覆盖主页）
 */
function createOverlayWindow(page: string, queryString?: string) {
  const title = pageTitles[page] || page

  // 如果窗口已存在，聚焦并返回
  const existing = overlayWindows.get(page)
  if (existing && !existing.isDestroyed()) {
    // 传入额外参数时重新导航（如 tab 切换）
    if (queryString) {
      if (isDev) {
        existing.loadURL(`${getDevServerUrl()}overlay.html?page=${page}&${queryString}`)
      } else {
        existing.loadFile(path.join(__dirname, '../renderer/overlay.html'), { query: { page, ...Object.fromEntries(new URLSearchParams(queryString)) } })
      }
    }
    existing.focus()
    return
  }

  const [pw, ph] = mainWindow?.getSize() || [1200, 800]
  const [px, py] = mainWindow?.getPosition() || [0, 0]

  const win = new BrowserWindow({
    width: pw,
    height: ph,
    x: px,
    y: py,
    parent: mainWindow || undefined,
    modal: true,

    webPreferences: {
      preload: path.join(__dirname, 'preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    },

    frame: true,
    show: false,
    backgroundColor: '#ffffff',
    title: `${title} - guineapig-client`
  })

  attachWindowSecurity(win)
  attachRendererLogging(win)

  if (isDev) {
    const url = `${getDevServerUrl()}overlay.html?page=${page}${queryString ? `&${queryString}` : ''}`
    win.loadURL(url)
  } else {
    const query: Record<string, string> = { page }
    if (queryString) {
      Object.assign(query, Object.fromEntries(new URLSearchParams(queryString)))
    }
    win.loadFile(path.join(__dirname, '../renderer/overlay.html'), { query })
  }

  if (isDev) {
    // 开发模式下自动打开 overlay 调试工具
    win.webContents.openDevTools()
  }

  win.once('ready-to-show', () => {
    logger.info(`[Window] 覆盖窗口就绪: ${page}`)
    win.show()
  })

  win.on('closed', () => {
    overlayWindows.delete(page)
  })

  overlayWindows.set(page, win)
}

app.whenReady().then(() => {
  logger.info('应用启动')
  loadCommandWhitelist()
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

app.on('window-all-closed', () => {
  logger.info('所有窗口已关闭')
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('before-quit', () => {
  logger.info('应用即将退出')
  void closeAllMcpConnections()
})

// ==================== 开发者工具 ====================

/**
 * 切换 DevTools（通过 IPC 触发，renderer 侧可按 F12 调用）
 * 仅开发模式生效，生产环境禁用
 */
ipcMain.on('toggle-devtools', (event) => {
  if (!isDev) return
  const win = BrowserWindow.fromWebContents(event.sender)
  if (win) {
    if (win.webContents.isDevToolsOpened()) {
      win.webContents.closeDevTools()
    } else {
      win.webContents.openDevTools()
    }
  }
})

/**
 * 返回应用运行状态（preload 用它判断是否启用 DevTools 快捷键）
 */
ipcMain.handle('get-app-state', () => {
  return { isDev }
})

/**
 * 获取 RSA 公钥内容（登录加密用）
 * - 开发模式：读取项目 public/public.key（Vite 以站点根服务 /public.key）
 * - 打包模式：从 extraResources 拷贝的 resources/public/public.key 读取
 *   （打包后 renderer 以 file:// 加载，fetch('/public.key') 不可用）
 */
ipcMain.handle('get-public-key', async () => {
  const candidates = isDev
    ? [path.join(__dirname, '../../public/public.key')]
    : [path.join(process.resourcesPath, 'public', 'public.key')]

  for (const p of candidates) {
    try {
      if (fs.existsSync(p)) {
        return fs.readFileSync(p, 'utf-8')
      }
    } catch (err) {
      logger.error(`读取公钥失败: ${p}, ${err}`)
    }
  }
  throw new Error('public.key 不存在')
})

// ==================== IPC 通信处理 ====================

ipcMain.handle('show-dialog', async (_event, options) => {
  const result = await dialog.showMessageBox(mainWindow!, options)
  return result
})

ipcMain.handle('get-app-version', () => {
  return app.getVersion()
})

ipcMain.handle('platform-info', () => {
  return {
    platform: process.platform,
    arch: process.arch,
    version: process.version
  }
})

ipcMain.handle('get-system-memory-info', () => {
  return process.getSystemMemoryInfo()
})

ipcMain.handle('get-versions', () => {
  return {
    node: process.versions.node,
    electron: process.versions.electron,
    chrome: process.versions.chrome
  }
})

/**
 * 获取当前设备唯一 ID
 */
ipcMain.handle('get-machine-id', async () => {
  return machineId()
})

/**
 * 打开覆盖窗口（按页面名称）
 */
ipcMain.handle('open-overlay-window', (_event, page: string, queryString?: string) => {
  logger.info(`[Overlay] 打开页面: ${page}${queryString ? `?${queryString}` : ''}`)
  createOverlayWindow(page, queryString)
})

/**
 * 关闭调用者所在的窗口
 */
ipcMain.on('close-window', (event) => {
  BrowserWindow.fromWebContents(event.sender)?.close()
})

/**
 * 保存临时文件（用于录音缓存）
 * data.dateDir — 二级目录名（如 20260603），自动创建
 * data.filename — 文件名（如 a1b2c3.mp3）
 * 保存至 userData/temp/{dateDir}/{filename}
 */
ipcMain.handle('save-temp-file', async (_event, data: { buffer: number[]; filename: string; dateDir?: string }) => {
  const filename = path.basename(data.filename || '')
  if (!filename) {
    logger.error(`[TempFile] 拒绝（文件名无效）: ${JSON.stringify(data.filename)}`)
    throw new Error('文件名无效')
  }
  if (data.dateDir && !/^\d{8}$/.test(data.dateDir)) {
    logger.error(`[TempFile] 拒绝（日期目录格式无效）: ${data.dateDir}`)
    throw new Error('日期目录格式无效')
  }
  let tempDir = path.join(app.getPath('userData'), 'temp')
  if (data.dateDir) {
    tempDir = path.join(tempDir, data.dateDir)
  }
  if (!fs.existsSync(tempDir)) {
    fs.mkdirSync(tempDir, { recursive: true })
  }
  const filePath = path.join(tempDir, filename)
  fs.writeFileSync(filePath, Buffer.from(data.buffer))
  logger.info(`[TempFile] 已保存: ${filePath} (${data.buffer?.length || 0}B)`)
  return filePath
})

/**
 * 读取本地文件，返回 ArrayBuffer（用于音频播放等）
 * 仅允许读取 userData 目录内的文件，防止任意文件读取
 */
ipcMain.handle('read-local-file', async (_event, filePath: string) => {
  const userDataRoot = path.resolve(app.getPath('userData'))
  const resolved = path.isAbsolute(filePath)
    ? path.resolve(filePath)
    : path.resolve(userDataRoot, filePath)

  if (resolved !== userDataRoot && !resolved.startsWith(userDataRoot + path.sep)) {
    logger.error(`[ReadLocalFile] 拒绝（越界读取）: ${filePath}`)
    throw new Error('无权读取该文件')
  }
  if (!fs.existsSync(resolved)) {
    logger.error(`[ReadLocalFile] 文件不存在: ${filePath}`)
    throw new Error('文件不存在')
  }
  const buffer = fs.readFileSync(resolved)
  logger.info(`[ReadLocalFile] 已读取: ${resolved} (${buffer.length}B)`)
  return buffer.buffer as ArrayBuffer
})

/**
 * 下载并解压 Skill zip 文件到 userData/skills/{skillName}/
 * 自动去除 zip 内公共顶层目录，确保只有一层 skillName
 * 如果同名 skill 已存在，直接覆盖
 * 使用 JS 解压库（adm-zip），禁用 shell unzip（防命令注入/路径穿越）
 */
ipcMain.handle('download-and-extract-skill', async (_event, data: { url: string; skillName: string }) => {
  const skillName = path.basename((data.skillName || '').trim())
  // 允许字母/数字/中文/点/连字符/空格等，仅拒绝路径分隔与危险字符（防目录穿越 / 覆盖 skillsBase）
  if (
    !skillName ||
    skillName === '.' ||
    skillName === '..' ||
    /[\/\\:*?"<>|\x00-\x1f]/.test(skillName)
  ) {
    logger.error(`[Skill] 技能名称不合法: ${JSON.stringify(data.skillName)}`)
    throw new Error('技能名称不合法')
  }

  const skillsBase = path.join(app.getPath('userData'), 'skills')
  const extractDir = path.join(skillsBase, skillName)

  // 如果已存在则删除重建（覆盖）
  if (fs.existsSync(extractDir)) {
    fs.rmSync(extractDir, { recursive: true })
  }

  logger.info(`[Skill] 开始下载解压: ${skillName}`)

  // 下载 zip 到临时文件
  const tmpZip = path.join(skillsBase, `${skillName}.zip`)
  const response = await fetch(data.url)
  if (!response.ok) {
    logger.error(`[Skill] 下载失败: ${skillName} | ${response.statusText}`)
    throw new Error(`下载失败: ${response.statusText}`)
  }
  const buffer = Buffer.from(await response.arrayBuffer())
  fs.writeFileSync(tmpZip, buffer)

  let writtenCount = 0
  try {
    const zip = new AdmZip(buffer)
    const entries = zip.getEntries()

    // 校验并收集安全条目（防 ../ 穿越 / 绝对路径），跳过 __MACOSX / 隐藏目录
    const safeEntries: { parts: string[]; data: Buffer }[] = []
    const topLevel = new Set<string>()
    const seenDirs = new Set<string>()

    for (const entry of entries) {
      const entryName = entry.entryName.replace(/\\/g, '/')
      const parts = entryName.split('/').filter(Boolean)
      if (parts.length === 0) continue

      if (entryName.startsWith('/') || /^[a-zA-Z]:/.test(entryName)) {
        throw new Error('ZIP 条目路径不合法')
      }
      if (parts.includes('..')) {
        throw new Error('ZIP 条目路径不合法')
      }
      if (parts.some(p => p.startsWith('__MACOSX') || p.startsWith('.'))) continue

      if (entry.isDirectory) {
        seenDirs.add(parts[0])
        continue
      }
      topLevel.add(parts[0])
      safeEntries.push({ parts, data: entry.getData() })
    }

    // 检测是否所有文件共享一个公共顶层目录
    let commonPrefix: string | null = null
    if (topLevel.size === 1) {
      const only = [...topLevel][0]
      const hasDeeper = safeEntries.some(e => e.parts.length > 1 && e.parts[0] === only)
      if (seenDirs.has(only) || hasDeeper) {
        commonPrefix = only
      }
    }

    fs.mkdirSync(extractDir, { recursive: true })
    for (const { parts, data } of safeEntries) {
      const rel = commonPrefix && parts[0] === commonPrefix ? parts.slice(1) : parts
      if (rel.length === 0) continue
      const dest = path.resolve(extractDir, ...rel)
      if (!dest.startsWith(path.resolve(extractDir) + path.sep)) {
        throw new Error('ZIP 解压路径越界')
      }
      fs.mkdirSync(path.dirname(dest), { recursive: true })
      fs.writeFileSync(dest, data)
      writtenCount++
    }
  } catch (err: any) {
    logger.error(`[Skill] 解压失败: ${skillName} | ${err.message || '未知错误'}`)
    throw new Error(`解压失败: ${err.message || '未知错误'}`)
  } finally {
    // 清理临时文件
    if (fs.existsSync(tmpZip)) {
      fs.unlinkSync(tmpZip)
    }
  }

  logger.info(`[Skill] 技能就绪: ${skillName} | ${extractDir} | ${writtenCount} 个文件`)
  return extractDir
})

/**
 * 在本地执行 CLI 命令（由 ChatPage 的 skill command dialog 触发）
 * 在 userData/skills/ 目录下执行，仅允许白名单二进制，拒绝 shell 元字符注入
 */
ipcMain.handle('execute-command', async (event, cmd: {
  type: string
  description: string
  command: string
  cwd?: string
  risk: string
}) => {
  if (!cmd || typeof cmd.command !== 'string' || !cmd.command.trim()) {
    logger.error(`[Command] 拒绝（参数无效）: ${JSON.stringify(cmd)}`)
    throw new Error('命令为空')
  }

  logger.info(`[Command] 收到: type=${cmd.type || '?'} | risk=${cmd.risk || '?'} | cwd=${cmd.cwd || '(默认)'} | ${cmd.command}`)

  const skillsBase = path.join(app.getPath('userData'), 'skills')
  fs.mkdirSync(skillsBase, { recursive: true })

  // cwd 限制在 userData/skills 下，禁止绝对路径与 ..
  let workingDir = skillsBase
  if (cmd.cwd) {
    const raw = String(cmd.cwd).trim()
    if (!raw) {
      workingDir = skillsBase
    } else {
      if (path.isAbsolute(raw)) {
        logger.error(`[Command] 拒绝（cwd 绝对路径）: ${raw}`)
        throw new Error('cwd 不允许绝对路径')
      }
      if (raw.split(/[\\/]/).includes('..')) {
        logger.error(`[Command] 拒绝（cwd .. 路径）: ${raw}`)
        throw new Error('cwd 不允许 .. 路径')
      }
      const resolved = path.resolve(skillsBase, raw)
      if (resolved !== skillsBase && !resolved.startsWith(skillsBase + path.sep)) {
        logger.error(`[Command] 拒绝（cwd 超出技能目录）: ${raw}`)
        throw new Error('cwd 超出技能目录')
      }
      workingDir = resolved
    }
  }

  // 非 low 风险命令需在主进程侧二次确认（不信任 renderer 传参）
  if (cmd.risk !== 'low') {
    const win = BrowserWindow.fromWebContents(event.sender)
    const opts: Electron.MessageBoxOptions = {
      type: 'warning',
      message: '确认执行命令？',
      detail: `命令: ${cmd.command}\n风险等级: ${cmd.risk || '未知'}\n描述: ${cmd.description || '无'}`,
      buttons: ['取消', '确认执行'],
      defaultId: 1,
      cancelId: 0,
      noLink: true,
    }
    const { response } = win
      ? await dialog.showMessageBox(win, opts)
      : await dialog.showMessageBox(opts)
    if (response !== 1) {
      logger.info(`[Command] 用户取消: ${cmd.command}`)
      throw new Error('命令已取消')
    }
    logger.info(`[Command] 用户已确认: ${cmd.command}`)
  }

  // 解析命令并校验白名单（首 token 二进制 + 参数安全字符集）
  const tokens = tokenizeCommand(cmd.command)
  if (tokens.length === 0) {
    logger.error(`[Command] 拒绝（命令为空）: ${cmd.command}`)
    throw new Error('命令为空')
  }
  const binary = tokens[0]
  if (!isAllowedBinary(binary, workingDir, skillsBase)) {
    logger.error(`[Command] 拒绝（不在白名单）: ${binary} | ${cmd.command}`)
    throw new Error(`命令不在白名单内: ${binary}`)
  }
  const args = tokens.slice(1)
  for (const arg of args) {
    if (!SAFE_ARG_TOKEN.test(arg)) {
      logger.error(`[Command] 拒绝（参数非法）: ${arg} | ${cmd.command}`)
      throw new Error(
        `命令参数包含非法字符: ${arg}（不支持 shell 重定向/管道等操作符，技能请改用白名单内二进制直接写文件）`
      )
    }
  }

  logger.info(`[Command] 执行: ${cmd.command} | cwd: ${workingDir} | risk: ${cmd.risk}`)

  // 显式构造 env，避免隐式继承
  const env: NodeJS.ProcessEnv = {
    PATH: process.env.PATH || '',
    HOME: process.env.HOME || '',
    USER: process.env.USER || '',
    SHELL: process.env.SHELL || '',
    LANG: process.env.LANG || 'en_US.UTF-8',
    LC_ALL: process.env.LC_ALL || process.env.LANG || 'en_US.UTF-8',
    SYSTEMROOT: process.env.SYSTEMROOT || '',
  }

  // Windows 下 npx/npm 为 .cmd shim，需要 shell 执行；参数已通过安全校验
  let bin = binary
  let useShell = false
  if (process.platform === 'win32') {
    const lower = binary.toLowerCase()
    if (lower === 'npx' || lower === 'npm') {
      bin = `${lower}.cmd`
      useShell = true
    }
  }

  return new Promise<{ stdout: string; stderr: string; exitCode: number }>((resolve) => {
    const child = spawn(bin, args, {
      cwd: workingDir,
      env,
      shell: useShell,
      timeout: 300000,
      windowsHide: true,
    })
    let stdout = ''
    let stderr = ''
    child.stdout.setEncoding('utf8')
    child.stderr.setEncoding('utf8')
    child.stdout.on('data', (d: string) => { stdout += d })
    child.stderr.on('data', (d: string) => { stderr += d })
    child.on('error', (err) => {
      logger.error(`[Command] 启动失败: ${cmd.command} | ${err.message}`)
      resolve({ stdout, stderr: stderr || err.message, exitCode: -1 })
    })
    child.on('close', (code) => {
      logger.info(
        `[Command] 完成: exit=${code ?? -1} | stdout=${stdout.length}B stderr=${stderr.length}B | ${cmd.command}`
      )
      if (stdout.trim()) logger.info(`[Command] stdout: ${truncate(stdout, 500)}`)
      if (stderr.trim()) logger.error(`[Command] stderr: ${truncate(stderr, 500)}`)
      resolve({ stdout, stderr, exitCode: code ?? -1 })
    })
  })
})

/** 截断长文本（日志只保留前 max 字符） */
function truncate(s: string, max = 500): string {
  if (s.length <= max) return s
  return `${s.slice(0, max)}...(截断 ${s.length - max}B)`
}

function tokenizeCommand(command: string): string[] {
  const tokens: string[] = []
  let current = ''
  let quote: string | null = null
  for (const ch of command) {
    if (quote) {
      if (ch === quote) {
        quote = null
      } else {
        current += ch
      }
    } else if (ch === "'" || ch === '"') {
      quote = ch
    } else if (ch === ' ' || ch === '\t') {
      if (current) {
        tokens.push(current)
        current = ''
      }
    } else {
      current += ch
    }
  }
  if (current) {
    tokens.push(current)
  }
  return tokens
}

function isAllowedBinary(binary: string, workingDir: string, skillsBase: string): boolean {
  const base = binary.toLowerCase()
  if (allowedCommandBinaries.has(base)) return true
  // 允许白名单内二进制以绝对/带路径形式出现（如 /usr/bin/open → basename open）
  if (allowedCommandBinaries.has(path.basename(base))) return true
  if (binary.includes('/') || binary.includes('\\')) {
    const resolved = path.resolve(workingDir, binary)
    if (resolved === skillsBase || resolved.startsWith(skillsBase + path.sep)) {
      return fs.existsSync(resolved)
    }
  }
  return false
}

// ==================== MCP 资源获取 ====================

/**
 * 连接 MCP Server 获取 tools/resources/prompts
 * 支持 stdio / sse / streamable-http 三种协议
 */
ipcMain.handle('fetch-mcp-resources', async (_event, params: {
  type: 'stdio' | 'sse' | 'streamablehttp'
  command?: string
  args?: string
  url?: string
  headers?: string
  env_vars?: string
  timeout?: number
}) => {
  const controller = new AbortController()
  let timeoutId: ReturnType<typeof setTimeout> | undefined

  logger.info(
    `[MCP] 获取资源: type=${params.type} | command=${params.command || ''} | url=${params.url || ''}`
  )

  try {
    const { Client } = await import('@modelcontextprotocol/sdk/client/index.js')

    // 创建 Transport
    let transport: any
    let timeout = params.timeout || 30000

    if (params.type === 'stdio') {
      const { StdioClientTransport } = await import('@modelcontextprotocol/sdk/client/stdio.js')
      const args = params.args ? params.args.trim().split(/\s+/) : []
      const env: Record<string, string> = {}
      if (params.env_vars) {
        params.env_vars.split('\n').forEach(line => {
          const trimmed = line.trim()
          if (trimmed) {
            const eqIdx = trimmed.indexOf('=')
            if (eqIdx > 0) {
              env[trimmed.substring(0, eqIdx).trim()] = trimmed.substring(eqIdx + 1).trim()
            }
          }
        })
      }
      transport = new StdioClientTransport({
        command: params.command || '',
        args,
        env: Object.keys(env).length > 0 ? env : undefined,
      })
    } else if (params.type === 'sse') {
      const { SSEClientTransport } = await import('@modelcontextprotocol/sdk/client/sse.js')
      const headers: Record<string, string> = {}
      if (params.headers) {
        params.headers.split('\n').forEach(line => {
          const trimmed = line.trim()
          if (trimmed) {
            const colonIdx = trimmed.indexOf(':')
            if (colonIdx > 0) {
              headers[trimmed.substring(0, colonIdx).trim()] = trimmed.substring(colonIdx + 1).trim()
            }
          }
        })
      }
      transport = new SSEClientTransport(new URL(params.url || ''), {
        eventSourceInit: { fetch: (url: string | URL, init?: RequestInit) => fetch(url, { ...init, headers: { ...headers } }) }
      })
    } else if (params.type === 'streamablehttp') {
      const { StreamableHTTPClientTransport } = await import('@modelcontextprotocol/sdk/client/streamableHttp.js')
      const headers: Record<string, string> = {}
      if (params.headers) {
        params.headers.split('\n').forEach(line => {
          const trimmed = line.trim()
          if (trimmed) {
            const colonIdx = trimmed.indexOf(':')
            if (colonIdx > 0) {
              headers[trimmed.substring(0, colonIdx).trim()] = trimmed.substring(colonIdx + 1).trim()
            }
          }
        })
      }
      transport = new StreamableHTTPClientTransport(new URL(params.url || ''), {
        requestInit: Object.keys(headers).length > 0 ? { headers } : undefined,
      })
    } else {
      throw new Error(`不支持的连接类型: ${params.type}`)
    }

    if (timeout > 0) {
      timeoutId = setTimeout(() => controller.abort(), timeout)
    }

    const client = new Client(
      { name: 'guineapig-client', version: '1.0.0' },
      { capabilities: {} }
    )

    await client.connect(transport)

    // 并行获取 tools / resources / prompts
    const [toolsResult, resourcesResult, promptsResult]: any[] = await Promise.all([
      client.listTools().catch(() => ({ tools: [] })),
      client.listResources().catch(() => ({ resources: [] })),
      client.listPrompts().catch(() => ({ prompts: [] })),
    ])

    // 关闭连接
    await client.close().catch(() => {})

    const tools = (toolsResult?.tools || []).map((t: any) => ({
      name: t.name,
      description: t.description || '',
      input_schema: t.inputSchema || t.input_schema || null,
    }))
    const resources = (resourcesResult?.resources || []).map((r: any) => ({
      uri: r.uri,
      name: r.name,
      description: r.description || '',
      mimeType: r.mimeType || '',
    }))
    const prompts = (promptsResult?.prompts || []).map((p: any) => ({
      name: p.name,
      description: p.description || '',
    }))
    logger.info(
      `[MCP] 获取成功: type=${params.type} | tools=${tools.length} resources=${resources.length} prompts=${prompts.length}`
    )

    return { tools, resources, prompts }
  } catch (err: any) {
    logger.error(`[MCP] 获取失败: type=${params.type} | ${err.message}`)
    throw new Error(`获取 MCP 资源失败: ${err.message}`)
  } finally {
    if (timeoutId) clearTimeout(timeoutId)
  }
})

// ==================== 执行 MCP 工具 ====================

// ==================== MCP 连接池 ====================

/** 单个 MCP 连接的池条目 */
interface McpPoolEntry {
  key: string
  client: any
  transport: any
  lastUsed: number
}

/** MCP 连接池：key = server_name（无则用 transport 特征串），复用避免重复 spawn stdio 进程 */
const mcpConnectionPool = new Map<string, McpPoolEntry>()

/** 连接空闲回收阈值：超过该时长未使用则自动关闭（ms） */
const MCP_IDLE_TIMEOUT_MS = 5 * 60 * 1000

/** 空闲回收扫描间隔（ms） */
const MCP_IDLE_REAP_INTERVAL_MS = 60 * 1000

/** 构建连接池 key：优先 server_name，回退到传输特征串 */
function buildMcpPoolKey(params: {
  type?: string
  server_name?: string
  command?: string
  args?: string[] | string
  url?: string
}): string {
  if (params.server_name) {
    return `mcp:${params.server_name}`
  }
  const rawType = params.type || 'streamable_http'
  const sdkType = rawType === 'streamable_http' ? 'streamablehttp' : rawType
  if (sdkType === 'stdio') {
    return `stdio:${params.command || ''}:${JSON.stringify(params.args || [])}`
  }
  return `${sdkType}:${params.url || ''}`
}

/** 创建 MCP Transport（stdio / sse / streamable-http） */
async function createMcpTransport(params: {
  type?: string
  command?: string
  args?: string[] | string
  env?: Record<string, string>
  url?: string
  headers?: Record<string, string> | string
}): Promise<any> {
  const rawType = params.type || 'streamable_http'
  const sdkType = rawType === 'streamable_http' ? 'streamablehttp' : rawType

  if (sdkType === 'stdio') {
    const { StdioClientTransport } = await import('@modelcontextprotocol/sdk/client/stdio.js')
    const args = Array.isArray(params.args)
      ? params.args
      : params.args
        ? params.args.trim().split(/\s+/)
        : []
    const env: Record<string, string> = {}
    if (params.env && typeof params.env === 'object') {
      Object.assign(env, params.env)
    }
    if (!params.command) {
      throw new Error('stdio MCP 缺少 command 配置')
    }
    return new StdioClientTransport({
      command: params.command,
      args,
      env: Object.keys(env).length > 0 ? env : undefined,
    })
  }

  const parseHeaders = (): Record<string, string> => {
    const headers: Record<string, string> = {}
    if (params.headers) {
      if (typeof params.headers === 'object') {
        Object.assign(headers, params.headers)
      } else {
        params.headers.split('\n').forEach(line => {
          const trimmed = line.trim()
          if (trimmed) {
            const colonIdx = trimmed.indexOf(':')
            if (colonIdx > 0) {
              headers[trimmed.substring(0, colonIdx).trim()] = trimmed.substring(colonIdx + 1).trim()
            }
          }
        })
      }
    }
    return headers
  }

  if (sdkType === 'sse') {
    const { SSEClientTransport } = await import('@modelcontextprotocol/sdk/client/sse.js')
    const headers = parseHeaders()
    return new SSEClientTransport(new URL(params.url || ''), {
      eventSourceInit: { fetch: (url: string | URL, init?: RequestInit) => fetch(url, { ...init, headers: { ...headers } }) }
    })
  }

  if (sdkType === 'streamablehttp') {
    const { StreamableHTTPClientTransport } = await import('@modelcontextprotocol/sdk/client/streamableHttp.js')
    const headers = parseHeaders()
    return new StreamableHTTPClientTransport(new URL(params.url || ''), {
      requestInit: Object.keys(headers).length > 0 ? { headers } : undefined,
    })
  }

  throw new Error(`不支持的连接类型: ${sdkType}`)
}

/** 关闭并移除指定 key 的连接 */
async function closeMcpConnection(key: string): Promise<void> {
  const entry = mcpConnectionPool.get(key)
  if (!entry) return
  mcpConnectionPool.delete(key)
  try {
    await entry.client.close()
  } catch { /* ignore */ }
  logger.info(`[MCP] 连接已关闭: ${key}`)
}

/** 关闭池内全部连接（应用退出 / 显式清理） */
async function closeAllMcpConnections(): Promise<void> {
  const keys = [...mcpConnectionPool.keys()]
  await Promise.all(keys.map(k => closeMcpConnection(k)))
}

/** 空闲回收：扫描并关闭超时未用的连接 */
function reapIdleMcpConnections(): void {
  const now = Date.now()
  for (const [key, entry] of mcpConnectionPool.entries()) {
    if (now - entry.lastUsed > MCP_IDLE_TIMEOUT_MS) {
      logger.info(`[MCP] 空闲回收连接: ${key}`)
      void closeMcpConnection(key)
    }
  }
}

// 定时扫描空闲连接
setInterval(reapIdleMcpConnections, MCP_IDLE_REAP_INTERVAL_MS)

/**
 * 连接 MCP Server 并调用指定工具（callTool）。
 * 支持 stdio / sse / streamable-http 三种协议。
 * stdio 需传 command/args/env；远程类型传 url/headers。
 * 复用连接池：同一 server 首次连接后缓存，后续步骤复用（避免重复 spawn stdio 进程）。
 */
ipcMain.handle('call-mcp-tool', async (_event, params: {
  type?: string
  server_name?: string
  command?: string
  args?: string[] | string
  env?: Record<string, string>
  url?: string
  headers?: Record<string, string> | string
  tool: string
  arguments?: any
  timeout?: number
}) => {
  const key = buildMcpPoolKey(params)
  logger.info(
    `[MCP] 调用工具: key=${key} | type=${params.type || ''} | tool=${params.tool} | command=${params.command || ''} | url=${params.url || ''} | args=${JSON.stringify(params.args) || ''} | env=${JSON.stringify(params.env) || ''} | headers=${typeof params.headers === 'string' ? params.headers : JSON.stringify(params.headers) || ''} | arguments=${JSON.stringify(params.arguments) || ''}`
  )

  const timeout = params.timeout || 30000
  const timer = new Promise<never>((_, reject) => {
    setTimeout(() => reject(new Error(`MCP 工具执行超时 (${timeout}s)`)), timeout)
  })

  try {
    // 命中连接池 → 复用；未命中 → 建立新连接
    let entry = mcpConnectionPool.get(key)
    let isNew = false
    if (!entry) {
      const { Client } = await import('@modelcontextprotocol/sdk/client/index.js')
      const transport = await createMcpTransport(params)
      const client = new Client(
        { name: 'guineapig-client', version: '1.0.0' },
        { capabilities: {} }
      )
      await client.connect(transport)
      entry = { key, client, transport, lastUsed: Date.now() }
      mcpConnectionPool.set(key, entry)
      isNew = true
      logger.info(`[MCP] 建立新连接: ${key} (${params.type || 'unknown'})`)
    }
    entry.lastUsed = Date.now()

    const result: any = await Promise.race([
      entry.client.callTool({
        name: params.tool,
        arguments: params.arguments || {},
      }),
      timer,
    ])

    logger.info(
      `[MCP] 工具执行${isNew ? '（新连接）' : '（复用连接）'}成功: key=${key} tool=${params.tool} | isError=${!!result.isError}`
    )
    return {
      result,
      isError: !!result.isError,
      content: result.content || [],
    }
  } catch (err: any) {
    // 调用失败 → 断开该连接，下次调用重建（避免复用坏连接）
    if (mcpConnectionPool.has(key)) {
      logger.warn(`[MCP] 调用失败移除连接: ${key} | ${err.message}`)
      void closeMcpConnection(key)
    }
    logger.error(`[MCP] 工具执行失败: tool=${params.tool} | ${err.message}`)
    throw new Error(`MCP 工具执行失败: ${err.message}`)
  }
})

/**
 * 预热 MCP 连接（仅建立连接，不调用工具）。
 * 在 agent 下发 MCP 步骤时由 renderer 自动触发，提前 spawn stdio 进程，
 * 避免用户点击执行时才等待首次启动。
 */
ipcMain.handle('prepare-mcp-connection', async (_event, params: {
  type?: string
  server_name?: string
  command?: string
  args?: string[] | string
  env?: Record<string, string>
  url?: string
  headers?: Record<string, string> | string
}) => {
  const key = buildMcpPoolKey(params)
  logger.info(
    `[MCP] 预热连接: key=${key} | type=${params.type || ''} | command=${params.command || ''} | url=${params.url || ''}`
  )

  try {
    let entry = mcpConnectionPool.get(key)
    let reused = true
    if (!entry) {
      const { Client } = await import('@modelcontextprotocol/sdk/client/index.js')
      const transport = await createMcpTransport(params)
      const client = new Client(
        { name: 'guineapig-client', version: '1.0.0' },
        { capabilities: {} }
      )
      await client.connect(transport)
      entry = { key, client, transport, lastUsed: Date.now() }
      mcpConnectionPool.set(key, entry)
      reused = false
      logger.info(`[MCP] 预热建立新连接: ${key} (${params.type || 'unknown'})`)
    }
    entry.lastUsed = Date.now()
    return { connected: true, key, reused }
  } catch (err: any) {
    if (mcpConnectionPool.has(key)) {
      void closeMcpConnection(key)
    }
    logger.error(`[MCP] 预热连接失败: key=${key} | ${err.message}`)
    throw new Error(`MCP 连接预热失败: ${err.message}`)
  }
})

/**
 * 关闭全部 MCP 连接（DAG 执行完成后由 renderer 调用，释放 stdio 子进程）
 */
ipcMain.handle('close-mcp-connections', async () => {
  const count = mcpConnectionPool.size
  await closeAllMcpConnections()
  logger.info(`[MCP] 已关闭全部连接: ${count} 个`)
  return { closed: count }
})

// ==================== 打开外部链接 ====================

/**
 * 用系统默认应用打开外部链接
 * 仅允许协议白名单（https/http/amapuri），拒绝 file:/javascript: 等
 */
ipcMain.handle('open-external', async (_event, url: string) => {
  if (typeof url !== 'string' || !isAllowedExternalUrl(url)) {
    logger.error(`[OpenExternal] 拒绝: ${url}`)
    throw new Error(`不允许打开该链接: ${url}`)
  }
  logger.info(`[OpenExternal] 打开: ${url}`)
  await shell.openExternal(url)
})

// ==================== 日志管理 ====================

/**
 * 获取日志文件列表
 * @param keyword — 可选搜索关键词
 */
ipcMain.handle('get-log-files', (_event, keyword?: string) => {
  return logger.getFiles(keyword)
})

/**
 * 删除日志文件
 */
ipcMain.handle('delete-log-file', (_event, filename: string) => {
  return logger.deleteFile(filename)
})

/**
 * 用系统默认文本编辑器打开日志文件
 */
ipcMain.handle('open-log-file', async (_event, filename: string) => {
  const filePath = logger.getFilePath(filename)
  if (!fs.existsSync(filePath)) {
    throw new Error('日志文件不存在')
  }
  await shell.openPath(filePath)
})

/**
 * 选择日期范围，打包下载日志文件为 zip
 */
ipcMain.handle('zip-and-download-logs', async (_event, params: {
  startDate: string  // YYYYMMDD
  endDate: string    // YYYYMMDD
  keyword?: string
}) => {
  const { startDate, endDate, keyword } = params
  const logDir = logger.getLogDir()

  // 收集匹配日期范围的文件
  const allFiles = logger.getFiles(keyword)
  const matchedFiles = allFiles.filter(f => {
    // 文件名格式: YYYYMMDD-error.log → 取前 8 位比较
    const fileDate = f.name.substring(0, 8)
    return fileDate >= startDate && fileDate <= endDate
  })

  if (matchedFiles.length === 0) {
    throw new Error('所选日期范围内没有日志文件')
  }

  // 弹出保存对话框
  const defaultName = `logs-${startDate}-${endDate}.zip`
  const { canceled, filePath } = await dialog.showSaveDialog({
    defaultPath: defaultName,
    filters: [{ name: 'ZIP 文件', extensions: ['zip'] }],
  })

  if (canceled || !filePath) {
    return { cancelled: true }
  }

  logger.info(`[Logs] 开始导出: ${startDate}-${endDate} | ${matchedFiles.length} 个文件`)

  // 创建 zip 并写入
  const { ZipArchive } = await import('archiver')
  return new Promise<{ path: string; count: number }>((resolve, reject) => {
    const output = createWriteStream(filePath)
    const archive = new ZipArchive({ zlib: { level: 9 } })

    output.on('close', () => {
      logger.info(`[Logs] 导出完成: ${filePath} | ${matchedFiles.length} 个文件`)
      resolve({ path: filePath, count: matchedFiles.length })
    })

    archive.on('error', (err) => {
      logger.error(`[Logs] 导出失败: ${err.message}`)
      reject(err)
    })

    archive.pipe(output)

    for (const file of matchedFiles) {
      const fullPath = path.join(logDir, file.name)
      if (fs.existsSync(fullPath)) {
        archive.file(fullPath, { name: file.name })
      }
    }

    archive.finalize()
  })
})

// ==================== 错误处理 ====================

process.on('uncaughtException', (error) => {
  logger.error(`Uncaught Exception: ${error.message}\n${error.stack || ''}`)
})
