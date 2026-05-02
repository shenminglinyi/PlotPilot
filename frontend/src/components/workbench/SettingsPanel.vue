<template>
  <div class="right-panel">
    <!-- 章节上下文（当有章节时显示） -->
    <div v-if="currentChapter" class="chapter-context-bar">
      <span class="chapter-context-label">第{{ currentChapter.number }}章</span>
      <n-tag
        :type="currentChapter.word_count > 0 ? 'success' : 'default'"
        size="tiny"
        round
      >
        {{ currentChapter.word_count > 0 ? '已收稿' : '未收稿' }}
      </n-tag>
    </div>

    <div class="branch-context-bar">
      <CandidateDraftBranchSwitcher :slug="slug" width="150px" />
    </div>

    <div class="panel-suite-switch" aria-label="右侧面板分组">
      <button
        class="suite-card suite-card--novelpro"
        :class="{ 'suite-card--active': activeGroup === 'novelpro' }"
        type="button"
        @click="selectGroup('novelpro')"
      >
        <span class="suite-eyebrow">新增功能</span>
        <strong>NovelPro 测试区</strong>
        <span>监控 · 候选 · 精修 · 连续性</span>
      </button>
      <button
        class="suite-card"
        :class="{ 'suite-card--active': activeGroup === 'base' }"
        type="button"
        @click="selectGroup('base')"
      >
        <span class="suite-eyebrow">原有能力</span>
        <strong>基础面板</strong>
        <span>设定 · 世界观 · 编年史 · 伏笔</span>
      </button>
    </div>

    <!-- 扁平化单层标签栏，使用 display-directive="if" 避免图表组件在 display:none 状态下挂载导致 width/height 为 0 -->
    <div class="settings-tab-strip" role="tablist" aria-label="右侧功能页签">
      <button
        v-for="tab in visibleTabs"
        :key="tab.name"
        class="settings-tab-button"
        :class="{ 'settings-tab-button--active': activeTab === tab.name }"
        type="button"
        role="tab"
        :aria-selected="activeTab === tab.name"
        @click="activeTab = tab.name"
      >
        {{ tab.label }}
      </button>
    </div>
    <n-tabs
      v-model:value="activeTab"
      type="line"
      size="small"
      class="settings-tabs"
      :tabs-padding="4"
    >
      <n-tab-pane v-if="activeGroup === 'novelpro'" name="novelpro-monitor" tab="监控中心" display-directive="if">
        <NovelProMonitorPanel :slug="slug" :current-chapter="currentChapter?.number ?? null" />
      </n-tab-pane>
      <n-tab-pane v-if="activeGroup === 'novelpro'" name="candidate-refine" tab="候选/精修" display-directive="if">
        <CandidateRefinePanel :slug="slug" :current-chapter="currentChapter" />
      </n-tab-pane>
      <n-tab-pane v-if="activeGroup === 'novelpro'" name="continuity" tab="连续性巡检" display-directive="if">
        <ContinuityPanel :slug="slug" :current-chapter="currentChapter?.number ?? null" />
      </n-tab-pane>
      <n-tab-pane v-if="activeGroup === 'novelpro'" name="voice-lock" tab="口吻锁定" display-directive="if">
        <VoiceLockPanel :slug="slug" :current-chapter="currentChapter?.number ?? null" />
      </n-tab-pane>
      <n-tab-pane v-if="activeGroup === 'novelpro'" name="voice-drift" tab="文风监控" display-directive="if">
        <VoiceDriftPanel :slug="slug" />
      </n-tab-pane>
      <n-tab-pane v-if="activeGroup === 'novelpro'" name="power-system" tab="战力系统" display-directive="if">
        <PowerSystemPanel :slug="slug" :current-chapter="currentChapter?.number ?? null" />
      </n-tab-pane>
      <n-tab-pane v-if="activeGroup === 'novelpro'" name="prop-ledger" tab="道具账本" display-directive="if">
        <PropLedgerPanel :slug="slug" :current-chapter="currentChapter?.number ?? null" />
      </n-tab-pane>
      <n-tab-pane v-if="activeGroup === 'novelpro'" name="coc-canon" tab="CoC正典" display-directive="if">
        <CocCanonPanel :slug="slug" :current-chapter="currentChapter?.number ?? null" />
      </n-tab-pane>
      <n-tab-pane v-if="activeGroup === 'novelpro'" name="coc-clues" tab="CoC线索" display-directive="if">
        <CocCluePanel :slug="slug" :current-chapter="currentChapter?.number ?? null" />
      </n-tab-pane>
      <n-tab-pane v-if="activeGroup === 'novelpro'" name="model-role" tab="PP AI" display-directive="if">
        <ModelRolePanel />
      </n-tab-pane>
      <n-tab-pane v-if="activeGroup === 'novelpro'" name="sandbox" tab="对话沙盒" display-directive="if">
        <SandboxDialoguePanel :slug="slug" />
      </n-tab-pane>
      <n-tab-pane v-if="activeGroup === 'novelpro'" name="style-bible" tab="手法库" display-directive="if">
        <StyleBiblePanel :slug="slug" :current-chapter="currentChapter?.number ?? null" />
      </n-tab-pane>
      <n-tab-pane v-if="activeGroup === 'base'" name="bible" tab="作品设定" display-directive="if">
        <BiblePanel :key="bibleKey" :slug="slug" />
      </n-tab-pane>
      <n-tab-pane v-if="activeGroup === 'base'" name="worldbuilding" tab="世界观" display-directive="if">
        <WorldbuildingPanel :slug="slug" />
      </n-tab-pane>
      <n-tab-pane v-if="activeGroup === 'base'" name="knowledge" tab="知识库" display-directive="if">
        <KnowledgePanel :slug="slug" />
      </n-tab-pane>
      <n-tab-pane v-if="activeGroup === 'base'" name="storyline-arc" tab="故事线" display-directive="if">
        <StorylinePlotOverviewPanel :slug="slug" :current-chapter="currentChapter?.number ?? null" />
      </n-tab-pane>
      <n-tab-pane v-if="activeGroup === 'base'" name="chronicles" tab="编年史" display-directive="if">
        <HolographicChroniclesPanel :slug="slug" />
      </n-tab-pane>
      <n-tab-pane v-if="activeGroup === 'base'" name="foreshadow" tab="伏笔账本" display-directive="if">
        <ForeshadowLedgerPanel :slug="slug" />
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import CandidateDraftBranchSwitcher from './CandidateDraftBranchSwitcher.vue'
import { useWorkbenchContextStore } from '@/stores/workbenchContextStore'

