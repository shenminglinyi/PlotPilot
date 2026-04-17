<!-- 向导内：用 Bible 地点列表生成简易力导向图（无知识三元组时预览「地图系统」） -->
<template>
  <div class="blgp">
    <n-text depth="3" style="font-size: 12px; display: block; margin-bottom: 8px">
      地点分布预览（按类型着色；线表示同属一书世界观下的关联占位，可在工作台「地点关系图」中编辑三元组后细化）
    </n-text>
    <div v-if="!locations.length" class="blgp-empty">
      <n-empty description="暂无地点数据" size="small" />
    </div>
    <div v-else class="blgp-chart">
      <GraphChart
        :nodes="graphNodes"
        :links="graphLinks"
        :categories="categoryLabels"
        height="320px"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import GraphChart from '../charts/GraphChart.vue'
import type { LocationDTO } from '../../api/bible'

const props = defineProps<{
  locations: LocationDTO[]
}>()

const typeOrder = ['城市', '区域', '建筑', '势力', '秘境', '其他']

function typeLabel(t: string | undefined): string {
  if (!t) return '其他'
  if (typeOrder.includes(t)) return t
  return t
}

const categoryLabels = computed(() => {
  const set = new Set<string>()
  for (const loc of props.locations) {
    set.add(typeLabel(loc.location_type))
  }
  const arr = [...set]
  arr.sort((a, b) => typeOrder.indexOf(a) - typeOrder.indexOf(b))
  return arr.length ? arr : ['地点']
})

const graphNodes = computed(() => {
  const cats = categoryLabels.value
  return props.locations.map((loc, index) => ({
    id: loc.id || `location-${index + 1}`,
    name: loc.name || `地点 ${index + 1}`,
    category: Math.max(0, cats.indexOf(typeLabel(loc.location_type))),
    symbolSize: 44,
  }))
})

/** 星型弱连接，便于力导向布局散开；非地理事实断言 */
const graphLinks = computed(() => {
  const nodes = graphNodes.value
  if (nodes.length < 2) return []
  const hub = nodes[0].id
  return nodes.slice(1).map((n) => ({
    source: hub,
    target: n.id,
    value: 1,
  }))
})
</script>

<style scoped>
.blgp {
  width: 100%;
  text-align: left;
}
.blgp-chart {
  border: 1px solid var(--n-border-color);
  border-radius: 8px;
  overflow: hidden;
  background: var(--n-color-modal);
}
.blgp-empty {
  padding: 24px;
  text-align: center;
}
</style>
