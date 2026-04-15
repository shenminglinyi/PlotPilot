<template>
  <div class="lrg-root">
    <div class="lrg-toolbar">
      <n-text depth="3" class="lrg-hint">
        地点关系图：从三元组自动生成，节点颜色表示重要程度（深绿=核心地点，浅绿=重要地点，灰=一般地点）
      </n-text>
      <n-space :size="8">
        <n-button size="small" quaternary :loading="loading" @click="reload">刷新</n-button>
        <n-button size="small" secondary @click="goToKnowledge">编辑三元组</n-button>
      </n-space>
    </div>
    <div class="lrg-chart">
      <div v-if="emptyHint" class="lrg-empty">
        <n-empty description="尚无地点三元组，请在「叙事与知识」中添加" size="small" />
      </div>
      <GraphChart v-else :nodes="graphData.nodes" :links="graphData.links" @node-click="handleNodeClick" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { knowledgeApi } from '../../api/knowledge'
import GraphChart from '../charts/GraphChart.vue'
import { convertGraph, type VisNode, type VisEdge, type EChartsGraphData, type EChartsNode } from '../../utils/visToEcharts'
import {
  tripleStringAttrs,
  locationImportanceZh,
  locationTypeZh,
} from '../../utils/knowledgeFactDisplay'

const props = defineProps<{ slug: string }>()
const emit = defineEmits<{
  loading: [boolean]
  nodeClick: [node: any]
}>()
const router = useRouter()

interface Fact {
  id: string
  subject: string
  predicate: string
  object: string
  chapter_id?: number | null
  note?: string
  entity_type?: 'character' | 'location'
  importance?: 'core' | 'important' | 'normal'
  location_type?: 'city' | 'region' | 'building' | 'faction' | 'realm'
  description?: string
  first_appearance?: number
  related_chapters?: number[]
  tags?: string[]
  attributes?: Record<string, any>
}

const loading = ref(false)
const facts = ref<Fact[]>([])
const graphData = ref<EChartsGraphData>({ nodes: [], links: [] })

const emptyHint = computed(() => facts.value.length === 0 && !loading.value)

// 根据重要程度返回颜色
const getColorByImportance = (importance?: string) => {
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

// 根据地点类型返回形状
const getShapeByType = (locationType?: string) => {
  switch (locationType) {
    case 'city':
      return 'dot' // 圆形
    case 'region':
      return 'diamond' // 菱形
    case 'building':
      return 'box' // 方形
    case 'faction':
      return 'star' // 星形
    case 'realm':
      return 'triangle' // 三角形
    default:
      return 'dot'
  }
}

const buildVisData = () => {
  const labelToId = new Map<string, string>()
  const labelToImportance = new Map<string, string>()
  const labelToType = new Map<string, string>()
  const labelToFact = new Map<string, Fact>()
  let nextN = 0

  const entityId = (raw: string, importance?: string, locationType?: string, fact?: Fact) => {
    const label = (raw || '').trim() || '（空）'
    if (!labelToId.has(label)) {
      labelToId.set(label, `loc_${nextN++}`)
      if (importance) {
        labelToImportance.set(label, importance)
      }
      if (locationType) {
        labelToType.set(label, locationType)
      }
      if (fact) {
        labelToFact.set(label, fact)
      }
    }
    return labelToId.get(label)!
  }

  const nodeSeen = new Set<string>()
  const nodes: VisNode[] = []
  const edges: VisEdge[] = []

  for (const f of facts.value) {
    // 只处理地点类型的三元组
    if (f.entity_type !== 'location') continue

    const a = tripleStringAttrs(f)
    const sid = entityId(f.subject, f.importance, f.location_type, f)
    const oid = entityId(f.object, a.object_importance, a.object_location_type, f)

    if (!nodeSeen.has(sid)) {
      nodeSeen.add(sid)
      const lab = (f.subject || '').trim() || '（空）'
      const importance = labelToImportance.get(lab) || f.importance
      const locationType = labelToType.get(lab) || f.location_type
      const fact = labelToFact.get(lab)
      const izh = locationImportanceZh(importance)
      const tzh = locationTypeZh(locationType)
      nodes.push({
        id: sid,
        label: lab.length > 42 ? `${lab.slice(0, 40)}…` : lab,
        title: [lab, izh && `重要程度：${izh}`, tzh && `类型：${tzh}`, f.description].filter(Boolean).join('\n'),
        color: getColorByImportance(importance),
        font: { size: 14 },
        shape: getShapeByType(locationType),
        borderWidth: 2,
        // 附加完整数据
        ...(fact && {
          location_type: fact.location_type,
          importance: fact.importance,
          description: fact.description,
          first_appearance: fact.first_appearance,
          related_chapters: fact.related_chapters,
          tags: fact.tags,
          attributes: fact.attributes,
        })
      })
    }

    if (!nodeSeen.has(oid)) {
      nodeSeen.add(oid)
      const lab = (f.object || '').trim() || '（空）'
      const oimp = labelToImportance.get(lab) || a.object_importance
      const olt = labelToType.get(lab) || a.object_location_type
      const oizh = locationImportanceZh(oimp)
      const otz = locationTypeZh(olt)
      nodes.push({
        id: oid,
        label: lab.length > 42 ? `${lab.slice(0, 40)}…` : lab,
        title: [lab, oizh && `重要程度：${oizh}`, otz && `类型：${otz}`].filter(Boolean).join('\n'),
        color: getColorByImportance(oimp),
        font: { size: 13 },
        shape: getShapeByType(olt),
        borderWidth: 2,
      })
    }

    const pred = (f.predicate || '').trim() || '—'
    const ch = f.chapter_id != null && f.chapter_id >= 1 ? `第${f.chapter_id}章` : ''
    const tip = [pred, f.note, f.description, ch].filter(Boolean).join('\n')
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
  emit('loading', true)
  try {
    const res = await knowledgeApi.getKnowledge(props.slug)
    facts.value = (res.facts || []) as Fact[]
    const locationFacts = facts.value.filter(f => f.entity_type === 'location')
    await redraw()
  } catch (error) {
    console.error('Failed to load location graph:', error)
    window.$message?.error('加载地点关系图失败，请稍后重试')
  } finally {
    loading.value = false
    emit('loading', false)
  }
}

const handleNodeClick = (node: EChartsNode) => {
  emit('nodeClick', node)
}

const goToKnowledge = () => {
  router.push(`/book/${props.slug}/knowledge`)
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

defineExpose({ reload })
</script>

<style scoped>
.lrg-root {
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

.lrg-toolbar {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.2);
  background: var(--app-surface);
}

.lrg-hint {
  font-size: 11px;
  line-height: 1.45;
  max-width: min(100%, 520px);
}

.lrg-chart {
  flex: 1;
  min-height: 400px;
  overflow: hidden;
  position: relative;
}

.lrg-empty {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  z-index: 1;
}
</style>
