<template>
  <div class="kp-root">
    <header class="kp-hero">
      <div class="kp-hero-copy">
        <h3 class="kp-title">侧栏资料</h3>
        <p class="kp-lead">
          可在「检索与编辑」「叙事知识」「关系图」间切换：检索与编辑含全书知识检索、三元组图谱与表格编辑；叙事含<strong>分章叙事</strong>与实体状态；<strong>梗概锁定已迁至右侧「剧本基建 → 作品设定」</strong>。<strong>关系图从知识库三元组自动生成</strong>（人物网 / 地点图全页与工作台均可打开「三元组表格」编辑）。书目级梗概以
          <strong>manifest</strong> 为准。
        </p>
      </div>
      <n-space v-show="sideTab === 'narrative'" :size="8" align="center" style="flex-shrink:0">
        <n-button
          size="small"
          secondary
          :loading="generating"
          @click="generateKnowledge"
          title="用 AI 根据 Bible 生成叙事知识（梗概锁定请在作品设定中编辑）"
        >
          ✦ AI 生成叙事
        </n-button>
        <n-button
          type="primary"
          size="small"
          :loading="saving"
          round
          @click="save"
        >
          保存到全书上下文
        </n-button>
      </n-space>
    </header>

    <n-radio-group v-model:value="sideTab" class="kp-seg" size="small">
      <n-radio-button value="search">检索与编辑</n-radio-button>
      <n-radio-button value="narrative">叙事知识</n-radio-button>
      <n-radio-button value="graph">关系图</n-radio-button>
    </n-radio-group>

    <div v-show="sideTab === 'search'" class="kp-search-container">
      <!-- 搜索区域 -->
      <n-card class="kp-search-card" size="small" :bordered="false">
        <n-space align="center" :size="10" wrap>
          <n-input
            v-model:value="searchQ"
            size="small"
            placeholder="全书知识检索：人物、关系、章摘要、事实…"
            class="kp-search-input"
            @keydown.enter.prevent="doSearch"
          />
          <n-button size="small" secondary :loading="searching" @click="doSearch">检索</n-button>
          <n-button size="small" quaternary @click="useHitToComposer" :disabled="!searchHits.length">
            引用到输入框
          </n-button>
        </n-space>
        <div v-if="searchHits.length" class="kp-search-list">
          <div
            v-for="(h, i) in searchHits"
            :key="h.id || i"
            class="kp-hit"
            :class="{ active: expandedIndex === i, collapsed: expandedIndex >= 0 && expandedIndex !== i }"
            @click="expandedIndex = expandedIndex === i ? -1 : i"
          >
            <div class="kp-hit-meta">
              <n-tag size="tiny" round :bordered="false" :type="h.meta?.match_type === 'semantic' ? 'success' : 'default'">
                {{ h.meta?.match_type === 'semantic' ? '向量' : '文本' }}
              </n-tag>
              <n-tag v-if="h.meta?.score != null" size="tiny" round :bordered="false" type="info">
                {{ (h.meta.score * 100).toFixed(0) }}%
              </n-tag>
              <span v-if="h.meta?.chapter_id" class="kp-hit-ch">第{{ h.meta.chapter_id }}章</span>
            </div>
            <div class="kp-hit-text" :class='{ "kp-hit-collapsed": expandedIndex >= 0 && expandedIndex !== i }'>
              {{ (expandedIndex === i || expandedIndex < 0) ? h.text : (h.text.length > 60 ? h.text.slice(0, 60) + '…' : h.text) }}
            </div>
          </div>
          <div v-if="searchHits.length > 1" class="kp-search-more">
            共 {{ searchHits.length }} 条结果 · 点击切换展开
          </div>
        </div>
        <div v-else-if="!searching" class="kp-search-empty">
          <n-text depth="3" style="font-size: 12px">提示：先用工具把资料写入侧栏，检索命中会更稳定。</n-text>
        </div>
      </n-card>

      <!-- 编辑区域 -->
      <div class="kp-edit-section">
        <div class="kp-edit-header">
          <n-text depth="3" style="font-size: 12px">
            三元组编辑：图谱总览、JSON 批量编辑、表格编辑
          </n-text>
          <n-space :size="8">
            <n-button size="small" secondary @click="knowledgeTableOpen = true">三元组表格</n-button>
            <n-button size="small" quaternary :loading="knowledgeLoading" @click="reloadKnowledge">刷新</n-button>
          </n-space>
        </div>

        <div class="kp-edit-toolbar">
          <n-button-group size="small">
            <n-button :type="knowledgeView === 'graph' ? 'primary' : 'default'" @click="knowledgeView = 'graph'">
              图谱
            </n-button>
            <n-button :type="knowledgeView === 'json' ? 'primary' : 'default'" @click="knowledgeView = 'json'">
              JSON
            </n-button>
            <n-button :type="knowledgeView === 'triples' ? 'primary' : 'default'" @click="knowledgeView = 'triples'; loadTriples()">
              三元组管理
            </n-button>
          </n-button-group>
        </div>

        <div class="kp-edit-content">
          <KnowledgeGraphView v-if="knowledgeView === 'graph'" :slug="slug" @reload="reloadKnowledge" />
          <KnowledgeJsonView v-if="knowledgeView === 'json'" :slug="slug" @reload="reloadKnowledge" />

          <!-- 三元组管理 -->
          <div v-if="knowledgeView === 'triples'" class="kp-triples-container">
            <!-- 统计 + 操作 -->
            <n-space justify="space-between" align="center" class="kp-triples-toolbar">
              <n-space :size="6" align="center" wrap>
                <template v-if="kgStats">
                  <n-tag type="info" size="small" round>共 {{ kgStats.total_triples }} 条</n-tag>
                  <n-tag size="small" round>高置信 {{ kgStats.confidence_distribution.high }}</n-tag>
                  <n-tag type="warning" size="small" round>中 {{ kgStats.confidence_distribution.medium }}</n-tag>
                  <n-tag type="error" size="small" round>低 {{ kgStats.confidence_distribution.low }}</n-tag>
                </template>
              </n-space>
              <n-space :size="6">
                <n-button size="tiny" secondary :loading="inferring" @click="inferAll">全书推断</n-button>
                <n-select
                  v-model:value="tripleFilter"
                  :options="tripleFilterOptions"
                  size="tiny"
                  style="width:110px"
                  @update:value="loadTriples"
                />
              </n-space>
            </n-space>

            <n-spin :show="triplesLoading">
              <n-space v-if="triples.length" vertical :size="6" class="kp-triples-list">
                <div
                  v-for="t in triples"
                  :key="t.id"
                  class="triple-row"
                >
                  <div class="triple-body">
                    <n-tag size="tiny" round :type="t.source_type === 'manual' ? 'success' : t.source_type === 'chapter_inferred' ? 'info' : 'default'">
                      {{ t.source_type }}
                    </n-tag>
                    <span class="triple-text">
                      <strong>{{ t.subject }}</strong>
                      <em> {{ t.predicate }} </em>
                      <strong>{{ t.object }}</strong>
                    </span>
                    <n-text depth="3" style="font-size:11px">
                      {{ (t.confidence * 100).toFixed(0) }}%
                    </n-text>
                  </div>
                  <n-space :size="4" class="triple-actions">
                    <n-button
                      v-if="t.source_type !== 'manual'"
                      size="tiny"
                      type="success"
                      secondary
                      :loading="confirmingId === t.id"
                      @click="doConfirmTriple(t)"
                    >确认</n-button>
                    <n-button
                      size="tiny"
                      type="error"
                      secondary
                      :loading="deletingId === t.id"
                      @click="doDeleteTriple(t)"
                    >删除</n-button>
                  </n-space>
                </div>
              </n-space>
              <n-empty v-else-if="!triplesLoading" description="暂无三元组，可点击「全书推断」自动生成" />
            </n-spin>
          </div>
        </div>
      </div>

      <!-- 三元组表格抽屉 -->
      <n-drawer v-model:show="knowledgeTableOpen" :width="920" placement="right" display-directive="if">
        <n-drawer-content title="三元组表格" closable>
          <KnowledgeTriplesTableEditor
            v-if="knowledgeTableOpen"
            :slug="slug"
            default-entity-filter="all"
            @saved="onKnowledgeTableSaved"
          />
        </n-drawer-content>
      </n-drawer>
    </div>

    <div v-show="sideTab === 'narrative'" class="kp-narrative-container">
      <div class="kp-banner">
        <span class="kp-banner-dot" aria-hidden="true" />
        <span class="kp-banner-text">
          分章叙事可由工具（<code>story_*</code>）写入，也可在此手改后保存。梗概锁定请在「作品设定」中编辑。每章「节拍」对应大纲子段落；人物名请与关系图一致。<strong>人物关系请在「知识库」中编辑三元组。</strong>
        </span>
      </div>

      <n-tabs
        v-model:value="subTab"
        type="line"
        size="small"
        animated
        class="kp-subtabs"
      >
        <n-tab-pane name="chapters" tab="分章叙事">
        <section class="kp-section">
        <div class="kp-section-head">
          <span class="kp-section-icon">◇</span>
          <span class="kp-section-title">分章叙事</span>
          <n-tag size="tiny" round :bordered="false" class="kp-tag-tool">story_upsert_chapter_summary</n-tag>
        </div>
        <p class="kp-section-hint">章标题来自书目大纲；每章含节拍子段、章末总结与同步状态。</p>

        <div class="kp-chapters">
          <n-card
            v-for="ch in sortedChapters"
            :key="ch.chapter_id"
            size="small"
            class="kp-card kp-ch-card"
            :bordered="false"
          >
            <template #header>
              <div class="kp-ch-head">
                <div class="kp-ch-title">
                  <span class="kp-ch-num">第 {{ ch.chapter_id }} 章</span>
                  <span v-if="chapterTitle(ch.chapter_id)" class="kp-ch-outline">{{ chapterTitle(ch.chapter_id) }}</span>
                </div>
                <n-select
                  v-model:value="ch.sync_status"
                  size="tiny"
                  class="kp-sync-select"
                  :options="syncOptions"
                />
              </div>
            </template>

            <div class="kp-ch-body">
              <div class="kp-field">
                <label class="kp-label">大纲下子段落 · 节拍</label>
                <n-dynamic-input
                  v-model:value="ch.beat_sections"
                  :min="0"
                  :on-create="() => ''"
                  placeholder="每行一条：如「夜袭前奏 · 主角与 X 对峙」"
                  class="kp-dynamic"
                />
              </div>

              <div class="kp-field">
                <label class="kp-label">章末总结</label>
                <n-input
                  v-model:value="ch.summary"
                  type="textarea"
                  :autosize="{ minRows: 3, maxRows: 12 }"
                  placeholder="本章收束叙述，供上下文与工具对齐…"
                  class="kp-textarea"
                />
              </div>

              <div class="kp-grid-2">
                <div class="kp-field">
                  <label class="kp-label">人物与关键事件</label>
                  <n-input
                    v-model:value="ch.key_events"
                    type="textarea"
                    :autosize="{ minRows: 2, maxRows: 8 }"
                    placeholder="与关系图人物名一致，便于图谱与叙事对齐…"
                    class="kp-textarea"
                  />
                </div>
                <div class="kp-field">
                  <label class="kp-label">埋线 / 未解</label>
                  <n-input
                    v-model:value="ch.open_threads"
                    type="textarea"
                    :autosize="{ minRows: 2, maxRows: 8 }"
                    placeholder="伏笔、未解问题…"
                    class="kp-textarea"
                  />
                </div>
              </div>

              <div class="kp-field">
                <label class="kp-label">一致性说明</label>
                <n-input
                  v-model:value="ch.consistency_note"
                  type="textarea"
                  :autosize="{ minRows: 2, maxRows: 6 }"
                  placeholder="与前章 / 大纲 / 梗概锁定的对齐说明…"
                  class="kp-textarea"
                />
              </div>

              <div class="kp-ch-foot">
                <n-button size="tiny" quaternary type="error" @click="removeChapterById(ch.chapter_id)">
                  移除此章条目
                </n-button>
                <n-button size="tiny" quaternary @click="goCastChapter(ch.chapter_id)">全页关系网 · 本章</n-button>
              </div>
            </div>
          </n-card>
        </div>

        <n-button dashed block class="kp-add-ch" @click="addChapter">+ 添加一章叙事块</n-button>
        </section>
      </n-tab-pane>

      <n-tab-pane name="entity-state" tab="实体状态">
        <section class="kp-section">
          <div class="kp-section-head">
            <span class="kp-section-icon">◈</span>
            <span class="kp-section-title">实体状态快照</span>
          </div>
          <p class="kp-section-hint">输入实体 ID 和章节号，查询该实体在指定章节时的叙事状态（通过回放该章之前所有事件计算得出）。</p>

          <n-card size="small" class="kp-card" :bordered="false">
            <n-space vertical :size="12">
              <n-space :size="10" align="center">
                <n-form-item label="实体 ID" label-placement="left" label-width="65" :show-feedback="false">
                  <n-input
                    v-model:value="entityStateId"
                    placeholder="如：char-001 或角色名"
                    style="width:160px"
                    size="small"
                  />
                </n-form-item>
                <n-form-item label="章节" label-placement="left" label-width="36" :show-feedback="false">
                  <n-input-number v-model:value="entityStateChapter" :min="1" style="width:88px" size="small" />
                </n-form-item>
                <n-button size="small" type="primary" :loading="entityStateLoading" @click="fetchEntityState">
                  查询
                </n-button>
              </n-space>

              <template v-if="entityStateResult">
                <n-divider style="margin:4px 0" />
                <n-space vertical :size="6">
                  <n-space align="center" :size="6">
                    <n-tag type="info" round size="small">{{ entityStateResult.entity_id }}</n-tag>
                    <n-text depth="3" style="font-size:12px">第 {{ entityStateChapter }} 章时的状态</n-text>
                  </n-space>
                  <div class="entity-state-grid">
                    <template v-for="(v, k) in entityStateDisplay" :key="k">
                      <n-text depth="3" class="estate-key">{{ k }}</n-text>
                      <n-text class="estate-val">{{ v }}</n-text>
                    </template>
                  </div>
                </n-space>
              </template>
              <n-alert v-else-if="entityStateError" type="warning" :show-icon="false" style="font-size:12px">
                {{ entityStateError }}
              </n-alert>
            </n-space>
          </n-card>
        </section>
      </n-tab-pane>
    </n-tabs>
    </div>

    <div v-if="sideTab === 'graph'" class="kp-graph-container">
      <div class="kp-graph-nav">
        <n-space :size="8">
          <n-button
            size="small"
            :type="graphFilter === 'character' ? 'primary' : 'default'"
            @click="graphFilter = 'character'"
          >
            <template #icon>
              <n-icon><PeopleOutline /></n-icon>
            </template>
            人物关系图
          </n-button>
          <n-button
            size="small"
            :type="graphFilter === 'location' ? 'primary' : 'default'"
            @click="graphFilter = 'location'"
          >
            <template #icon>
              <n-icon><LocationOutline /></n-icon>
            </template>
            地点关系图
          </n-button>
        </n-space>
      </div>
      <CastGraphCompact v-if="graphFilter === 'character'" :slug="slug" class="kp-graph-embed" />
      <LocationGraphCompact v-if="graphFilter === 'location'" :slug="slug" class="kp-graph-embed" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useWorkbenchRefreshStore } from '../../stores/workbenchRefreshStore'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import { PeopleOutline, LocationOutline } from '@vicons/ionicons5'
