import { apiClient } from './config'

const request = apiClient

// TypeScript interfaces
export interface StoryEvent {
  id: string
  summary: string
  chapter_id?: number | null
  importance: string
}

export interface Character {
  id: string
  name: string
  aliases: string[]
  role: string
  traits: string
  note: string
  story_events: StoryEvent[]
}

export interface Relationship {
  id: string
  source_id: string
  target_id: string
  label: string
  note: string
  directed: boolean
  story_events: StoryEvent[]
}

export interface CastGraph {
  version: number
  characters: Character[]
  relationships: Relationship[]
}

export interface CastSearchResult {
  characters: Character[]
  relationships: Relationship[]
}

export interface CharacterCoverage {
  id: string
  name: string
  mentioned: boolean
  chapter_ids: number[]
}

export interface BibleCharacter {
  name: string
  role: string
  in_novel_text: boolean
  chapter_ids: number[]
}

export interface QuotedText {
  text: string
  count: number
  chapter_ids: number[]
}

export interface CastCoverage {
  chapter_files_scanned: number
  characters: CharacterCoverage[]
  bible_not_in_cast: BibleCharacter[]
  quoted_not_in_cast: QuotedText[]
}

// ── cast/schedule types ──────────────────────────────────────────────────

export interface ScheduledCharacterItem {
  character_id: string
  name: string
  importance: 'major' | 'normal' | 'minor'
  is_new_suggestion: boolean
  scene_function?: string
  needs_review?: boolean
}

export interface CastScheduleRequest {
  chapter_number: number
  outline?: string
  /** 'suggest' = dry-run, 'apply' = write to chapter_elements */
  mode?: 'suggest' | 'apply'
}

export interface CastScheduleResponse {
  chapter_number: number
  cast: ScheduledCharacterItem[]
  new_character_hints: string[]
  new_character_candidates?: Array<Record<string, unknown>>
  generated_context?: string
  scheduling_log?: string[]
}

export interface CharacterNarrativeProfile {
  character_id: string
  name: string
  base_profile: Record<string, unknown>
  current_state: Record<string, unknown>
  cast_history: Array<Record<string, unknown>>
  relationship_edges: Array<Record<string, unknown>>
  knowledge_facts: Array<Record<string, unknown>>
  hidden_facts: Array<Record<string, unknown>>
  open_debts: Array<Record<string, unknown>>
  foreshadow_links: Array<Record<string, unknown>>
  causal_links: Array<Record<string, unknown>>
  recent_dialogue_samples: Array<Record<string, unknown>>
  consistency_risks: Array<Record<string, unknown>>
}

export const castApi = {
  /**
   * Get cast graph for a novel
   */
  getCast: (novelId: string) =>
    request.get(`/novels/${novelId}/cast`) as Promise<CastGraph>,

  /**
   * @deprecated Cast graph is a read model generated from knowledge triples.
   * Do not use as a write model.
   */
  putCast: (novelId: string, data: CastGraph) =>
    request.put(`/novels/${novelId}/cast`, data) as Promise<CastGraph>,

  /**
   * Search characters and relationships
   */
  searchCast: (novelId: string, query: string) =>
    request.get(`/novels/${novelId}/cast/search`, {
      params: { q: query }
    }) as Promise<CastSearchResult>,

  /**
   * Get cast coverage analysis
   */
  getCastCoverage: (novelId: string) =>
    request.get(`/novels/${novelId}/cast/coverage`) as Promise<CastCoverage>,

  /**
   * Schedule cast for a chapter.
   * mode='suggest': returns AI suggestions without writing to DB
   * mode='apply':   same + writes to chapter_elements (INSERT OR IGNORE)
   */
  scheduleAndPersist: (novelId: string, payload: CastScheduleRequest) =>
    request.post(`/novels/${novelId}/cast/schedule`, payload) as Promise<CastScheduleResponse>,

  /**
   * Dry-run: analyse outline and return suggested cast without any DB writes.
   */
  analyzeOutline: (novelId: string, chapterNumber: number, outline: string) =>
    castApi.scheduleAndPersist(novelId, {
      chapter_number: chapterNumber,
      outline,
      mode: 'suggest',
    }),

  getCharacterNarrativeProfile: (novelId: string, characterId: string) =>
    request.get(
      `/novels/${novelId}/characters/${characterId}/narrative-profile`,
    ) as Promise<CharacterNarrativeProfile>,
}
