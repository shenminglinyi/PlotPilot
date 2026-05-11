import { computed, reactive, ref, watch } from 'vue'
import { useMediaQuery, useStorage } from '@vueuse/core'
import type { ChapterDeskDeepSurfaceId } from '../workbench/chapterDeskSurface'
import { CHAPTER_DESK_DEEP_SURFACES, chapterDeskDeepLabel } from '../workbench/chapterDeskSurface'

const STACK_MEDIA = '(max-width: 992px)'
const STORAGE_RAIL_EXPANDED = 'aitext.chapterDesk.railExpanded'

export interface UseChapterDeskLayoutOptions {
  /** 与 CSS / Shell 保持一致 */
  stackMediaQuery?: string
}

/**
 * 章节工作台布局状态机：栈式断点、侧栏显隐、深度抽屉。
 * 不含任何业务 API；宿主负责把 drawerSurface 映射到具体子组件。
 */
export function useChapterDeskLayout(options: UseChapterDeskLayoutOptions = {}) {
  const mq = options.stackMediaQuery ?? STACK_MEDIA
  const stacked = useMediaQuery(mq)

  const railExpanded = useStorage(STORAGE_RAIL_EXPANDED, true)

  watch(
    stacked,
    (isStack) => {
      if (isStack) railExpanded.value = false
    },
    { immediate: true }
  )

  const deepDrawerOpen = ref(false)
  const deepDrawerSurface = ref<ChapterDeskDeepSurfaceId | null>(null)

  const deepDrawerTitle = computed(() =>
    deepDrawerSurface.value ? chapterDeskDeepLabel(deepDrawerSurface.value) : ''
  )

  function openDeepDrawer(surface: ChapterDeskDeepSurfaceId) {
    if (stacked.value) {
      railExpanded.value = false
    }
    deepDrawerSurface.value = surface
    deepDrawerOpen.value = true
  }

  function closeDeepDrawer() {
    deepDrawerOpen.value = false
    deepDrawerSurface.value = null
  }

  function toggleRail() {
    if (stacked.value) {
      const next = !railExpanded.value
      if (next) closeDeepDrawer()
      railExpanded.value = next
      return
    }
    railExpanded.value = !railExpanded.value
  }

  function expandRail() {
    if (stacked.value) {
      closeDeepDrawer()
    }
    railExpanded.value = true
  }

  watch(railExpanded, (v) => {
    if (v && stacked.value) {
      closeDeepDrawer()
    }
  })

  /** 回到「只写正文」：关深度抽屉；窄屏顺带收起任务侧栏 */
  function focusManuscript() {
    closeDeepDrawer()
    if (stacked.value) railExpanded.value = false
  }

  /** 流式 / 快速生成结束后：提示用户看侧栏信号 */
  function nudgeRailAfterGeneration() {
    expandRail()
  }

  return reactive({
    stacked,
    railExpanded,
    deepDrawerOpen,
    deepDrawerSurface,
    deepDrawerTitle,
    deepMeta: CHAPTER_DESK_DEEP_SURFACES,
    openDeepDrawer,
    closeDeepDrawer,
    toggleRail,
    expandRail,
    focusManuscript,
    nudgeRailAfterGeneration,
  })
}