import { chapterApi } from '../../api/chapter'
import { knowledgeApi } from '../../api/knowledge'
import { narrativeStateApi } from '../../api/tools'
import type { EntityState } from '../../api/tools'
import { knowledgeGraphApi } from '../../api/knowledgeGraph'
import type { TripleDTO, KGStatistics } from '../../api/knowledgeGraph'
import CastGraphCompact from '../graphs/CastGraphCompact.vue'
import LocationGraphCompact from '../graphs/LocationGraphCompact.vue'
import KnowledgeGraphView from './KnowledgeGraphView.vue'
import KnowledgeJsonView from './KnowledgeJsonView.vue'
import KnowledgeTriplesTableEditor from './KnowledgeTriplesTableEditor.vue'


const props = defineProps<{ slug: string }>()
const router = useRouter()
const message = useMessage()

// 关系图过滤器：切换人物/地点
const graphFilter = ref<'character' | 'location'>('character')

// 知识库编辑相关
const knowledgeTableOpen = ref(false)
const knowledgeLoading = ref(false)

interface Ch {
  chapter_id: number
  summary: string
  key_events: string
  open_threads: string
  consistency_note: string
  beat_sections: string[]
  sync_status: string
}

interface Fact {
  id: string
  subject: string
  predicate: string
  object: string
  chapter_id: number | null
  note: string
}

