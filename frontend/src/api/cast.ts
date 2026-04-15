import axios from 'axios'

const request = axios.create({
  baseURL: '/',
  timeout: 30000,
})

request.interceptors.response.use(response => response.data)

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

export const castApi = {
  /**
   * Get cast graph for a novel
   */
  getCast: (novelId: string) =>
    request.get(`/api/v1/novels/${novelId}/cast`) as unknown as Promise<CastGraph>,

  /**
   * Update cast graph for a novel
   */
  putCast: (novelId: string, data: CastGraph) =>
    request.put(`/api/v1/novels/${novelId}/cast`, data) as unknown as Promise<CastGraph>,

  /**
   * Search characters and relationships
   */
  searchCast: (novelId: string, query: string) =>
    request.get(`/api/v1/novels/${novelId}/cast/search`, {
      params: { q: query }
    }) as unknown as Promise<CastSearchResult>,

  /**
   * Get cast coverage analysis
   */
  getCastCoverage: (novelId: string) =>
    request.get(`/api/v1/novels/${novelId}/cast/coverage`) as unknown as Promise<CastCoverage>,
}
