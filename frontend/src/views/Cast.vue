<template>
  <div class="cast-page">
    <header class="cast-header">
      <n-space align="center">
        <n-button quaternary round @click="goWorkbench">
          <template #icon><span class="ico">←</span></template>
          工作台
        </n-button>
        <n-divider vertical />
        <h1 class="cast-title">人物关系网</h1>
        <n-text depth="3">{{ slug }}</n-text>
      </n-space>
      <n-space>
        <n-input
          v-model:value="searchQ"
          placeholder="检索姓名、角色、关系…"
          clearable
          round
          style="width: 260px"
          @update:value="onSearch"
        />
        <n-button secondary @click="reload">刷新</n-button>
        <n-button type="primary" @click="openTriplesDrawer()">三元组表格</n-button>
        <n-button quaternary @click="goKnowledge">工作台 · 知识库</n-button>
      </n-space>
    </header>

    <div class="cast-body">
      <div class="net-wrap">
        <GraphChart
          :nodes="echartsNodes"
          :links="echartsLinks"
          height="100%"
          @node-click="handleNodeClick"
          @edge-click="handleEdgeClick"
        />
      </div>
      <aside class="cast-side">
        <n-collapse :default-expanded-names="['cov']" class="cov-collapse">
          <n-collapse-item title="正文与关系图" name="cov">
            <n-spin :show="covLoading" size="small">
              <template v-if="coverage">
                <n-text depth="3" class="cov-meta">
                  已扫描 {{ coverage.chapter_files_scanned }} 个章节文件
                  <template v-if="chapterFilter != null"> · 当前筛选第 {{ chapterFilter }} 章</template>
                </n-text>

                <div class="cov-block">
                  <div class="cov-block-title">关系图内角色</div>
                  <div v-for="row in visibleCastRows" :key="row.id" class="cov-row">
                    <div class="cov-row-main">
                      <n-button text type="primary" size="small" @click="focusCastNode(row.id)">
                        {{ row.name }}
                      </n-button>
                      <n-tag v-if="row.mentioned" size="small" type="success" round>正文已出现</n-tag>
                      <n-tag v-else size="small" type="warning" round>正文未见</n-tag>
                    </div>
                    <n-space v-if="row.chapter_ids.length" size="small" class="cov-chapters">
                      <n-button
                        v-for="cid in row.chapter_ids"
                        :key="cid"
                        size="tiny"
                        quaternary
                        :disabled="cid === 0"
                        @click="goChapter(cid)"
                      >
                        {{ cid === 0 ? '合并稿' : `第${cid}章` }}
                      </n-button>
                    </n-space>
                  </div>
                </div>

                <div v-if="coverage.bible_not_in_cast.length" class="cov-block">
                  <div class="cov-block-title">设定中有、关系图中尚无</div>
                  <div v-for="(b, i) in coverage.bible_not_in_cast" :key="'b' + i" class="cov-row">
                    <span class="cov-name">{{ b.name }}</span>
                    <n-tag v-if="b.in_novel_text" size="small" type="warning" round>正文已出现</n-tag>
                    <n-tag v-else size="small" round>未见正文</n-tag>
                    <n-space v-if="b.chapter_ids.length" size="small" class="cov-chapters">
                      <n-button
                        v-for="cid in b.chapter_ids"
                        :key="cid"
                        size="tiny"
                        quaternary
                        :disabled="cid === 0"
                        @click="goChapter(cid)"
                      >
                        {{ cid === 0 ? '合并稿' : `第${cid}章` }}
                      </n-button>
                    </n-space>
                  </div>
                </div>

                <div v-if="coverage.quoted_not_in_cast.length" class="cov-block">
                  <div class="cov-block-title">书名号「」未匹配关系图（需核对是否为人名）</div>
                  <div v-for="(q, i) in coverage.quoted_not_in_cast" :key="'q' + i" class="cov-row cov-row-quote">
                    <span>「{{ q.text }}」</span>
                    <n-text depth="3" class="cov-count">×{{ q.count }}</n-text>
                    <n-space v-if="q.chapter_ids.length" size="small" class="cov-chapters">
                      <n-button
                        v-for="cid in q.chapter_ids"
                        :key="cid"
                        size="tiny"
                        quaternary
                        @click="goChapter(cid)"
                      >
                        第{{ cid }}章
                      </n-button>
                    </n-space>
                  </div>
                </div>
              </template>
              <n-text v-else-if="!covLoading" depth="3">未能加载对照数据</n-text>
            </n-spin>
          </n-collapse-item>
        </n-collapse>

        <n-alert type="info" title="关系图由知识库三元组生成，可在此页直接编辑" style="margin-bottom: 16px;">
          <p>点击上方<strong>三元组表格</strong>打开抽屉编辑（默认筛选人物）；或在侧栏选中人物后点「编辑与此人相关」。</p>
          <p style="margin-top: 8px;"><strong>人物节点规范：</strong></p>
          <ul style="margin: 4px 0; padding-left: 20px;">
            <li>主语：人物名称</li>
            <li>谓词：是</li>
            <li>宾语：主角 / 配角 / 反派 / 人物</li>
            <li>备注：人物描述</li>
          </ul>
          <p style="margin-top: 8px;"><strong>人物关系规范：</strong></p>
          <ul style="margin: 4px 0; padding-left: 20px;">
            <li>主语：人物A</li>
            <li>谓词：师徒 / 父子 / 朋友 / 敌对 / ...</li>
            <li>宾语：人物B</li>
            <li>备注：关系说明</li>
          </ul>
          <n-space style="margin-top: 12px">
            <n-button type="primary" @click="openTriplesDrawer()">打开三元组表格</n-button>
            <n-button @click="goKnowledge">工作台知识库</n-button>
          </n-space>
        </n-alert>

        <n-tabs v-model:value="castPane" type="segment" animated>
          <n-tab-pane name="node" tab="人物详情">
            <div v-if="formChar.id" class="side-form">
              <n-button
                block
                type="primary"
                size="small"
                style="margin-bottom: 12px"
                @click="openTriplesDrawer(formChar.name)"
              >
                编辑与此人相关的三元组
              </n-button>
              <n-descriptions label-placement="left" :column="1" bordered size="small">
                <n-descriptions-item label="ID">{{ formChar.id }}</n-descriptions-item>
                <n-descriptions-item label="姓名">{{ formChar.name }}</n-descriptions-item>
                <n-descriptions-item label="别名">{{ formChar.aliasesStr || '无' }}</n-descriptions-item>
                <n-descriptions-item label="角色定位">{{ formChar.role || '无' }}</n-descriptions-item>
                <n-descriptions-item label="特点">{{ formChar.traits || '无' }}</n-descriptions-item>
                <n-descriptions-item label="备注">{{ formChar.note || '无' }}</n-descriptions-item>
              </n-descriptions>
            </div>
            <n-empty v-else description="点击图中节点查看人物详情" size="small" style="margin-top: 40px;" />
          </n-tab-pane>
          <n-tab-pane name="edge" tab="关系详情">
            <div v-if="formRel.id" class="side-form">
              <n-descriptions label-placement="left" :column="1" bordered size="small">
                <n-descriptions-item label="关系 ID">{{ formRel.id }}</n-descriptions-item>
                <n-descriptions-item label="起点人物">{{ formRel.source_id }}</n-descriptions-item>
                <n-descriptions-item label="终点人物">{{ formRel.target_id }}</n-descriptions-item>
                <n-descriptions-item label="关系类型">{{ formRel.label }}</n-descriptions-item>
                <n-descriptions-item label="备注">{{ formRel.note || '无' }}</n-descriptions-item>
                <n-descriptions-item label="有向边">{{ formRel.directed ? '是' : '否' }}</n-descriptions-item>
              </n-descriptions>
            </div>
            <n-empty v-else description="点击图中边查看关系详情" size="small" style="margin-top: 40px;" />
          </n-tab-pane>
        </n-tabs>
      </aside>
    </div>

    <n-drawer v-model:show="triplesDrawerOpen" :width="920" placement="right" display-directive="if">
      <n-drawer-content title="人物相关三元组" closable>
        <KnowledgeTriplesTableEditor
          v-if="triplesDrawerOpen"
          :key="triplesDrawerKey"
          :slug="slug"
          default-entity-filter="character"
          :focus-entity-name="triplesDrawerFocus"
          @saved="onTriplesSaved"
        />
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import GraphChart from '../components/charts/GraphChart.vue'
import KnowledgeTriplesTableEditor from '../components/knowledge/KnowledgeTriplesTableEditor.vue'
import { convertGraph, type VisNode, type VisEdge, type EChartsNode, type EChartsLink } from '../utils/visToEcharts'
import { castApi } from '../api/cast'