const data = ref({
  version: 1,
  premise_lock: '',
  chapters: [] as Ch[],
  facts: [] as Fact[],
})

const saving = ref(false)
const generating = ref(false)
const sideTab = ref<'search' | 'narrative' | 'graph'>('search')
const subTab = ref<'chapters' | 'entity-state'>('chapters')
const knowledgeView = ref<'graph' | 'json' | 'triples'>('graph')

// 三元组管理
const triples = ref<TripleDTO[]>([])
const kgStats = ref<KGStatistics | null>(null)
const triplesLoading = ref(false)
const inferring = ref(false)
const confirmingId = ref<string | null>(null)
const deletingId = ref<string | null>(null)
const tripleFilter = ref<string | undefined>(undefined)
const tripleFilterOptions = [
  { label: '全部', value: undefined },
  { label: '手动', value: 'manual' },
  { label: '推断', value: 'chapter_inferred' },
  { label: 'AI生成', value: 'ai_generated' },
]

const loadTriples = async () => {
  triplesLoading.value = true
  try {
    const [tripleRes, statsRes] = await Promise.all([
      knowledgeGraphApi.getTriples(props.slug, tripleFilter.value),
      knowledgeGraphApi.getStatistics(props.slug),
    ])
    triples.value = tripleRes.data.triples
    kgStats.value = statsRes.data
  } catch {
    message.error('加载三元组失败')
  } finally {
    triplesLoading.value = false
  }
}

