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
                  :current-chapter-id="currentChapterId"
                  :chapter-content="chapterContent"
                  :chapter-loading="chapterLoading"
                  @chapter-updated="handleChapterUpdated"
                />
              </template>

              <template #2>
                <SettingsPanel
                  :slug="slug"
                  :current-panel="rightPanel"
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
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, computed, ref, watch, type ComponentPublicInstance } from 'vue'
import { useRoute } from 'vue-router'
import { useMessage } from 'naive-ui'
import { useWorkbench } from '../composables/useWorkbench'
import { useStatsStore } from '../stores/statsStore'
import { useWorkbenchRefreshStore } from '../stores/workbenchRefreshStore'
import StatsTopBar from '../components/stats/StatsTopBar.vue'
import ChapterList from '../components/workbench/ChapterList.vue'
import WorkArea from '../components/workbench/WorkArea.vue'
import SettingsPanel from '../components/workbench/SettingsPanel.vue'
import ActPlanningModal from '../components/workbench/ActPlanningModal.vue'
import LLMSettingsModal from '../components/LLMSettingsModal.vue'
import {
  WORKBENCH_CHAPTER_DESK_CHANGE_EVENT,
  WORKBENCH_OPEN_SETTINGS_PANEL_EVENT,
  isWorkbenchSettingsPanelName,
} from '../workbench/deskEvents'

const route = useRoute()
const message = useMessage()
const statsStore = useStatsStore()
const workbenchRefresh = useWorkbenchRefreshStore()

const slug = computed(() => String(route.params.slug ?? ''))

const chapterListRef = ref<ComponentPublicInstance<{ refreshStoryTree: () => void }> | null>(null)
const workAreaRef = ref<ComponentPublicInstance<{ ensureAssistedMode: () => void }> | null>(null)

async function onSidebarChapterSelect(chapterId: number, title = '') {
  await handleChapterSelect(chapterId, title)
  workAreaRef.value?.ensureAssistedMode?.()
}

/** 合并短时间内的多次「整桌刷新」：全托管状态抖动 / 多源 emit 时只拉一次 API，减轻闪烁与日志刷屏 */
let chapterDeskReloadTimer: ReturnType<typeof setTimeout> | null = null
const CHAPTER_DESK_RELOAD_DEBOUNCE_MS = 1100

async function runChapterDeskReload() {
  await loadDesk()
  void statsStore.loadBookStats(slug.value, true).catch(() => {})
  window.dispatchEvent(new CustomEvent('aitext:bible-panel:soft-reload'))
  chapterListRef.value?.refreshStoryTree?.()
  workbenchRefresh.bumpAfterChapterDeskChange()
}

const handleChapterUpdated = () => {
  if (chapterDeskReloadTimer) clearTimeout(chapterDeskReloadTimer)
  chapterDeskReloadTimer = setTimeout(() => {
    chapterDeskReloadTimer = null
    void runChapterDeskReload()
  }, CHAPTER_DESK_RELOAD_DEBOUNCE_MS)
}

function onDeskChangeSignalFromPanels() {
  handleChapterUpdated()
}

function onOpenSettingsPanelFromChild(e: Event) {
  const panel = (e as CustomEvent<{ panel?: string }>).detail?.panel
  if (typeof panel === 'string' && isWorkbenchSettingsPanelName(panel)) {
    rightPanel.value = panel
  }
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
  pageLoading,
  bookMeta,
  currentJobId,
  currentChapterId,
  chapterContent,
  chapterLoading,
  setRightPanel,
  loadDesk,
  reloadDeskForSlugChange,
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
  window.addEventListener(WORKBENCH_CHAPTER_DESK_CHANGE_EVENT, onDeskChangeSignalFromPanels)
  window.addEventListener(WORKBENCH_OPEN_SETTINGS_PANEL_EVENT, onOpenSettingsPanelFromChild)
  try {
    await loadDesk()
    await syncChapterFromRoute()
  } catch {
    message.error('加载失败，请检查网络与后端是否已启动')
    bookTitle.value = slug.value
  } finally {
    pageLoading.value = false
  }
})

onUnmounted(() => {
  window.removeEventListener(WORKBENCH_CHAPTER_DESK_CHANGE_EVENT, onDeskChangeSignalFromPanels)
  window.removeEventListener(WORKBENCH_OPEN_SETTINGS_PANEL_EVENT, onOpenSettingsPanelFromChild)
  if (chapterDeskReloadTimer) {
    clearTimeout(chapterDeskReloadTimer)
    chapterDeskReloadTimer = null
  }
})

watch(
  () => route.query.chapter,
  () => {
    void syncChapterFromRoute()
  }
)

watch(
  slug,
  async (next, prev) => {
    if (!next || prev === next) return
    try {
      await reloadDeskForSlugChange()
      await syncChapterFromRoute()
      void statsStore.loadBookStats(next, true).catch(() => {})
      chapterListRef.value?.refreshStoryTree?.()
      workbenchRefresh.bumpAfterChapterDeskChange()
    } catch {
      message.error('切换作品失败，请检查网络与后端是否已启动')
      bookTitle.value = next
    }
  }
)
</script>

<style scoped>
.workbench {
  height: 100vh;
  min-height: 0;
  max-height: 100vh;
  overflow: hidden;
  background: var(--app-page-bg, #f0f2f8);
  display: flex;
  flex-direction: column;
}

.workbench-spin {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.workbench-spin :deep(.n-spin-content) {
  flex: 1;
  min-height: 0;
  height: auto;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.workbench-inner {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.workbench-inner :deep(.n-split) {
  flex: 1;
  min-height: 0;
  height: 100%;
}

.workbench-inner :deep(.n-split-pane-1),
.workbench-inner :deep(.n-split-pane-2) {
  min-height: 0;
  overflow: hidden;
}
</style>
