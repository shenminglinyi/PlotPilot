import type { App } from 'vue'
import ECharts from 'vue-echarts'
import { use } from 'echarts/core'
import {
  BarChart,
  LineChart,
  PieChart,
  ScatterChart,
  EffectScatterChart,
  RadarChart,
  HeatmapChart,
  GaugeChart,
  GraphChart,
  TreeChart,
  TreemapChart,
  SunburstChart,
  SankeyChart,
  FunnelChart,
  ParallelChart,
  CandlestickChart,
  BoxplotChart,
  ThemeRiverChart
} from 'echarts/charts'
import {
  TitleComponent,
  TooltipComponent,
  GridComponent,
  PolarComponent,
  RadarComponent,
  GeoComponent,
  SingleAxisComponent,
  ParallelComponent,
  GraphicComponent,
  ToolboxComponent,
  DataZoomComponent,
  VisualMapComponent,
  LegendComponent,
  LegendScrollComponent,
  LegendPlainComponent
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import * as echarts from 'echarts'

// Register components, charts, and renderer
use([
  TitleComponent,
  TooltipComponent,
  GridComponent,
  PolarComponent,
  RadarComponent,
  GeoComponent,
  SingleAxisComponent,
  ParallelComponent,
  GraphicComponent,
  ToolboxComponent,
  DataZoomComponent,
  VisualMapComponent,
  LegendComponent,
  LegendScrollComponent,
  LegendPlainComponent,
  BarChart,
  LineChart,
  PieChart,
  ScatterChart,
  EffectScatterChart,
  RadarChart,
  HeatmapChart,
  GaugeChart,
  GraphChart,
  TreeChart,
  TreemapChart,
  SunburstChart,
  SankeyChart,
  FunnelChart,
  ParallelChart,
  CandlestickChart,
  BoxplotChart,
  ThemeRiverChart,
  CanvasRenderer
])

export default function installECharts(app: App) {
  app.component('VChart', ECharts)
  app.config.globalProperties.$echarts = echarts
}

export { echarts }
