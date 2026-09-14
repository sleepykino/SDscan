import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 后端固定监听 127.0.0.1:8000；开发期 /api、/ws、/screenshots 全部代理
export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/screenshots': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
    },
  },
})
