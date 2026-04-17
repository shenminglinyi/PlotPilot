/**
 * 章节 / Chapter 相关类型
 */

export type ReviewStatus = 'pending' | 'ok' | 'revise'

export interface ChapterBody {
  content: string
  filename?: string
}

export interface ChapterReview {
  status: ReviewStatus
  memo: string
}

export interface ChapterListItem {
  id: number
  title: string
  one_liner: string
  has_file: boolean
  filename: string
  review_status: ReviewStatus
  memo_preview: string
}

export interface ChapterFolderRelations {
  follows?: number
  parallels: number[]
  notes: string
}

export interface ChapterFolderMeta {
  version: number
  chapter_id: number
  title: string
  use_parts: boolean
  parts_order: string[]
  relations: ChapterFolderRelations
}

export interface ChapterStructure {
  chapter_id: number
  storage_dir?: string
  meta?: ChapterFolderMeta
  has_content: boolean
  composite_char_len: number
}

export interface ChapterBeatScene {
  summary: string
  setting?: string
}

export interface ChapterBeats {
  chapter_id: number
  chapter_title: string
  pov: string
  scenes: ChapterBeatScene[]
  must_resolve: string
  foreshadow_refs: string[]
}

export interface ChapterNarrativeEntry {
  chapter_id: number
  summary: string
  key_events: string
  open_threads: string
  consistency_note: string
  beat_sections: string[]
  sync_status: string
}

// ── 请求体 ────────────────────────────────────────────────────

export interface SaveBodyPayload {
  content: string
}

export interface ReviewPayload {
  status: ReviewStatus
  memo: string
}

export interface ChapterReviewAiPayload {
  save: boolean
}

export interface ChapterReviewAiResponse {
  ok: boolean
  status: ReviewStatus
  memo: string
  saved: boolean
}

export interface PlanJobPayload {
  dry_run?: boolean
  mode?: 'initial' | 'revise'
}

export interface WriteJobPayload {
  from_chapter: number
  to_chapter?: number
  dry_run?: boolean
  continuity?: boolean
}

export interface RunJobPayload {
  dry_run?: boolean
  continuity?: boolean
}

export interface ChatPayload {
  message: string
  regenerate_digest?: boolean
  use_cast_tools?: boolean
  history_mode?: 'full' | 'fresh'
  clear_thread?: boolean
}

export interface ChatClearPayload {
  digest_too?: boolean
}

export interface AppendEventPayload {
  role: 'system' | 'assistant'
  content: string
  meta?: Record<string, unknown>
}

export interface DigestPayload {
  force?: boolean
}
