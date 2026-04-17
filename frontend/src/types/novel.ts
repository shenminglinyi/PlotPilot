/**
 * 小说 / Book 相关类型
 */

export type Stage = 'init' | 'planned' | 'writing' | 'completed'

export interface BookListItem {
  slug: string
  title: string
  genre: string
  stage: Stage
  stage_label: string
}

export interface BookDesk {
  title: string
  slug: string
  genre: string
  stage_label: string
  has_bible: boolean
  has_outline: boolean
}

export interface NovelManifest {
  novel_id: string
  slug: string
  title: string
  premise: string
  genre: string
  target_chapter_count: number
  target_words_per_chapter: number
  current_stage: Stage
  completed_chapters: number[]
  style_hint: string
}

export interface OutlineChapter {
  id: number
  title: string
  one_liner: string
}

export interface Outline {
  chapters: OutlineChapter[]
}

// ── 请求体 ────────────────────────────────────────────────────

export interface CreateBookPayload {
  title: string
  premise: string
  slug?: string
  genre?: string
  chapters?: number
  words?: number
  style?: string
}
