<template>
  <div class="right-panel">
    <!-- Tab 分组切换器 -->
    <div class="tab-group-bar">
      <button
        v-for="g in TAB_GROUPS"
        :key="g.value"
        class="tab-group-btn"
        :class="{ 'tab-group-btn--active': activeGroup === g.value }"
        @click="switchGroup(g.value)"
      >
        {{ g.label }}
      </button>
      <button class="tab-collapse-btn" title="收起面板" @click="emit('collapse')">▶</button>
    </div>

    <!-- 写作支撑组：当前语境 / 伏笔账本 / 故事演进 -->
    <n-tabs
      v-show="activeGroup === 'writing'"
      v-model:value="activeWritingTab"
      type="line"
      size="small"
      class="settings-tabs"
      :tabs-padding="4"
      @update:value="onTabActivated"
    >
      <n-tab-pane name="context" display-directive="show">
        <template #tab>
          <span class="tab-label">
            <n-icon size="13" class="tab-icon"><FlashOutline /></n-icon>当前语境
          </span>
        </template>
        <CurrentChapterContextPanel
          v-if="visited.has('context')"
          :slug="slug"
          :current-chapter="currentChapter ?? null"
          :generation-prefs="generationPrefs"
          @jump-tab="onJumpTab"
        />
      </n-tab-pane>

      <n-tab-pane name="foreshadow" display-directive="show">
        <template #tab>
          <span class="tab-label">
            <n-icon size="13" class="tab-icon"><BookmarkOutline /></n-icon>伏笔账本
            <span v-if="pendingForeshadowCount > 0" class="tab-badge">
              {{ pendingForeshadowCount > 99 ? '99+' : pendingForeshadowCount }}
            </span>
          </span>
        </template>
        <ForeshadowLedgerPanel
          v-if="visited.has('foreshadow')"
          :slug="slug"
          :current-chapter-number="currentChapter?.number ?? null"
          @pending-count="pendingForeshadowCount = $event"
        />
      </n-tab-pane>

      <!-- 故事演进含图表，保留 if 确保 DOM 宽度正确 -->
      <n-tab-pane name="story-evolution" display-directive="if">
        <template #tab>
          <span class="tab-label">
            <n-icon size="13" class="tab-icon"><GitBranchOutline /></n-icon>故事演进
          </span>
        </template>
        <StoryEvolutionPanel :slug="slug" :current-chapter="currentChapter?.number ?? null" />
      </n-tab-pane>
    </n-tabs>

    <!-- 作品基础组：作品设定 / 世界观 / 知识库 / 角色档案 / 手稿道具 -->
    <n-tabs
      v-show="activeGroup === 'reference'"
      v-model:value="activeReferenceTab"
      type="line"
      size="small"
      class="settings-tabs"
      :tabs-padding="4"
      @update:value="onTabActivated"
    >
      <n-tab-pane name="bible" display-directive="show">
        <template #tab>
          <span class="tab-label">
            <n-icon size="13" class="tab-icon"><DocumentTextOutline /></n-icon>作品设定
          </span>
        </template>
        <BiblePanel v-if="visited.has('bible')" :slug="slug" />
      </n-tab-pane>

      <n-tab-pane name="worldbuilding" display-directive="show">
        <template #tab>
          <span class="tab-label">
            <n-icon size="13" class="tab-icon"><EarthOutline /></n-icon>世界观
          </span>
        </template>
        <WorldbuildingPanel v-if="visited.has('worldbuilding')" :slug="slug" />
      </n-tab-pane>

      <!-- 知识库含关系图，保留 if -->
      <n-tab-pane name="knowledge" display-directive="if">
        <template #tab>
          <span class="tab-label">
            <n-icon size="13" class="tab-icon"><LibraryOutline /></n-icon>知识库
          </span>
        </template>
        <KnowledgePanel :slug="slug" />
      </n-tab-pane>

      <n-tab-pane name="sandbox" display-directive="show">
        <template #tab>
          <span class="tab-label">
            <n-icon size="13" class="tab-icon"><PeopleOutline /></n-icon>角色档案
          </span>
        </template>
        <CharacterDialoguePanel
          v-if="visited.has('sandbox')"
          :slug="slug"
          :current-chapter-number="currentChapter?.number ?? null"
        />
      </n-tab-pane>

      <n-tab-pane name="props" display-directive="show">
        <template #tab>
          <span class="tab-label">
            <n-icon size="13" class="tab-icon"><BriefcaseOutline /></n-icon>手稿道具
          </span>
        </template>
        <ManuscriptPropsPanel
          v-if="visited.has('props')"
          :slug="slug"
          :current-chapter="currentChapter"
        />
      </n-tab-pane>
    </n-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import {
  FlashOutline, BookmarkOutline, GitBranchOutline,
  DocumentTextOutline, EarthOutline, LibraryOutline,
  PeopleOutline, BriefcaseOutline,
} from '@vicons/ionicons5'
import BiblePanel from '../panels/BiblePanel.vue'
import ManuscriptPropsPanel from './ManuscriptPropsPanel.vue'
import KnowledgePanel from '../knowledge/KnowledgePanel.vue'
import WorldbuildingPanel from './WorldbuildingPanel.vue'
import StoryEvolutionPanel from './StoryEvolutionPanel.vue'
import ForeshadowLedgerPanel from './ForeshadowLedgerPanel.vue'
import CharacterDialoguePanel from './CharacterDialoguePanel.vue'
import CurrentChapterContextPanel from './CurrentChapterContextPanel.vue'
import type { GenerationPrefsDTO } from '@/api/novel'
import {
  resolveTabName,
  tabGroup,
  type TabGroup,
} from '@/constants/workbenchTabs'