const inferAll = async () => {
  inferring.value = true
  try {
    const res = await knowledgeGraphApi.inferNovel(props.slug)
    message.success('全书推断完成')
    await loadTriples()
  } catch {
    message.error('推断失败')
  } finally {
    inferring.value = false
  }
}

const doConfirmTriple = async (t: TripleDTO) => {
  confirmingId.value = t.id
  try {
    await knowledgeGraphApi.confirmTriple(t.id)
    message.success('已确认为手动三元组')
    t.source_type = 'manual'
    t.confidence = 1.0
  } catch {
    message.error('确认失败')
  } finally {
    confirmingId.value = null
  }
}

const doDeleteTriple = async (t: TripleDTO) => {
  deletingId.value = t.id
  try {
    await knowledgeGraphApi.deleteTriple(t.id)
    message.success('已删除')
    triples.value = triples.value.filter(x => x.id !== t.id)
    if (kgStats.value) kgStats.value.total_triples -= 1
  } catch {
    message.error('删除失败')
  } finally {
    deletingId.value = null
  }
}

// 实体状态查询
const entityStateId = ref('')
const entityStateChapter = ref(1)
const entityStateLoading = ref(false)
const entityStateResult = ref<EntityState | null>(null)
const entityStateError = ref('')

const entityStateDisplay = computed(() => {
  if (!entityStateResult.value) return {}
  const { entity_id, ...rest } = entityStateResult.value
  return rest
})

