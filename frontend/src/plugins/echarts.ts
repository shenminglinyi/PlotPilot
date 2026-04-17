import type { App } from 'vue'
import ECharts from 'vue-echarts'
import { use } from 'echarts/core'
import {
  BarChart,
  LineChart,
  PieChart,
  GraphChart,
} from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  GridComponent,
  GraphicComponent,
  LegendComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

// Register components, charts, and renderer
use([
  TitleComponent,
  TooltipComponent,
  GridComponent,
  GraphicComponent,
  LegendComponent,
  BarChart,
  LineChart,
  PieChart,
  GraphChart,
  CanvasRenderer
])

export default function installECharts(app: App) {
  app.component('VChart', ECharts)
}
