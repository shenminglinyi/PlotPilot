/** 右侧 Tab 栏元数据 — 单一真值源，SettingsPanel 从此处 import */

export interface TabMeta {
  name: string
  label: string
  icon: string
  /** badge 数据来源 key，由 SettingsPanel 从子面板 emit 中汇总 */
  badgeKey?: string
}

/** 写作支撑组：写作过程中高频使用 */
export const WRITING_TABS: TabMeta[] = [
  { name: 'narrative-brief', label: '叙事简报', icon: 'SparklesOutline' },
  { name: 'context',         label: '当前语境', icon: 'FlashOutline',        badgeKey: 'dueCount' },
  { name: 'foreshadow',      label: '伏笔账本', icon: 'BookmarkOutline',     badgeKey: 'pendingCount' },
  { name: 'story-evolution', label: '故事演进', icon: 'GitBranchOutline' },
]

/** 作品基础组：按需查阅的参考素材 */
export const REFERENCE_TABS: TabMeta[] = [
  { name: 'bible',         label: '作品设定', icon: 'DocumentTextOutline' },
  { name: 'worldbuilding', label: '世界观',   icon: 'EarthOutline' },
  { name: 'knowledge',     label: '知识库',   icon: 'LibraryOutline' },
  { name: 'sandbox',       label: '角色档案', icon: 'PeopleOutline' },
  { name: 'props',         label: '手稿道具', icon: 'BriefcaseOutline' },
]

export const ALL_TABS: TabMeta[] = [...WRITING_TABS, ...REFERENCE_TABS]

export const ALL_TAB_NAMES = new Set(ALL_TABS.map(t => t.name))

/** 旧版 tab name → 新 tab name（向后兼容路由参数） */
export const LEGACY_TAB_MAP: Record<string, string> = {
  storylines: 'story-evolution',
  'plot-arc': 'story-evolution',
  timeline: 'story-evolution',
  chronicles: 'story-evolution',
  checkpoint: 'story-evolution',
  'story-phase': 'story-evolution',
  'character-soul': 'sandbox',
  'voice-drift': 'sandbox',
  'foreshadow-suggestions': 'sandbox',
  'macro-refactor': 'bible',
}

export function resolveTabName(panel: string | undefined): string {
  if (!panel) return 'narrative-brief'
  if (ALL_TAB_NAMES.has(panel)) return panel
  return LEGACY_TAB_MAP[panel] ?? 'narrative-brief'
}

export type TabGroup = 'writing' | 'reference'

export function tabGroup(name: string): TabGroup {
  return WRITING_TABS.some(t => t.name === name) ? 'writing' : 'reference'
}
