import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src')
    }
  },
  server: {
    allowedHosts: ['guineapig-ops.local','guineapig-ops-web.local' ],
    proxy: {
      '/admin/api/v1': {
        target: 'http://guineapig-ops.local:6880',
        changeOrigin: true,
        secure: true,
        rewrite: (path) => path.replace(/^\/admin\/api\/v1/, '/admin/api/v1')
      },
      '/api/v1': {
        target: 'http://guineapig-ops.local:6880',
        changeOrigin: true,
        secure: true,
        rewrite: (path) => path.replace(/^\/api\/v1/, '/api/v1')
      }
    }
  }
})