const BiblePanel = defineAsyncComponent(() => import('../panels/BiblePanel.vue'))
const KnowledgePanel = defineAsyncComponent(() => import('../knowledge/KnowledgePanel.vue'))
const WorldbuildingPanel = defineAsyncComponent(() => import('./WorldbuildingPanel.vue'))
const StorylinePlotOverviewPanel = defineAsyncComponent(() => import('./StorylinePlotOverviewPanel.vue'))
const HolographicChroniclesPanel = defineAsyncComponent(() => import('./HolographicChroniclesPanel.vue'))
const NovelProMonitorPanel = defineAsyncComponent(() => import('./NovelProMonitorPanel.vue'))
const CandidateRefinePanel = defineAsyncComponent(() => import('./CandidateRefinePanel.vue'))
const ContinuityPanel = defineAsyncComponent(() => import('./ContinuityPanel.vue'))
const ForeshadowLedgerPanel = defineAsyncComponent(() => import('./ForeshadowLedgerPanel.vue'))
const SandboxDialoguePanel = defineAsyncComponent(() => import('./SandboxDialoguePanel.vue'))
const VoiceLockPanel = defineAsyncComponent(() => import('./VoiceLockPanel.vue'))
const VoiceDriftPanel = defineAsyncComponent(() => import('./VoiceDriftPanel.vue'))
const PowerSystemPanel = defineAsyncComponent(() => import('./PowerSystemPanel.vue'))
const PropLedgerPanel = defineAsyncComponent(() => import('./PropLedgerPanel.vue'))
const CocCanonPanel = defineAsyncComponent(() => import('./CocCanonPanel.vue'))
const CocCluePanel = defineAsyncComponent(() => import('./CocCluePanel.vue'))
const ModelRolePanel = defineAsyncComponent(() => import('./ModelRolePanel.vue'))
const StyleBiblePanel = defineAsyncComponent(() => import('./StyleBiblePanel.vue'))

