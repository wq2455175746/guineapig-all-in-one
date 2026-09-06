/**
 * 全局类型声明文件
 * 通常命名为 env.d.ts 或 shims-vue.d.ts
 * 作用：为 TypeScript 提供全局类型定义，补充 Vite、Vue 和 Electron API 的类型
 * 
 * 注意：这个文件不需要手动导入，TypeScript 会自动识别项目中的 .d.ts 文件
 */

/**
 * 三斜线指令（Triple-Slash Directive）
 * 告诉 TypeScript 编译器引入 Vite 客户端类型定义
 * 
 * 作用：提供 Vite 特有的类型支持，例如：
 * - import.meta.env - 环境变量
 * - import.meta.glob - 批量导入文件
 * - import.meta.hot - 热模块替换（HMR）
 * 
 * 等价于在 tsconfig.json 中配置 "types": ["vite/client"]
 * 但三斜线指令更显式，确保这个文件即使单独也能正常工作
 */
/// <reference types="vite/client" />

/**
 * Vue 单文件组件（.vue 文件）的模块声明
 * 
 * 为什么需要这个？
 * TypeScript 默认不认识 .vue 文件，导入 .vue 文件会报错
 * 这个声明告诉 TypeScript：".vue 文件是一个 Vue 组件模块"
 * 
 * 作用：让 TypeScript 能够理解 import ... from '*.vue' 语句
 */
declare module '*.vue' {
  // 导入 Vue 的类型定义
  import type { DefineComponent } from 'vue'
  
  /**
   * 定义 .vue 文件导出的组件类型
   * 
   * DefineComponent<Props, Emits, Slots> 是 Vue 提供的通用组件类型
   * 这里使用空对象 {} 表示基础组件类型（具体组件有自己的类型推断）
   * 
   * 实际上，Vue 的 Vite 插件会提供更精确的类型（基于 <script setup lang="ts">）
   * 这个声明是兜底方案，确保最基本的类型支持
   */
  const component: DefineComponent<{}, {}, any>
  
  // 默认导出这个组件
  export default component
}

/**
 * 扩展 Window 接口
 * 
 * 作用：为全局 window 对象添加自定义属性（electronAPI）
 * 这样 TypeScript 就能识别 window.electronAPI 了
 * 
 * 为什么需要这个？
 * 预加载脚本中通过 contextBridge.exposeInMainWorld('electronAPI', ...)
 * 在 window 对象上添加了 electronAPI 属性
 * 
 * 如果不声明类型，TypeScript 会报错：
 * Property 'electronAPI' does not exist on type 'Window'
 */
