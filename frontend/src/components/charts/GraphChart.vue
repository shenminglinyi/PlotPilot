<template>
  <ChartWrapper
    :option="chartOption"
    :height="height"
    :theme="echartsTheme"
    :aria-label="`关系图表 - ${nodes.length} 个节点，${links.length} 个连接`"
    @click="handleNodeClick"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import ChartWrapper from './ChartWrapper.vue'
import type { EChartsOption } from 'echarts'
import { useThemeStore } from '../../stores/themeStore'

const themeStore = useThemeStore()

interface GraphNode {
  id: string
  name: string
  category?: number
}

interface GraphLink {
  source: string
  target: string
  value?: number
}

interface GraphEventParams {
  dataType?: 'node' | 'edge'
  data?: GraphNode | GraphLink
}

const props = withDefaults(defineProps<{
  nodes: GraphNode[]
  links: GraphLink[]
  categories?: string[]
  height?: string
}>(), {
  height: '600px',
  categories: () => []
})

const emit = defineEmits<{
  nodeClick: [node: GraphNode]
  edgeClick: [link: GraphLink]
}>()

/** 同步 ECharts 内置主题与 app 主题，修复暗色模式下图表始终用 light 主题的问题 */
const echartsTheme = computed(() => themeStore.isDark ? 'dark' : 'light')

/** 节点和边的数量，用于动态调整渲染策略 */
const nodeCount = computed(() => props.nodes.length)

/**
 * tooltip 颜色与 CSS 变量体系保持一致：
 * surface → --app-surface, border → --app-border-strong, text → --app-text-secondary
 */
const tooltipColors = computed(() => {
  const { isDark, isAnchor } = themeStore
  if (isAnchor) {
    return {
      bg: '#111620',
      border: 'rgba(201,162,39,0.14)',
      text: '#c4b99a',
    }
  }
    if (isDark) {
      return {
        bg: '#1a2235',
        border: 'rgba(148,163,184,0.12)',
        text: '#d1d5db',
      }
    }
  return {
    bg: '#ffffff',
    border: 'rgba(15,23,42,0.09)',
    text: '#1f2937',
  }
})

const tooltip = computed(() => ({
  backgroundColor: tooltipColors.value.bg,
  borderColor: tooltipColors.value.border,
  textStyle: {
    color: tooltipColors.value.text,
    fontSize: 12,
  },
  formatter: (params: any) => {
    const eventParams = params as unknown as GraphEventParams
    if (eventParams.dataType === 'node') {
      return `${(eventParams.data as GraphNode)?.name ?? ''}`
    }
    const link = eventParams.data as GraphLink | undefined
    return `${link?.source ?? ''} → ${link?.target ?? ''}`
  },
}))

/**
 * 大图（>80节点）关闭动画并降低 force 强度，减少掉帧。
 * 小图保留动画以提升视觉体验。
 */
const chartOption = computed(() => {
  const large = nodeCount.value > 80

  return {
    backgroundColor: 'transparent',
    animation: !large,
    series: [
      {
        type: 'graph',
        layout: 'force',
        data: props.nodes,
        links: props.links,
        categories: props.categories.map(name => ({ name })),
        roam: true,
        label: {
          show: true,
          position: 'right',
          fontSize: 12,
        },
        lineStyle: {
          color: 'source',
          opacity: 0.45,
          width: 1.5,
          curveness: 0.2,
        },
        force: {
          repulsion: large ? 80 : 120,
          edgeLength: large ? 120 : 160,
          gravity: large ? 0.12 : 0.08,
          layoutAnimation: !large,
          friction: large ? 0.9 : 0.6,
        },
        emphasis: {
          focus: 'adjacency',
          lineStyle: { width: 3 },
        },
        // 大图启用渐进渲染，避免首帧阻塞主线程
        progressive: large ? 200 : 0,
        progressiveThreshold: large ? 80 : 9999,
      },
    ],
    tooltip: tooltip.value,
  } as EChartsOption
})

const handleNodeClick = (params: GraphEventParams) => {
  if (params.dataType === 'node') {
    emit('nodeClick', params.data as GraphNode)
  } else if (params.dataType === 'edge') {
    emit('edgeClick', params.data as GraphLink)
  }
}
</script>
