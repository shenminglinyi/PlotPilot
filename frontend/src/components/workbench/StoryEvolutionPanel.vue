<!-- frontend/src/components/workbench/StoryEvolutionPanel.vue -->
<template>
  <div class="story-evolution-panel">
    <header class="story-evolution-banner" role="region" aria-label="故事演进控制台">
      <div class="story-evolution-banner__head">
        <div class="story-evolution-banner__title-block">
          <div class="story-evolution-banner__title">
            <n-icon size="16" class="story-evolution-banner__icon"><PulseOutline /></n-icon>
            <n-text strong>故事演进</n-text>
            <n-tag v-if="currentChapter" size="small" round :bordered="false" type="info">
              第 {{ currentChapter }} 章
            </n-tag>
          </div>
          <span class="story-evolution-banner__subtitle">
            汇总叙事治理、状态快照、时间轴与世界线分支
          </span>
        </div>
        <n-space class="story-evolution-banner__actions" size="small" align="center" wrap>
          <n-button-group size="small">
            <n-button
              :type="activeTab === 'command' ? 'primary' : 'default'"
              @click="activeTab = 'command'"
            >
              <template #icon><n-icon><GitNetworkOutline /></n-icon></template>
              司令塔
            </n-button>
            <n-button
              :type="activeTab === 'state' ? 'primary' : 'default'"
              @click="activeTab = 'state'"
            >
              <template #icon><n-icon><PulseOutline /></n-icon></template>
              状态机
            </n-button>
            <n-button
              :type="activeTab === 'timeline' ? 'primary' : 'default'"
              @click="activeTab = 'timeline'"
            >
              <template #icon><n-icon><TimeOutline /></n-icon></template>
              时间轴
            </n-button>
            <n-button
              :type="activeTab === 'worldline' ? 'primary' : 'default'"
              @click="activeTab = 'worldline'"
            >
              <template #icon><n-icon><ReorderFourOutline /></n-icon></template>
              世界线
            </n-button>
          </n-button-group>
          <n-button size="small" secondary @click="openCharacterAnchor">角色档案</n-button>
        </n-space>
      </div>
    </header>

    <div v-if="activeTab === 'worldline'" class="worldline-board">
      <WorldlineDAG
        :slug="slug"
        @checkpoint-restored="onCheckpointRestored"
      />
    </div>

    <div v-else-if="activeTab === 'command'" class="evolution-command">
      <section class="command-hero">
        <div class="command-hero__main">
          <span class="command-kicker">Narrative Ops</span>
          <div class="command-title-row">
            <n-text strong class="command-title">演进司令塔</n-text>
            <n-tag size="small" :type="riskSummaryType" :bordered="false">{{ riskSummaryLabel }}</n-tag>
          </div>
          <p>以写前约束、连续性证据和分支存档为核心，快速判断下一章是否可以推进。</p>
        </div>
        <div class="command-score command-score--governance">
          <span>承诺命中</span>
          <strong>{{ governanceHitRate }}</strong>
          <div class="score-bar" aria-hidden="true">
            <span :style="{ width: governanceHitPercent + '%' }"></span>
          </div>
        </div>
        <div class="command-score command-score--snapshot">
          <span>状态快照</span>
          <strong>{{ latestSnapshot ? `第 ${latestSnapshot.chapter_number} 章` : '未生成' }}</strong>
          <small>{{ snapshotStatusLabel }}</small>
        </div>
        <div class="command-score command-score--worldline">
          <span>世界线</span>
          <strong>{{ worldlineSummary }}</strong>
          <small>{{ worldlineHeadName }}</small>
        </div>
      </section>

      <section class="command-panel setup-anchor-panel">
        <div class="command-panel__head">
          <div>
            <n-text strong>引导落点</n-text>
            <span>建档与引导阶段写入的关键约束，后续演进不得漂移。</span>
          </div>
          <n-tag size="small" :type="setupAnchorRows.length ? 'success' : 'default'" :bordered="false">
            {{ setupAnchorsLoading ? '读取中' : `${setupAnchorRows.length} 项` }}
          </n-tag>
        </div>
        <div v-if="setupAnchorRows.length" class="setup-anchor-grid">
          <article v-for="anchor in setupAnchorRows" :key="anchor.key" class="setup-anchor-card">
            <div class="setup-anchor-card__top">
              <strong>{{ anchor.title }}</strong>
              <n-tag size="tiny" :type="anchor.type" :bordered="false">{{ anchor.meta }}</n-tag>
            </div>
            <p>{{ anchor.detail }}</p>
          </article>
        </div>
        <div v-else class="compact-empty">
          暂无可展示的引导落点；完成作品设定、人物、地图或剧情总纲后会在这里汇总。
        </div>
      </section>

      <section class="command-grid">
        <article class="command-panel command-panel--budget">
          <div class="command-panel__head">
            <div>
              <n-text strong>自动写前约束</n-text>
              <span>下一章可用叙事预算</span>
            </div>
            <n-tag size="small" :bordered="false">内置</n-tag>
          </div>
          <div class="compact-list">
            <div class="compact-row">
              <strong>叙事预算</strong>
              <span>{{ budgetSummary }}</span>
            </div>
            <div class="compact-row">
              <strong>必须服务</strong>
              <span>{{ budgetPromiseTags }}</span>
            </div>
            <div class="compact-row">
              <strong>连续性</strong>
              <span>写作管线会在生成前自动检查角色状态、未完成动作和重复事件。</span>
            </div>
          </div>
        </article>

        <article class="command-panel command-panel--governance">
          <div class="command-panel__head">
            <div>
              <n-text strong>叙事治理</n-text>
              <span>承诺兑现与结构债务</span>
            </div>
            <n-tag size="small" :type="governanceSeverityType" :bordered="false">
              {{ governanceState?.latest_report?.severity || 'ready' }}
            </n-tag>
          </div>
          <div class="compact-list">
            <div v-for="issue in governanceIssues" :key="issue.code + issue.title" class="compact-row">
              <strong>{{ issue.title }}</strong>
              <span>{{ issue.detail }}</span>
            </div>
            <div v-if="governanceIssues.length === 0" class="compact-empty">没有最新治理风险。</div>
          </div>
        </article>

        <article class="command-panel command-panel--state">
          <div class="command-panel__head">
            <div>
              <n-text strong>状态连续性</n-text>
              <span>角色、场景与动作证据</span>
            </div>
            <n-tag size="small" :type="snapshotStatusType" :bordered="false">
              {{ latestSnapshot?.status || 'empty' }}
            </n-tag>
          </div>
          <div class="compact-list">
            <div v-for="item in evidenceRows" :key="item.label" class="compact-row">
              <strong>{{ item.label }}</strong>
              <span>{{ item.value }}</span>
            </div>
          </div>
        </article>

        <article class="command-panel command-panel--worldline">
          <div class="command-panel__head">
            <div>
              <n-text strong>世界线</n-text>
              <span>检查点、分叉与 HEAD</span>
            </div>
            <n-button size="tiny" secondary @click="activeTab = 'worldline'">打开</n-button>
          </div>
          <div class="compact-list">
            <div class="compact-row">
              <strong>检查点</strong>
              <span>{{ worldlineGraph.nodes.length }} 个</span>
            </div>
            <div class="compact-row">
              <strong>分支</strong>
              <span>{{ worldlineGraph.branches.length }} 条</span>
            </div>
            <div class="compact-row">
              <strong>HEAD</strong>
              <span>{{ worldlineHeadName }}</span>
            </div>
          </div>
        </article>
      </section>

      <section class="command-panel command-panel--wide">
        <div class="command-panel__head">
          <div>
            <n-text strong>风险与修复队列</n-text>
            <span>优先处理会阻断生成或污染连续性的项目</span>
          </div>
          <n-tag size="small" :type="riskSummaryType" :bordered="false">{{ combinedRisks.length }}</n-tag>
        </div>
        <div class="risk-lane">
          <div
            v-for="risk in combinedRisks"
            :key="risk.kind + risk.title"
            class="risk-card"
            :class="`risk-card--${risk.type}`"
          >
            <n-tag size="small" :type="risk.type" :bordered="false">{{ risk.kind }}</n-tag>
            <strong>{{ risk.title }}</strong>
            <span>{{ risk.detail }}</span>
          </div>
          <div v-if="combinedRisks.length === 0" class="compact-empty">当前没有需要拦截的演进风险。</div>
        </div>
      </section>
    </div>

    <div v-else-if="activeTab === 'state'" class="evolution-console">
      <section class="evolution-col">
        <div class="evolution-col__head">
          <div>
            <n-text strong>状态树</n-text>
            <span>本章结束时的叙事世界状态</span>
          </div>
          <n-tag size="small" :type="snapshotStatusType" :bordered="false">
            {{ latestSnapshot ? `第 ${latestSnapshot.chapter_number} 章` : '未生成' }}
          </n-tag>
        </div>
        <n-empty v-if="!latestSnapshot" description="保存章节后生成演进快照" />
        <template v-else>
          <div class="state-summary-grid">
            <div class="state-metric">
              <span>Schema</span>
              <strong>{{ latestSnapshot.schema_version }}</strong>
            </div>
            <div class="state-metric">
              <span>状态</span>
              <strong>{{ latestSnapshot.status }}</strong>
            </div>
            <div class="state-metric state-metric--wide">
              <span>时空锚点</span>
              <strong>{{ sceneState.time_anchor || '未标定' }} / {{ sceneState.location || '未标定' }}</strong>
            </div>
            <div class="state-metric state-metric--wide">
              <span>情绪余波</span>
              <strong>{{ sceneState.emotional_residue || '无' }}</strong>
            </div>
          </div>
          <n-scrollbar class="state-list">
            <div v-for="[id, char] in characterRows" :key="id" class="state-row">
              <div class="state-row__main">
                <n-text strong>{{ char.name || id }}</n-text>
                <span>{{ char.status || 'alive' }} · {{ char.location || '未知地点' }}</span>
              </div>
              <n-dropdown
                trigger="click"
                :options="characterStatusOptions"
                @select="(status: string | number) => updateCharacterStatus(id, String(status))"
              >
                <n-button size="tiny" quaternary>状态</n-button>
              </n-dropdown>
            </div>
          </n-scrollbar>
        </template>
      </section>

      <section class="evolution-col">
        <div class="evolution-col__head">
          <div>
            <n-text strong>状态流</n-text>
            <span>{{ actionCount }} 个动作 · {{ conflictCount }} 个冲突</span>
          </div>
          <n-button size="tiny" secondary :loading="snapshotsLoading" @click="loadEvolutionSnapshots">刷新</n-button>
        </div>
        <n-scrollbar class="action-list">
          <div v-for="action in latestActions" :key="action.action_id" class="action-row">
            <n-tag size="small" :bordered="false">{{ action.type }}</n-tag>
            <code>{{ action.action_id }}</code>
          </div>
          <div v-for="conflict in latestSnapshot?.conflicts || []" :key="String(conflict.conflict_type || conflict.type || conflict.message)" class="violation-row">
            <n-tag size="small" :type="conflict.level === 'blocking' ? 'error' : 'warning'" :bordered="false">
              {{ conflict.level || 'warning' }}
            </n-tag>
            <span>{{ conflict.message }}</span>
          </div>
          <div v-if="latestActions.length === 0 && conflictCount === 0" class="compact-empty">暂无动作或冲突记录。</div>
        </n-scrollbar>
      </section>

      <section class="evolution-col">
        <div class="evolution-col__head">
          <div>
            <n-text strong>证据</n-text>
            <span>用于回放、审计与冲突解释</span>
          </div>
          <n-tag size="small" :bordered="false">Graph-backed</n-tag>
        </div>
        <n-scrollbar class="evidence-list">
          <div v-for="item in evidenceRows" :key="item.label" class="evidence-row">
            <n-text strong>{{ item.label }}</n-text>
            <span>{{ item.value }}</span>
          </div>
        </n-scrollbar>
      </section>
    </div>

    <!-- 传统时间轴详情模式 -->
    <n-split
      v-else
      direction="horizontal"
      :default-size="0.24"
      :min="0.17"
      :max="0.34"
    >
      <!-- 左栏：故事导航 -->
      <template #1>
        <StoryNavigator
          :slug="slug"
          :current-chapter="currentChapter"
          :evolution-bundle="bundle"
          :evolution-loading="bundleLoading"
          @select-storyline="onSelectStoryline"
        />
      </template>

      <!-- 中栏 + 右栏 -->
      <template #2>
        <n-split direction="horizontal" :default-size="0.55" :min="0.40" :max="0.68">
          <!-- 中栏：时间轴 -->
          <template #1>
            <StoryTimeline
              :slug="slug"
              :highlight-range="highlightRange"
              :chronicles-from-bundled-parent="true"
              :bundled-chronicle-rows="bundledChronicleRows"
              @select-event="onSelectEvent"
              @select-snapshot="onSelectSnapshot"
              @request-bundle-refresh="loadBundle"
            />
          </template>

          <!-- 右栏：详情面板 -->
          <template #2>
            <StoryDetailPanel
              :slug="slug"
              :selected-item="selectedItem"
              @refresh="onCheckpointRestored"
            />
          </template>
        </n-split>
      </template>
    </n-split>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { PulseOutline, ReorderFourOutline, GitNetworkOutline, TimeOutline } from '@vicons/ionicons5'
