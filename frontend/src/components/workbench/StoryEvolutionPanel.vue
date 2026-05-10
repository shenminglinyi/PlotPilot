<!-- frontend/src/components/workbench/StoryEvolutionPanel.vue -->
<template>
  <div class="story-evolution-panel">
    <n-split direction="horizontal" :default-size="0.25" :min="0.20" :max="0.35">
      <!-- 左栏：故事导航 -->
      <template #1>
        <StoryNavigator
          :slug="slug"
          :current-chapter="currentChapter"
          @select-storyline="onSelectStoryline"
        />
      </template>

      <!-- 中栏 + 右栏 -->
      <template #2>
        <n-split direction="horizontal" :default-size="0.70" :min="0.60" :max="0.80">
          <!-- 中栏：时间轴 -->
          <template #1>
            <StoryTimeline
              :slug="slug"
              :highlight-range="highlightRange"
              @select-event="onSelectEvent"
              @select-snapshot="onSelectSnapshot"
            />
          </template>

          <!-- 右栏：详情面板 -->
          <template #2>
            <StoryDetailPanel
              :slug="slug"
              :selected-item="selectedItem"
              @rollback="onRollback"
              @refresh="onRefresh"
            />
          </template>
        </n-split>
      </template>
    </n-split>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import StoryNavigator from './StoryNavigator.vue'
import StoryTimeline from './StoryTimeline.vue'
import StoryDetailPanel from './StoryDetailPanel.vue'

interface Props {
  slug: string
  currentChapter: number | null
}

const props = defineProps<Props>()

// 高亮范围（选中故事线时高亮对应章节）
const highlightRange = ref<{ start: number; end: number } | null>(null)

// 选中的项目（事件或快照）
const selectedItem = ref<any>(null)

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

// 回滚操作
function onRollback() {
  // 刷新时间轴和导航
  highlightRange.value = null
  selectedItem.value = null
}

// 刷新
function onRefresh() {
  highlightRange.value = null
  selectedItem.value = null
}
</script>

<style scoped>
.story-evolution-panel {
  height: 100%;
  min-height: 0;
  display: flex;
  overflow: hidden;
  background: var(--app-surface);
}

.story-evolution-panel :deep(.n-split) {
  height: 100%;
}

.story-evolution-panel :deep(.n-split-pane-1),
.story-evolution-panel :deep(.n-split-pane-2) {
  min-height: 0;
  overflow: hidden;
}
</style>