/** 所有合法 tab 名 */
const ALL_TABS = new Set([
  'bible', 'worldbuilding', 'knowledge',
  'storyline-arc', 'chronicles',
  'novelpro-monitor', 'candidate-refine',
  'continuity', 'voice-lock', 'voice-drift', 'power-system', 'prop-ledger', 'coc-canon', 'coc-clues', 'model-role', 'sandbox', 'style-bible', 'foreshadow',
])
const NOVELPRO_TABS = new Set(['novelpro-monitor', 'candidate-refine', 'continuity', 'voice-lock', 'voice-drift', 'power-system', 'prop-ledger', 'coc-canon', 'coc-clues', 'model-role', 'sandbox', 'style-bible'])
const BASE_TABS = new Set(['bible', 'worldbuilding', 'knowledge', 'storyline-arc', 'chronicles', 'foreshadow'])
const GROUP_TABS = {
  novelpro: ['novelpro-monitor', 'candidate-refine', 'continuity', 'voice-lock', 'voice-drift', 'power-system', 'prop-ledger', 'coc-canon', 'coc-clues', 'model-role', 'sandbox', 'style-bible'],
  base: ['bible', 'worldbuilding', 'knowledge', 'storyline-arc', 'chronicles', 'foreshadow'],
} as const
const TAB_LABELS: Record<string, string> = {
  'novelpro-monitor': '监控中心',
  'candidate-refine': '候选/精修',
  continuity: '连续性巡检',
  'voice-lock': '口吻锁定',
  'voice-drift': '文风监控',
  'power-system': '战力系统',
  'prop-ledger': '道具账本',
  'coc-canon': 'CoC正典',
  'coc-clues': 'CoC线索',
  'model-role': 'PP AI',
  sandbox: '对话沙盒',
  'style-bible': '手法库',
  bible: '作品设定',
  worldbuilding: '世界观',
  knowledge: '知识库',
  'storyline-arc': '故事线',
  chronicles: '编年史',
  foreshadow: '伏笔账本',
}
const GROUP_DEFAULT_TAB = {
  novelpro: 'novelpro-monitor',
  base: 'bible',
} as const

type PanelGroup = keyof typeof GROUP_DEFAULT_TAB

/** 旧版 tab 名映射到新 tab 名 */
const LEGACY_TAB_MAP: Record<string, string> = {
  'storylines': 'storyline-arc',
  'plot-arc': 'storyline-arc',
  'timeline': 'chronicles',
  'snapshots': 'chronicles',
  'foreshadow-suggestions': 'sandbox',
  'macro-refactor': 'bible',
}

function resolveTab(panel: string | undefined): string {
  if (!panel) return 'novelpro-monitor'
  if (ALL_TABS.has(panel)) return panel
  return LEGACY_TAB_MAP[panel] ?? 'bible'
}

function resolveGroup(panel: string | undefined): PanelGroup {
  const tab = resolveTab(panel)
  if (NOVELPRO_TABS.has(tab)) return 'novelpro'
  return 'base'
}

interface Chapter {
  id: number
  number: number
  title: string
  word_count: number
}

interface Props {
  slug: string
  currentPanel?: string
  bibleKey?: number
  currentChapter?: Chapter | null
}

const props = withDefaults(defineProps<Props>(), {
  currentPanel: 'novelpro-monitor',
  bibleKey: 0,
  currentChapter: null,
})

const emit = defineEmits<{
  'update:currentPanel': [panel: string]
}>()

const activeTab = ref(resolveTab(props.currentPanel))
const activeGroup = ref<PanelGroup>(resolveGroup(activeTab.value))
const visibleTabs = computed(() => GROUP_TABS[activeGroup.value].map(name => ({
  name,
  label: TAB_LABELS[name],
})))
const contextStore = useWorkbenchContextStore()
const { targetPanel, voiceLockDraftVersion, voiceLockDraft, sandboxDraftVersion, sandboxDraft } = storeToRefs(contextStore)

function selectGroup(group: PanelGroup) {
  activeGroup.value = group
  const groupTabs = group === 'novelpro' ? NOVELPRO_TABS : BASE_TABS
  if (!groupTabs.has(activeTab.value)) {
    activeTab.value = GROUP_DEFAULT_TAB[group]
  }
}

watch(() => props.currentPanel, (newVal) => {
  const nextTab = resolveTab(newVal)
  activeGroup.value = resolveGroup(nextTab)
  activeTab.value = nextTab
})

watch(activeTab, (tab) => {
  activeGroup.value = resolveGroup(tab)
  emit('update:currentPanel', tab)
})

watch(
  [targetPanel, voiceLockDraftVersion, sandboxDraftVersion, () => props.slug],
  ([panel, _voiceVersion, _sandboxVersion, slug]) => {
    if (panel === 'voice-lock' && voiceLockDraft.value?.slug === slug) {
      activeGroup.value = 'novelpro'
      activeTab.value = 'voice-lock'
      return
    }
    if (panel === 'sandbox' && sandboxDraft.value?.slug === slug) {
      activeGroup.value = 'novelpro'
      activeTab.value = 'sandbox'
    }
  },
)
</script>