import {
  WORKBENCH_CHAPTER_DESK_CHANGE_EVENT,
  WORKBENCH_OPEN_SETTINGS_PANEL_EVENT,
} from '@/workbench/deskEvents'
import { narrativeEngineApi, type StoryEvolutionReadModel } from '@/api/narrativeEngine'
import { evolutionApi, type EvolutionSnapshot } from '@/api/evolution'
import { getGovernanceState, type GovernanceStateDTO } from '@/api/governance'
import { worldlineApi, type WorldlineGraph } from '@/api/worldline'
import { novelApi, type NovelDTO } from '@/api/novel'
import { bibleApi, type BibleDTO } from '@/api/bible'
import { workflowApi, type PlotOutlineDTO } from '@/api/workflow'
import type { ChronicleRow } from '@/api/chronicles'
import { useWorkbenchPlotTimelineReload } from '@/composables/useWorkbenchNarrativeSync'
import StoryNavigator from './StoryNavigator.vue'
import StoryTimeline from './StoryTimeline.vue'
import StoryDetailPanel from './StoryDetailPanel.vue'
import WorldlineDAG from './WorldlineDAG.vue'

interface Props {
  slug: string
  currentChapter: number | null
}

const props = defineProps<Props>()

const bundle = ref<StoryEvolutionReadModel | null>(null)
const bundleLoading = ref(false)

