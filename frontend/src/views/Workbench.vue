<template>
  <div class="workbench">
    <StatsTopBar :slug="slug" @open-settings="showLLMSettings = true" />

    <n-spin :show="pageLoading" class="workbench-spin" description="加载工作台…">
      <div class="workbench-inner">
        <n-split direction="horizontal" :min="0.14" :max="0.32" :default-size="0.2">
          <template #1>
            <ChapterList
              ref="chapterListRef"
              :slug="slug"
              :chapters="chapters"
              :current-chapter-id="currentChapterId"
              @select="onSidebarChapterSelect"
              @back="handleBackToHome"
              @refresh="handleChapterUpdated"
              @plan-act="handlePlanAct"
            />
          </template>

          <template #2>
            <n-split direction="horizontal" :min="0.38" :max="0.74" :default-size="0.58">
              <template #1>
                <WorkArea
                  ref="workAreaRef"
                  :slug="slug"
                  :book-title="bookTitle"
                  :chapters="chapters"
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
  </div>
</template>

<script setup lang="ts">
import { onMounted, computed, ref, watch, type ComponentPublicInstance } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useMessage, useDialog } from 'naive-ui'
import { useWorkbench } from '../composables/useWorkbench'
import { useStatsStore } from '../stores/statsStore'
import { useWorkbenchRefreshStore } from '../stores/workbenchRefreshStore'
import StatsTopBar from '../components/stats/StatsTopBar.vue'
import ChapterList from '../components/workbench/ChapterList.vue'
import WorkArea from '../components/workbench/WorkArea.vue'
import SettingsPanel from '../components/workbench/SettingsPanel.vue'
import ActPlanningModal from '../components/workbench/ActPlanningModal.vue'
import LLMSettingsModal from '../components/LLMSettingsModal.vue'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const dialog = useDialog()
const statsStore = useStatsStore()
const workbenchRefresh = useWorkbenchRefreshStore()

const slug = route.params.slug as string

const chapterListRef = ref<ComponentPublicInstance<{ refreshStoryTree: () => void }> | null>(null)
const workAreaRef = ref<ComponentPublicInstance<{
  ensureAssistedMode: () => void
  getHasUnsavedChanges: () => boolean
}> | null>(null)

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
  setRightPanel,
  loadDesk,
  goHome,
  goToChapter,
  handleChapterSelect,
} = useWorkbench({ slug })

function confirmDiscardDraft(): Promise<boolean> {
  return new Promise((resolve) => {
    dialog.warning({
      title: '未保存的修改',
      content: '当前章节正文有未保存的修改。继续将放弃这些修改。',
      positiveText: '放弃修改并继续',
      negativeText: '取消',
      maskClosable: false,
      onPositiveClick: () => {
        resolve(true)
      },
      onNegativeClick: () => {
        resolve(false)
      },
      onClose: () => {
        resolve(false)
      },
    })
  })
}

async function onSidebarChapterSelect(chapterId: number, title = '') {
  if (chapterId === currentChapterId.value) {
    workAreaRef.value?.ensureAssistedMode?.()
    return
  }
  const dirty = workAreaRef.value?.getHasUnsavedChanges?.() ?? false
  if (dirty) {
    const ok = await confirmDiscardDraft()
    if (!ok) return
  }
  await handleChapterSelect(chapterId, title)
  workAreaRef.value?.ensureAssistedMode?.()
}

async function handleBackToHome() {
  const dirty = workAreaRef.value?.getHasUnsavedChanges?.() ?? false
  if (dirty) {
    const ok = await confirmDiscardDraft()
    if (!ok) return
  }
  goHome()
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
    if (n === currentChapterId.value) return
    const dirty = workAreaRef.value?.getHasUnsavedChanges?.() ?? false
    if (dirty) {
      const ok = await confirmDiscardDraft()
      if (!ok) {
        const cur = currentChapterId.value
        const reverted = { ...route.query } as Record<string, string | string[] | undefined>
        if (cur != null) reverted.chapter = String(cur)
        else delete reverted.chapter
        await router.replace({
          name: 'Workbench',
          params: { slug },
          query: reverted,
        })
        return
      }
    }
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
