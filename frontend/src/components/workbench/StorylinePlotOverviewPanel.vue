<template>
  <div class="spo-panel">
    <div class="spo-intro">
      <div class="spo-intro-header">
        <span class="spo-intro-icon">📊</span>
        <h4 class="spo-intro-title">故事线（全书骨架）</h4>
      </div>
      <ul class="spo-bullets">
        <li><strong>写</strong>：宏观规划（MACRO_PLANNING）或重大转折后人工调整故事线起止章。</li>
        <li><strong>读</strong>：幕/章规划（ACT_PLANNING）与生成上下文组装时注入「当前处于哪条线」。</li>
      </ul>
    </div>

    <div class="spo-mode-switch">
      <n-radio-group v-model:value="spoView" size="small">
        <n-radio-button value="charts">
          <span class="mode-icon">📈</span>
          <span>图表概览</span>
        </n-radio-button>
        <n-radio-button value="storylines">
          <span class="mode-icon">📚</span>
          <span>故事线列表与编辑</span>
        </n-radio-button>
      </n-radio-group>
    </div>

    <n-spin :show="loading" class="spo-spin">
      <div class="spo-view-body">
        <!-- 故事阶段进度条 -->
        <n-collapse :default-expanded-names="['phase']" class="spo-engine-collapse">
          <n-collapse-item name="phase" title="📈 故事阶段">
            <StoryPhasePanel :slug="slug" />
          </n-collapse-item>
          <n-collapse-item name="checkpoint" title="📸 版本时间线">
            <CheckpointTimelinePanel :slug="slug" />
          </n-collapse-item>
        </n-collapse>

        <n-space v-show="spoView === 'charts'" vertical :size="14" class="spo-view-charts">
        <!-- 迷你甘特：故事线 -->
        <n-card title="故事线覆盖（章节轴示意）" size="small" :bordered="true">
          <template #header-extra>
            <n-text depth="3" class="spo-card-hint">横轴为章号，色条为线体跨度</n-text>
          </template>
          <n-empty
            v-if="storylines.length === 0"
            class="spo-empty-inline"
            size="small"
            description="暂无故事线"
          >
            <template #extra>
              <n-text depth="3" style="font-size: 12px; max-width: 260px; text-align: center">
                切换到「故事线列表与编辑」添加主线/支线后，此处会显示章节轴示意。
              </n-text>
            </template>
          </n-empty>
          <div v-else class="gantt-wrap">
            <div class="gantt-axis">
              <span>1</span>
              <span v-if="maxChapter > 1">{{ midChapterLabel }}</span>
              <span>{{ maxChapter }}</span>
            </div>
            <div
              v-for="sl in storylines"
              :key="sl.id"
              class="gantt-row"
            >
              <div class="gantt-label" :title="sl.name || sl.id">
                <n-tag :type="typeColor(sl.storyline_type)" size="tiny" round>
                  {{ typeLabel(sl.storyline_type) }}
                </n-tag>
                <span class="gantt-name">{{ shortName(sl) }}</span>
              </div>
              <div class="gantt-track">
                <div
                  class="gantt-bar"
                  :style="barStyle(sl.estimated_chapter_start, sl.estimated_chapter_end)"
                />
              </div>
            </div>
          </div>
        </n-card>
        </n-space>

        <div v-show="spoView === 'storylines'" class="spo-view-embed">
          <StorylinePanel :slug="slug" :current-chapter="currentChapter" />
        </div>
      </div>
    </n-spin>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useWorkbenchRefreshStore } from '../../stores/workbenchRefreshStore'
import { workflowApi } from '../../api/workflow'
import type { StorylineDTO } from '../../api/workflow'
import StorylinePanel from './StorylinePanel.vue'
import StoryPhasePanel from './StoryPhasePanel.vue'
import CheckpointTimelinePanel from './CheckpointTimelinePanel.vue'

const props = defineProps<{ slug: string; currentChapter?: number | null }>()

type SpoView = 'charts' | 'storylines'
const spoView = ref<SpoView>('charts')

const loading = ref(false)
const storylines = ref<StorylineDTO[]>([])