// 活跃 tab
const activeTab = ref<'command' | 'state' | 'timeline' | 'worldline'>('command')

// 高亮范围（选中故事线时高亮对应章节）
const highlightRange = ref<{ start: number; end: number } | null>(null)

// 选中的项目（事件或快照）
const selectedItem = ref<any>(null)
const snapshots = ref<EvolutionSnapshot[]>([])
const snapshotsLoading = ref(false)
const governanceState = ref<GovernanceStateDTO | null>(null)
const worldlineGraph = ref<WorldlineGraph>({ nodes: [], edges: [], branches: [], head_id: null })
const setupNovel = ref<NovelDTO | null>(null)
const setupBible = ref<BibleDTO | null>(null)
const setupPlotOutline = ref<PlotOutlineDTO | null>(null)
const setupAnchorsLoading = ref(false)
const overrideLoading = ref(false)
const characterStatusOptions = [
  { label: 'alive', key: 'alive' },
  { label: 'dead', key: 'dead' },
  { label: 'missing', key: 'missing' },
  { label: 'ambiguous', key: 'ambiguous' },
  { label: 'severely_injured', key: 'severely_injured' },
]

async function loadBundle() {
  bundleLoading.value = true
  bundle.value = null
  try {
    bundle.value = await narrativeEngineApi.getStoryEvolution(props.slug)
  } catch {
    bundle.value = null
  } finally {
    bundleLoading.value = false
  }
}

