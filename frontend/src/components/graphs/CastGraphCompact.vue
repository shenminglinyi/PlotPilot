<template>
  <div class="cgc-root">
    <div class="cgc-toolbar">
      <n-text depth="3" class="cgc-hint">
        从三元组自动生成（只读）；若无人物三元组会自动合并 Bible 关系。占位实体名（char 005 等）已过滤。
      </n-text>
      <n-space :size="8">
        <n-button size="small" quaternary :loading="loading" @click="reload">刷新</n-button>
        <n-button size="small" secondary @click="goFull">完整查看页</n-button>
      </n-space>
    </div>
    <div v-if="emptyHint" class="cgc-empty">
      <n-empty description="尚无可用人物关系（知识库为空且 Bible 未配置结构化关系）" size="small" />
    </div>
    <div v-else class="cgc-canvas">
      <GraphChart :nodes="nodes" :links="links" height="100%" @node-click="handleNodeClick" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { knowledgeApi } from '../../api/knowledge'
import { bibleApi } from '../../api/bible'
import GraphChart from '../charts/GraphChart.vue'
import { convertGraph, type VisNode, type VisEdge } from '../../utils/visToEcharts'
import type { EChartsNode } from '../../utils/visToEcharts'
import {
  tripleStringAttrs,
  characterImportanceZh,
} from '../../utils/knowledgeFactDisplay'
import { mergeKnowledgeFactsWithBibleCharacters } from '../../utils/characterGraphMerge'

const props = defineProps<{ slug: string }>()
const router = useRouter()

interface KnowledgeTriple {
  id: string
  subject: string
  predicate: string
  object: string
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

// 从三元组中提取人物节点和关系
const graph = computed(() => {
  const characterTriples = triples.value.filter(t => t.entity_type === 'character')

  // 提取所有人物节点（从 subject 和 object 中）
  const characterMap = new Map<string, { name: string; importance?: string; note?: string }>()

  characterTriples.forEach(t => {
    const a = tripleStringAttrs(t)
    const objImp = a.object_importance
    const noteFromDesc = t.description?.trim()
    if (!characterMap.has(t.subject)) {
      characterMap.set(t.subject, {
        name: t.subject,
        importance: t.importance,
        note: [t.note, noteFromDesc].filter(Boolean).join('\n') || '',
      })
    }
    if (!characterMap.has(t.object)) {
      characterMap.set(t.object, {
        name: t.object,
        importance: objImp,
        note: '',
      })
    } else if (objImp && !characterMap.get(t.object)?.importance) {
      const cur = characterMap.get(t.object)!
      characterMap.set(t.object, { ...cur, importance: objImp })
    }
  })

  const characters = Array.from(characterMap.entries()).map(([id, data]) => ({
    id,
    name: data.name,
    importance: data.importance,
    note: data.note || '',
  }))

  const relationships = characterTriples.map(t => ({
    id: t.id,
    source_id: t.subject,
    target_id: t.object,
    label: t.predicate,
    note: [t.note, t.description].filter(Boolean).join('\n') || '',
  }))

  return { characters, relationships }
})

const emptyHint = computed(() => graph.value.characters.length === 0 && !loading.value)

// 根据重要程度返回颜色
const getNodeColor = (importance?: string) => {
  switch (importance) {
    case 'primary':
      return { background: '#fecaca', border: '#ef4444' } // 主角-红色
    case 'secondary':
      return { background: '#fed7aa', border: '#f97316' } // 重要配角-橙色
    case 'minor':
      return { background: '#bfdbfe', border: '#3b82f6' } // 次要人物-蓝色
    default:
      return { background: '#e5e7eb', border: '#6b7280' } // 未分类-灰色
  }
}

const graphData = computed(() => {
  const visNodes: VisNode[] = graph.value.characters.map(c => {
    const importanceLabel = characterImportanceZh(c.importance)

    return {
      id: c.id,
      label: c.name + (importanceLabel ? `\n[${importanceLabel}]` : ''),
      title: [c.name, importanceLabel && `重要程度：${importanceLabel}`, c.note].filter(Boolean).join('\n'),
      color: getNodeColor(c.importance),
      font: { size: 14 },
      shape: 'box',
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
    let merged = (data.facts || []) as KnowledgeTriple[]
    try {
      const bible = await bibleApi.getBible(props.slug)
      merged = mergeKnowledgeFactsWithBibleCharacters(merged, bible.characters || []) as KnowledgeTriple[]
    } catch {
      merged = mergeKnowledgeFactsWithBibleCharacters(merged, []) as KnowledgeTriple[]
    }

    // Only update if this is still the latest request
    if (currentRequestId === requestId) {
      triples.value = merged
    }
  } catch (error) {
    console.error('Failed to load knowledge data:', error)
    if (currentRequestId === requestId) {
      window.$message?.error('加载人物关系失败，请稍后重试')
    }
  } finally {
    if (currentRequestId === requestId) {
      loading.value = false
    }
  }
}

const handleNodeClick = (node: EChartsNode) => {
  router.push({ path: `/book/${props.slug}/cast`, query: { focus: node.id } })
}

const goFull = () => {
  router.push(`/book/${props.slug}/cast`)
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
.cgc-root {
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

.cgc-toolbar {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--app-border);
  background: var(--app-surface);
}

.cgc-hint {
  font-size: 11px;
  line-height: 1.45;
  max-width: min(100%, 380px);
}

.cgc-hint code {
  font-size: 10px;
  padding: 0 4px;
  border-radius: 4px;
  background: rgba(79, 70, 229, 0.08);
  color: #4338ca;
}

.cgc-canvas {
  flex: 1;
  min-height: 500px;
  width: 100%;
  position: relative;
}

/* 勿用 absolute + 固定 top：工具栏换行后高度 >48px 会与空状态叠在一起 */
.cgc-empty {
  flex: 1;
  min-height: 500px;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