const maxChapter = computed(() => {
  let m = 1
  for (const sl of storylines.value) {
    m = Math.max(m, sl.estimated_chapter_end || 1, sl.estimated_chapter_start || 1)
  }
  return Math.max(m, 12)
})

const midChapterLabel = computed(() => String(Math.round(maxChapter.value / 2)))

function barStyle(start: number, end: number) {
  const max = maxChapter.value
  const s = Math.max(1, start)
  const e = Math.max(s, end)
  const leftPct = ((s - 1) / max) * 100
  const widthPct = ((e - s + 1) / max) * 100
  return {
    left: `${leftPct}%`,
    width: `${Math.min(100 - leftPct, widthPct)}%`,
  }
}

function typeLabel(t: string) {
  const map: Record<string, string> = {
    main_plot: '主线',
    romance: '感情',
    mystery: '悬疑',
    subplot: '支线',
  }
  return map[t] || t
}

function typeColor(t: string): 'success' | 'warning' | 'error' | 'info' | 'default' {
  if (t === 'main_plot') return 'success'
  if (t === 'romance') return 'error'
  if (t === 'mystery') return 'warning'
  return 'info'
}

function shortName(sl: StorylineDTO) {
  const n = (sl.name || '').trim()
  if (n) return n.length > 10 ? `${n.slice(0, 10)}…` : n
  return sl.id.slice(0, 8)
}

async function load() {
  loading.value = true
  try {
    const sl = await workflowApi.getStorylines(props.slug)
    storylines.value = sl || []
  } catch {
    storylines.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.slug, () => void load(), { immediate: true })

const refreshStore = useWorkbenchRefreshStore()
const { deskTick } = storeToRefs(refreshStore)
watch(deskTick, () => void load())
</script>

<style scoped>
.spo-panel {
  height: 100%;
  min-height: 0;
  overflow-y: auto;
  padding: 20px 16px;
  background: linear-gradient(135deg, var(--n-color-modal) 0%, rgba(99, 102, 241, 0.03) 100%);
}

/* 优化顶部提示信息样式 */
.spo-intro {
  margin-bottom: 16px;
  padding: 16px 18px;
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.08) 0%, rgba(139, 92, 246, 0.05) 100%);
  border: 1px solid rgba(99, 102, 241, 0.15);
  box-shadow: 0 2px 12px rgba(99, 102, 241, 0.08);
  transition: all 0.3s ease;
}

.spo-intro:hover {
  box-shadow: 0 4px 20px rgba(99, 102, 241, 0.12);
  border-color: rgba(99, 102, 241, 0.25);
}

.spo-intro-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.spo-intro-icon {
  font-size: 20px;
  line-height: 1;
}

.spo-intro-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--n-text-color-1);
  letter-spacing: 0.02em;
}

/* 优化视图切换按钮样式 */
.spo-mode-switch {
  width: 100%;
  margin-bottom: 16px;
}

.spo-mode-switch :deep(.n-radio-group) {
  display: flex;
  flex-wrap: wrap;
  width: 100%;
  gap: 8px;
}

.spo-mode-switch :deep(.n-radio-button) {
  flex: 1 1 auto;
  min-width: 0;
  border-radius: 10px;
  transition: all 0.3s ease;
}

.spo-mode-switch :deep(.n-radio-button__state-border) {
  white-space: normal;
  text-align: center;
  line-height: 1.4;
  padding: 8px 12px;
  border-radius: 10px;
}

.mode-icon {
  font-size: 14px;
  margin-right: 4px;
  opacity: 0.9;
}

.spo-view-body {
  width: 100%;
  min-height: 0;
}

.spo-view-charts {
  width: 100%;
}

