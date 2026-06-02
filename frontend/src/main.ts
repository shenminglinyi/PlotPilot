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
import './assets/styles/tokens-layout.css'

// Tauri API 初始化（动态端口、环境检测）
import { initApiClient } from './api/config'
import { installGlobalFeedbackIncidentCapture } from './support/feedbackGlobalInstall'

function startupErrorMessage(err: unknown): string {
  if (err instanceof Error && err.message.trim().length > 0) {
    return err.message
  }
  if (typeof err === 'string' && err.trim().length > 0) {
    return err
  }
  return '后端启动失败，请查看 PlotPilot 日志。'
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function renderStartupFailure(err: unknown): void {
  const root = document.querySelector<HTMLElement>('#app')
  if (!root) return

  const message = escapeHtml(startupErrorMessage(err))
  root.innerHTML = `
    <main style="
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 32px;
      background: #f8fafc;
      color: #0f172a;
      font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
    ">
      <section style="
        width: min(560px, 100%);
        padding: 28px;
        border: 1px solid #e2e8f0;
        border-radius: 18px;
        background: #ffffff;
        box-shadow: 0 18px 45px rgba(15, 23, 42, 0.08);
      ">
        <p style="margin: 0 0 8px; font-size: 13px; color: #64748b;">PlotPilot 启动失败</p>
        <h1 style="margin: 0 0 14px; font-size: 22px; line-height: 1.35;">后端服务暂未就绪</h1>
        <p style="margin: 0; line-height: 1.8; color: #334155;">${message}</p>
      </section>
    </main>
  `
}

async function bootstrap() {
  const app = createApp(App)
  installGlobalFeedbackIncidentCapture(app)

  app.use(createPinia())
  app.use(router)
  app.use(naive)
  app.use(installECharts)

  // Tauri 下须先拿到真实端口再挂路由，否则首屏请求会打到错误 origin（抽屉/广场像「没连上库」）
  try {
    await initApiClient()
  } catch (err) {
    console.error('[Init] API 客户端初始化失败:', err)
    renderStartupFailure(err)
    return
  }

  app.mount('#app')
}

void bootstrap()