async function loadEvolutionSnapshots() {
  snapshotsLoading.value = true
  try {
    const result = await evolutionApi.listSnapshots(props.slug)
    snapshots.value = result.snapshots || []
  } catch {
    snapshots.value = []
  } finally {
    snapshotsLoading.value = false
  }
}

async function loadGovernanceState() {
  try {
    governanceState.value = await getGovernanceState(props.slug)
  } catch {
    governanceState.value = null
  }
}

async function loadWorldlineGraph() {
  try {
    worldlineGraph.value = await worldlineApi.getGraph(props.slug)
  } catch {
    worldlineGraph.value = { nodes: [], edges: [], branches: [], head_id: null }
  }
}

async function loadSetupAnchors() {
  setupAnchorsLoading.value = true
  try {
    const [novelResult, bibleResult, outlineResult] = await Promise.allSettled([
      novelApi.getNovel(props.slug),
      bibleApi.getBible(props.slug),
      workflowApi.getPlotOutline(props.slug),
    ])
    setupNovel.value = novelResult.status === 'fulfilled' ? novelResult.value : null
    setupBible.value = bibleResult.status === 'fulfilled' ? bibleResult.value : null
    setupPlotOutline.value = outlineResult.status === 'fulfilled' ? outlineResult.value.plot_outline : null
  } finally {
    setupAnchorsLoading.value = false
  }
}