.spo-view-embed {
  width: 100%;
  min-height: 360px;
  height: min(65vh, 640px);
  max-height: 720px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.spo-view-embed :deep(.storyline-panel) {
  flex: 1;
  min-height: 0;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.spo-bullets {
  margin: 0;
  padding-left: 1.3rem;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--n-text-color-2);
}

.spo-bullets li {
  margin-bottom: 6px;
  position: relative;
}

.spo-bullets li:last-child {
  margin-bottom: 0;
}

.spo-spin {
  width: 100%;
}

/* 优化甘特图样式 */
.gantt-wrap {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 8px 0;
  margin: 0;
}

.gantt-axis {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  font-weight: 600;
  color: var(--n-text-color-3);
  padding: 0 6px 8px;
  letter-spacing: 0.02em;
}

.gantt-row {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 36px;
  padding: 6px 0;
  border-radius: 8px;
  transition: all 0.25s ease;
}

.gantt-row:hover {
  background: rgba(99, 102, 241, 0.04);
  padding-left: 4px;
  padding-right: 4px;
  margin-left: -4px;
  margin-right: -4px;
}

.gantt-label {
  width: 130px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  overflow: hidden;
}

.gantt-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--n-text-color-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.gantt-track {
  flex: 1;
  height: 18px;
  background: linear-gradient(90deg, rgba(24, 160, 88, 0.06) 0%, rgba(24, 160, 88, 0.1) 50%, rgba(24, 160, 88, 0.06) 100%);
  border-radius: 9px;
  position: relative;
  min-width: 0;
  box-shadow: inset 0 1px 4px rgba(0, 0, 0, 0.06);
  overflow: hidden;
}

.gantt-track::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 50%;
  background: linear-gradient(to bottom, rgba(255, 255, 255, 0.15), transparent);
  border-radius: 9px 9px 0 0;
}

.gantt-bar {
  position: absolute;
  top: 3px;
  height: 12px;
  border-radius: 6px;
  background: linear-gradient(135deg, #36ad6a 0%, #18a058 100%);
  min-width: 8px;
  box-shadow: 0 2px 8px rgba(24, 160, 88, 0.35);
  transition: all 0.25s ease;
  cursor: pointer;
}

.gantt-bar::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 50%;
  background: linear-gradient(to bottom, rgba(255, 255, 255, 0.25), transparent);
  border-radius: 6px 6px 0 0;
}

.gantt-bar:hover {
  box-shadow: 0 4px 16px rgba(24, 160, 88, 0.5);
  transform: translateY(-1px);
}

.spo-card-hint {
  font-size: 11px;
  white-space: nowrap;
}

/* 优化卡片样式 */
.spo-panel :deep(.n-card) {
  border-radius: 14px;
  box-shadow: 0 2px 16px rgba(0, 0, 0, 0.06);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  border: 1px solid rgba(99, 102, 241, 0.08);
  overflow: visible;
}

.spo-panel :deep(.n-card:hover) {
  box-shadow: 0 6px 28px rgba(99, 102, 241, 0.12);
  border-color: rgba(99, 102, 241, 0.15);
  transform: translateY(-1px);
}

.spo-panel :deep(.n-card-header) {
  padding: 14px 18px !important;
  font-weight: 600;
  border-bottom: 1px solid rgba(99, 102, 241, 0.1);
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.04) 0%, rgba(139, 92, 246, 0.02) 100%);
}

.spo-panel :deep(.n-card-header__main) {
  display: flex;
  align-items: center;
  gap: 8px;
}

.spo-panel :deep(.n-card-header__extra) {
  display: flex;
  align-items: center;
  gap: 8px;
}

.spo-panel :deep(.n-card__content) {
  padding: 14px 18px !important;
}

.spo-panel :deep(.spo-empty-inline.n-empty) {
  padding: 16px 12px !important;
  min-height: auto !important;
}

.spo-panel :deep(.n-empty:not(.spo-empty-inline)) {
  padding: 24px 16px;
  min-height: 88px;
}

.spo-panel :deep(.n-empty__description) {
  font-size: 13px;
  color: var(--n-text-color-3);
}

.spo-panel :deep(.n-button) {
  height: 28px;
  min-height: 28px;
  padding: 0 12px;
  font-size: 13px;
}

.spo-engine-collapse {
  margin-bottom: 12px;
  border: 1px solid rgba(99, 102, 241, 0.1);
  border-radius: 12px;
  overflow: hidden;
  background: var(--n-color-modal);
}

.spo-engine-collapse :deep(.n-collapse-item__header) {
  font-weight: 600;
  font-size: 13px;
}

.spo-engine-collapse :deep(.n-collapse-item__content-wrapper) {
  max-height: 300px;
  overflow-y: auto;
}

</style>
