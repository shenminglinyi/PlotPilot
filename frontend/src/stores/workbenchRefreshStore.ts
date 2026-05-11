import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * 工作台右栏「软刷新」信号：不整页 remount，仅驱动各面板重新拉数。
 * 在 loadDesk 成功后由 Workbench 触发（全托管完章、保存、规划确认等同源）。
 * 另见 `frontend/src/workbench/deskEvents.ts`：快照回滚等通过浏览器事件请求整桌 loadDesk。
 */
export const useWorkbenchRefreshStore = defineStore('workbenchRefresh', () => {
  const foreshadowTick = ref(0)
  const chroniclesTick = ref(0)
  /** 通用：知识库、故事线·弧光、片场、宏观提示等统一监听 */
  const deskTick = ref(0)

  function bumpForeshadowLedger() {
    foreshadowTick.value += 1
  }

  function bumpChronicles() {
    chroniclesTick.value += 1
  }

  function bumpDesk() {
    deskTick.value += 1
  }

  /** 章节落库或结构变化后：伏笔、编年史、知识库、故事线等同源刷新 */
  function bumpAfterChapterDeskChange() {
    bumpForeshadowLedger()
    bumpChronicles()
    bumpDesk()
  }

  return {
    foreshadowTick,
    chroniclesTick,
    deskTick,
    bumpForeshadowLedger,
    bumpChronicles,
    bumpDesk,
    bumpAfterChapterDeskChange,
  }
})
