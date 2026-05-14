/**
 * 工作台跨组件叙事/章节同步事件。
 * 与 {@link useWorkbenchRefreshStore} 互补：Pinia tick 驱动右栏增量拉数；
 * 本事件请求 Workbench 执行完整 `loadDesk`（章节树、正文指针等与引擎一致）。
 */
export const WORKBENCH_CHAPTER_DESK_CHANGE_EVENT = 'plotpilot:workbench:chapter-desk-change' as const

/** 与 SettingsPanel 中 `n-tab-pane` 的 `name` 一致 */
export const WORKBENCH_SETTINGS_PANEL_NAMES = [
  'bible',
  'worldbuilding',
  'knowledge',
  'props',
  'story-evolution',
  'sandbox',
  'foreshadow',
] as const

export type WorkbenchSettingsPanelName = (typeof WORKBENCH_SETTINGS_PANEL_NAMES)[number]

/**
 * 从任意子面板请求切换右侧设置区 Tab（如角色锚点空状态「前往世界观」）。
 * detail: `{ panel: WorkbenchSettingsPanelName }`
 */
export const WORKBENCH_OPEN_SETTINGS_PANEL_EVENT = 'plotpilot:workbench:open-settings-panel' as const

export function isWorkbenchSettingsPanelName(v: string): v is WorkbenchSettingsPanelName {
  return (WORKBENCH_SETTINGS_PANEL_NAMES as readonly string[]).includes(v)
}
