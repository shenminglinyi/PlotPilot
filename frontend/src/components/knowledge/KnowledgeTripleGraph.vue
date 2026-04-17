<template>
  <div class="ktg-root">
    <div class="ktg-toolbar">
      <n-text depth="3" class="ktg-hint">
        由 <code>novel_knowledge.facts</code> 三元组生成可视化：节点为实体，边为谓词；悬停可看备注与章号。与叙事页「知识三元组」同源。
      </n-text>
      <n-space :size="8">
        <n-select
          v-model:value="filterType"
          :options="filterOptions"
          size="small"
          style="width: 120px"
          @update:value="redraw"
        />
        <n-button size="small" quaternary :loading="loading" @click="reload">刷新</n-button>
      </n-space>
    </div>
    <div v-if="emptyHint" class="ktg-empty">
      <n-empty description="尚无三元组，可在「叙事与知识」中填写或由 kg_upsert_fact 写入" size="small" />
    </div>
    <div v-else-if="filteredFacts.length === 0" class="ktg-empty">
      <n-empty :description="`无${filterType === 'character' ? '人物' : '地点'}类型的三元组`" size="small" />
    </div>
    <GraphChart v-else :nodes="graphData.nodes" :links="graphData.links" height="100%" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { knowledgeApi } from '../../api/knowledge'
import GraphChart from '../charts/GraphChart.vue'
import { convertGraph, type VisNode, type VisEdge, type EChartsGraphData } from '../../utils/visToEcharts'

const props = defineProps<{ slug: string }>()

interface Fact {
  id: string
  subject: string
  predicate: string
  object: string
  chapter_id?: number | null
  note?: string
  entity_type?: 'character' | 'location'
  importance?: string
  location_type?: string
}

const loading = ref(false)
const facts = ref<Fact[]>([])
const graphData = ref<EChartsGraphData>({ nodes: [], links: [] })
const filterType = ref<'all' | 'character' | 'location'>('all')

const filterOptions = [
  { label: '全部', value: 'all' },
  { label: '人物', value: 'character' },
  { label: '地点', value: 'location' },
]

const emptyHint = computed(() => facts.value.length === 0 && !loading.value)

const filteredFacts = computed(() => {
  if (filterType.value === 'all') return facts.value
  return facts.value.filter(f => f.entity_type === filterType.value)
})

// 根据实体类型和重要程度返回颜色
const getColorByType = (entityType?: string, importance?: string) => {
  if (entityType === 'character') {
    // 人物节点
    switch (importance) {
      case 'primary':
        return { background: '#fecaca', border: '#ef4444' } // 红色 - 主角
      case 'secondary':
        return { background: '#fed7aa', border: '#f97316' } // 橙色 - 重要配角
      case 'minor':
        return { background: '#bfdbfe', border: '#3b82f6' } // 蓝色 - 次要人物
      default:
        return { background: '#e0e7ff', border: '#6366f1' } // 默认紫色
    }
  } else if (entityType === 'location') {
    // 地点节点
    switch (importance) {
      case 'core':
        return { background: '#a7f3d0', border: '#10b981' } // 深绿 - 核心地点
      case 'important':
        return { background: '#d1fae5', border: '#6ee7b7' } // 浅绿 - 重要地点
      case 'normal':
        return { background: '#e5e7eb', border: '#9ca3af' } // 灰色 - 一般地点
      default:
        return { background: '#e0e7ff', border: '#6366f1' } // 默认紫色
    }
  }
  // 默认颜色
  return { background: '#e0e7ff', border: '#6366f1' }
}

const buildVisData = () => {
  const labelToId = new Map<string, string>()
  const labelToMeta = new Map<string, { entityType?: string; importance?: string }>()
  let nextN = 0

  const entityId = (raw: string, entityType?: string, importance?: string) => {
    const label = (raw || '').trim() || '（空）'
    if (!labelToId.has(label)) {
      labelToId.set(label, `ent_${nextN++}`)
      labelToMeta.set(label, { entityType, importance })
    }
    return labelToId.get(label)!
  }

  const nodeSeen = new Set<string>()
  const nodes: VisNode[] = []
  const edges: VisEdge[] = []

  for (const f of filteredFacts.value) {
    const sid = entityId(f.subject, f.entity_type, f.importance)
    const oid = entityId(f.object)

    if (!nodeSeen.has(sid)) {
      nodeSeen.add(sid)
      const lab = (f.subject || '').trim() || '（空）'
      const meta = labelToMeta.get(lab)
      nodes.push({
        id: sid,
        label: lab.length > 42 ? `${lab.slice(0, 40)}…` : lab,
        title: lab + (meta?.importance ? `\n重要程度: ${meta.importance}` : ''),
        color: getColorByType(meta?.entityType, meta?.importance),
        font: { size: 14 },
        shape: meta?.entityType === 'character' ? 'box' : 'dot',
        borderWidth: 2,
      })
    }
    if (!nodeSeen.has(oid)) {
      nodeSeen.add(oid)
      const lab = (f.object || '').trim() || '（空）'
      nodes.push({
        id: oid,
        label: lab.length > 42 ? `${lab.slice(0, 40)}…` : lab,
        title: lab,
        color: { background: '#fce7f3', border: '#db2777' },
        font: { size: 13 },
      })
    }
    const pred = (f.predicate || '').trim() || '—'
    const ch = f.chapter_id != null && f.chapter_id >= 1 ? `第${f.chapter_id}章` : ''
    const tip = [pred, f.note, ch].filter(Boolean).join('\n')
    edges.push({
      id: f.id,
      from: sid,
      to: oid,
      label: pred.length > 28 ? `${pred.slice(0, 26)}…` : pred,
      title: tip,
      arrows: 'to',
      font: { size: 11, align: 'middle' },
    })
  }

  return convertGraph(nodes, edges)
}

const redraw = async () => {
  await nextTick()
  graphData.value = buildVisData()
}

const reload = async () => {
  loading.value = true
  try {
    const res = await knowledgeApi.getKnowledge(props.slug)
    facts.value = (res.facts || []) as Fact[]
    await redraw()
  } catch (error) {
    console.error('Failed to load knowledge graph:', error)
    window.$message?.error('加载知识图谱失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

watch(
  () => props.slug,
  () => {
    void reload()
  }
)

onMounted(async () => {
  await nextTick()
  await reload()
})
</script>

<style scoped>
.ktg-root {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  position: relative;
  background: var(--app-surface-subtle);
  border-radius: 10px;
  border: 1px solid var(--app-border-strong);
  overflow: hidden;
}

.ktg-toolbar {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--app-border);
  background: var(--app-surface);
}

.ktg-hint {
  font-size: 11px;
  line-height: 1.45;
  max-width: min(100%, 420px);
}

.ktg-hint code {
  font-size: 10px;
  padding: 0 4px;
  border-radius: 4px;
  background: rgba(79, 70, 229, 0.08);
  color: #4338ca;
}

.ktg-canvas {
  flex: 1;
  min-height: 260px;
  width: 100%;
  display: flex;
}

.ktg-empty {
  position: absolute;
  left: 0;
  right: 0;
  top: 48px;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  z-index: 1;
}
</style>