function escapeJsonPointer(value: string) {
  return value.replace(/~/g, '~0').replace(/\//g, '~1')
}

async function updateCharacterStatus(characterId: string, status: string) {
  const snapshot = latestSnapshot.value
  if (!snapshot || overrideLoading.value) return
  overrideLoading.value = true
  try {
    await evolutionApi.applyOverrides(props.slug, snapshot.chapter_number, [
      {
        op: 'replace',
        path: `/characters/${escapeJsonPointer(characterId)}/status`,
        value: status,
      },
    ])
    await loadEvolutionSnapshots()
  } finally {
    overrideLoading.value = false
  }
}

const bundledChronicleRows = computed((): ChronicleRow[] => {
  const raw = bundle.value?.chronotope?.rows
  if (!Array.isArray(raw)) return []
  return raw as ChronicleRow[]
})

const latestSnapshot = computed(() => snapshots.value[0] || null)
const sceneState = computed(() => (latestSnapshot.value?.ending_state?.scene || {}) as Record<string, any>)
const characterRows = computed(() => Object.entries((latestSnapshot.value?.ending_state?.characters || {}) as Record<string, any>).slice(0, 16))
const latestActions = computed(() => latestSnapshot.value?.delta_actions || [])
const actionCount = computed(() => latestActions.value.length)
const conflictCount = computed(() => latestSnapshot.value?.conflicts.length || 0)
function cleanText(value: unknown): string {
  if (typeof value !== 'string') return ''
  return value.replace(/\s+/g, ' ').trim()
}

function clipText(value: unknown, max = 120): string {
  const text = cleanText(value)
  if (text.length <= max) return text
  return `${text.slice(0, max)}...`
}

function joinTexts(values: unknown[], max = 140): string {
  return clipText(values.map(cleanText).filter(Boolean).join('；'), max)
}

const setupAnchorRows = computed(() => {
  const rows: Array<{
    key: string
    title: string
    meta: string
    detail: string
    type: 'default' | 'info' | 'success' | 'warning' | 'error'
  }> = []
  const novel = setupNovel.value
  const bible = setupBible.value
  const outline = setupPlotOutline.value

  if (novel?.locked_genre || novel?.locked_world_preset) {
    rows.push({
      key: 'genre-world',
      title: '类型与世界基调',
      meta: novel.locked_genre || '赛道',
      detail: clipText(novel.locked_world_preset || novel.premise, 150) || '已在建档阶段锁定类型方向。',
      type: 'info',
    })
  }

  if (novel?.premise) {
    rows.push({
      key: 'premise',
      title: '初始粗纲',
      meta: 'Premise',
      detail: clipText(novel.premise, 170),
      type: 'default',
    })
  }

  if (novel?.locked_story_structure || novel?.locked_pacing_control) {
    rows.push({
      key: 'structure',
      title: '故事骨架与节奏',
      meta: '结构',
      detail: joinTexts([novel.locked_story_structure, novel.locked_pacing_control], 150),
      type: 'success',
    })
  }

  if (outline?.main_story_overview || outline?.core_conflict) {
    rows.push({
      key: 'plot-outline',
      title: '主线总纲',
      meta: `${outline.stage_plan?.length || 0} 阶段`,
      detail: clipText(outline.main_story_overview || outline.core_conflict, 170),
      type: 'info',
    })
  }

  if (outline?.core_conflict) {
    rows.push({
      key: 'core-conflict',
      title: '核心冲突',
      meta: '冲突',
      detail: clipText(outline.core_conflict, 150),
      type: 'warning',
    })
  }

  if (outline?.expected_ending) {
    rows.push({
      key: 'ending',
      title: '结局走向',
      meta: '收束',
      detail: clipText(outline.expected_ending, 150),
      type: 'success',
    })
  }

  const characterSummary = joinTexts(
    (bible?.characters || []).slice(0, 5).map(char =>
      `${char.name}${char.core_motivation ? `：${char.core_motivation}` : char.description ? `：${char.description}` : ''}`,
    ),
    170,
  )
  if (characterSummary) {
    rows.push({
      key: 'characters',
      title: '核心人物',
      meta: `${bible?.characters.length || 0} 人`,
      detail: characterSummary,
      type: 'default',
    })
  }

  const worldSummary = joinTexts(
    (bible?.world_settings || []).slice(0, 4).map(setting =>
      `${setting.name}${setting.description ? `：${setting.description}` : ''}`,
    ),
    170,
  )
  if (worldSummary) {
    rows.push({
      key: 'world-settings',
      title: '世界观落点',
      meta: `${bible?.world_settings.length || 0} 条`,
      detail: worldSummary,
      type: 'info',
    })
  }

  const locationSummary = joinTexts(
    (bible?.locations || []).slice(0, 4).map(location =>
      `${location.name}${location.description ? `：${location.description}` : ''}`,
    ),
    150,
  )
  if (locationSummary) {
    rows.push({
      key: 'locations',
      title: '关键地点',
      meta: `${bible?.locations.length || 0} 处`,
      detail: locationSummary,
      type: 'default',
    })
  }

  const styleSummary = cleanText(bible?.style) || joinTexts((bible?.style_notes || []).map(note => note.content), 170)
  if (styleSummary || novel?.locked_writing_style) {
    rows.push({
      key: 'style',
      title: '文风公约',
      meta: 'Style',
      detail: clipText(styleSummary || novel?.locked_writing_style, 170),
      type: 'success',
    })
  }

  if (novel?.locked_special_requirements) {
    rows.push({
      key: 'special-requirements',
      title: '特殊要求',
      meta: '约束',
      detail: clipText(novel.locked_special_requirements, 150),
      type: 'warning',
    })
  }

  return rows.slice(0, 10)
})
const evidenceRows = computed(() => {
  const snapshot = latestSnapshot.value
  if (!snapshot) return [{ label: '状态', value: '暂无证据' }]
  return [
    { label: 'Source refs', value: `${snapshot.source_refs.length} 条` },
    { label: 'Conflicts', value: `${snapshot.conflicts.length} 条` },
    { label: 'Active', value: bundle.value?.evolution_surface?.active_snapshot?.summary || '暂无水化摘要' },
    { label: 'Actions', value: `${snapshot.delta_actions.length} 条标准动作` },
  ]
})
const governanceIssues = computed(() => governanceState.value?.latest_report?.issues || [])
const governanceBudget = computed(() => governanceState.value?.chapter_budget_preview || null)
const budgetSummary = computed(() => {
  const budget = governanceBudget.value
  if (!budget) return '等待治理层生成下一章预算'
  return `第 ${budget.chapter_number} 章 · 揭秘 ${budget.allowed_reveal_level} · 新线 ${budget.max_new_storylines} · 债务 ${budget.max_debt_closures}`
})
const budgetPromiseTags = computed(() => {
  const tags = governanceBudget.value?.must_serve_promise_tags || []
  return tags.length ? tags.join('、') : '无强制承诺标签'
})
const governanceHitRate = computed(() => {
  const rate = governanceState.value?.latest_report?.promise_hit_rate
  return typeof rate === 'number' ? `${Math.round(rate * 100)}%` : '未评估'
})
const governanceHitPercent = computed(() => {
  const rate = governanceState.value?.latest_report?.promise_hit_rate
  if (typeof rate !== 'number') return 0
  return Math.max(0, Math.min(100, Math.round(rate * 100)))
})
const governanceSeverityType = computed<'default' | 'info' | 'success' | 'warning' | 'error'>(() => {
  const severity = governanceState.value?.latest_report?.severity || 'info'
  if (severity === 'critical' || severity === 'high') return 'error'
  if (severity === 'medium') return 'warning'
  if (severity === 'low') return 'info'
  return 'success'
})
const worldlineHeadName = computed(() => {
  const head = worldlineGraph.value.nodes.find(n => n.id === worldlineGraph.value.head_id)
  return head?.name || '未设置'
})
const worldlineSummary = computed(() => {
  const branches = worldlineGraph.value.branches.length
  const checkpoints = worldlineGraph.value.nodes.length
  return `${branches} 分支 / ${checkpoints} 存档`
})
const snapshotStatusType = computed<'default' | 'info' | 'success' | 'warning' | 'error'>(() => {
  const status = latestSnapshot.value?.status
  if (!status) return 'default'
  if (status === 'blocked' || conflictCount.value > 0) return 'error'
  if (status === 'stale') return 'warning'
  return 'success'
})
const snapshotStatusLabel = computed(() => {
  if (!latestSnapshot.value) return '等待章节保存'
  if (conflictCount.value > 0) return `${conflictCount.value} 个冲突待处理`
  return '连续性可回放'
})
const combinedRisks = computed(() => {
  const risks: Array<{ kind: string; title: string; detail: string; type: 'default' | 'info' | 'success' | 'warning' | 'error' }> = []
  for (const issue of governanceIssues.value) {
    risks.push({ kind: '治理', title: issue.title, detail: issue.suggestion || issue.detail, type: issue.severity === 'high' || issue.severity === 'critical' ? 'error' : 'warning' })
  }
  for (const conflict of latestSnapshot.value?.conflicts || []) {
    risks.push({ kind: '状态', title: String(conflict.conflict_type || conflict.type || 'Conflict'), detail: String(conflict.message || ''), type: conflict.level === 'blocking' ? 'error' : 'warning' })
  }
  return risks.slice(0, 12)
})
const riskSummaryType = computed<'default' | 'info' | 'success' | 'warning' | 'error'>(() => {
  if (combinedRisks.value.some(r => r.type === 'error')) return 'error'
  if (combinedRisks.value.length > 0) return 'warning'
  return 'success'
})
const riskSummaryLabel = computed(() => {
  if (combinedRisks.value.some(r => r.type === 'error')) return '需处理'
  if (combinedRisks.value.length > 0) return '有提醒'
  return '可推进'
})

watch(
  () => props.slug,
  () => {
    highlightRange.value = null
    selectedItem.value = null
    void loadBundle()
    void loadEvolutionSnapshots()
    void loadGovernanceState()
    void loadWorldlineGraph()
    void loadSetupAnchors()
  },
  { immediate: true },
)

useWorkbenchPlotTimelineReload(() => {
  void loadBundle()
  void loadEvolutionSnapshots()
  void loadGovernanceState()
  void loadWorldlineGraph()
  void loadSetupAnchors()
})

// 选中故事线时高亮章节范围
function onSelectStoryline(storyline: { startChapter: number; endChapter: number }) {
  highlightRange.value = {
    start: storyline.startChapter,
    end: storyline.endChapter,
  }
}

// 选中剧情事件
function onSelectEvent(event: any) {
  selectedItem.value = { type: 'event', data: event }
}

// 选中快照
function onSelectSnapshot(snapshot: any) {
  selectedItem.value = { type: 'snapshot', data: snapshot }
}

/** 快照回滚等：与 Workbench 整桌同步（章节树、正文、伏笔 tick 等） */
function onCheckpointRestored() {
  highlightRange.value = null
  selectedItem.value = null
  window.dispatchEvent(new CustomEvent(WORKBENCH_CHAPTER_DESK_CHANGE_EVENT))
  void loadEvolutionSnapshots()
  void loadWorldlineGraph()
}

function openCharacterAnchor() {
  window.dispatchEvent(
    new CustomEvent(WORKBENCH_OPEN_SETTINGS_PANEL_EVENT, { detail: { panel: 'sandbox' } }),
  )
}
</script>

<style scoped>
.story-evolution-panel {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--app-page-bg, var(--app-surface));
}

