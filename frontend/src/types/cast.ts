/**
 * 角色 / Cast 相关类型
 */

export interface CastStoryEvent {
  id: string
  summary: string
  chapter_id?: number
  importance: string
}

export interface Character {
  id: string
  name: string
  aliases: string[]
  role: string
  traits: string
  note: string
  story_events: CastStoryEvent[]
}

export interface Relationship {
  id: string
  source_id: string
  target_id: string
  label: string
  note: string
  directed: boolean
  story_events: CastStoryEvent[]
}

export interface CastGraph {
  version: number
  characters: Character[]
  relationships: Relationship[]
}

export interface CastCoverage {
  [key: string]: unknown
}

export interface CastSearchResponse {
  characters: Character[]
  relationships: Relationship[]
}
