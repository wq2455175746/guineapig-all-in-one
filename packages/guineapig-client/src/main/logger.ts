/**
 * 零依赖自定义日志模块
 * 输出到 userData/temp/logs/，每天 3 个文件（error/info/debug）
 */

import path from 'path'
import fs from 'fs'
import { app } from 'electron'

type LogLevel = 'debug' | 'info' | 'error'

const LOG_DIR = path.join(app.getPath('userData'), 'temp', 'logs')

function ensureLogDir(): void {
  if (!fs.existsSync(LOG_DIR)) {
    fs.mkdirSync(LOG_DIR, { recursive: true })
  }
}

function formatDate(date: Date): string {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}${m}${d}`
}

function formatTimestamp(date: Date): string {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  const h = String(date.getHours()).padStart(2, '0')
  const min = String(date.getMinutes()).padStart(2, '0')
  const s = String(date.getSeconds()).padStart(2, '0')
  return `[${y}-${m}-${d} ${h}:${min}:${s}]`
}

function writeLog(level: LogLevel, message: string): void {
  try {
    ensureLogDir()
    const now = new Date()
    const filename = `${formatDate(now)}-${level}.log`
    const filePath = path.join(LOG_DIR, filename)
    const prefix = level.toUpperCase().padEnd(5)
    const line = `${formatTimestamp(now)} [${prefix}] ${message}\n`

    fs.appendFileSync(filePath, line, 'utf-8')
  } catch {
    // 日志写入失败时静默处理，不影响主流程
  }
}

export const logger = {
  debug: (message: string) => writeLog('debug', message),
  info: (message: string) => writeLog('info', message),
  error: (message: string) => writeLog('error', message),

  /** 获取日志目录路径 */
  getLogDir: (): string => LOG_DIR,

  /** 获取日志目录下所有 .log 文件列表，支持按关键词过滤 */
  getFiles: (keyword?: string): LogFileItem[] => {
    ensureLogDir()
    const entries = fs.readdirSync(LOG_DIR, { withFileTypes: true })
    const files: LogFileItem[] = []

    for (const entry of entries) {
      if (!entry.isFile() || !entry.name.endsWith('.log')) continue
      if (keyword && !entry.name.toLowerCase().includes(keyword.toLowerCase())) continue

      const filePath = path.join(LOG_DIR, entry.name)
      const stat = fs.statSync(filePath)
      files.push({
        name: entry.name,
        size: stat.size,
        created_at: stat.birthtime.toISOString(),
      })
    }

    // 按文件名（即日期）降序排列
    files.sort((a, b) => b.name.localeCompare(a.name))
    return files
  },

  /** 删除指定日志文件 */
  deleteFile: (filename: string): boolean => {
    // 安全检查：只允许删除 logs 目录下的 .log 文件
    const sanitized = path.basename(filename)
    if (!sanitized.endsWith('.log')) return false
    const filePath = path.join(LOG_DIR, sanitized)
    if (!fs.existsSync(filePath)) return false
    fs.unlinkSync(filePath)
    return true
  },

  /** 获取日志文件的完整路径 */
  getFilePath: (filename: string): string => {
    const sanitized = path.basename(filename)
    return path.join(LOG_DIR, sanitized)
  },
}

export interface LogFileItem {
  name: string
  size: number
  created_at: string
}
