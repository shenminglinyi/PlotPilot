<template>
  <div class="lgc-root">
    <div class="lgc-toolbar">
      <n-text depth="3" class="lgc-hint">
        从三元组自动生成（只读）· 要编辑地点关系，请在「叙事与知识」中修改三元组 · 点节点进入全页查看
      </n-text>
      <n-space :size="8">
        <n-button size="small" quaternary :loading="loading" @click="reload">刷新</n-button>
        <n-button size="small" secondary @click="goFull">完整查看页</n-button>
      </n-space>
    </div>
    <div v-if="emptyHint" class="lgc-empty">
      <n-empty description="尚无地点相关三元组，请在「叙事与知识」中添加" size="small" />
    </div>
    <div v-else class="lgc-canvas">
      <GraphChart :nodes="nodes" :links="links" height="100%" @node-click="handleNodeClick" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { knowledgeApi } from '../../api/knowledge'
import GraphChart from '../charts/GraphChart.vue'
import { convertGraph, type VisNode, type VisEdge } from '../../utils/visToEcharts'
import type { EChartsNode } from '../../utils/visToEcharts'
import {
  tripleStringAttrs,
  locationImportanceZh,
  locationTypeZh,
} from '../../utils/knowledgeFactDisplay'

const props = defineProps<{ slug: string }>()
const router = useRouter()

interface KnowledgeTriple {
  id: string
  subject: string
  predicate: string
  object: string
  subject_entity_id?: string
  object_entity_id?: string
  chapter_id?: number | null
  note?: string
  entity_type?: string
  importance?: string
  location_type?: string
  description?: string
  attributes?: Record<string, unknown>
}

const loading = ref(false)
const triples = ref<KnowledgeTriple[]>([])
let requestId = 0

// 从三元组中提取地点节点和关系
const graph = computed(() => {
  const locationTriples = triples.value.filter(t => t.entity_type === 'location')

  // 提取所有地点节点（从 subject 和 object 中）
  const locationMap = new Map<string, {
    name: string
    importance?: string
    location_type?: string
    note?: string
  }>()

  locationTriples.forEach(t => {
    const a = tripleStringAttrs(t)
    const objImp = a.object_importance
    const objLt = a.object_location_type
    const subjectId = t.subject_entity_id || t.subject
    const objectId = t.object_entity_id || t.object
    const subjectLabel = a.subject_label || t.subject
    const objectLabel = a.object_label || t.object

    if (!locationMap.has(subjectId)) {
      locationMap.set(subjectId, {
        name: subjectLabel,
        importance: t.importance,
        location_type: t.location_type,
        note: [t.note, t.description].filter(Boolean).join('\n') || '',
      })
    }
    if (!locationMap.has(objectId)) {
      locationMap.set(objectId, {
        name: objectLabel,
        importance: objImp,
        location_type: objLt,
        note: '',
      })
    } else {
      const cur = locationMap.get(objectId)!
      const next = { ...cur }
      if (objectLabel && (!cur.name || cur.name === objectId)) next.name = objectLabel
      if (objImp && !cur.importance) next.importance = objImp
      if (objLt && !cur.location_type) next.location_type = objLt
      locationMap.set(objectId, next)
    }
  })

  const locations = Array.from(locationMap.entries()).map(([id, data]) => ({
    id,
    name: data.name,
    importance: data.importance,
    location_type: data.location_type,
    note: data.note || '',
  }))

  const relationships = locationTriples.map(t => ({
    id: t.id,
    source_id: t.subject_entity_id || t.subject,
    target_id: t.object_entity_id || t.object,
    label: t.predicate,
    note: [t.note, t.description].filter(Boolean).join('\n') || '',
  }))

  return { locations, relationships }
})

const emptyHint = computed(() => graph.value.locations.length === 0 && !loading.value)

// 根据重要程度返回颜色
const getNodeColor = (importance?: string) => {
  switch (importance) {
    case 'core':
      return { background: '#a7f3d0', border: '#059669' } // 核心地点-深绿
    case 'important':
      return { background: '#d1fae5', border: '#10b981' } // 重要地点-浅绿
    case 'normal':
      return { background: '#e5e7eb', border: '#6b7280' } // 一般地点-灰色
    default:
      return { background: '#f3f4f6', border: '#9ca3af' } // 未分类-浅灰
  }
}

// 根据地点类型返回形状
const getNodeShape = (locationType?: string) => {
  switch (locationType) {
    case 'city':
      return 'circle'
    case 'region':
      return 'box'
    case 'building':
      return 'triangle'
    case 'faction':
      return 'diamond'
    case 'realm':
      return 'star'
    default:
      return 'circle'
  }
}

const graphData = computed(() => {
  const visNodes: VisNode[] = graph.value.locations.map(loc => {
    const importanceLabel = locationImportanceZh(loc.importance)
    const typeLabel = locationTypeZh(loc.location_type)

    return {
      id: loc.id,
      label: loc.name + (typeLabel ? `\n[${typeLabel}]` : '') + (importanceLabel ? `\n(${importanceLabel})` : ''),
      title: [
        loc.name,
        importanceLabel && `重要程度：${importanceLabel}`,
        typeLabel && `类型：${typeLabel}`,
        loc.note,
      ].filter(Boolean).join('\n'),
      color: getNodeColor(loc.importance),
      font: { size: 14 },
      shape: getNodeShape(loc.location_type),
      borderWidth: 2,
    }
  })

  const visEdges: VisEdge[] = graph.value.relationships.map(r => {
    return {
      id: r.id,
      from: r.source_id,
      to: r.target_id,
      label: r.label,
      title: [r.label, r.note].filter(Boolean).join('\n') || undefined,
      arrows: 'to',
      font: { size: 11, align: 'middle' },
    }
  })

  return convertGraph(visNodes, visEdges)
})

const nodes = computed(() => graphData.value.nodes)
const links = computed(() => graphData.value.links)

const reload = async () => {
  const currentRequestId = ++requestId

  loading.value = true
  try {
    const data = await knowledgeApi.getKnowledge(props.slug)

    // Only update if this is still the latest request
    if (currentRequestId === requestId) {
      triples.value = data.facts || []
    }
  } catch (error) {
    console.error('Failed to load knowledge data:', error)
    if (currentRequestId === requestId) {
      window.$message?.error('加载地点关系失败，请稍后重试')
    }
  } finally {
    if (currentRequestId === requestId) {
      loading.value = false
    }
  }
}

const handleNodeClick = (node: EChartsNode) => {
  router.push({ path: `/book/${props.slug}/location-graph`, query: { focus: node.id } })
}

const goFull = () => {
  router.push(`/book/${props.slug}/location-graph`)
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
.lgc-root {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  position: relative;
  background: #fafafa;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.25);
  overflow: hidden;
}

.lgc-toolbar {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
  background: var(--app-surface);
}

.lgc-hint {
  font-size: 11px;
  line-height: 1.45;
  max-width: min(100%, 380px);
}

.lgc-hint code {
  font-size: 10px;
  padding: 0 4px;
  border-radius: 4px;
  background: rgba(79, 70, 229, 0.08);
  color: #4338ca;
}

.lgc-empty {
  flex: 1;
  min-height: 500px;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 侧栏 flex 内 height:100% 需可解析的块高，否则 ECharts 高度为 0 不可见 */
.lgc-canvas {
  flex: 1;
  min-height: 500px;
  width: 100%;
  position: relative;
}
</style>