interface Window {
  /**
   * Electron API 对象
   * 由预加载脚本（preload/index.ts）暴露给渲染进程
   * 
   * 作用：提供安全的桥梁，让 Vue 组件能够调用 Electron 原生功能
   * 而无需直接暴露整个 Node.js/Electron API
   */
  electronAPI: {
    /**
     * 显示系统对话框
     * @param options - 对话框配置选项
     * @returns Promise 返回用户操作结果
     * 
     * @example
     * const result = await window.electronAPI.showDialog({
     *   type: 'info',
     *   title: '提示',
     *   message: '操作成功',
     *   buttons: ['确定']
     * })
     */
    showDialog: (options: any) => Promise<any>
    
    /**
     * 获取应用版本号
     * @returns Promise 返回版本字符串（来自 package.json）
     * 
     * @example
     * const version = await window.electronAPI.getAppVersion()
     * console.log(version) // "0.0.0"
     */
    getAppVersion: () => Promise<string>
    
    /**
     * 获取当前平台信息
     * @returns Promise 返回包含平台、架构和 Node.js 版本的对象
     * 
     * @example
     * const info = await window.electronAPI.getPlatformInfo()
     * console.log(info)
     * // { platform: "win32", arch: "x64", nodeVersion: "v18.0.0" }
     */
    getPlatformInfo: () => Promise<{
      platform: string      // 操作系统：win32/darwin/linux
      arch: string          // CPU架构：x64/arm64/ia32
      nodeVersion: string   // Node.js 版本号
    }>

    /**
     * 获取系统内存信息
     * @returns Promise 返回系统内存使用情况（字节）
     */
    getSystemMemoryInfo: () => Promise<{
      total: number
      free: number
      swapTotal: number
      swapFree: number
    }>

    /**
     * 获取 Node/Electron/Chrome 版本号
     * @returns Promise 返回版本信息对象
     */
    getVersions: () => Promise<{
      node: string
      electron: string
      chrome: string
    }>

    /**
     * 监听来自主进程的消息
     * @param channel - 消息频道名称
     * @param callback - 回调函数
     * 
     * @example
     * window.electronAPI.on('update-progress', (progress) => {
     *   console.log(`进度：${progress}%`)
     * })
     */
    on: (channel: string, callback: Function) => void
    
    /**
     * 发送消息到主进程
     * @param channel - 消息频道名称
     * @param data - 要发送的数据
     * 
     * @example
     * window.electronAPI.send('app-ready', { timestamp: Date.now() })
     */
    send: (channel: string, data: any) => void

    /**
     * 获取当前设备唯一 ID
     * @returns Promise 返回机器唯一标识（sha256 哈希值）
     *
     * @example
     * const id = await window.electronAPI.getMachineId()
     * console.log(id) // "a1b2c3d4..."
     */
    getMachineId: () => Promise<string>

    /**
     * 打开覆盖窗口（独立渲染进程，全尺寸覆盖主页）
     * 在 Electron 中创建模态子窗口加载对应页面
     *
     * @example
     * window.electronAPI.openOverlayWindow('avatar')
     */
    openOverlayWindow: (page: string, queryString?: string) => void

    /**
     * 关闭当前窗口
     * 用于覆盖窗口关闭自身
     *
     * @example
     * window.electronAPI.closeCurrentWindow()
     */
    closeCurrentWindow: () => void

    /**
     * 保存临时文件（用于录音缓存）
     * @param data - 包含 ArrayBuffer 数据和文件名的对象
     * @returns Promise 返回保存后的文件路径
     *
     * @example
     * const path = await window.electronAPI.saveTempFile({
     *   buffer: arrayBuffer,
     *   filename: 'recording.mp3'
     * })
     */
    saveTempFile: (data: { buffer: ArrayBuffer; filename: string; dateDir?: string }) => Promise<string>

    /**
     * 读取本地文件
     * @param filePath - 文件绝对路径
     * @returns Promise 返回文件的 ArrayBuffer
     */
    readLocalFile: (filePath: string) => Promise<ArrayBuffer>

    /**
     * 下载并解压 Skill zip 到 userData/skills/{skillName}/
     * @param data - 包含下载 URL 和 skill 名称的对象
     * @returns Promise 返回解压后的目录路径
     */
    downloadAndExtractSkill: (data: { url: string; skillName: string }) => Promise<string>

    /**
     * 执行 CLI 命令（由 ChatPage skill command dialog 触发）
     * @param cmd - 命令对象，包含 type/description/command/cwd/risk
     * @returns Promise 返回执行结果（stdout/stderr/exitCode）
     */
    executeCommand: (cmd: CommandItem) => Promise<CommandResult>

    /**
     * 获取 MCP Server 的 tools/resources/prompts
     */
    fetchMcpResources: (params: McpFetchParams) => Promise<McpFetchResult>

    /**
     * 切换开发者工具（F12）
     */
    toggleDevtools: () => void

    /**
     * 获取日志文件列表（支持搜索关键词）
     */
    getLogFiles: (keyword?: string) => Promise<LogFileItem[]>

    /**
     * 删除日志文件
     */
    deleteLogFile: (filename: string) => Promise<boolean>

    /**
     * 用系统默认文本编辑器打开日志文件
     */
    openLogFile: (filename: string) => Promise<void>

    /**
     * 选择日期范围打包下载日志为 zip
     */
    zipAndDownloadLogs: (params: {
      startDate: string
      endDate: string
      keyword?: string
    }) => Promise<{ path: string; count: number; cancelled?: boolean }>

    /**
     * 用系统默认应用打开外部链接
     * 支持 http/https 及自定义协议（如 amapuri://）
     *
     * @example
     * window.electronAPI.openExternal('https://example.com')
     * window.electronAPI.openExternal('amapuri://workInAmap/createWithToken?polymericId=xxx')
     */
    openExternal: (url: string) => Promise<void>

    /**
     * 获取应用运行状态（如 isDev，用于 DevTools 快捷键等开发功能开关）
     */
    getAppState: () => Promise<{ isDev: boolean }>

    /**
     * 获取 RSA 公钥内容（登录加密用）
     * 打包环境以 file:// 加载 renderer，fetch('/public.key') 不可用，故由主进程读取后透传
     */
    getPublicKey: () => Promise<string>
  }
}

// ========== 日志文件类型 ==========

interface LogFileItem {
  name: string
  size: number
  created_at: string
}

/**
 * Skill Command 相关类型
 */
interface CommandItem {
  type: string
  description: string
  command: string
  cwd?: string
  risk: 'low' | 'medium' | 'high'
}

interface CommandResult {
  stdout: string
  stderr: string
  exitCode: number
}

// ========== MCP 资源获取类型 ==========

interface McpFetchParams {
  type: 'stdio' | 'sse' | 'streamablehttp'
  command?: string
  args?: string
  url?: string
  headers?: string
  env_vars?: string
  timeout?: number
}

interface McpFetchResult {
  tools: McpToolInfo[]
  resources: McpResourceInfo[]
  prompts: McpPromptInfo[]
}

interface McpToolInfo {
  name: string
  description: string
  input_schema: any
}

interface McpResourceInfo {
  uri: string
  name: string
  description: string
  mimeType: string
}

interface McpPromptInfo {
  name: string
  description: string
}