<style scoped>
.right-panel {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--aitext-panel-muted);
  border-left: 1px solid var(--aitext-split-border);
}

/* 当前章节上下文提示条 */
.chapter-context-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  background: var(--app-surface);
  border-bottom: 1px solid var(--aitext-split-border);
  flex-shrink: 0;
  font-size: 12px;
  color: var(--app-text-muted);
}

.chapter-context-label {
  font-weight: 600;
  color: var(--app-text-secondary);
}

.branch-context-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--app-surface);
  border-bottom: 1px solid var(--aitext-split-border);
  flex-shrink: 0;
}

.panel-suite-switch {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  padding: 10px 12px;
  background:
    radial-gradient(circle at 18% 0%, rgba(31, 129, 255, 0.10), transparent 34%),
    var(--app-surface);
  border-bottom: 1px solid var(--aitext-split-border);
  flex-shrink: 0;
}

.suite-card {
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 9px 10px;
  border: 1px solid var(--aitext-split-border);
  border-radius: 12px;
  color: var(--app-text-secondary);
  background: var(--aitext-panel-muted);
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.18s ease,
    background-color 0.18s ease,
    box-shadow 0.18s ease,
    transform 0.18s ease;
}

.suite-card:hover {
  transform: translateY(-1px);
  border-color: rgba(31, 129, 255, 0.35);
}

.suite-card--active {
  border-color: rgba(31, 129, 255, 0.55);
  background: linear-gradient(135deg, rgba(31, 129, 255, 0.12), rgba(56, 189, 248, 0.05));
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
  color: var(--app-text-primary);
}

.suite-card--novelpro.suite-card--active {
  border-color: rgba(34, 197, 94, 0.58);
  background: linear-gradient(135deg, rgba(34, 197, 94, 0.13), rgba(20, 184, 166, 0.06));
}

.suite-eyebrow {
  font-size: 11px;
  line-height: 1;
  color: var(--app-text-muted);
}

.suite-card strong {
  font-size: 13px;
  line-height: 1.25;
}

.suite-card span:last-child {
  max-width: 100%;
  overflow: hidden;
  font-size: 11px;
  line-height: 1.25;
  color: var(--app-text-muted);
  white-space: nowrap;
  text-overflow: ellipsis;
}

.settings-tab-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(74px, 1fr));
  gap: 6px;
  padding: 7px 8px;
  background: var(--app-surface);
  border-bottom: 1px solid var(--aitext-split-border);
  flex-shrink: 0;
}

.settings-tab-button {
  min-width: 0;
  height: 30px;
  padding: 0 8px;
  border: 1px solid transparent;
  border-radius: 999px;
  background: var(--aitext-panel-muted);
  color: var(--app-text-secondary);
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
  white-space: nowrap;
  cursor: pointer;
  transition:
    border-color 0.18s ease,
    background-color 0.18s ease,
    color 0.18s ease;
}

.settings-tab-button:hover {
  border-color: rgba(31, 129, 255, 0.28);
  color: var(--app-text-primary);
}

.settings-tab-button--active {
  border-color: rgba(31, 129, 255, 0.45);
  background: rgba(31, 129, 255, 0.10);
  color: var(--color-brand);
}

.settings-tabs {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.settings-tabs :deep(.n-tabs-nav) {
  display: none;
}

.settings-tabs :deep(.n-tabs-nav-scroll-wrapper) {
  overflow: visible;
}

.settings-tabs :deep(.n-tabs-nav-scroll-content) {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 7px 0;
  transform: none !important;
}

.settings-tabs :deep(.n-tabs-tab) {
  margin: 0 !important;
  padding: 5px 9px;
  border-radius: 999px;
  background: var(--aitext-panel-muted);
  border: 1px solid transparent;
  transition:
    border-color 0.18s ease,
    background-color 0.18s ease,
    color 0.18s ease;
}

.settings-tabs :deep(.n-tabs-tab:hover) {
  border-color: rgba(31, 129, 255, 0.28);
}

.settings-tabs :deep(.n-tabs-tab--active) {
  border-color: rgba(31, 129, 255, 0.45);
  background: rgba(31, 129, 255, 0.10);
}

.settings-tabs :deep(.n-tabs-bar) {
  display: none;
}

.settings-tabs :deep(.n-tabs-content) {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.settings-tabs :deep(.n-tabs-content-wrapper) {
  height: 100%;
  overflow: hidden;
}

.settings-tabs :deep(.n-tabs-pane-wrapper) {
  height: 100%;
  overflow: hidden;
}

.settings-tabs :deep(.n-tab-pane) {
  height: 100%;
  overflow: hidden;
}
</style>