const TAB_GROUPS = [
  { value: 'writing' as TabGroup,   label: '写作支撑' },
  { value: 'reference' as TabGroup, label: '作品基础' },
]

interface Chapter {
  id: number
  number: number
  title: string
  word_count: number
}

interface Props {
  slug: string
  currentPanel?: string
  currentChapter?: Chapter | null
  generationPrefs?: GenerationPrefsDTO | null
}

const props = withDefaults(defineProps<Props>(), {
  currentPanel: 'context',
  currentChapter: null,
  generationPrefs: null,
})

const emit = defineEmits<{
  'update:currentPanel': [panel: string]
  'collapse': []
}>()

const initialTab = resolveTabName(props.currentPanel)
const initialGroup = tabGroup(initialTab)

const activeGroup = ref<TabGroup>(initialGroup)
const activeWritingTab = ref(initialGroup === 'writing' ? initialTab : 'context')
const activeReferenceTab = ref(initialGroup === 'reference' ? initialTab : 'bible')
const visited = reactive(new Set<string>([initialTab]))
const pendingForeshadowCount = ref(0)

const activeTab = computed(() =>
  activeGroup.value === 'writing' ? activeWritingTab.value : activeReferenceTab.value
)

function switchGroup(group: TabGroup) {
  activeGroup.value = group
  const tab = activeTab.value
  visited.add(tab)
  emit('update:currentPanel', tab)
}

function onTabActivated(name: string | number) {
  const tab = String(name)
  visited.add(tab)
  emit('update:currentPanel', tab)
}

function onJumpTab(tabName: string) {
  const target = resolveTabName(tabName)
  const group = tabGroup(target)
  activeGroup.value = group
  if (group === 'writing') {
    activeWritingTab.value = target
  } else {
    activeReferenceTab.value = target
  }
  visited.add(target)
  emit('update:currentPanel', target)
}

watch(() => props.currentPanel, (newVal) => {
  const target = resolveTabName(newVal)
  const group = tabGroup(target)
  activeGroup.value = group
  if (group === 'writing') {
    activeWritingTab.value = target
  } else {
    activeReferenceTab.value = target
  }
  visited.add(target)
})
</script>

<style scoped>
.right-panel {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--plotpilot-panel-muted);
  border-left: 1px solid var(--plotpilot-split-border);
}

/* 分组切换栏 */
.tab-group-bar {
  display: flex;
  gap: 2px;
  padding: 6px 8px 5px;
  background: var(--app-surface);
  border-bottom: 1px solid var(--plotpilot-split-border);
  flex-shrink: 0;
}

.tab-group-btn {
  flex: 1;
  padding: 4px 0;
  border: none;
  border-radius: 5px;
  background: transparent;
  font-size: 12px;
  color: var(--app-text-muted);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.tab-group-btn:hover {
  background: var(--plotpilot-panel-muted);
  color: var(--app-text-secondary);
}

.tab-group-btn--active {
  background: var(--plotpilot-panel-muted);
  color: var(--app-text-primary);
  font-weight: 600;
}

.tab-collapse-btn {
  flex-shrink: 0;
  width: 28px;
  padding: 4px 0;
  border: none;
  border-radius: 5px;
  background: transparent;
  font-size: 11px;
  color: var(--app-text-muted);
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  margin-left: auto;
}

.tab-collapse-btn:hover {
  background: var(--plotpilot-panel-muted);
  color: var(--app-text-primary);
}

/* Tab 标签内容（图标 + 文字 + badge） */
.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.tab-icon {
  opacity: 0.75;
  flex-shrink: 0;
}

.tab-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 14px;
  padding: 0 4px;
  border-radius: 7px;
  background: var(--n-error-color, #e03131);
  color: #fff;
  font-size: 10px;
  font-weight: 600;
  line-height: 1;
}

/* n-tabs 充满剩余空间 */
.settings-tabs {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.settings-tabs :deep(.n-tabs-nav) {
  padding: 0 8px;
  background: var(--app-surface);
  border-bottom: 1px solid var(--plotpilot-split-border);
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