interface CastCharacter {
  id: string
  name: string
  aliases: string[]
  role: string
  traits: string
  note: string
  story_events?: Array<{ id: string; summary: string; chapter_id?: number | null; importance?: string }>
}

interface CastRelationship {
  id: string
  source_id: string
  target_id: string
  label: string
  note: string
  directed: boolean
  story_events?: Array<{ id: string; summary: string; chapter_id?: number | null; importance?: string }>
}

const route = useRoute()
const router = useRouter()
const message = useMessage()
const slug = route.params.slug as string

const graph = ref<{ characters: CastCharacter[]; relationships: CastRelationship[] }>({
  characters: [],
  relationships: [],
})

const searchQ = ref('')
const highlightIds = ref<Set<string>>(new Set())

const triplesDrawerOpen = ref(false)
const triplesDrawerFocus = ref('')
const triplesDrawerKey = ref(0)

interface CastCoveragePayload {
  chapter_files_scanned: number
  characters: Array<{ id: string; name: string; mentioned: boolean; chapter_ids: number[] }>
  bible_not_in_cast: Array<{
    name: string
    role: string
    in_novel_text: boolean
    chapter_ids: number[]
  }>
  quoted_not_in_cast: Array<{ text: string; count: number; chapter_ids: number[] }>
}

