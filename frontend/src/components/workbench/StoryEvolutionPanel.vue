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
const activeTab = ref<'timeline' | 'worldline'>('timeline')

// 高亮范围（选中故事线时高亮对应章节）
const highlightRange = ref<{ start: number; end: number } | null>(null)

// 选中的项目（事件或快照）
const selectedItem = ref<any>(null)

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

const bundledChronicleRows = computed((): ChronicleRow[] => {
  const raw = bundle.value?.chronotope?.rows
  if (!Array.isArray(raw)) return []
  return raw as ChronicleRow[]
})

watch(
  () => props.slug,
  () => {
    highlightRange.value = null
    selectedItem.value = null
    void loadBundle()
  },
  { immediate: true },
)

useWorkbenchPlotTimelineReload(() => {
  void loadBundle()
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
</style>
