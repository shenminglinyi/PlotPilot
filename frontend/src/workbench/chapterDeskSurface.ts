/**
 * 章节工作台「表面」注册表：与具体 Vue 组件解耦，仅描述可挂载区域与元数据。
 * 新增一章内工具页时：在此扩展 id + 文案，再在宿主（如 WorkArea）挂载对应组件。
 */

export const CHAPTER_DESK_PRIMARY_ID = 'manuscript' as const

/** 常驻侧栏（任务单 + 状态）：与正文同屏，宽屏为 aside，窄屏为抽屉 */
export const CHAPTER_DESK_RAIL_ZONE = 'rail_context' as const

/**
 * 主栏 Tab：与「章节编辑」同列切换（元素 / 护栏 / 溯源）。
 */
export type ChapterDeskDeepSurfaceId = 'elements' | 'guardrail' | 'trace'

/** 主工作区当前 Tab：正文或某一深度面板 */
export type PrimaryChapterDeskTab = 'manuscript' | ChapterDeskDeepSurfaceId

export interface ChapterDeskSurfaceMeta {
  id: string
  /** Tab / 菜单标题 */
  label: string
  /** 窄顶栏、折叠轨上的短标签 */
  shortLabel: string
}

export const CHAPTER_DESK_DEEP_SURFACES: Record<ChapterDeskDeepSurfaceId, ChapterDeskSurfaceMeta> = {
  elements: { id: 'elements', label: '章节元素', shortLabel: '元素' },
  guardrail: { id: 'guardrail', label: '质量护栏', shortLabel: '护栏' },
  trace: { id: 'trace', label: '引擎溯源', shortLabel: '溯源' },
}

export const CHAPTER_DESK_DEEP_ORDER: ChapterDeskDeepSurfaceId[] = ['elements', 'guardrail', 'trace']

export function chapterDeskDeepLabel(id: ChapterDeskDeepSurfaceId): string {
  return CHAPTER_DESK_DEEP_SURFACES[id].label
}

export function isChapterDeskDeepSurface(id: string | null | undefined): id is ChapterDeskDeepSurfaceId {
  return id != null && id in CHAPTER_DESK_DEEP_SURFACES
}
