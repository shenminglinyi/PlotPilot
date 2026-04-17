<template>
  <div class="right-panel">
    <!-- 一级：剧本基建 / 叙事脉络 / 片场 — 监控在中栏「监控大盘」 -->
    <div class="group-bar">
      <n-radio-group v-model:value="activeGroup" size="small" class="group-switch">
        <n-radio-button value="foundation">剧本基建</n-radio-button>
        <n-radio-button value="narrative">叙事脉络</n-radio-button>
        <n-radio-button value="tactical">片场</n-radio-button>
      </n-radio-group>
      <n-text v-if="currentChapter" depth="3" style="font-size:11px;flex-shrink:0">
        第{{ currentChapter.number }}章
        <n-tag :type="currentChapter.word_count > 0 ? 'success' : 'default'" size="tiny" round style="margin-left:4px">
          {{ currentChapter.word_count > 0 ? '已收稿' : '未收稿' }}
        </n-tag>
      </n-text>
    </div>

    <!-- 剧本基建：作品设定 / 世界观 / 知识库 -->
    <n-tabs
      v-if="activeGroup === 'foundation'"
      v-model:value="foundationTab"
      type="line"
      size="small"
      class="settings-tabs"
      :tabs-padding="8"
    >
      <n-tab-pane name="bible" tab="作品设定">
        <BiblePanel :key="bibleKey" :slug="slug" />
      </n-tab-pane>
      <n-tab-pane name="worldbuilding" tab="世界观">
        <WorldbuildingPanel :slug="slug" />
      </n-tab-pane>
      <n-tab-pane name="knowledge" tab="知识库">
        <KnowledgePanel :slug="slug" />
      </n-tab-pane>
    </n-tabs>

    <!-- 叙事脉络：故事线·弧光 / 全息编年史（剧情×快照双螺旋）/ 宏观诊断 -->
    <n-tabs
      v-if="activeGroup === 'narrative'"
      v-model:value="narrativeTab"
      type="line"
      size="small"
      class="settings-tabs"
      :tabs-padding="8"
    >
      <n-tab-pane name="storyline-arc" tab="故事线·弧光">
        <StorylinePlotOverviewPanel :slug="slug" :current-chapter="currentChapter?.number ?? null" />
      </n-tab-pane>
      <n-tab-pane name="chronicles" tab="全息编年史">
        <HolographicChroniclesPanel :slug="slug" />
      </n-tab-pane>
      <n-tab-pane name="macro-refactor" tab="宏观诊断">
        <MacroRefactorPanel :slug="slug" />
      </n-tab-pane>
    </n-tabs>

    <!-- 片场：对话沙盒 / 伏笔账本（「本章伏笔回收建议」已迁至中栏辅助撰稿 → 章节元素） -->
    <n-tabs
      v-if="activeGroup === 'tactical'"
      v-model:value="tacticalTab"
      type="line"
      size="small"
      class="settings-tabs"
      :tabs-padding="8"
    >
      <n-tab-pane name="sandbox" tab="对话沙盒">
        <SandboxDialoguePanel :slug="slug" />
      </n-tab-pane>
      <n-tab-pane name="foreshadow" tab="伏笔账本">
        <ForeshadowLedgerPanel :slug="slug" />
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent, ref, watch } from 'vue'

const BiblePanel = defineAsyncComponent(() => import('../panels/BiblePanel.vue'))
const KnowledgePanel = defineAsyncComponent(() => import('../knowledge/KnowledgePanel.vue'))
const WorldbuildingPanel = defineAsyncComponent(() => import('./WorldbuildingPanel.vue'))
const StorylinePlotOverviewPanel = defineAsyncComponent(() => import('./StorylinePlotOverviewPanel.vue'))
const HolographicChroniclesPanel = defineAsyncComponent(() => import('./HolographicChroniclesPanel.vue'))
const ForeshadowLedgerPanel = defineAsyncComponent(() => import('./ForeshadowLedgerPanel.vue'))
const MacroRefactorPanel = defineAsyncComponent(() => import('./MacroRefactorPanel.vue'))
const SandboxDialoguePanel = defineAsyncComponent(() => import('./SandboxDialoguePanel.vue'))

