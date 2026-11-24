import { apiClient } from './config'

export interface EvidencePassage {
  chapter_number: number
  quote: string
  start: number
  end: number
}

export interface ReviewedItem {
  id: string
  description: string
  status: 'open' | 'resolved'
  evidence_chapters?: number[]
  evidence_revisions?: Record<string, string>
  evidence_passages?: EvidencePassage[]
  evidence_current: boolean
}

interface EndingReview {
  reviewed_through_chapter: number
  terminal_revision_current: boolean
  reviewed_through_revision?: string
  core_conflict?: ReviewedItem
  character_outcomes?: ReviewedItem
  ending?: ReviewedItem
  required_promises?: ReviewedItem[]
  open_ending_notes?: string[]
}

interface NarrativeReport {
  target_chapters: number
  completed_chapters: number
  story_finished: boolean
  generation_finished: boolean
  volumes: { id: string; title: string; milestones: ReviewedItem[]; issues: string[] }[]
  ending_review?: EndingReview
}

export function getNarrativeReport(novelId: string): Promise<NarrativeReport> {
  return apiClient.get<NarrativeReport>(`/novels/${encodeURIComponent(novelId)}/structure/progress`)
}

export interface EvidenceSource {
  title: string
  content: string | null
  status: string
  manuscript_revision: string | null
}

export function getEvidenceSource(novelId: string, number: number): Promise<EvidenceSource> {
  return apiClient.get<EvidenceSource>(`/novels/${encodeURIComponent(novelId)}/chapters/${number}/evidence-source`)
}
