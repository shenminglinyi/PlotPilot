/**
 * 工作台跨组件叙事/章节同步事件。
 * 与 {@link useWorkbenchRefreshStore} 互补：Pinia tick 驱动右栏增量拉数；
 * 本事件请求 Workbench 执行完整 `loadDesk`（章节树、正文指针等与引擎一致）。
 */
export const WORKBENCH_CHAPTER_DESK_CHANGE_EVENT = 'aitext:workbench:chapter-desk-change' as const
