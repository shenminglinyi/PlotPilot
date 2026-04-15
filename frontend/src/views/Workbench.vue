<template>
  <div class="workbench">
    <StatsTopBar :slug="slug" />

    <n-spin :show="pageLoading" class="workbench-spin" description="加载工作台…">
      <div class="workbench-inner">

        <!-- 左侧面板 -->
        <div
          class="side-pane left-pane"
          :style="{ width: leftCollapsed ? '0px' : leftWidth + 'px' }"
        >
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
        </div>

        <!-- 左侧分割线 + 折叠按钮 -->
        <div
          class="divider left-divider"
          @mousedown="startDragLeft"
        >
          <button
            class="collapse-btn"
            @mousedown.stop
            @click="leftCollapsed = !leftCollapsed"
            :title="leftCollapsed ? '展开左侧' : '收起左侧'"
          >{{ leftCollapsed ? '›' : '‹' }}</button>
        </div>

        <!-- 中间主区域 -->
        <div class="main-pane">
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
        </div>

        <!-- 右侧分割线 + 折叠按钮 -->
        <div
          class="divider right-divider"
          @mousedown="startDragRight"
        >
          <button
            class="collapse-btn"
            @mousedown.stop
            @click="rightCollapsed = !rightCollapsed"
            :title="rightCollapsed ? '展开右侧' : '收起右侧'"
          >{{ rightCollapsed ? '‹' : '›' }}</button>
        </div>

        <!-- 右侧面板 -->
        <div
          class="side-pane right-pane"
          :style="{ width: rightCollapsed ? '0px' : rightWidth + 'px' }"
        >
          <SettingsPanel
            :slug="slug"
            :current-panel="rightPanel"
            :bible-key="biblePanelKey"
            :current-chapter="currentChapter"
            @update:current-panel="onSettingsPanelChange"
          />
        </div>

      </div>
    </n-spin>

    <!-- 幕→章 AI 规划弹层 -->
    <ActPlanningModal
      v-model:show="showActPlanning"
      :act-id="actPlanningId"
      :act-title="actPlanningTitle"
      @confirmed="handleChapterUpdated"
    />
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

const route = useRoute()
const message = useMessage()
const statsStore = useStatsStore()
const workbenchRefresh = useWorkbenchRefreshStore()

const slug = route.params.slug as string

const chapterListRef = ref<ComponentPublicInstance<{ refreshStoryTree: () => void }> | null>(null)
const workAreaRef = ref<ComponentPublicInstance<{ ensureAssistedMode: () => void }> | null>(null)

// ── 侧栏宽度 & 折叠 ──────────────────────────────────
const LEFT_MIN = 140
const LEFT_MAX = 800
const RIGHT_MIN = 368
const RIGHT_MAX = 800

const leftWidth = ref(388)
const rightWidth = ref(558)
const leftCollapsed = ref(false)
const rightCollapsed = ref(false)

// 拖拽左侧分割线
let dragging: 'left' | 'right' | null = null
let dragStartX = 0
let dragStartWidth = 0

function startDragLeft(e: MouseEvent) {
  dragging = 'left'
  dragStartX = e.clientX
  dragStartWidth = leftWidth.value
  document.addEventListener('mousemove', onDrag)
  document.addEventListener('mouseup', stopDrag)
}

function startDragRight(e: MouseEvent) {
  dragging = 'right'
  dragStartX = e.clientX
  dragStartWidth = rightWidth.value
  document.addEventListener('mousemove', onDrag)
  document.addEventListener('mouseup', stopDrag)
}

function onDrag(e: MouseEvent) {
  if (dragging === 'left') {
    const delta = e.clientX - dragStartX
    const next = Math.min(LEFT_MAX, Math.max(LEFT_MIN, dragStartWidth + delta))
    leftWidth.value = next
    if (leftCollapsed.value) leftCollapsed.value = false
  } else if (dragging === 'right') {
    const delta = dragStartX - e.clientX   // 右侧：向左拖变大
    const next = Math.min(RIGHT_MAX, Math.max(RIGHT_MIN, dragStartWidth + delta))
    rightWidth.value = next
    if (rightCollapsed.value) rightCollapsed.value = false
  }
}

function stopDrag() {
  dragging = null
  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)
}

onUnmounted(stopDrag)

// ── Workbench 逻辑 ────────────────────────────────────
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

const showActPlanning = ref(false)
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
  () => { void syncChapterFromRoute() }
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
  height: 100%;
  min-height: 100%;
}

.workbench-inner {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: row;
  overflow: hidden;
}

/* ── 侧面板 ── */
.side-pane {
  flex-shrink: 0;
  overflow: hidden;
  transition: width 0.2s ease;
  min-width: 0;
}

.left-pane  { border-right: 1px solid var(--aitext-split-border, #e4e4e4); }
.right-pane { border-left:  1px solid var(--aitext-split-border, #e4e4e4); }

/* 折叠时去掉边框避免 1px 残留 */
.left-pane[style*="width: 0"]  { border-right: none; }
.right-pane[style*="width: 0"] { border-left: none; }

/* ── 中间区 ── */
.main-pane {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

/* ── 分割线 ── */
.divider {
  position: relative;
  flex-shrink: 0;
  width: 5px;
  background: transparent;
  cursor: col-resize;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
}

.divider::after {
  content: '';
  position: absolute;
  top: 0; bottom: 0;
  left: 2px;
  width: 1px;
  background: transparent;
  transition: background 0.15s;
}

.divider:hover::after {
  background: var(--n-primary-color, #18a058);
}

/* ── 折叠按钮 ── */
.collapse-btn {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  z-index: 20;
  width: 16px;
  height: 44px;
  padding: 0;
  border: 1px solid var(--aitext-split-border, #ddd);
  border-radius: 4px;
  background: var(--app-surface, #fff);
  cursor: pointer;
  font-size: 12px;
  color: #aaa;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 1px 6px rgba(0,0,0,0.10);
  transition: color 0.15s, background 0.15s;
  user-select: none;
  line-height: 1;
}

.collapse-btn:hover {
  color: var(--n-primary-color, #18a058);
  background: #f0faf5;
  border-color: var(--n-primary-color, #18a058);
}
</style>
