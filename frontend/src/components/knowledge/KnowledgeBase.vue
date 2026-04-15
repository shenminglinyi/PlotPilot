<template>
  <div class="kb-root">
    <div class="kb-toolbar">
      <n-text depth="3" class="kb-hint">
        知识库：全书三元组。图谱总览、JSON 批量编辑；结构化表格请点「三元组表格」（与人物网 / 地点关系图全页的编辑能力相同）。
      </n-text>
      <n-space :size="8">
        <n-button size="small" secondary @click="tableDrawerOpen = true">三元组表格</n-button>
        <n-button size="small" quaternary :loading="loading" @click="reload">刷新</n-button>
      </n-space>
    </div>

    <n-tabs v-model:value="viewMode" type="line" size="medium" animated class="kb-tabs">
      <n-tab-pane name="graph" tab="图谱">
        <div v-if="emptyHint" class="kb-empty">
          <n-empty description="尚无三元组，可打开「三元组表格」添加，或编辑 JSON / 使用 kg_upsert_fact" size="small" />
        </div>
        <GraphChart v-else :nodes="graphData.nodes" :links="graphData.links" height="calc(100vh - 200px)" />
      </n-tab-pane>

      <n-tab-pane name="json" tab="JSON">
        <n-space :size="8" style="margin-bottom: 10px">
          <n-button size="small" type="primary" :loading="saving" @click="saveJson">保存 JSON</n-button>
          <n-button size="small" @click="formatJson">格式化</n-button>
        </n-space>
        <n-input
          v-model:value="jsonText"
          type="textarea"
          :autosize="{ minRows: 20, maxRows: 40 }"
          placeholder="JSON 数组：与 GET /knowledge 返回的 facts 格式一致"
          class="kb-json-editor"
          :status="jsonError ? 'error' : undefined"
        />
        <n-text v-if="jsonError" type="error" depth="3" style="font-size: 12px; margin-top: 8px; display: block;">
          {{ jsonError }}
        </n-text>
      </n-tab-pane>
    </n-tabs>

    <n-drawer v-model:show="tableDrawerOpen" :width="drawerWidth" placement="right" display-directive="if">
      <n-drawer-content title="三元组表格" closable>
        <KnowledgeTriplesTableEditor
          v-if="tableDrawerOpen"
          :slug="slug"
          default-entity-filter="all"
          @saved="onTableSaved"
        />
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { useMessage } from 'naive-ui'
import { knowledgeApi, type ChapterSummary, type KnowledgeTriple } from '../../api/knowledge'
import GraphChart from '../charts/GraphChart.vue'
import KnowledgeTriplesTableEditor from './KnowledgeTriplesTableEditor.vue'
import { convertGraph, type VisNode, type VisEdge, type EChartsGraphData } from '../../utils/visToEcharts'

const props = defineProps<{ slug: string }>()
const message = useMessage()

const drawerWidth = 920

const viewMode = ref<'graph' | 'json'>('graph')
const tableDrawerOpen = ref(false)
const loading = ref(false)
const saving = ref(false)
const facts = ref<KnowledgeTriple[]>([])
const storyVersion = ref(1)
const premiseLock = ref('')
const chaptersSnapshot = ref<ChapterSummary[]>([])
const jsonText = ref('')
const jsonError = ref('')
const graphData = ref<EChartsGraphData>({ nodes: [], links: [] })

const emptyHint = computed(() => facts.value.length === 0 && !loading.value)

const buildVisData = () => {
  const labelToId = new Map<string, string>()
  let nextN = 0

  const entityId = (raw: string) => {
    const label = (raw || '').trim() || '（空）'
    if (!labelToId.has(label)) {
      labelToId.set(label, `ent_${nextN++}`)
    }
    return labelToId.get(label)!
  }

  const nodeSeen = new Set<string>()
  const nodes: VisNode[] = []
  const edges: VisEdge[] = []

  for (const f of facts.value) {
    const sid = entityId(f.subject)
    const oid = entityId(f.object)
    if (!nodeSeen.has(sid)) {
      nodeSeen.add(sid)
      const lab = (f.subject || '').trim() || '（空）'
      nodes.push({
        id: sid,
        label: lab.length > 42 ? `${lab.slice(0, 40)}…` : lab,
        title: lab,
        color: { background: '#e0e7ff', border: '#6366f1' },
        font: { size: 13 },
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
    const data = await knowledgeApi.getKnowledge(props.slug)
    storyVersion.value = data.version ?? 1
    premiseLock.value = data.premise_lock ?? ''
    chaptersSnapshot.value = Array.isArray(data.chapters) ? [...data.chapters] : []
    facts.value = data.facts || []
    jsonText.value = JSON.stringify(data.facts || [], null, 2)
    jsonError.value = ''
    await redraw()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '加载失败')
  } finally {
    loading.value = false
  }
}

const onTableSaved = async () => {
  await reload()
}

const save = async () => {
  saving.value = true
  try {
    await knowledgeApi.putKnowledge(props.slug, {
      version: storyVersion.value,
      premise_lock: premiseLock.value,
      chapters: chaptersSnapshot.value,
      facts: facts.value,
    })
    message.success('已保存')
    await reload()
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

const formatJson = () => {
  try {
    const parsed = JSON.parse(jsonText.value)
    jsonText.value = JSON.stringify(parsed, null, 2)
    jsonError.value = ''
  } catch (e: any) {
    jsonError.value = `JSON 格式错误: ${e.message}`
  }
}

const saveJson = async () => {
  try {
    const parsed = JSON.parse(jsonText.value)
    if (!Array.isArray(parsed)) {
      jsonError.value = 'JSON 必须是数组格式'
      return
    }
    facts.value = parsed
    jsonError.value = ''
    await save()
  } catch (e: any) {
    jsonError.value = `JSON 格式错误: ${e.message}`
  }
}

watch(() => facts.value, redraw, { deep: true })

onMounted(() => {
  void reload()
})
</script>

<style scoped>
.kb-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--app-surface);
}

.kb-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid #e5e7eb;
  flex-shrink: 0;
}

.kb-hint {
  font-size: 13px;
}

.kb-tabs {
  flex: 1;
  overflow: hidden;
}

.kb-tabs :deep(.n-tabs-nav) {
  padding-left: 16px;
}

.kb-tabs :deep(.n-tabs-pane-wrapper) {
  padding: 16px;
  overflow-y: auto;
  height: calc(100vh - 200px);
}

.kb-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 400px;
}

.kb-json-editor {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
}
</style>
