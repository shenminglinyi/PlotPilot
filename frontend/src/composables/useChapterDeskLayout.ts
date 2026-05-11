import { reactive, watch } from 'vue'
import { useMediaQuery, useStorage } from '@vueuse/core'

const STACK_MEDIA = '(max-width: 992px)'
const STORAGE_RAIL_EXPANDED = 'aitext.chapterDesk.railExpanded'

export interface UseChapterDeskLayoutOptions {
  /** 与 CSS / Shell 保持一致 */
  stackMediaQuery?: string
}

/**
 * 章节工作台布局状态机：栈式断点、任务侧栏显隐。
 * 主栏 Tab（正文 / 元素 / 护栏 / 溯源）由宿主自行管理，保持本层与业务解耦。
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

  function toggleRail() {
    railExpanded.value = !railExpanded.value
  }

  function expandRail() {
    railExpanded.value = true
  }

  /** 回到正文优先：窄屏顺带收起任务侧栏（主栏 Tab 由宿主切到「章节编辑」） */
  function focusManuscript() {
    if (stacked.value) railExpanded.value = false
  }

  /** 流式 / 快速生成结束后：展开侧栏便于看质检 */
  function nudgeRailAfterGeneration() {
    expandRail()
  }

  return reactive({
    stacked,
    railExpanded,
    toggleRail,
    expandRail,
    focusManuscript,
    nudgeRailAfterGeneration,
  })
}
