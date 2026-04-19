import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig({
  build: {
    // 大型 SPA 常见体积；需要更细拆分时再改 code-splitting，而非被默认 500k 告警刷屏
    chunkSizeWarningLimit: 1200,
  },
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 3000,
    host: '127.0.0.1',
    proxy: {
      // 代理到后端服务器（默认 8005 端口）
      '/api': {
        target: 'http://127.0.0.1:8005',
        changeOrigin: true,
        ws: true,
        // SSE 长连接，避免代理过早断开
        timeout: 0,
        // 不要重写路径
        rewrite: (path) => path,
      },
    },
  },
})