const coverage = ref<CastCoveragePayload | null>(null)
const covLoading = ref(false)

const chapterFilter = computed(() => {
  const c = route.query.chapter
  if (c == null || c === '') return null
  const n = parseInt(String(c), 10)
  return Number.isFinite(n) && n >= 0 ? n : null
})

const visibleCastRows = computed(() => {
  if (!coverage.value) return []
  const rows = coverage.value.characters
  const cf = chapterFilter.value
  if (cf == null) return rows
  return rows.filter(r => r.chapter_ids.includes(cf))
})

const castPane = ref<'node' | 'edge'>('node')

// 只读显示用的数据
const formChar = ref({
  id: '',
  name: '',
  aliasesStr: '',
  role: '',
  traits: '',
  note: '',
})

const formRel = ref({
  id: '',
  source_id: '',
  target_id: '',
  label: '',
  note: '',
  directed: true,
})

// 编辑功能已移除 - 关系图现为只读，从三元组自动生成

const buildVisData = () => {
  const hi = highlightIds.value
  const nodes: VisNode[] = graph.value.characters.map(c => {
    const ne = (c.story_events || []).length
    const base = [c.name, ...(c.aliases || []), c.traits, c.note].filter(Boolean).join('\n')
    const title = ne ? `${base}\n—\n人物线事件 ${ne} 条` : base
    return {
      id: c.id,
      label: c.name + (c.role ? `\n${c.role}` : '') + (ne ? `\n·${ne}事件` : ''),
      title,
      color: hi.size && !hi.has(c.id) ? { background: '#e2e8f0', border: '#cbd5e1' } : { background: '#c7d2fe', border: '#6366f1' },
      font: { size: 14 },
    }
  })
  const edges: VisEdge[] = graph.value.relationships.map(r => {
    const ne = (r.story_events || []).length
    const base = [r.label, r.note].filter(Boolean).join('\n')
    const title = ne ? `${base || '关系'}\n—\n共同经历 ${ne} 条` : base || undefined
    return {
      id: r.id,
      from: r.source_id,
      to: r.target_id,
      label: (r.label || '') + (ne ? ` ·${ne}` : ''),
      title,
      arrows: r.directed ? 'to' : undefined,
      font: { size: 11, align: 'middle' },
    }
  })
  return convertGraph(nodes, edges)
}

const echartsNodes = computed(() => buildVisData().nodes)
const echartsLinks = computed(() => buildVisData().links)

const handleNodeClick = (node: EChartsNode) => {
  const c = graph.value.characters.find(x => x.id === node.id)
  if (c) {
    castPane.value = 'node'
    formChar.value = {
      id: c.id,
      name: c.name,
      aliasesStr: (c.aliases || []).join(', '),
      role: c.role || '',
      traits: c.traits || '',
      note: c.note || '',
    }
  }
}

const handleEdgeClick = (link: EChartsLink) => {
  // Find relationship by matching source and target
  const r = graph.value.relationships.find(
    x => x.source_id === link.source && x.target_id === link.target
  )
  if (r) {
    castPane.value = 'edge'
    formRel.value = {
      id: r.id,
      source_id: r.source_id,
      target_id: r.target_id,
      label: r.label || '',
      note: r.note || '',
      directed: r.directed,
    }
  }
}