.story-evolution-banner {
  flex-shrink: 0;
  padding: 10px 12px;
  border-bottom: 1px solid var(--app-border, rgba(0, 0, 0, 0.08));
  background: var(--app-surface);
}

.story-evolution-banner__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.story-evolution-banner__title-block {
  min-width: 180px;
  display: grid;
  gap: 2px;
}

.story-evolution-banner__title {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 14px;
  min-width: 0;
}

.story-evolution-banner__subtitle {
  color: var(--app-text-muted, rgba(0, 0, 0, 0.58));
  font-size: 11px;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.story-evolution-banner__icon {
  color: var(--color-brand);
  flex-shrink: 0;
}

.story-evolution-banner__actions {
  min-width: 0;
}

.story-evolution-banner :deep(.n-button-group .n-button) {
  min-width: 76px;
}

.story-evolution-panel :deep(.n-split) {
  flex: 1;
  min-height: 0;
  height: auto;
}

.story-evolution-panel :deep(.n-split-pane-1),
.story-evolution-panel :deep(.n-split-pane-2) {
  min-height: 0;
  overflow: hidden;
}

.evolution-command {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px;
  background: var(--app-page-bg, var(--app-surface));
  overflow-x: hidden;
}

.command-hero {
  display: grid;
  grid-template-columns: minmax(260px, 1fr) repeat(3, minmax(128px, 168px));
  gap: 10px;
  align-items: stretch;
  margin-bottom: 12px;
  min-width: 0;
}

.command-hero__main,
.command-score,
.command-panel {
  border: 1px solid var(--app-border, rgba(0, 0, 0, 0.08));
  border-radius: 8px;
  background: var(--app-surface);
  box-shadow: var(--app-shadow-sm, 0 1px 3px rgba(15, 23, 42, 0.06));
}

.command-hero__main {
  padding: 14px;
  border-left: 3px solid var(--color-brand);
}

.command-kicker {
  display: block;
  margin-bottom: 5px;
  color: var(--color-brand);
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0;
}

.command-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  margin-bottom: 4px;
  flex-wrap: wrap;
}

