<template>
  <aside class="sidebar">
    <div class="sidebar-head">
      <n-button quaternary size="small" class="back-btn" @click="handleBack">
        <template #icon>
          <span class="ico-arrow">←</span>
        </template>
        书目列表
      </n-button>

      <!-- 视图模式切换 -->
      <div class="view-mode-row">
        <n-select
          v-model:value="viewMode"
          :options="viewModeOptions"
          size="small"
          style="flex: 1;"
        />
      </div>
    </div>

    <n-scrollbar class="sidebar-scroll">
      <!-- 平铺视图：分页显示章节列表，避免大量章节一次性渲染 -->
      <div v-if="viewMode === 'flat'">
        <div v-if="!chapters.length" class="sidebar-empty">
          <p>暂无章节</p>
          <p class="hint">可在正文区直接生成下一章正文</p>
        </div>
        <template v-else>
          <n-list hoverable clickable>
            <n-list-item
              v-for="ch in visibleChapters"
              :key="ch.id"
              :class="{ 'is-active': currentChapterId === ch.id }"
              @click="handleChapterClick(ch.id, ch.title)"
            >
              <n-thing :title="narrativeOrdinalLabel(ch.number, generationPrefs)">
                <template #description>
                  <div style="display: flex; flex-direction: column; gap: 4px;">
                    <n-text depth="3" style="font-size: 12px;">{{ ch.title }}</n-text>
                    <n-tag size="small" :type="ch.word_count > 0 ? 'success' : 'default'" round>
                      {{ ch.word_count > 0 ? '已收稿' : '未收稿' }}
                    </n-tag>
                    <n-tag
                      v-if="props.writingChapterNumber != null && ch.number === props.writingChapterNumber"
                      size="small"
                      type="info"
                      round
                      class="ch-writing-tag"
                    >
                      {{ props.writingPipelineStep ? `步骤${props.writingPipelineStep}·写作中` : '写作中' }}
                    </n-tag>
                  </div>
                </template>
              </n-thing>
            </n-list-item>
          </n-list>
          <div v-if="hasMoreChapters" class="load-more-bar">
            <n-button text size="small" @click="loadMoreChapters">
              查看更多（剩余 {{ chapters.length - visibleCount }} {{ narrativeUnitNoun(generationPrefs) }}）
            </n-button>
          </div>
        </template>
      </div>

      <!-- 树形视图：显示完整叙事结构（部-卷-幕-章） -->
      <div v-else-if="viewMode === 'tree'">
        <StoryStructureTree
          ref="storyTreeRef"
          :slug="slug"
          :chapters="chapters"
          :current-chapter-id="currentChapterId"
          :generation-prefs="generationPrefs"
          @select-chapter="handleChapterClick"
          @plan-act="handlePlanAct"
          @open-plan-modal="showMacroPlan = true"
          @tree-loaded="handleTreeLoaded"
        />
      </div>
    </n-scrollbar>

    <!-- MVP 生文空态提示 -->
    <div v-if="!chapters.length && viewMode === 'flat'" class="sidebar-foot-hint">
      <n-alert type="info" :show-icon="false" style="font-size: 12px">
        <strong>提示</strong>：正文区可直接生成正文
      </n-alert>
    </div>
  </aside>

  <MacroPlanModal
    v-model:show="showMacroPlan"
    :novel-id="slug"
    @confirmed="emit('refresh')"
  />
</template>

<script setup lang="ts">
import { ref, computed, type ComponentPublicInstance } from 'vue'
import StoryStructureTree from '@/components/StoryStructureTree.vue'
import MacroPlanModal from '@/components/workbench/MacroPlanModal.vue'
import type { GenerationPrefsDTO } from '@/api/novel'
import { narrativeOrdinalLabel, narrativeUnitNoun } from '@/utils/narrativeUnitLabel'

const INITIAL_VISIBLE_COUNT = 50
const LOAD_MORE_STEP = 50

interface Chapter {
  id: number
  number: number
  title: string
  word_count: number
}

interface ChapterListProps {
  slug: string
  chapters: Chapter[]
  currentChapterId?: number | null
  generationPrefs?: GenerationPrefsDTO | null
  writingChapterNumber?: number | null
  writingPipelineStep?: number | null
}

const props = withDefaults(defineProps<ChapterListProps>(), {
  chapters: () => [],
  currentChapterId: null,
  generationPrefs: null,
  writingChapterNumber: null,
  writingPipelineStep: null,
})

