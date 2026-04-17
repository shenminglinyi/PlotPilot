import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
    },
  },
  build: {
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      output: {
        manualChunks(id) {
          const normalizedId = id.replace(/\\/g, '/')

          if (normalizedId.includes('node_modules')) {
            if (normalizedId.includes('/vue-echarts/')) return 'vendor-vchart'
            if (normalizedId.includes('/zrender/')) return 'vendor-zrender'
            if (normalizedId.includes('/echarts/')) {
              if (normalizedId.includes('/echarts/charts/')) return 'vendor-echarts-charts'
              if (normalizedId.includes('/echarts/components/')) return 'vendor-echarts-components'
              if (normalizedId.includes('/echarts/renderers/')) return 'vendor-echarts-renderers'
              return 'vendor-echarts-core'
            }
            if (normalizedId.includes('/naive-ui/')) {
              const match = normalizedId.match(/\/naive-ui\/es\/([^/]+)\//)
              if (match?.[1]) {
                return `vendor-naive-${match[1]}`
              }
              return 'vendor-naive-core'
            }
            if (
              normalizedId.includes('/vue/') ||
              normalizedId.includes('/vue-router/') ||
              normalizedId.includes('/pinia/')
            ) {
              return 'vendor-vue'
            }
            return 'vendor-misc'
          }

          if (
            normalizedId.includes('/src/components/workbench/') ||
            normalizedId.includes('/src/components/autopilot/') ||
            normalizedId.includes('/src/components/knowledge/') ||
            normalizedId.includes('/src/components/panels/')
          ) {
            return 'workbench'
          }

          if (normalizedId.includes('/src/components/stats/')) {
            return 'stats'
          }

          return undefined
        },
      },
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
