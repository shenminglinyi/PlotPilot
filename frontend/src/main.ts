import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import App from './App.vue'

// Naive UI
import naive from 'naive-ui'

// ECharts
import installECharts from './plugins/echarts'

// 样式
import './assets/styles/main.css'

// Tauri API 初始化（动态端口、环境检测）
import { initApiClient } from './api/config'

async function bootstrap() {
  const app = createApp(App)

  app.use(createPinia())
  app.use(router)
  app.use(naive)
  app.use(installECharts)

  // Tauri 下须先拿到真实端口再挂路由，否则首屏请求会打到错误 origin（抽屉/广场像「没连上库」）
  try {
    await initApiClient()
  } catch (err) {
    console.warn('[Init] API 客户端初始化失败（可稍后重试）:', err)
  }

  app.mount('#app')
}

void bootstrap()
