<template>
  <ChartWrapper :option="chartOption" :height="height" :aria-label="`关系图表 - ${nodes.length} 个节点，${links.length} 个连接`" @click="handleNodeClick" />
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

const tooltip = computed(() => ({
  backgroundColor: themeStore.isDark ? '#1a2436' : '#ffffff',
  borderColor: themeStore.isDark ? 'rgba(148,163,184,0.16)' : 'rgba(15,23,42,0.09)',
  textStyle: {
    color: themeStore.isDark ? '#d1d5db' : '#1f2937',
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

const chartOption = computed(() => ({
  backgroundColor: 'transparent',
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
      },
      lineStyle: {
        opacity: 0.7,
        width: 1.5,
        curveness: 0.2,
      },
      force: {
        repulsion: 120,
        edgeLength: 160,
        gravity: 0.08,
      },
      emphasis: {
        focus: 'adjacency',
        lineStyle: { width: 3 },
      },
    },
  ],
  tooltip: tooltip.value,
}) as EChartsOption)

const handleNodeClick = (params: GraphEventParams) => {
  if (params.dataType === 'node') {
    emit('nodeClick', params.data as GraphNode)
  } else if (params.dataType === 'edge') {
    emit('edgeClick', params.data as GraphLink)
  }
}
</script>
