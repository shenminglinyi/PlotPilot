<!-- frontend/src/components/workbench/StoryEvolutionPanel.vue -->
<template>
  <div class="story-evolution-panel">
    <header class="story-evolution-banner" role="region" aria-label="故事演进说明">
      <div class="story-evolution-banner__head">
        <div class="story-evolution-banner__title">
          <n-icon size="15" class="story-evolution-banner__icon"><PulseOutline /></n-icon>
          <n-text strong>故事演进</n-text>
          <n-tag v-if="currentChapter" size="small" round :bordered="false" type="info" style="margin-left:2px">
            第 {{ currentChapter }} 章
          </n-tag>
        </div>
        <n-space size="small" align="center" wrap>
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
              <template #icon><n-icon><ReorderFourOutline /></n-icon></template>
              时间轴
            </n-button>
            <n-button
              :type="activeTab === 'worldline' ? 'primary' : 'default'"
              @click="activeTab = 'worldline'"
            >
              <template #icon><n-icon><GitNetworkOutline /></n-icon></template>
              世界线
            </n-button>
          </n-button-group>
          <n-button size="tiny" secondary @click="openCharacterAnchor">角色档案</n-button>
        </n-space>
      </div>
    </header>

    <!-- 世界线 DAG 模式 -->
    <WorldlineDAG
      v-if="activeTab === 'worldline'"
      :slug="slug"
      @checkpoint-restored="onCheckpointRestored"
    />

    <div v-else-if="activeTab === 'command'" class="evolution-command">
      <section class="command-hero">
        <div class="command-hero__main">
          <n-text strong class="command-title">演进司令塔</n-text>
          <p>把叙事治理、状态机和世界线存档放在同一个决策面：先看结构风险，再决定写、回滚或分叉。</p>
        </div>
        <div class="command-score">
          <span>承诺命中</span>
          <strong>{{ governanceHitRate }}</strong>
        </div>
        <div class="command-score">
          <span>状态快照</span>
          <strong>{{ latestSnapshot ? `第 ${latestSnapshot.chapter_number} 章` : '未生成' }}</strong>
        </div>
        <div class="command-score">
          <span>世界线</span>
          <strong>{{ worldlineSummary }}</strong>
        </div>
      </section>

      <section class="command-grid">
        <article class="command-panel">
          <div class="command-panel__head">
            <n-text strong>自动写前约束</n-text>
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

        <article class="command-panel">
          <div class="command-panel__head">
            <n-text strong>叙事治理</n-text>
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

        <article class="command-panel">
          <div class="command-panel__head">
            <n-text strong>状态连续性</n-text>
            <n-tag size="small" :type="latestSnapshot?.status === 'blocked' ? 'error' : 'success'" :bordered="false">
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

        <article class="command-panel">
          <div class="command-panel__head">
            <n-text strong>世界线</n-text>
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
          <n-text strong>风险与修复队列</n-text>
          <n-tag size="small" :bordered="false">{{ combinedRisks.length }}</n-tag>
        </div>
        <div class="risk-lane">
          <div v-for="risk in combinedRisks" :key="risk.kind + risk.title" class="risk-card">
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
          <n-text strong>状态树</n-text>
          <n-tag size="small" :type="latestSnapshot?.status === 'blocked' ? 'error' : 'success'" :bordered="false">
            {{ latestSnapshot ? `第 ${latestSnapshot.chapter_number} 章` : '未生成' }}
          </n-tag>
        </div>
        <n-empty v-if="!latestSnapshot" description="保存章节后生成演进快照" />
        <template v-else>
          <n-descriptions size="small" :column="1" bordered>
            <n-descriptions-item label="Schema">{{ latestSnapshot.schema_version }}</n-descriptions-item>
            <n-descriptions-item label="状态">{{ latestSnapshot.status }}</n-descriptions-item>
            <n-descriptions-item label="时空">
              {{ sceneState.time_anchor || '未标定' }} / {{ sceneState.location || '未标定' }}
            </n-descriptions-item>
            <n-descriptions-item label="情绪余波">{{ sceneState.emotional_residue || '无' }}</n-descriptions-item>
          </n-descriptions>
          <n-divider />
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
          <n-text strong>状态流</n-text>
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
        </n-scrollbar>
      </section>

      <section class="evolution-col">
        <div class="evolution-col__head">
          <n-text strong>证据</n-text>
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

    <!-- 传统时间轴模式（外：导航略收窄，为「时间轴 + 详情」留出宽度；内：提高右栏默认占比，避免详情过窄） -->
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
import { PulseOutline, ReorderFourOutline, GitNetworkOutline } from '@vicons/ionicons5'
import {
  WORKBENCH_CHAPTER_DESK_CHANGE_EVENT,
  WORKBENCH_OPEN_SETTINGS_PANEL_EVENT,
} from '@/workbench/deskEvents'
import { narrativeEngineApi, type StoryEvolutionReadModel } from '@/api/narrativeEngine'
import { evolutionApi, type EvolutionSnapshot } from '@/api/evolution'
import { getGovernanceState, type GovernanceStateDTO } from '@/api/governance'
import { worldlineApi, type WorldlineGraph } from '@/api/worldline'
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

