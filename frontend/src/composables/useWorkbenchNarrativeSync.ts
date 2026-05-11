/**
 * 剧情工作台与全站「章节落库 / 编年史」信号同源。
 * @see useWorkbenchRefreshStore — Workbench.handleChapterUpdated、Autopilot 等 bump。
 */
import { watch, type WatchStopHandle } from 'vue'
import { storeToRefs } from 'pinia'
import { useWorkbenchRefreshStore } from '@/stores/workbenchRefreshStore'

export function useWorkbenchDeskTickReload(run: () => void): WatchStopHandle {
  const store = useWorkbenchRefreshStore()
  const { deskTick } = storeToRefs(store)
  return watch(deskTick, () => run())
}

export function useWorkbenchChroniclesTickReload(run: () => void): WatchStopHandle {
  const store = useWorkbenchRefreshStore()
  const { chroniclesTick } = storeToRefs(store)
  return watch(chroniclesTick, () => run())
}

/** 故事演进时间轴：章节与 Bible 纪事均可能变化 */
export function useWorkbenchPlotTimelineReload(run: () => void) {
  useWorkbenchDeskTickReload(run)
  useWorkbenchChroniclesTickReload(run)
}
