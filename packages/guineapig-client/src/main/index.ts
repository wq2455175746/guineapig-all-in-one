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

/** 命令参数合法字符集（拒绝 shell 元字符 / 注入） */
const SAFE_ARG_TOKEN = /^[A-Za-z0-9_./:@+=~-]+$/

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
      shell.openExternal(url).catch(() => {})
    }
    return { action: 'deny' }
  })

  win.webContents.on('will-navigate', (event, url) => {
    if (!isAllowedInternalUrl(url)) {
      event.preventDefault()
      if (isAllowedExternalUrl(url)) {
        shell.openExternal(url).catch(() => {})
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

  if (isDev) {
    mainWindow.loadURL(getDevServerUrl())
    // 可选：自动打开开发者工具（调试用）
    mainWindow.webContents.openDevTools()
  } else {
    mainWindow.loadFile(path.join(__dirname, '../renderer/index.html'))
  }

  mainWindow.once('ready-to-show', () => {
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
    throw new Error('文件名无效')
  }
  if (data.dateDir && !/^\d{8}$/.test(data.dateDir)) {
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
    throw new Error('无权读取该文件')
  }
  if (!fs.existsSync(resolved)) {
    throw new Error('文件不存在')
  }
  const buffer = fs.readFileSync(resolved)
  return buffer.buffer as ArrayBuffer
})

/**
 * 下载并解压 Skill zip 文件到 userData/skills/{skillName}/
 * 自动去除 zip 内公共顶层目录，确保只有一层 skillName
 * 如果同名 skill 已存在，直接覆盖
 * 使用 JS 解压库（adm-zip），禁用 shell unzip（防命令注入/路径穿越）
 */
ipcMain.handle('download-and-extract-skill', async (_event, data: { url: string; skillName: string }) => {
  const skillName = path.basename(data.skillName || '')
  if (!/^[A-Za-z0-9_-]+$/.test(skillName)) {
    throw new Error('技能名称不合法')
  }

  const skillsBase = path.join(app.getPath('userData'), 'skills')
  const extractDir = path.join(skillsBase, skillName)

  // 如果已存在则删除重建（覆盖）
  if (fs.existsSync(extractDir)) {
    fs.rmSync(extractDir, { recursive: true })
  }

  // 下载 zip 到临时文件
  const tmpZip = path.join(skillsBase, `${skillName}.zip`)
  const response = await fetch(data.url)
  if (!response.ok) {
    throw new Error(`下载失败: ${response.statusText}`)
  }
  const buffer = Buffer.from(await response.arrayBuffer())
  fs.writeFileSync(tmpZip, buffer)

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
    }
  } catch (err: any) {
    throw new Error(`解压失败: ${err.message || '未知错误'}`)
  } finally {
    // 清理临时文件
    if (fs.existsSync(tmpZip)) {
      fs.unlinkSync(tmpZip)
    }
  }

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
    throw new Error('命令为空')
  }

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
        throw new Error('cwd 不允许绝对路径')
      }
      if (raw.split(/[\\/]/).includes('..')) {
        throw new Error('cwd 不允许 .. 路径')
      }
      const resolved = path.resolve(skillsBase, raw)
      if (resolved !== skillsBase && !resolved.startsWith(skillsBase + path.sep)) {
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
      throw new Error('命令已取消')
    }
  }

  // 解析命令并校验白名单（首 token 二进制 + 参数安全字符集）
  const tokens = tokenizeCommand(cmd.command)
  if (tokens.length === 0) {
    throw new Error('命令为空')
  }
  const binary = tokens[0]
  if (!isAllowedBinary(binary, workingDir, skillsBase)) {
    throw new Error(`命令不在白名单内: ${binary}`)
  }
  const args = tokens.slice(1)
  for (const arg of args) {
    if (!SAFE_ARG_TOKEN.test(arg)) {
      throw new Error(`命令参数包含非法字符: ${arg}`)
    }
  }

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
      resolve({ stdout, stderr: stderr || err.message, exitCode: -1 })
    })
    child.on('close', (code) => {
      resolve({ stdout, stderr, exitCode: code ?? -1 })
    })
  })
})

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

    return {
      tools: (toolsResult?.tools || []).map((t: any) => ({
        name: t.name,
        description: t.description || '',
        input_schema: t.inputSchema || t.input_schema || null,
      })),
      resources: (resourcesResult?.resources || []).map((r: any) => ({
        uri: r.uri,
        name: r.name,
        description: r.description || '',
        mimeType: r.mimeType || '',
      })),
      prompts: (promptsResult?.prompts || []).map((p: any) => ({
        name: p.name,
        description: p.description || '',
      })),
    }
  } catch (err: any) {
    throw new Error(`获取 MCP 资源失败: ${err.message}`)
  } finally {
    if (timeoutId) clearTimeout(timeoutId)
  }
})

// ==================== 打开外部链接 ====================

/**
 * 用系统默认应用打开外部链接
 * 仅允许协议白名单（https/http/amapuri），拒绝 file:/javascript: 等
 */
ipcMain.handle('open-external', async (_event, url: string) => {
  if (typeof url !== 'string' || !isAllowedExternalUrl(url)) {
    throw new Error(`不允许打开该链接: ${url}`)
  }
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

  // 创建 zip 并写入
  const { ZipArchive } = await import('archiver')
  return new Promise<{ path: string; count: number }>((resolve, reject) => {
    const output = createWriteStream(filePath)
    const archive = new ZipArchive({ zlib: { level: 9 } })

    output.on('close', () => {
      resolve({ path: filePath, count: matchedFiles.length })
    })

    archive.on('error', (err) => {
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
