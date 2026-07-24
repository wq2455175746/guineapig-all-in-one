/**
 * Electron 主进程入口文件
 */

import { app, BrowserWindow, ipcMain, dialog, globalShortcut, shell } from 'electron'
import path from 'path'
import fs from 'fs'
import { fileURLToPath } from 'url'
import { execSync, exec } from 'child_process'
import machineIdPkg from 'node-machine-id'
const { machineId } = machineIdPkg
import { createWriteStream } from 'fs'
import { logger } from './logger'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged

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
      webSecurity: false
    },

    frame: true,
    show: false,
    backgroundColor: '#ffffff',
    title: 'guineapig-client'
  })

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
      webSecurity: false
    },

    frame: true,
    show: false,
    backgroundColor: '#ffffff',
    title: `${title} - guineapig-client`
  })

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
 */
ipcMain.on('toggle-devtools', (event) => {
  const win = BrowserWindow.fromWebContents(event.sender)
  if (win) {
    if (win.webContents.isDevToolsOpened()) {
      win.webContents.closeDevTools()
    } else {
      win.webContents.openDevTools()
    }
  }
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
  let tempDir = path.join(app.getPath('userData'), 'temp')
  if (data.dateDir) {
    tempDir = path.join(tempDir, data.dateDir)
  }
  if (!fs.existsSync(tempDir)) {
    fs.mkdirSync(tempDir, { recursive: true })
  }
  const filePath = path.join(tempDir, data.filename)
  fs.writeFileSync(filePath, Buffer.from(data.buffer))
  return filePath
})

/**
 * 读取本地文件，返回 ArrayBuffer（用于音频播放等）
 */
ipcMain.handle('read-local-file', async (_event, filePath: string) => {
  if (!fs.existsSync(filePath)) {
    throw new Error('文件不存在')
  }
  const buffer = fs.readFileSync(filePath)
  return buffer.buffer as ArrayBuffer
})

/**
 * 下载并解压 Skill zip 文件到 userData/skills/{skillName}/
 * 自动去除 zip 内公共顶层目录，确保只有一层 skillName
 * 如果同名 skill 已存在，直接覆盖
 */
ipcMain.handle('download-and-extract-skill', async (_event, data: { url: string; skillName: string }) => {
  const skillsBase = path.join(app.getPath('userData'), 'skills')
  const extractDir = path.join(skillsBase, data.skillName)

  // 如果已存在则删除重建（覆盖）
  if (fs.existsSync(extractDir)) {
    fs.rmSync(extractDir, { recursive: true })
  }

  // 先解压到临时目录以检测公共顶层目录
  const tmpRoot = path.join(skillsBase, `._tmp_${data.skillName}`)
  if (fs.existsSync(tmpRoot)) {
    fs.rmSync(tmpRoot, { recursive: true })
  }
  fs.mkdirSync(tmpRoot, { recursive: true })

  // 下载 zip 到临时文件
  const tmpZip = path.join(skillsBase, `${data.skillName}.zip`)
  const response = await fetch(data.url)
  if (!response.ok) {
    throw new Error(`下载失败: ${response.statusText}`)
  }
  const buffer = Buffer.from(await response.arrayBuffer())
  fs.writeFileSync(tmpZip, buffer)

  try {
    // 解压到临时目录
    execSync(`unzip -o "${tmpZip}" -d "${tmpRoot}"`, { stdio: 'pipe', timeout: 30000 })

    // 检测是否所有文件共享一个公共顶层目录
    const entries = fs.readdirSync(tmpRoot).filter(n => !n.startsWith('__MACOSX') && !n.startsWith('.'))
    let commonPrefix: string | null = null

    if (entries.length === 1) {
      const only = entries[0]
      const onlyPath = path.join(tmpRoot, only)
      if (fs.statSync(onlyPath).isDirectory()) {
        commonPrefix = only
      }
    }

    if (commonPrefix) {
      // 有公共顶层目录 — 将里面的内容上移一层
      const innerDir = path.join(tmpRoot, commonPrefix)
      const innerEntries = fs.readdirSync(innerDir)
      fs.mkdirSync(extractDir, { recursive: true })
      for (const entry of innerEntries) {
        const src = path.join(innerDir, entry)
        const dst = path.join(extractDir, entry)
        fs.renameSync(src, dst)
      }
    } else {
      // 没有公共目录，直接移动所有文件
      fs.mkdirSync(extractDir, { recursive: true })
      for (const entry of entries) {
        const src = path.join(tmpRoot, entry)
        const dst = path.join(extractDir, entry)
        fs.renameSync(src, dst)
      }
    }
  } catch {
    throw new Error('解压失败，请确认系统已安装 unzip')
  } finally {
    // 清理临时文件
    if (fs.existsSync(tmpZip)) {
      fs.unlinkSync(tmpZip)
    }
    if (fs.existsSync(tmpRoot)) {
      fs.rmSync(tmpRoot, { recursive: true })
    }
  }

  return extractDir
})

/**
 * 在本地执行 CLI 命令（由 ChatPage 的 skill command dialog 触发）
 * 在 userData/skills/ 目录下执行，支持 shell/python/npx
 */
ipcMain.handle('execute-command', async (_event, cmd: {
  type: string
  description: string
  command: string
  cwd?: string
  risk: string
}) => {
  const userDataPath = app.getPath('userData')
  const workingDir = cmd.cwd ? path.join(userDataPath, cmd.cwd) : userDataPath

  return new Promise<{ stdout: string; stderr: string; exitCode: number }>((resolve) => {
    exec(cmd.command, { cwd: workingDir, timeout: 300000 }, (err, stdout, stderr) => {
      resolve({
        stdout: stdout || '',
        stderr: stderr || '',
        exitCode: err ? (err.code || -1) : 0,
      })
    })
  })
})

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
 * 用系统默认应用打开外部链接（支持 http/https 及自定义协议如 amapuri://）
 */
ipcMain.handle('open-external', async (_event, url: string) => {
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
