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
import { ref, watch } from 'vue'
import BiblePanel from '../panels/BiblePanel.vue'
import KnowledgePanel from '../knowledge/KnowledgePanel.vue'
import WorldbuildingPanel from './WorldbuildingPanel.vue'
import StorylinePlotOverviewPanel from './StorylinePlotOverviewPanel.vue'
import HolographicChroniclesPanel from './HolographicChroniclesPanel.vue'
import ForeshadowLedgerPanel from './ForeshadowLedgerPanel.vue'
import SandboxDialoguePanel from './SandboxDialoguePanel.vue'

/** 所有合法 tab 名 */
const ALL_TABS = new Set([
  'bible', 'worldbuilding', 'knowledge',
  'storyline-arc', 'chronicles',
  'sandbox', 'foreshadow',
  // 兼容旧版映射
  'character-soul', 'checkpoint', 'story-phase',
])

/** 旧版 tab 名映射到新 tab 名 */
const LEGACY_TAB_MAP: Record<string, string> = {
  'storylines': 'storyline-arc',
  'plot-arc': 'storyline-arc',
  'timeline': 'chronicles',
  'snapshots': 'checkpoint',
  'checkpoint': 'storyline-arc',       // Checkpoint 已融入故事线面板
  'story-phase': 'storyline-arc',      // 故事阶段已融入故事线面板
  'character-soul': 'sandbox',         // 角色灵魂已融入对话沙盒面板
  'voice-drift': 'sandbox',
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

watch(() => props.currentPanel, (newVal) => {
  activeTab.value = resolveTab(newVal)
})

watch(activeTab, (tab) => {
  emit('update:currentPanel', tab)
})
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