/** 剧本基建组 */
const FOUNDATION_TABS = new Set(['bible', 'worldbuilding', 'knowledge'])
/** 叙事脉络组（时间轴+快照已并入「全息编年史」；旧 tab id 见 LEGACY_NARRATIVE） */
const NARRATIVE_TABS = new Set(['storyline-arc', 'chronicles', 'macro-refactor'])
const LEGACY_NARRATIVE = new Set(['storylines', 'plot-arc', 'timeline', 'snapshots'])
/** 片场；本章伏笔建议在中栏「辅助撰稿 → 🧩 章节元素」 */
const TACTICAL_TABS = new Set(['sandbox', 'foreshadow'])
/** 旧版「本章建议」Tab 已移除，映射到对话沙盒 */
const LEGACY_TACTICAL = new Set(['foreshadow-suggestions'])

function resolveGroup(panel: string | undefined): 'foundation' | 'narrative' | 'tactical' {
  if (!panel) return 'foundation'
  if (LEGACY_TACTICAL.has(panel)) return 'tactical'
  if (TACTICAL_TABS.has(panel)) return 'tactical'
  if (NARRATIVE_TABS.has(panel) || LEGACY_NARRATIVE.has(panel)) return 'narrative'
  return 'foundation'
}

function normalizeNarrativeTab(panel: string | undefined): string {
  if (panel === 'storylines' || panel === 'plot-arc') return 'storyline-arc'
  if (panel === 'timeline' || panel === 'snapshots') return 'chronicles'
  if (panel && NARRATIVE_TABS.has(panel)) return panel
  return 'storyline-arc'
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

const activeGroup = ref<'foundation' | 'narrative' | 'tactical'>(resolveGroup(props.currentPanel))

const foundationTab = ref(
  FOUNDATION_TABS.has(props.currentPanel ?? '') ? props.currentPanel! : 'bible'
)
const narrativeTab = ref(normalizeNarrativeTab(props.currentPanel))
function normalizeTacticalTab(panel: string | undefined): string {
  if (panel && LEGACY_TACTICAL.has(panel)) return 'sandbox'
  if (panel && TACTICAL_TABS.has(panel)) return panel
  return 'sandbox'
}

const tacticalTab = ref(normalizeTacticalTab(props.currentPanel))

function activePanelId(): string {
  if (activeGroup.value === 'foundation') return foundationTab.value
  if (activeGroup.value === 'narrative') return narrativeTab.value
  return tacticalTab.value
}

watch(() => props.currentPanel, (newVal) => {
  if (!newVal) return
  if (TACTICAL_TABS.has(newVal) || LEGACY_TACTICAL.has(newVal)) {
    activeGroup.value = 'tactical'
    tacticalTab.value = normalizeTacticalTab(newVal)
  } else if (NARRATIVE_TABS.has(newVal) || LEGACY_NARRATIVE.has(newVal)) {
    activeGroup.value = 'narrative'
    narrativeTab.value = normalizeNarrativeTab(newVal)
  } else if (FOUNDATION_TABS.has(newVal)) {
    activeGroup.value = 'foundation'
    foundationTab.value = newVal
  } else {
    activeGroup.value = 'foundation'
    foundationTab.value = 'bible'
  }
})

/** 用户切换顶部三组或任一组内子 Tab 时，回写父级 rightPanel（保持与路由/程序化跳转一致） */
watch([activeGroup, foundationTab, narrativeTab, tacticalTab], () => {
  emit('update:currentPanel', activePanelId())
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

.group-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 10px;
  background: var(--app-surface);
  border-bottom: 1px solid var(--aitext-split-border);
  flex-shrink: 0;
}

.group-switch {
  flex-shrink: 0;
  flex-wrap: wrap;
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
