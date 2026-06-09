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
  MarkLineComponent,
  MarkPointComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

// Keep the registry aligned with actual chart usage to avoid shipping unused ECharts modules.
use([
  TitleComponent,
  TooltipComponent,
  GridComponent,
  MarkLineComponent,
  MarkPointComponent,
  BarChart,
  LineChart,
  PieChart,
  GraphChart,
  CanvasRenderer
])