const fetchEntityState = async () => {
  if (!entityStateId.value.trim()) { message.warning('请输入实体 ID'); return }
  entityStateLoading.value = true
  entityStateResult.value = null
  entityStateError.value = ''
  try {
    entityStateResult.value = await narrativeStateApi.getState(
      props.slug,
      entityStateId.value.trim(),
      entityStateChapter.value
    )
  } catch (e: unknown) {
    const err = e as { response?: { status?: number } }
    entityStateError.value = err.response?.status === 404
      ? `未找到实体「${entityStateId.value}」`
      : '查询失败，请确认实体 ID 是否正确'
  } finally {
    entityStateLoading.value = false
  }
}
const outlineTitles = ref<Record<number, string>>({})
const searchQ = ref('')
const searching = ref(false)
const searchHits = ref<any[]>([])
const expandedIndex = ref(0) // 默认展开第一条

const doSearch = async () => {
  const q = searchQ.value.trim()
  if (!q) return
  searching.value = true
  expandedIndex.value = 0 // 每次搜索重置为展开第一条
  try {
    const r = await knowledgeApi.searchKnowledge(props.slug, q, 8)
    searchHits.value = r.hits || []
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '检索失败')
  } finally {
    searching.value = false
  }
}

const useHitToComposer = () => {
  const h = expandedIndex.value >= 0 ? searchHits.value[expandedIndex.value] : null
  if (!h) return
  const t = String(h.text || '').trim()
  if (!t) return
  window.dispatchEvent(new CustomEvent('aitext:composer:insert', { detail: { text: t } }))
  message.success('已引用到输入框')
}

