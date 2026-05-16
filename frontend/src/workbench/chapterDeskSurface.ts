/**
 * 章节工作台「表面」注册表：与具体 Vue 组件解耦。
 * 质量护栏 / 引擎溯源：保存后自动运行并落库，不作为一级 Tab（见章后管线与 traces API）。
 */

export const CHAPTER_DESK_PRIMARY_ID = 'manuscript' as const

/** 常驻侧栏（任务单 + 状态）：与正文同屏，宽屏为 aside，窄屏为抽屉 */
export const CHAPTER_DESK_RAIL_ZONE = 'rail_context' as const

/** 主栏可选工具页（仅保留需手点编辑的「章节元素」） */
export type ChapterDeskAuxPaneId = 'elements'

/** 主工作区当前 Tab */
export type PrimaryChapterDeskTab = 'manuscript' | ChapterDeskAuxPaneId

export interface ChapterDeskSurfaceMeta {
  id: string
  label: string
  shortLabel: string
}

export const CHAPTER_DESK_AUX_SURFACES: Record<ChapterDeskAuxPaneId, ChapterDeskSurfaceMeta> = {
  elements: { id: 'elements', label: '章节元素', shortLabel: '元素' },
}

export const CHAPTER_DESK_AUX_ORDER: ChapterDeskAuxPaneId[] = ['elements']

export function chapterDeskAuxLabel(id: ChapterDeskAuxPaneId): string {
  return CHAPTER_DESK_AUX_SURFACES[id].label
}

export function isChapterDeskAuxPane(id: string | null | undefined): id is ChapterDeskAuxPaneId {
  return id != null && id in CHAPTER_DESK_AUX_SURFACES
}
