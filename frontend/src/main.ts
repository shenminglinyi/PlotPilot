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

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(naive)
app.use(installECharts)

app.mount('#app')