const syncOptions = [
  { label: '草稿', value: 'draft' },
  { label: '已对齐', value: 'synced' },
  { label: '待更新', value: 'stale' },
]

const sortedChapters = computed(() =>
  [...data.value.chapters].sort((a, b) => a.chapter_id - b.chapter_id)
)

const chapterTitle = (cid: number) => outlineTitles.value[cid] || ''

const loadOutlineTitles = async () => {
  try {
    const list = await chapterApi.listChapters(props.slug)
    const m: Record<number, string> = {}
    for (const ch of list) {
      if (ch.number != null) m[Number(ch.number)] = (ch.title || '').trim()
    }
    outlineTitles.value = m
  } catch {
    outlineTitles.value = {}
  }
}

const load = async () => {
  try {
    const k = await knowledgeApi.getKnowledge(props.slug)
    data.value = {
      version: k.version ?? 1,
      premise_lock: k.premise_lock || '',
      chapters: (k.chapters || []).map((c: any) => ({
        chapter_id: c.chapter_id,
        summary: c.summary || '',
        key_events: c.key_events || '',
        open_threads: c.open_threads || '',
        consistency_note: c.consistency_note || '',
        beat_sections: Array.isArray(c.beat_sections) ? [...c.beat_sections] : [],
        sync_status: (() => {
          const s = String(c.sync_status || 'draft').toLowerCase()
          return ['draft', 'synced', 'stale'].includes(s) ? s : 'draft'
        })(),
      })),
      facts: (k.facts || []).map((f: any) => ({
        id: f.id,
        subject: f.subject || '',
        predicate: f.predicate || '',
        object: f.object || '',
        chapter_id: f.chapter_id ?? null,
        note: f.note || '',
      })),
    }
    await loadOutlineTitles()
  } catch (e: any) {
    console.error('加载叙事知识失败:', e)
    message.error(e?.response?.data?.detail || '加载叙事知识失败')
  }
}

