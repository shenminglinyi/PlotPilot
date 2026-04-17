/**
 * 知识图谱 / Knowledge Graph 相关类型
 */

import type { ChapterNarrativeEntry } from './chapter'

export interface KnowledgeTriple {
  id: string
  subject: string
  predicate: string
  object: string
  chapter_id?: number
  note: string
}

export interface StoryKnowledge {
  version: number
  premise_lock: string
  chapters: ChapterNarrativeEntry[]
  facts: KnowledgeTriple[]
}

export interface KnowledgeSearchHit {
  [key: string]: unknown
}

export interface KnowledgeSearchResponse {
  ok: boolean
  query: string
  hits: KnowledgeSearchHit[]
}