const emit = defineEmits<{
  select: [id: number, title: string]
  back: []
  refresh: []
  planAct: [actId: string, actTitle: string]
}>()

const viewMode = ref('tree')
const viewModeOptions = [
  { label: '树形视图', value: 'tree' },
  { label: '平铺视图', value: 'flat' }
]

const visibleCount = ref(INITIAL_VISIBLE_COUNT)
const visibleChapters = computed(() => props.chapters.slice(0, visibleCount.value))
const hasMoreChapters = computed(() => props.chapters.length > visibleCount.value)

function loadMoreChapters() {
  visibleCount.value += LOAD_MORE_STEP
}

const showMacroPlan = ref(false)
const hasStructure = ref(true)

const storyTreeRef = ref<ComponentPublicInstance<{ loadTree: () => Promise<void> }> | null>(null)

/** 合并短时间内的多次刷新（全托管 desk 更新等），减轻结构树请求叠压 */
let storyTreeRefreshTimer: ReturnType<typeof setTimeout> | null = null
const STORY_TREE_REFRESH_DEBOUNCE_MS = 200

/** 幕→章确认后由工作台调用，刷新左侧叙事结构树 */
function refreshStoryTree() {
  if (storyTreeRefreshTimer != null) {
    clearTimeout(storyTreeRefreshTimer)
  }
  storyTreeRefreshTimer = setTimeout(() => {
    storyTreeRefreshTimer = null
    void storyTreeRef.value?.loadTree?.()
  }, STORY_TREE_REFRESH_DEBOUNCE_MS)
}

defineExpose({ refreshStoryTree })

const handleChapterClick = (id: number, title = '') => {
  emit('select', id, title)
}

const handleBack = () => {
  emit('back')
}

const handlePlanAct = (id: string, title: string) => {
  emit('planAct', id, title)
}

const handleTreeLoaded = (hasData: boolean) => {
  hasStructure.value = hasData
}

</script>

<style scoped>
.sidebar {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 10px 10px 12px;
  background: var(--app-surface);
  border-right: 1px solid var(--plotpilot-split-border);
}

.sidebar-head {
  margin-bottom: 8px;
}

.back-btn {
  margin-bottom: 10px;
  padding-left: 2px;
  color: var(--app-text-muted);
  font-size: 14px;
  font-weight: 600;
}

.ico-arrow {
  font-size: 14px;
  margin-right: 3px;
  color: var(--app-text-muted);
}

.view-mode-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 0;
  padding: 2px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--app-surface-subtle) 70%, transparent);
  border: 1px solid color-mix(in srgb, var(--app-border) 55%, transparent);
}

.sidebar-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.sidebar-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.sidebar-scroll {
  flex: 1;
  min-height: 0;
  margin: 0 -2px;
}

.sidebar-foot-hint {
  padding: 8px 4px;
  border-top: 1px solid var(--n-divider-color, rgba(0,0,0,.06));
}

.sidebar-empty {
  padding: 12px;
  font-size: 13px;
  color: var(--app-muted);
  line-height: 1.6;
}

.sidebar-empty .hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--color-brand, #18a058);
}

.sidebar :deep(.n-list-item) {
  border-radius: 6px;
  margin-bottom: 4px;
  transition: background var(--app-transition), transform 0.15s ease;
}

.sidebar :deep(.n-list-item:hover) {
  background: var(--color-brand-light);
}

.sidebar :deep(.n-list-item.is-active) {
  background: var(--color-brand-light);
  box-shadow: inset 0 0 0 1px var(--color-brand-border);
}

.load-more-bar {
  padding: 8px 12px;
  text-align: center;
  border-top: 1px solid var(--app-border);
}

.ch-writing-tag {
  animation: ch-writing-pulse 1.4s ease-in-out infinite;
}

.view-mode-row :deep(.n-base-selection) {
  --n-border: none !important;
  --n-border-hover: none !important;
  --n-border-focus: none !important;
  --n-box-shadow-focus: none !important;
  --n-height: 32px !important;
  background: transparent;
}

.view-mode-row :deep(.n-base-selection-label) {
  background: transparent;
  color: var(--app-text-secondary);
  font-size: 13px;
  font-weight: 600;
}

.view-mode-row :deep(.n-base-selection__border),
.view-mode-row :deep(.n-base-selection__state-border) {
  display: none;
}

@keyframes ch-writing-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.55; }
}
</style>