const save = async () => {
  saving.value = true
  try {
    const server = await knowledgeApi.getKnowledge(props.slug)
    await knowledgeApi.updateKnowledge(props.slug, {
      version: server.version,
      premise_lock: server.premise_lock,
      chapters: sortedChapters.value.map(c => ({
        ...c,
        chapter_id: Number(c.chapter_id),
        beat_sections: (c.beat_sections || []).map(s => String(s || '').trim()).filter(Boolean),
        sync_status: (c.sync_status || 'draft').toLowerCase(),
      })),
      facts: server.facts ?? [],
    })
    data.value.premise_lock = server.premise_lock
    message.success('已保存并进入全书上下文')
  } catch (e: any) {
    message.error(e?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

const generateKnowledge = async () => {
  generating.value = true
  try {
    const res = await knowledgeApi.generateKnowledge(props.slug)
    message.success(res.message || 'Knowledge 生成成功')
    await load()
    subTab.value = 'chapters'
  } catch (e: any) {
    message.error(e?.response?.data?.detail || 'AI 生成失败，请确认 API Key 已配置')
  } finally {
    generating.value = false
  }
}

const addChapter = () => {
  const ids = data.value.chapters.map(c => Number(c.chapter_id)).filter(n => Number.isFinite(n))
  const next = ids.length ? Math.max(...ids) + 1 : 1
  data.value.chapters.push({
    chapter_id: next,
    summary: '',
    key_events: '',
    open_threads: '',
    consistency_note: '',
    beat_sections: [],
    sync_status: 'draft',
  })
}

const removeChapterById = (cid: number) => {
  data.value.chapters = data.value.chapters.filter(c => c.chapter_id !== cid)
}

const goCastChapter = (cid: number) => {
  router.push({ path: `/book/${props.slug}/cast`, query: { chapter: String(cid) } })
}

const reloadKnowledge = () => {
  knowledgeLoading.value = true
  // 触发子组件重新加载
  window.dispatchEvent(new CustomEvent('aitext:knowledge:reload'))
  setTimeout(() => {
    knowledgeLoading.value = false
  }, 500)
}

const onKnowledgeTableSaved = () => {
  reloadKnowledge()
}

watch(
  () => props.slug,
  () => {
    void load()
  }
)

const refreshStore = useWorkbenchRefreshStore()
const { deskTick } = storeToRefs(refreshStore)
watch(deskTick, () => {
  void load()
  void loadTriples()
})

function onKnowledgeReloadFromOutside() {
  void load()
}

onMounted(() => {
  void load()
  window.addEventListener('aitext:knowledge:reload', onKnowledgeReloadFromOutside)
})

onUnmounted(() => {
  window.removeEventListener('aitext:knowledge:reload', onKnowledgeReloadFromOutside)
})
</script>

<style scoped>
.kp-root {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 12px 12px 8px;
  background: linear-gradient(180deg, var(--app-surface-subtle) 0%, var(--app-border) 100%);
}

.kp-hero {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;
  flex-shrink: 0;
}

.kp-title {
  margin: 0 0 6px;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.03em;
  color: var(--app-text-primary);
}

.kp-lead {
  margin: 0;
  font-size: 12px;
  line-height: 1.65;
  color: var(--app-text-muted);
  max-width: 520px;
}

.kp-lead strong {
  color: var(--app-text-secondary);
}

.kp-lead code {
  font-size: 11px;
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--color-brand-light);
  color: var(--color-brand);
}

.kp-banner {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  margin-bottom: 12px;
  border-radius: 10px;
  background: var(--color-brand-light);
  border: 1px solid var(--color-brand-border);
  flex-shrink: 0;
}

.kp-banner-dot {
  width: 6px;
  height: 6px;
  margin-top: 6px;
  border-radius: 50%;
  background: var(--color-brand);
  flex-shrink: 0;
}

.kp-banner-text {
  font-size: 11px;
  line-height: 1.55;
  color: var(--app-text-muted);
}

.kp-scroll {
  flex: 1;
  min-height: 0;
}

.kp-subtabs {
  flex: 1;
  min-height: 0;
  margin-top: 10px;
}

.kp-subtabs :deep(.n-tabs-nav) {
  padding: 0 2px 6px;
}

.kp-subtabs :deep(.n-tab-pane) {
  padding-top: 6px;
}

.kp-section {
  margin-bottom: 18px;
}

.kp-section-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.kp-section-icon {
  color: var(--app-text-secondary, #94a3b8);
  font-size: 12px;
}

.kp-section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--app-text-primary);
}

.kp-tag-tool {
  font-size: 10px !important;
  font-family: ui-monospace, monospace;
  color: var(--color-brand) !important;
  background: var(--color-brand-light) !important;
}

.kp-section-hint {
  margin: 0 0 10px;
  font-size: 11px;
  color: var(--app-text-muted);
  line-height: 1.5;
}

.kp-card {
  border-radius: 12px !important;
  box-shadow: var(--app-shadow-sm);
}

.kp-card-premise {
  background: var(--app-surface);
  border: 1px solid var(--app-border) !important;
}

.kp-textarea :deep(textarea) {
  font-size: 13px;
  line-height: 1.6;
}

.kp-chapters {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.kp-ch-card {
  background: var(--app-surface);
  border: 1px solid var(--app-border) !important;
  overflow: hidden;
}

.kp-ch-card :deep(.n-card-header) {
  padding: 10px 14px;
  background: linear-gradient(90deg, var(--color-brand-light), transparent);
  border-bottom: 1px solid var(--app-divider);
}

.kp-ch-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  width: 100%;
}

.kp-ch-title {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.kp-ch-num {
  font-size: 13px;
  font-weight: 700;
  color: var(--app-text-primary);
}

.kp-ch-outline {
  font-size: 11px;
  color: var(--app-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.kp-sync-select {
  width: 108px;
  flex-shrink: 0;
}

.kp-ch-body {
  padding-top: 4px;
}

.kp-field {
  margin-bottom: 12px;
}

.kp-label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: var(--app-text-muted);
  margin-bottom: 6px;
  letter-spacing: 0.02em;
}

.kp-grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

@media (max-width: 520px) {
  .kp-grid-2 {
    grid-template-columns: 1fr;
  }
}

.kp-dynamic :deep(.n-dynamic-input-item) {
  margin-bottom: 6px;
}

.kp-ch-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 4px;
  padding-top: 8px;
  border-top: 1px dashed var(--app-divider);
}

.kp-add-ch {
  margin-top: 4px;
}

.kp-triples-container {
  padding: 8px 0;
}
.kp-triples-toolbar {
  margin-bottom: 8px;
}
.kp-triples-list {
  max-height: 360px;
  overflow-y: auto;
}
.triple-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 8px;
  background: var(--app-surface-subtle);
  border: 1px solid var(--app-divider);
  font-size: 12px;
}
.triple-body {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 0;
  overflow: hidden;
}
.triple-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.triple-actions { flex-shrink: 0; }

.entity-state-grid {
  display: grid;
  grid-template-columns: 100px 1fr;
  gap: 4px 8px;
  font-size: 12px;
}
.estate-key {
  color: var(--text-color-3);
  word-break: break-all;
}
.estate-val {
  word-break: break-all;
}

.kp-seg {
  flex-shrink: 0;
  margin-bottom: 10px;
}

.kp-search-container {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.kp-search-card {
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 12px;
  flex-shrink: 0;
}

.kp-edit-section {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--app-surface);
  border: 1px solid var(--app-border);
  border-radius: 12px;
  overflow: hidden;
}

.kp-edit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  border-bottom: 1px solid var(--app-divider);
  background: var(--app-surface-subtle);
  flex-shrink: 0;
}