const loadCoverage = async () => {
  covLoading.value = true
  try {
    coverage.value = await castApi.getCastCoverage(slug)
  } catch {
    coverage.value = null
  } finally {
    covLoading.value = false
  }
}

const focusCastNode = (id: string) => {
  router.replace({ query: { ...route.query, focus: id } })
}

const goChapter = (cid: number) => {
  if (cid <= 0) return
  router.push(`/book/${slug}/chapter/${cid}`)
}

const reload = async () => {
  try {
    const data = await castApi.getCast(slug)
    graph.value = {
      characters: data.characters || [],
      relationships: data.relationships || [],
    }
    highlightIds.value = new Set()
    searchQ.value = ''
    await loadCoverage()
  } catch {
    message.error('加载失败')
  }
}

let searchTimer: number | null = null
const onSearch = () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = window.setTimeout(async () => {
    const q = searchQ.value.trim()
    if (!q) {
      highlightIds.value = new Set()
      return
    }
    try {
      const res = await castApi.searchCast(slug, q)
      const ids = new Set<string>()
      const chList = (res.characters || []) as CastCharacter[]
      const relList = (res.relationships || []) as CastRelationship[]
      chList.forEach(c => ids.add(c.id))
      relList.forEach(r => {
        ids.add(r.source_id)
        ids.add(r.target_id)
      })
      highlightIds.value = ids
    } catch {
      message.error('检索失败')
    }
  }, 280)
}

// 编辑功能已移除 - 关系图现为只读，从三元组自动生成

const goWorkbench = () => {
  router.push(`/book/${slug}/workbench`)
}

const goKnowledge = () => {
  router.push(`/book/${slug}/workbench?tab=knowledge`)
}

const openTriplesDrawer = (focusName?: string) => {
  triplesDrawerFocus.value = (focusName || '').trim()
  triplesDrawerKey.value += 1
  triplesDrawerOpen.value = true
}

const onTriplesSaved = async () => {
  await reload()
}

onMounted(async () => {
  await reload()
})

onUnmounted(() => {
  if (searchTimer) clearTimeout(searchTimer)
})
</script>

<style scoped>
.cast-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--app-page-bg, #f0f2f8);
}

.cast-header {
  flex-shrink: 0;
  padding: 12px 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  border-bottom: 1px solid var(--app-border);
  background: var(--app-surface);
}

.cast-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
}

.ico {
  font-size: 15px;
}

.cast-body {
  flex: 1;
  min-height: 0;
  display: flex;
}

.net-wrap {
  flex: 1;
  min-width: 0;
  min-height: 0;
  background: var(--app-surface-subtle);
  border-right: 1px solid var(--app-border);
}

.cast-side {
  width: min(400px, 42vw);
  flex-shrink: 0;
  padding: 12px;
  overflow: auto;
  background: var(--app-surface);
}

.side-form {
  padding-top: 8px;
}

.ev-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: flex-start;
  margin-bottom: 10px;
  padding: 8px;
  border-radius: 8px;
  background: rgba(79, 70, 229, 0.05);
  border: 1px solid rgba(99, 102, 241, 0.12);
}

.ev-id {
  width: 100px;
  flex-shrink: 0;
}

.ev-ch {
  width: 88px;
  flex-shrink: 0;
}

.ev-imp {
  width: 92px;
  flex-shrink: 0;
}

.ev-sum {
  flex: 1 1 100%;
  min-width: 0;
}

.cast-hint {
  margin-top: 12px;
}

.cov-collapse {
  margin-bottom: 10px;
}

.cov-collapse :deep(.n-collapse-item__header) {
  font-weight: 600;
  font-size: 13px;
}

.cov-meta {
  display: block;
  margin-bottom: 10px;
  font-size: 12px;
}

.cov-block {
  margin-bottom: 12px;
}

.cov-block-title {
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  margin-bottom: 6px;
}

.cov-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 6px 0;
  border-bottom: 1px solid rgba(15, 23, 42, 0.06);
  font-size: 13px;
}

.cov-row:last-child {
  border-bottom: none;
}

.cov-row-main {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.cov-name {
  font-weight: 500;
}

.cov-chapters {
  flex-wrap: wrap;
}

.cov-row-quote {
  flex-direction: row;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.cov-count {
  font-size: 12px;
}
</style>
