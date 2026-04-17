/**
 * Frontend API Type Definitions — 统一出口
 *
 * 各领域类型已拆分到独立模块：
 *   - common.ts   通用响应、Job、日志
 *   - novel.ts    小说 / Book
 *   - chapter.ts  章节
 *   - bible.ts    世界观设定
 *   - cast.ts     角色关系
 *   - knowledge.ts 知识图谱
 *   - stats.ts    统计
 *
 * 此文件保持向后兼容，统一 re-export 所有类型。
 * 新代码请直接从对应子模块导入（tree-shaking 更友好）。
 */

export * from './common'
export * from './novel'
export * from './chapter'
export * from './bible'
export * from './cast'
export * from './knowledge'
export * from './stats'

// ── 组合响应类型（跨模块） ─────────────────────────────────────

import type { SuccessResponse } from './common'

export interface ErrorResponse {
  success: false;
  message: string;
  code: string;
  details?: unknown;
}

export type ApiResponse<T> = SuccessResponse<T> | ErrorResponse;

export interface PaginatedResponse<T> {
  success: true;
  data: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  message?: string;
}

// ============================================================================
// Statistics Types (from stats_models.py)
// ============================================================================

export interface GlobalStats {
  total_books: number;
  total_chapters: number;
  total_words: number;
  total_characters: number;
  books_by_stage: Record<string, number>;
}

export interface BookStats {
  slug: string;
  title: string;
  total_chapters: number;
  completed_chapters: number;
  total_words: number;
  avg_chapter_words: number;
  completion_rate: number;
  last_updated: string;
  generation_quality?: {
    total_measured: number;
    within_tolerance_count: number;
    pass_rate: number | null;
    expansion_trigger_count: number;
    trim_trigger_count: number;
    expansion_trigger_rate: number | null;
    trim_trigger_rate: number | null;
    avg_expansion_attempts: number;
  } | null;
}

export interface ChapterStats {
  chapter_id: number;
  title: string;
  word_count: number;
  character_count: number;
  paragraph_count: number;
  has_content: boolean;
}

export interface WritingProgress {
  date: string;
  words_written: number;
  chapters_completed: number;
}

export interface ContentAnalysis {
  character_mentions: Record<string, number>;
  dialogue_ratio: number;
  scene_count: number;
  avg_paragraph_length: number;
}

// ============================================================================
// Book Types (from models.py and desk.py)
// ============================================================================

export type Stage = 'init' | 'planned' | 'writing' | 'completed';

export interface BookListItem {
  slug: string;
  title: string;
  genre: string;
  stage: Stage;
  stage_label: string;
}

export interface BookDesk {
  title: string;
  slug: string;
  genre: string;
  stage_label: string;
  has_bible: boolean;
  has_outline: boolean;
}

export interface NovelManifest {
  novel_id: string;
  slug: string;
  title: string;
  premise: string;
  genre: string;
  target_chapter_count: number;
  target_words_per_chapter: number;
  current_stage: Stage;
  completed_chapters: number[];
  style_hint: string;
}

export interface OutlineChapter {
  id: number;
  title: string;
  one_liner: string;
}

export interface Outline {
  chapters: OutlineChapter[];
}

export interface BibleCharacter {
  name: string;
  role: string;
  traits: string;
  arc_note: string;
}

export interface BibleLocation {
  name: string;
  description: string;
}

export interface Bible {
  characters: BibleCharacter[];
  locations: BibleLocation[];
  timeline_notes: string[];
  style_notes: string;
}

// ============================================================================
// Character & Relationship Types (from models.py)
// ============================================================================

export interface CastStoryEvent {
  id: string;
  summary: string;
  chapter_id?: number;
  importance: string;
}

export interface Character {
  id: string;
  name: string;
  aliases: string[];
  role: string;
  traits: string;
  note: string;
  story_events: CastStoryEvent[];
}

export interface Relationship {
  id: string;
  source_id: string;
  target_id: string;
  label: string;
  note: string;
  directed: boolean;
  story_events: CastStoryEvent[];
}

export interface CastGraph {
  version: number;
  characters: Character[];
  relationships: Relationship[];
}

export interface CastCoverage {
  [key: string]: unknown;
}

