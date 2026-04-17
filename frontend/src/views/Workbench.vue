<template>
  <div class="workbench">
    <StatsTopBar :slug="slug" @open-settings="showLLMSettings = true" />

    <n-spin :show="pageLoading" class="workbench-spin" description="加载工作台…">
      <div class="workbench-inner">
        <n-split direction="horizontal" :min="0.12" :max="0.30" :default-size="0.18">
          <template #1>
            <ChapterList
              ref="chapterListRef"
              :slug="slug"
              :chapters="chapters"
              :current-chapter-id="currentChapterId"
              @select="onSidebarChapterSelect"
              @back="goHome"
              @refresh="handleChapterUpdated"
              @plan-act="handlePlanAct"
            />
          </template>

          <template #2>
            <n-split direction="horizontal" :min="0.40" :max="0.75" :default-size="0.60">
              <template #1>
                <WorkArea
                  ref="workAreaRef"
                  :slug="slug"
                  :book-title="bookTitle"
                  :chapters="chapters"
                  :target-words-per-chapter="targetWordsPerChapter"
                  :current-chapter-id="currentChapterId"
                  :chapter-content="chapterContent"
                  :chapter-loading="chapterLoading"
                  @set-right-panel="setRightPanel"
                  @chapter-updated="handleChapterUpdated"
                />
              </template>

              <template #2>
                <SettingsPanel
                  :slug="slug"
                  :current-panel="rightPanel"
                  :bible-key="biblePanelKey"
                  :current-chapter="currentChapter"
                  @update:current-panel="onSettingsPanelChange"
                />
              </template>
            </n-split>
          </template>
        </n-split>
      </div>
    </n-spin>

    <!-- 幕→章 AI 规划弹层 -->
    <ActPlanningModal
      v-model:show="showActPlanning"
      :act-id="actPlanningId"
      :act-title="actPlanningTitle"
      @confirmed="handleChapterUpdated"
    />

    <!-- LLM Settings Modal -->
    <LLMSettingsModal v-model:show="showLLMSettings" />

    <!-- 全局浮动按钮 -->
    <GlobalLLMFloatingButton />
    <PromptPlazaFAB />
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent, onMounted, computed, ref, watch, type ComponentPublicInstance } from 'vue'
import { useRoute } from 'vue-router'
import { useMessage } from 'naive-ui'
import { useWorkbench } from '../composables/useWorkbench'
import { useStatsStore } from '../stores/statsStore'
import { useWorkbenchRefreshStore } from '../stores/workbenchRefreshStore'

const StatsTopBar = defineAsyncComponent(() => import('../components/stats/StatsTopBar.vue'))
const ChapterList = defineAsyncComponent(() => import('../components/workbench/ChapterList.vue'))
const WorkArea = defineAsyncComponent(() => import('../components/workbench/WorkArea.vue'))
const SettingsPanel = defineAsyncComponent(() => import('../components/workbench/SettingsPanel.vue'))
const ActPlanningModal = defineAsyncComponent(() => import('../components/workbench/ActPlanningModal.vue'))
const LLMSettingsModal = defineAsyncComponent(() => import('../components/LLMSettingsModal.vue'))
const GlobalLLMFloatingButton = defineAsyncComponent(() => import('../components/global/GlobalLLMFloatingButton.vue'))
const PromptPlazaFAB = defineAsyncComponent(() => import('../components/global/PromptPlazaFAB.vue'))

const route = useRoute()
const message = useMessage()
const statsStore = useStatsStore()
const workbenchRefresh = useWorkbenchRefreshStore()

const slug = route.params.slug as string

const chapterListRef = ref<ComponentPublicInstance<{ refreshStoryTree: () => void }> | null>(null)
const workAreaRef = ref<ComponentPublicInstance<{ ensureAssistedMode: () => void }> | null>(null)

async function onSidebarChapterSelect(chapterId: number, title = '') {
  await handleChapterSelect(chapterId, title)
  workAreaRef.value?.ensureAssistedMode?.()
}

const handleChapterUpdated = async () => {
  await loadDesk()
  void statsStore.loadBookStats(slug, true).catch(() => {})
  biblePanelKey.value += 1
  chapterListRef.value?.refreshStoryTree?.()
  workbenchRefresh.bumpAfterChapterDeskChange()
}

// 幕→章 规划弹层
const showActPlanning = ref(false)
const showLLMSettings = ref(false)
const actPlanningId = ref('')
const actPlanningTitle = ref('')

const handlePlanAct = (actId: string, actTitle: string) => {
  actPlanningId.value = actId
  actPlanningTitle.value = actTitle
  showActPlanning.value = true
}

const {
  bookTitle,
  chapters,
  rightPanel,
  biblePanelKey,
  pageLoading,
  bookMeta,
  currentJobId,
  currentChapterId,
  chapterContent,
  chapterLoading,
  targetWordsPerChapter,
  setRightPanel,
  loadDesk,
  goHome,
  goToChapter,
  handleChapterSelect,
} = useWorkbench({ slug })

const currentChapter = computed(() => {
  if (!currentChapterId.value) return null
  return chapters.value.find(ch => ch.id === currentChapterId.value) || null
})

function onSettingsPanelChange(panel: string) {
  rightPanel.value = panel
}

function parseChapterQuery(q: unknown): number | null {
  if (q == null || q === '') return null
  const raw = Array.isArray(q) ? q[0] : q
  const n = Number(raw)
  return !Number.isNaN(n) && n >= 1 ? n : null
}

async function syncChapterFromRoute() {
  const n = parseChapterQuery(route.query.chapter)
  if (n != null) {
    await goToChapter(n)
  }
}

onMounted(async () => {
  try {
    await loadDesk()
    await syncChapterFromRoute()
  } catch {
    message.error('加载失败，请检查网络与后端是否已启动')
    bookTitle.value = slug
  } finally {
    pageLoading.value = false
  }
})

watch(
  () => route.query.chapter,
  () => {
    void syncChapterFromRoute()
  }
)
</script>

<style scoped>
.workbench {
  height: 100vh;
  min-height: 0;
  background: var(--app-page-bg, #f0f2f8);
  display: flex;
  flex-direction: column;
}

.workbench-spin {
  flex: 1;
  min-height: 0;
}

.workbench-spin :deep(.n-spin-content) {
  min-height: 100%;
  height: 100%;
}

.workbench-inner {
  height: 100%;
  min-height: 0;
}

.workbench-inner :deep(.n-split) {
  height: 100%;
}

.workbench-inner :deep(.n-split-pane-1) {
  min-height: 0;
  overflow: hidden;
}
</style>