.kp-edit-toolbar {
  padding: 10px 14px;
  border-bottom: 1px solid var(--app-divider);
  background: var(--app-surface-subtle);
  flex-shrink: 0;
}

.kp-edit-content {
  flex: 1;
  min-height: 500px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.kp-knowledge-section {
  flex: 1;
  min-height: 400px;
  display: flex;
  flex-direction: column;
}

.kp-narrative-container {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.kp-search-input {
  flex: 1;
  min-width: 200px;
}

.kp-search-list {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 600px;
  overflow-y: auto;
}

.kp-hit {
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--app-surface-subtle);
  border: 1px solid var(--app-border);
  cursor: pointer;
  transition: all 0.15s ease;
}

.kp-hit:hover {
  background: var(--app-surface);
  border-color: var(--app-border-strong);
}

.kp-hit.active {
  background: var(--color-brand-light);
  border-color: var(--color-brand);
}

.kp-hit-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.kp-hit-id {
  font-size: 11px;
  color: var(--app-text-muted);
  font-family: monospace;
}

.kp-hit-text {
  font-size: 13px;
  line-height: 1.5;
  color: var(--app-text-secondary);
}

.kp-hit-text.kp-hit-collapsed {
  max-height: 22px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  opacity: 0.55;
}

.kp-hit.collapsed {
  padding: 6px 10px;
  background: transparent;
  border-color: transparent;
}

.kp-hit.collapsed:hover {
  background: var(--app-surface-subtle);
  border-color: var(--app-border);
}

.kp-hit-ch {
  font-size: 10px;
  color: var(--app-text-muted);
}

.kp-search-more {
  text-align: center;
  font-size: 11px;
  color: var(--app-text-muted);
  padding: 4px 0 0;
}

.kp-search-empty {
  margin-top: 20px;
  text-align: center;
  padding: 40px 20px;
}

.kp-graph-embed {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.kp-graph-container {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.kp-graph-nav {
  padding: 12px;
  border-bottom: 1px solid var(--app-border);
  background: var(--app-surface-subtle);
}
</style>