.command-title {
  font-size: 16px;
  line-height: 1.25;
}

.command-hero__main p {
  margin: 0;
  color: var(--app-text-muted, rgba(0, 0, 0, 0.58));
  font-size: 12px;
  line-height: 1.6;
}

.command-score {
  position: relative;
  padding: 12px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 5px;
  overflow: hidden;
}

.command-score::before {
  content: '';
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  background: var(--color-brand);
  opacity: 0.65;
}

.command-score--snapshot::before {
  background: var(--color-success);
}

.command-score--worldline::before {
  background: var(--color-gold);
}

.command-score span {
  color: var(--app-text-muted, rgba(0, 0, 0, 0.58));
  font-size: 11px;
}

.command-score strong {
  font-size: 18px;
  line-height: 1.15;
  overflow-wrap: anywhere;
}

.command-score small {
  color: var(--app-text-muted, rgba(0, 0, 0, 0.58));
  font-size: 11px;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.score-bar {
  height: 4px;
  margin-top: 3px;
  border-radius: 999px;
  background: var(--app-surface-subtle, rgba(0, 0, 0, 0.05));
  overflow: hidden;
}

.score-bar span {
  display: block;
  height: 100%;
  min-width: 0;
  border-radius: inherit;
  background: var(--color-brand);
}

.command-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(185px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
  min-width: 0;
}

.command-panel {
  min-width: 0;
  padding: 12px;
  border-top: 2px solid transparent;
}

.command-panel--budget {
  border-top-color: var(--color-brand);
}

.command-panel--governance {
  border-top-color: var(--color-warning);
}

.command-panel--state {
  border-top-color: var(--color-success);
}

.command-panel--worldline {
  border-top-color: var(--color-gold);
}

.command-panel--wide {
  margin-bottom: 14px;
}

.setup-anchor-panel {
  margin-bottom: 12px;
  border-top-color: var(--color-purple, var(--color-brand));
}

.setup-anchor-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 8px;
  max-height: 260px;
  overflow: auto;
  padding-right: 2px;
}

.setup-anchor-card {
  min-width: 0;
  display: grid;
  gap: 6px;
  padding: 10px;
  border: 1px solid var(--app-divider, rgba(15, 23, 42, 0.06));
  border-radius: 7px;
  background: var(--app-surface-subtle, rgba(0, 0, 0, 0.03));
}

.setup-anchor-card__top {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.setup-anchor-card__top strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}

.setup-anchor-card p {
  margin: 0;
  color: var(--app-text-muted, rgba(0, 0, 0, 0.58));
  font-size: 12px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.command-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
}