// ============================================================================
// Chapter Types (from models.py and desk.py)
// ============================================================================

export interface ChapterBody {
  content: string;
  filename?: string;
}

export type ReviewStatus = 'pending' | 'ok' | 'revise';

export interface ChapterReview {
  status: ReviewStatus;
  memo: string;
}

export interface ChapterListItem {
  id: number;
  title: string;
  one_liner: string;
  has_file: boolean;
  filename: string;
  review_status: ReviewStatus;
  memo_preview: string;
}

export interface ChapterFolderRelations {
  follows?: number;
  parallels: number[];
  notes: string;
}

export interface ChapterFolderMeta {
  version: number;
  chapter_id: number;
  title: string;
  use_parts: boolean;
  parts_order: string[];
  relations: ChapterFolderRelations;
}

export interface ChapterStructure {
  chapter_id: number;
  storage_dir?: string;
  meta?: ChapterFolderMeta;
  has_content: boolean;
  composite_char_len: number;
}

export interface ChapterBeatScene {
  summary: string;
  setting?: string;
}

export interface ChapterBeats {
  chapter_id: number;
  chapter_title: string;
  pov: string;
  scenes: ChapterBeatScene[];
  must_resolve: string;
  foreshadow_refs: string[];
}

export interface ChapterNarrativeEntry {
  chapter_id: number;
  summary: string;
  key_events: string;
  open_threads: string;
  consistency_note: string;
  ending_state: string;
  ending_emotion: string;
  carry_over_question: string;
  next_opening_hint: string;
  beat_sections: string[];
  sync_status: string;
}

// ============================================================================
// Knowledge Graph Types (from models.py)
// ============================================================================

export interface KnowledgeTriple {
  id: string;
  subject: string;
  predicate: string;
  object: string;
  chapter_id?: number;
  note: string;
}

export interface StoryKnowledge {
  version: number;
  premise_lock: string;
  chapters: ChapterNarrativeEntry[];
  facts: KnowledgeTriple[];
}

export interface KnowledgeSearchHit {
  [key: string]: unknown;
}

export interface KnowledgeSearchResponse {
  ok: boolean;
  query: string;
  hits: KnowledgeSearchHit[];
}

// ============================================================================
// Job Types (from jobs.py)
// ============================================================================

export type JobKind = 'plan' | 'write' | 'run';

export type JobStatus = 'queued' | 'running' | 'done' | 'error' | 'cancelled';

export interface JobCreateResponse {
  ok: boolean;
  job_id: string;
}

export interface JobStatusResponse {
  job_id: string;
  kind: JobKind;
  slug: string;
  status: JobStatus;
  phase: string;
  message: string;
  error?: string;
  started?: string;
  finished?: string;
  done: boolean;
  ok: boolean;
}

// ============================================================================
// Request Payload Types
// ============================================================================

export interface CreateBookPayload {
  title: string;
  premise: string;
  slug?: string;
  genre?: string;
  chapters?: number;
  words?: number;
  style?: string;
}

export interface SaveBodyPayload {
  content: string;
}

export interface ReviewPayload {
  status: ReviewStatus;
  memo: string;
}

export interface ChapterReviewAiPayload {
  save: boolean;
}

export interface PlanJobPayload {
  dry_run?: boolean;
  mode?: 'initial' | 'revise';
}

export interface WriteJobPayload {
  from_chapter: number;
  to_chapter?: number;
  dry_run?: boolean;
  continuity?: boolean;
}

export interface RunJobPayload {
  dry_run?: boolean;
  continuity?: boolean;
}

export interface ChatPayload {
  message: string;
  regenerate_digest?: boolean;
  use_cast_tools?: boolean;
  history_mode?: 'full' | 'fresh';
  clear_thread?: boolean;
}

export interface ChatClearPayload {
  digest_too?: boolean;
}

export interface AppendEventPayload {
  role: 'system' | 'assistant';
  content: string;
  meta?: Record<string, unknown>;
}

export interface DigestPayload {
  force?: boolean;
}

// ============================================================================
// Composite Response Types
// ============================================================================

export interface BookDeskResponse {
  book: BookDesk | null
  chapters: ChapterListItem[]
}
