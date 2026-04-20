<template>
  <ChartWrapper :option="chartOption" :height="height" :aria-label="`${title} - 趋势图表`" />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ChartWrapper from './ChartWrapper.vue'
import type { EChartsOption } from 'echarts'
import { CHART_COLORS } from '@/constants/chartTheme'

interface TrendData {
  date: string
  value: number
}

const props = withDefaults(defineProps<{
  data: TrendData[]
  title?: string
  height?: string
}>(), {
  title: '趋势图',
  height: '400px'
})

const chartData = computed(() => props.data.map(d => ({
  date: d.date,
  value: d.value
})))

const chartOption = computed<EChartsOption>(() => ({
  title: {
    text: props.title,
    left: 'center'
  },
  xAxis: {
    type: 'category',
    data: chartData.value.map(d => d.date)
  },
  yAxis: {
    type: 'value'
  },
  series: [
    {
      type: 'line',
      data: chartData.value.map(d => d.value),
      smooth: true,
      itemStyle: {
        color: CHART_COLORS.primary
      },
      areaStyle: {
        color: 'rgba(13, 148, 136, 0.14)'
      }
    }
  ],
  tooltip: {
    trigger: 'axis'
  },
  grid: {
    left: '3%',
    right: '4%',
    bottom: '3%',
    containLabel: true
  }
}))
</script>
