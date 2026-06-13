import { apiClient } from './config'
import { runtimePerformance } from '@/config/performance'

const kgRequestConfig = { timeout: runtimePerformance.network.mediumTaskTimeoutMs }

export interface InferenceProvenanceRow {
  id: string
  chapter_element_id: string | null
  rule_id: string
  role: string
}

export interface InferenceFactPayload {
  id: string
  subject: string
  predicate: string
  object: string
  chapter_number: number | null
  confidence: number | null
  source_type: string | null
}

export interface InferenceFactBundle {
  fact: InferenceFactPayload
  provenance: InferenceProvenanceRow[]
}

export interface ChapterInferenceEvidenceData {
  story_node_id: string | null
  chapter_number: number
  facts: InferenceFactBundle[]
  hint?: string
}

// ── 三元组 DTO ──────────────────────────────────────────────

export interface TripleDTO {
  id: string
  subject: string
  subject_type: string
  predicate: string
  object: string
  object_type: string
  confidence: number
  source_type: string
  chapter_number: number | null
  is_starred?: boolean
}

export interface KGStatistics {
  total_triples: number
  source_distribution: Record<string, number>
  confidence_distribution: { high: number; medium: number; low: number }
  predicate_distribution: Record<string, number>
}

export const knowledgeGraphApi = {
  // ── 本章推断证据（已有）──────────────────────────────────

  getChapterInferenceEvidence(
    novelId: string,
    chapterNumber: number
  ): Promise<{ success: boolean; data: ChapterInferenceEvidenceData }> {
    return apiClient.get(
      `/knowledge-graph/novels/${encodeURIComponent(novelId)}/chapters/by-number/${chapterNumber}/inference-evidence`,
      kgRequestConfig,
    ) as Promise<{ success: boolean; data: ChapterInferenceEvidenceData }>
  },

  revokeChapterInference(
    novelId: string,
    chapterNumber: number
  ): Promise<{ success: boolean; data: { removed_provenance_triples: number; deleted_inferred_facts: number } }> {
    return apiClient.delete(
      `/knowledge-graph/novels/${encodeURIComponent(novelId)}/chapters/by-number/${chapterNumber}/inference`,
      kgRequestConfig,
    ) as Promise<{ success: boolean; data: { removed_provenance_triples: number; deleted_inferred_facts: number } }>
  },

  revokeInferredTriple(
    novelId: string,
    tripleId: string
  ): Promise<{ success: boolean; message: string }> {
    return apiClient.delete(
      `/knowledge-graph/novels/${encodeURIComponent(novelId)}/inferred-triples/${encodeURIComponent(tripleId)}`,
      kgRequestConfig,
    ) as Promise<{ success: boolean; message: string }>
  },

  // ── 新增：全书推断 ──────────────────────────────────────

  /** POST /api/v1/knowledge-graph/novels/{id}/infer */
  inferNovel(novelId: string): Promise<{ success: boolean; data: Record<string, unknown> }> {
    return apiClient.post(
      `/knowledge-graph/novels/${encodeURIComponent(novelId)}/infer`,
      {},
      kgRequestConfig,
    ) as Promise<{ success: boolean; data: Record<string, unknown> }>
  },

  // ── 三元组查询 ──────────────────────────────────────────

  /** GET /api/v1/knowledge-graph/novels/{id}/triples */
  getTriples(
    novelId: string,
    sourceType?: string,
    minConfidence = 0
  ): Promise<{ success: boolean; data: { total: number; triples: TripleDTO[] } }> {
    return apiClient.get(
      `/knowledge-graph/novels/${encodeURIComponent(novelId)}/triples`,
      {
        ...kgRequestConfig,
        params: { ...(sourceType ? { source_type: sourceType } : {}), min_confidence: minConfidence },
      },
    ) as Promise<{ success: boolean; data: { total: number; triples: TripleDTO[] } }>
  },

  /** POST /api/v1/knowledge-graph/triples/{id}/confirm */
  confirmTriple(tripleId: string): Promise<{ success: boolean; data: TripleDTO }> {
    return apiClient.post(
      `/knowledge-graph/triples/${encodeURIComponent(tripleId)}/confirm`,
      {},
      kgRequestConfig,
    ) as Promise<{ success: boolean; data: TripleDTO }>
  },

  /** PATCH /api/v1/knowledge-graph/novels/{id}/triples/{tripleId}/star */
  starTriple(novelId: string, tripleId: string, starred: boolean): Promise<{ success: boolean; triple_id: string; starred: boolean }> {
    return apiClient.patch(
      `/knowledge-graph/novels/${encodeURIComponent(novelId)}/triples/${encodeURIComponent(tripleId)}/star`,
      { starred },
      kgRequestConfig,
    ) as Promise<{ success: boolean; triple_id: string; starred: boolean }>
  },

  /** DELETE /api/v1/knowledge-graph/triples/{id} */
  deleteTriple(tripleId: string): Promise<{ success: boolean; message: string }> {
    return apiClient.delete(
      `/knowledge-graph/triples/${encodeURIComponent(tripleId)}`,
      kgRequestConfig,
    ) as Promise<{ success: boolean; message: string }>
  },

  // ── 统计 ────────────────────────────────────────────────

  /** GET /api/v1/knowledge-graph/novels/{id}/statistics */
  getStatistics(novelId: string): Promise<{ success: boolean; data: KGStatistics }> {
    return apiClient.get(
      `/knowledge-graph/novels/${encodeURIComponent(novelId)}/statistics`,
      kgRequestConfig,
    ) as Promise<{ success: boolean; data: KGStatistics }>
  },
}
