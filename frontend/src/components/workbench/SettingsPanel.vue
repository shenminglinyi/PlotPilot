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

    <!-- 扁平化单层标签栏，使用 display-directive="if" 避免图表组件在 display:none 状态下挂载导致 width/height 为 0 -->
    <n-tabs
      v-model:value="activeTab"
      type="line"
      size="small"
      class="settings-tabs"
      :tabs-padding="4"
    >
      <n-tab-pane name="bible" tab="作品设定" display-directive="if">
        <BiblePanel :key="bibleKey" :slug="slug" />
      </n-tab-pane>
      <n-tab-pane name="worldbuilding" tab="世界观" display-directive="if">
        <WorldbuildingPanel :slug="slug" />
      </n-tab-pane>
      <n-tab-pane name="knowledge" tab="知识库" display-directive="if">
        <KnowledgePanel :slug="slug" />
      </n-tab-pane>
      <n-tab-pane name="storyline-arc" tab="故事线" display-directive="if">
        <StorylinePlotOverviewPanel :slug="slug" :current-chapter="currentChapter?.number ?? null" />
      </n-tab-pane>
      <n-tab-pane name="chronicles" tab="编年史" display-directive="if">
        <HolographicChroniclesPanel :slug="slug" />
      </n-tab-pane>
      <n-tab-pane name="continuity" tab="连续性" display-directive="if">
        <ContinuityPanel :slug="slug" :current-chapter="currentChapter?.number ?? null" />
      </n-tab-pane>
      <n-tab-pane name="voice-lock" tab="口吻锁定" display-directive="if">
        <VoiceLockPanel :slug="slug" :current-chapter="currentChapter?.number ?? null" />
      </n-tab-pane>
      <n-tab-pane name="power-system" tab="战力系统" display-directive="if">
        <PowerSystemPanel :slug="slug" :current-chapter="currentChapter?.number ?? null" />
      </n-tab-pane>
      <n-tab-pane name="model-role" tab="模型分工" display-directive="if">
        <ModelRolePanel />
      </n-tab-pane>
      <n-tab-pane name="sandbox" tab="对话沙盒" display-directive="if">
        <SandboxDialoguePanel :slug="slug" />
      </n-tab-pane>
      <n-tab-pane name="foreshadow" tab="伏笔账本" display-directive="if">
        <ForeshadowLedgerPanel :slug="slug" />
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import CandidateDraftBranchSwitcher from './CandidateDraftBranchSwitcher.vue'
import { useWorkbenchContextStore } from '@/stores/workbenchContextStore'

const BiblePanel = defineAsyncComponent(() => import('../panels/BiblePanel.vue'))
const KnowledgePanel = defineAsyncComponent(() => import('../knowledge/KnowledgePanel.vue'))
const WorldbuildingPanel = defineAsyncComponent(() => import('./WorldbuildingPanel.vue'))
const StorylinePlotOverviewPanel = defineAsyncComponent(() => import('./StorylinePlotOverviewPanel.vue'))
const HolographicChroniclesPanel = defineAsyncComponent(() => import('./HolographicChroniclesPanel.vue'))
const ContinuityPanel = defineAsyncComponent(() => import('./ContinuityPanel.vue'))
const ForeshadowLedgerPanel = defineAsyncComponent(() => import('./ForeshadowLedgerPanel.vue'))
const SandboxDialoguePanel = defineAsyncComponent(() => import('./SandboxDialoguePanel.vue'))
const VoiceLockPanel = defineAsyncComponent(() => import('./VoiceLockPanel.vue'))
const PowerSystemPanel = defineAsyncComponent(() => import('./PowerSystemPanel.vue'))
const ModelRolePanel = defineAsyncComponent(() => import('./ModelRolePanel.vue'))

/** 所有合法 tab 名 */
const ALL_TABS = new Set([
  'bible', 'worldbuilding', 'knowledge',
  'storyline-arc', 'chronicles',
  'continuity', 'voice-lock', 'power-system', 'model-role', 'sandbox', 'foreshadow',
])

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
  if (!panel) return 'bible'
  if (ALL_TABS.has(panel)) return panel
  return LEGACY_TAB_MAP[panel] ?? 'bible'
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
  currentPanel: 'bible',
  bibleKey: 0,
  currentChapter: null,
})

const emit = defineEmits<{
  'update:currentPanel': [panel: string]
}>()

const activeTab = ref(resolveTab(props.currentPanel))
const contextStore = useWorkbenchContextStore()
const { targetPanel, voiceLockDraftVersion, voiceLockDraft, sandboxDraftVersion, sandboxDraft } = storeToRefs(contextStore)

watch(() => props.currentPanel, (newVal) => {
  activeTab.value = resolveTab(newVal)
})

watch(activeTab, (tab) => {
  emit('update:currentPanel', tab)
})

watch(
  [targetPanel, voiceLockDraftVersion, sandboxDraftVersion, () => props.slug],
  ([panel, _voiceVersion, _sandboxVersion, slug]) => {
    if (panel === 'voice-lock' && voiceLockDraft.value?.slug === slug) {
      activeTab.value = 'voice-lock'
      return
    }
    if (panel === 'sandbox' && sandboxDraft.value?.slug === slug) {
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

.settings-tabs {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.settings-tabs :deep(.n-tabs-nav) {
  padding: 0 8px;
  background: var(--app-surface);
  border-bottom: 1px solid var(--aitext-split-border);
  overflow-x: auto;
  scrollbar-width: none;
}
.settings-tabs :deep(.n-tabs-nav::-webkit-scrollbar) {
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
