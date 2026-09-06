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
        changeOrigin: true
      },
      '/api/v1': {
        target: 'http://guineapig-ops.local:6880',
        changeOrigin: true
      }
    }
  }
})