import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import electron from 'vite-plugin-electron'
import path from 'path'
import { fileURLToPath } from 'url'

// 获取 __dirname（兼容 ESM），在 ESM 模块系统中（"module": "ESNext"），没有 CommonJS 的 __dirname 变量。这行代码手动获取当前文件所在目录，用于后续的路径别名。
const __dirname = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [
    //让 Vite 能编译 .vue 文件
    vue(),
    // 接受一个数组，每个对象代表一个 Electron 进程的配置
    electron([
      // 主进程配置
      {
        entry: 'src/main/index.ts', // 主进程入口文件
        vite: {
          build: {
            outDir: 'dist/electron', // 输出到 dist-electron 目录
            rollupOptions: {
              external: ['electron', 'node-machine-id', 'archiver', 'adm-zip', /^@modelcontextprotocol\/sdk/],
              output: {
                entryFileNames: 'index.js' // 输出文件名
              }
            } 
          }
        },
        onstart(args) {
          // 开发环境启动 Electron
          if (process.env.NODE_ENV === 'development') {
            args.startup()
          }
        }
      },
      // 预加载脚本配置
      {
        entry: 'src/preload/index.ts',  // 预加载脚本入口
        vite: {
          build: {
            outDir: 'dist/electron',
            minify: false,
            lib: {
              formats: ['cjs'],
              fileName: () => 'preload/index.js'
            },
            rollupOptions: {
              external: ['electron']
            }
          }
        }
      }
    ])
  ],
  // 路径别名 // 不用写复杂的相对路径
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@renderer': path.resolve(__dirname, './src/renderer')
    }
  },
  // 开发服务器
  server: {
    port: 5173,
    strictPort: false // 如果 5173 被占用，自动换端口
  },
  // 公共基础路径,设置为 './' 让 Electron 能正确从文件系统加载资源（而不是从网络）
  base: './',
  // build - 生产构建配置
  build: {
    outDir: 'dist/renderer',  // 渲染进程输出目录
    emptyOutDir: true,   // 构建前清空目录
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, 'index.html'),
        overlay: path.resolve(__dirname, 'overlay.html')
      }
    }
  }
})