import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('electronAPI', {
  showDialog: (options: any) => ipcRenderer.invoke('show-dialog', options),

  getAppVersion: () => ipcRenderer.invoke('get-app-version'),

  getPlatformInfo: () => ipcRenderer.invoke('platform-info'),

  getSystemMemoryInfo: () => ipcRenderer.invoke('get-system-memory-info'),

  getVersions: () => ipcRenderer.invoke('get-versions'),

  /**
   * 打开覆盖窗口（独立渲染进程，模态覆盖主页）
   * @param page - 页面名称：avatar / chat-history / ai-capabilities / my-resources / notification-channels / system-settings
   */
  getMachineId: () => ipcRenderer.invoke('get-machine-id'),

  openOverlayWindow: (page: string, queryString?: string) => ipcRenderer.invoke('open-overlay-window', page, queryString),

  /**
   * 关闭当前窗口
   */
  closeCurrentWindow: () => ipcRenderer.send('close-window'),

  saveTempFile: (data: { buffer: ArrayBuffer; filename: string; dateDir?: string }) =>
    ipcRenderer.invoke('save-temp-file', data),

  readLocalFile: (filePath: string) =>
    ipcRenderer.invoke('read-local-file', filePath),

  downloadAndExtractSkill: (data: { url: string; skillName: string }) =>
    ipcRenderer.invoke('download-and-extract-skill', data),

  /**
   * 执行 CLI 命令（由 ChatPage skill command dialog 触发）
   */
  executeCommand: (cmd: {
    type: string
    description: string
    command: string
    cwd?: string
    risk: string
  }) => ipcRenderer.invoke('execute-command', cmd),

  /**
   * 获取命令白名单（系统设置页）
   */
  getCommandWhitelist: () => ipcRenderer.invoke('get-command-whitelist'),

  /**
   * 保存命令白名单（系统设置页），立即生效并持久化
   */
  setCommandWhitelist: (binaries: string[]) =>
    ipcRenderer.invoke('set-command-whitelist', { allowedBinaries: binaries }),

  /**
   * 获取 MCP Server 的 tools/resources/prompts
   */
  fetchMcpResources: (params: {
    type: 'stdio' | 'sse' | 'streamablehttp'
    command?: string
    args?: string
    url?: string
    headers?: string
    env_vars?: string
    timeout?: number
  }) => ipcRenderer.invoke('fetch-mcp-resources', params),

  /**
   * 调用 MCP Server 的指定工具（callTool），支持 stdio / sse / streamable-http
   */
  callMcpTool: (params: {
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
  }) => ipcRenderer.invoke('call-mcp-tool', params),

  /**
   * 预热 MCP 连接（仅建立连接不调工具，提前 spawn stdio 进程）
   */
  prepareMcpConnection: (params: {
    type?: string
    server_name?: string
    command?: string
    args?: string[] | string
    env?: Record<string, string>
    url?: string
    headers?: Record<string, string> | string
  }) => ipcRenderer.invoke('prepare-mcp-connection', params),

  /**
   * 关闭全部 MCP 连接（DAG 执行完成后释放 stdio 子进程）
   */
  closeMcpConnections: () => ipcRenderer.invoke('close-mcp-connections'),

  /**
   * 切换开发者工具（F12）
   */
  toggleDevtools: () => ipcRenderer.send('toggle-devtools'),

  /**
   * 获取日志文件列表（支持搜索关键词）
   */
  getLogFiles: (keyword?: string) => ipcRenderer.invoke('get-log-files', keyword),

  /**
   * 删除日志文件
   */
  deleteLogFile: (filename: string) => ipcRenderer.invoke('delete-log-file', filename),

  /**
   * 用系统默认文本编辑器打开日志文件
   */
  openLogFile: (filename: string) => ipcRenderer.invoke('open-log-file', filename),

  /**
   * 选择日期范围打包下载日志为 zip
   */
  zipAndDownloadLogs: (params: {
    startDate: string
    endDate: string
    keyword?: string
  }) => ipcRenderer.invoke('zip-and-download-logs', params),

  /**
   * 获取应用运行状态（如 isDev）
   */
  getAppState: () => ipcRenderer.invoke('get-app-state'),

  /**
   * 获取 RSA 公钥内容（登录加密用）
   * 打包环境以 file:// 加载 renderer，fetch('/public.key') 不可用，故由主进程读取后透传
   */
  getPublicKey: () => ipcRenderer.invoke('get-public-key'),

  /**
   * 用系统默认应用打开外部链接（http/https 及自定义协议如 amapuri://）
   */
  openExternal: (url: string) => ipcRenderer.invoke('open-external', url),

  on: (channel: string, callback: Function) => {
    const validChannels = ['update-progress']
    if (validChannels.includes(channel)) {
      ipcRenderer.on(channel, (_event, ...args) => callback(...args))
    }
  },

  send: (channel: string, data: any) => {
    const validChannels = ['app-ready']
    if (validChannels.includes(channel)) {
      ipcRenderer.send(channel, data)
    }
  }
})

// ========== 全局快捷键 ==========
// F12 切换开发者工具（仅开发模式生效）
ipcRenderer.invoke('get-app-state')
  .then((state: { isDev: boolean }) => {
    if (!state.isDev) return
    document.addEventListener('keydown', (e: KeyboardEvent) => {
      if (e.key === 'F12') {
        e.preventDefault()
        ipcRenderer.send('toggle-devtools')
      }
    })
  })
  .catch(() => {})