watch(
  () => props.slug,
  () => {
    highlightRange.value = null
    selectedItem.value = null
    void loadBundle()
    void loadEvolutionSnapshots()
    void loadGovernanceState()
    void loadWorldlineGraph()
  },
  { immediate: true },
)

useWorkbenchPlotTimelineReload(() => {
  void loadBundle()
  void loadEvolutionSnapshots()
  void loadGovernanceState()
  void loadWorldlineGraph()
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
  background: var(--app-surface);
}

.story-evolution-banner {
  flex-shrink: 0;
  padding: 8px 12px;
  border-bottom: 1px solid var(--app-border, rgba(0, 0, 0, 0.08));
  background: var(--app-surface-elevated, var(--app-surface));
}

.story-evolution-banner__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.story-evolution-banner__title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  min-width: 0;
}

.story-evolution-banner__icon {
  color: var(--color-brand);
  opacity: 0.8;
  flex-shrink: 0;
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
  padding: 14px;
  background: var(--app-page-bg, var(--app-surface));
}

.command-hero {
  display: grid;
  grid-template-columns: minmax(280px, 1fr) repeat(3, minmax(130px, 180px));
  gap: 10px;
  align-items: stretch;
  margin-bottom: 12px;
}

.command-hero__main,
.command-score,
.command-panel {
  border: 1px solid var(--app-border, rgba(0, 0, 0, 0.08));
  border-radius: 8px;
  background: var(--app-surface);
}

.command-hero__main {
  padding: 14px;
}

.command-title {
  display: block;
  margin-bottom: 5px;
  font-size: 16px;
}

.command-hero__main p {
  margin: 0;
  color: var(--app-text-muted, rgba(0, 0, 0, 0.58));
  font-size: 12px;
  line-height: 1.6;
}

.command-score {
  padding: 12px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
}

.command-score span {
  color: var(--app-text-muted, rgba(0, 0, 0, 0.58));
  font-size: 11px;
}

.command-score strong {
  font-size: 18px;
}

.command-grid {
  display: grid;
  grid-template-columns: minmax(260px, 1.1fr) repeat(3, minmax(220px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.command-panel {
  min-width: 0;
  padding: 12px;
}

.command-panel--wide {
  margin-bottom: 14px;
}

.command-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 10px;
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
  border-radius: 7px;
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
  border-radius: 8px;
  background: var(--app-surface-subtle, rgba(0, 0, 0, 0.03));
  font-size: 12px;
}

.risk-card span:last-child {
  color: var(--app-text-muted, rgba(0, 0, 0, 0.58));
  line-height: 1.5;
}

.evolution-console {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(240px, 0.9fr) minmax(280px, 1.1fr) minmax(240px, 0.9fr);
  gap: 0;
  overflow: hidden;
}

.evolution-col {
  min-width: 0;
  min-height: 0;
  padding: 12px;
  border-right: 1px solid var(--app-border, rgba(0, 0, 0, 0.08));
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow: hidden;
}

.evolution-col:last-child {
  border-right: 0;
}

.evolution-col__head {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
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
    border-right: 0;
    border-bottom: 1px solid var(--app-border, rgba(0, 0, 0, 0.08));
  }
}
</style>