.command-panel__head > div {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.command-panel__head > div > span {
  color: var(--app-text-muted, rgba(0, 0, 0, 0.58));
  font-size: 11px;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.compact-list {
  display: grid;
  gap: 8px;
  max-height: 210px;
  overflow: auto;
}

.compact-row {
  display: grid;
  gap: 3px;
  padding: 8px;
  border-radius: 6px;
  border: 1px solid var(--app-divider, rgba(15, 23, 42, 0.06));
  background: var(--app-surface-subtle, rgba(0, 0, 0, 0.03));
  font-size: 12px;
}

.compact-row span,
.compact-empty {
  color: var(--app-text-muted, rgba(0, 0, 0, 0.58));
  line-height: 1.5;
}

.compact-empty {
  padding: 10px 0;
  font-size: 12px;
}

.risk-lane {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 8px;
}

.risk-card {
  display: grid;
  gap: 6px;
  padding: 10px;
  border: 1px solid var(--app-border, rgba(0, 0, 0, 0.08));
  border-radius: 7px;
  background: var(--app-surface-subtle, rgba(0, 0, 0, 0.03));
  font-size: 12px;
  border-left-width: 3px;
}

.risk-card--error {
  border-left-color: var(--color-danger);
}

.risk-card--warning {
  border-left-color: var(--color-warning);
}

.risk-card--success {
  border-left-color: var(--color-success);
}

.risk-card--info,
.risk-card--default {
  border-left-color: var(--color-brand);
}

.risk-card span:last-child {
  color: var(--app-text-muted, rgba(0, 0, 0, 0.58));
  line-height: 1.5;
}

.worldline-board {
  flex: 1;
  min-height: 0;
  min-width: 0;
  overflow: hidden;
  background: var(--app-page-bg, var(--app-surface));
}

.evolution-console {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(260px, 0.95fr) minmax(300px, 1.1fr) minmax(240px, 0.9fr);
  gap: 10px;
  padding: 12px;
  overflow: hidden;
  background: var(--app-page-bg, var(--app-surface));
}

.evolution-col {
  min-width: 0;
  min-height: 0;
  padding: 12px;
  border: 1px solid var(--app-border, rgba(0, 0, 0, 0.08));
  border-radius: 8px;
  background: var(--app-surface);
  box-shadow: var(--app-shadow-sm, 0 1px 3px rgba(15, 23, 42, 0.06));
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow: hidden;
}

.evolution-col__head {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.evolution-col__head > div {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.evolution-col__head > div > span {
  color: var(--app-text-muted, rgba(0, 0, 0, 0.58));
  font-size: 11px;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.state-summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  flex-shrink: 0;
}

.state-metric {
  min-width: 0;
  display: grid;
  gap: 3px;
  padding: 8px;
  border: 1px solid var(--app-divider, rgba(15, 23, 42, 0.06));
  border-radius: 6px;
  background: var(--app-surface-subtle, rgba(0, 0, 0, 0.03));
}

.state-metric--wide {
  grid-column: 1 / -1;
}

.state-metric span {
  color: var(--app-text-muted, rgba(0, 0, 0, 0.58));
  font-size: 11px;
  line-height: 1.3;
}

.state-metric strong {
  min-width: 0;
  font-size: 12px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.state-list,
.action-list,
.evidence-list {
  flex: 1;
  min-height: 0;
}

.state-row,
.action-row,
.violation-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 0;
  border-bottom: 1px solid var(--app-border-soft, rgba(0, 0, 0, 0.06));
  font-size: 12px;
}

.state-row {
  justify-content: space-between;
}

.state-row__main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.state-row span,
.violation-row span {
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--app-text-muted, rgba(0, 0, 0, 0.58));
}

.action-row code {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--app-text-muted, rgba(0, 0, 0, 0.58));
}

.evidence-row {
  padding: 8px 0;
  border-bottom: 1px solid var(--app-border-soft, rgba(0, 0, 0, 0.06));
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
}

.evidence-row span {
  color: var(--app-text-muted, rgba(0, 0, 0, 0.58));
  line-height: 1.5;
  overflow-wrap: anywhere;
}

@media (max-width: 900px) {
  .command-hero,
  .command-grid {
    grid-template-columns: 1fr;
  }

  .evolution-console {
    grid-template-columns: 1fr;
    overflow: auto;
  }

  .evolution-col {
    min-height: 260px;
  }
}

@media (max-width: 640px) {
  .story-evolution-banner__subtitle {
    white-space: normal;
  }

  .story-evolution-banner :deep(.n-button-group) {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    width: 100%;
  }

  .story-evolution-banner :deep(.n-button-group .n-button) {
    min-width: 0;
  }

  .story-evolution-banner__actions {
    width: 100%;
  }

  .state-summary-grid {
    grid-template-columns: 1fr;
  }
}
</style>
