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
      <!-- 平铺视图：仅显示章节列表 -->
      <div v-if="viewMode === 'flat'">
        <div v-if="!chapters.length" class="sidebar-empty">暂无章节，请先在底部执行「启动结构规划」创建章节大纲</div>
        <n-list v-else hoverable clickable>
          <n-list-item
            v-for="ch in chapters"
            :key="ch.id"
            :class="{ 'is-active': currentChapterId === ch.id }"
            @click="handleChapterClick(ch.id, ch.title)"
          >
            <n-thing :title="`第${ch.number}章`">
              <template #description>
                <div style="display: flex; flex-direction: column; gap: 4px;">
                  <n-text depth="3" style="font-size: 12px;">{{ ch.title }}</n-text>
                  <n-tag size="small" :type="ch.word_count > 0 ? 'success' : 'default'" round>
                    {{ ch.word_count > 0 ? '已收稿' : '未收稿' }}
                  </n-tag>
                </div>
              </template>
            </n-thing>
          </n-list-item>
        </n-list>
      </div>

      <!-- 树形视图：显示完整叙事结构（部-卷-幕-章） -->
      <div v-else-if="viewMode === 'tree'">
        <StoryStructureTree
          ref="storyTreeRef"
          :slug="slug"
          :current-chapter-id="currentChapterId"
          @select-chapter="handleChapterClick"
          @plan-act="handlePlanAct"
          @open-plan-modal="showMacroPlan = true"
          @tree-loaded="handleTreeLoaded"
        />
      </div>
    </n-scrollbar>

    <!-- 底部操作区：仅在平铺视图或树形视图有数据时显示 -->
    <div v-if="viewMode === 'flat' || (viewMode === 'tree' && hasStructure)" class="sidebar-foot">
      <n-button
        size="small"
        secondary
        block
        @click="showMacroPlan = true"
      >
        🎯 启动结构规划
      </n-button>
    </div>
  </aside>

  <MacroPlanModal
    v-model:show="showMacroPlan"
    :novel-id="slug"
    @confirmed="emit('refresh')"
  />
</template>

<script setup lang="ts">
import { ref, type ComponentPublicInstance } from 'vue'
import StoryStructureTree from '@/components/StoryStructureTree.vue'
import MacroPlanModal from '@/components/workbench/MacroPlanModal.vue'

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
}

const props = withDefaults(defineProps<ChapterListProps>(), {
  chapters: () => [],
  currentChapterId: null
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

const showMacroPlan = ref(false)
const hasStructure = ref(true) // 默认假设有结构，由 StoryStructureTree 更新

const storyTreeRef = ref<ComponentPublicInstance<{ loadTree: () => Promise<void> }> | null>(null)

/** 幕→章确认后由工作台调用，刷新左侧叙事结构树 */
function refreshStoryTree() {
  void storyTreeRef.value?.loadTree?.()
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
  padding: 12px 10px;
  background: var(--app-surface);
  border-right: 1px solid var(--aitext-split-border);
}

.sidebar-head {
  margin-bottom: 10px;
}

.back-btn {
  margin-bottom: 8px;
  font-weight: 500;
}

.ico-arrow {
  font-size: 14px;
  margin-right: 2px;
}

.view-mode-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
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
}

.sidebar-foot {
  padding: 8px 10px;
  border-top: 1px solid var(--n-divider-color, rgba(0,0,0,.06));
}

.sidebar-empty {
  padding: 12px;
  font-size: 13px;
  color: var(--app-muted);
  line-height: 1.5;
}

.sidebar :deep(.n-list-item) {
  border-radius: 10px;
  margin-bottom: 4px;
  transition: background var(--app-transition), transform 0.15s ease;
}

.sidebar :deep(.n-list-item:hover) {
  background: rgba(79, 70, 229, 0.06);
}

.sidebar :deep(.n-list-item.is-active) {
  background: rgba(79, 70, 229, 0.12);
  box-shadow: inset 0 0 0 1px rgba(79, 70, 229, 0.25);
}
</style>
