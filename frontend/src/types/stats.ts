/**
 * 统计 / Statistics 相关类型
 */

export interface GlobalStats {
  total_books: number
  total_chapters: number
  total_words: number
  total_characters: number
  books_by_stage: Record<string, number>
}

export interface BookStats {
  slug: string
  title: string
  total_chapters: number
  completed_chapters: number
  total_words: number
  avg_chapter_words: number
  completion_rate: number
  last_updated: string
  generation_quality?: {
    total_measured: number
    within_tolerance_count: number
    pass_rate: number | null
    expansion_trigger_count: number
    trim_trigger_count: number
    expansion_trigger_rate: number | null
    trim_trigger_rate: number | null
    avg_expansion_attempts: number
  } | null
}

export interface ChapterStats {
  chapter_id: number
  title: string
  word_count: number
  character_count: number
  paragraph_count: number
  has_content: boolean
}

export interface WritingProgress {
  date: string
  words_written: number
  chapters_completed: number
}

export interface ContentAnalysis {
  character_mentions: Record<string, number>
  dialogue_ratio: number
  scene_count: number
  avg_paragraph_length: number
}
