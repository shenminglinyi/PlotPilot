/**
 * 引擎内核 API — Checkpoint / QualityGuardrail / StoryPhase / CharacterPsyche
 *
 * 与后端 interfaces/api/v1/engine/checkpoint_routes.py 一一对应。
 */
import { apiClient } from './config'

// ─── Checkpoint ────────────────────────────────────────────────

export interface CheckpointDTO {
  id: string
  story_id: string
  trigger_type: string
  trigger_reason: string
  parent_id: string | null
  chapter_number: number | null
  created_at: string
  is_head: boolean
}

export interface CheckpointListResponse {
  checkpoints: CheckpointDTO[]
  head_id: string | null
}

export interface CreateCheckpointRequest {
  reason?: string
  chapter_number?: number | null
}

export interface CreateCheckpointResponse {
  checkpoint_id: string
  message: string
}

export interface RollbackResponse {
  checkpoint_id: string
  trigger_reason: string
  message: string
}

export interface BranchDTO {
  branch_point_id: string
  reason: string
  children: Array<{ id: string; reason: string }>
}

export interface BranchesResponse {
  branches: BranchDTO[]
}

export interface HeadStateResponse {
  head_id: string | null
  state: {
    trigger_type: string
    trigger_reason: string
    story_state: Record<string, unknown>
    active_foreshadows: string[]
  } | null
}

export const checkpointApi = {
  /** GET /novels/{novel_id}/checkpoints */
  list: (novelId: string, limit = 50) =>
    apiClient.get<CheckpointListResponse>(
      `/novels/${novelId}/checkpoints`,
      { params: { limit } },
    ) as unknown as Promise<CheckpointListResponse>,

  /** POST /novels/{novel_id}/checkpoints */
  create: (novelId: string, body: CreateCheckpointRequest = {}) =>
    apiClient.post<CreateCheckpointResponse>(
      `/novels/${novelId}/checkpoints`,
      body,
    ) as unknown as Promise<CreateCheckpointResponse>,

  /** POST /novels/{novel_id}/checkpoints/{id}/rollback */
  rollback: (novelId: string, checkpointId: string) =>
    apiClient.post<RollbackResponse>(
      `/novels/${novelId}/checkpoints/${checkpointId}/rollback`,
      {},
    ) as unknown as Promise<RollbackResponse>,

  /** GET /novels/{novel_id}/checkpoints/branches */
  listBranches: (novelId: string) =>
    apiClient.get<BranchesResponse>(
      `/novels/${novelId}/checkpoints/branches`,
    ) as unknown as Promise<BranchesResponse>,

  /** GET /novels/{novel_id}/checkpoints/head */
  getHead: (novelId: string) =>
    apiClient.get<HeadStateResponse>(
      `/novels/${novelId}/checkpoints/head`,
    ) as unknown as Promise<HeadStateResponse>,
}

// ─── QualityGuardrail ──────────────────────────────────────────

export interface GuardrailCheckRequest {
  text: string
  character_names?: string[]
  chapter_goal?: string
  era?: string
  scene_type?: string
  mode?: 'advise' | 'enforce'
}

export interface GuardrailDimensionScore {
  name: string
  key: string
  score: number
  weight: number
}

export interface GuardrailViolationDTO {
  dimension: string
  type: string
  severity: string
  description: string
  original: string
  suggestion: string
  character: string
}

export interface GuardrailCheckResponse {
  overall_score: number
  passed: boolean
  dimensions: GuardrailDimensionScore[]
  violations: GuardrailViolationDTO[]
}

export const guardrailApi = {
  /** POST /novels/{novel_id}/guardrail/check (advise/enforce both via body.mode) */
  check: (novelId: string, body: GuardrailCheckRequest) =>
    apiClient.post<GuardrailCheckResponse>(
      `/novels/${novelId}/guardrail/check`,
      body,
    ) as unknown as Promise<GuardrailCheckResponse>,

  /** POST /novels/{novel_id}/guardrail/check with enforce mode */
  enforce: (novelId: string, body: Omit<GuardrailCheckRequest, 'mode'>) =>
    apiClient.post<GuardrailCheckResponse>(
      `/novels/${novelId}/guardrail/check`,
      { ...body, mode: 'enforce' },
    ) as unknown as Promise<GuardrailCheckResponse>,
}

// ─── StoryPhase ────────────────────────────────────────────────

export interface StoryPhaseDTO {
  phase: string
  progress: number
  description: string
  can_advance: boolean
}

export const storyPhaseApi = {
  /** GET /novels/{novel_id}/story-phase */
  get: (novelId: string) =>
    apiClient.get<StoryPhaseDTO>(
      `/novels/${novelId}/story-phase`,
    ) as unknown as Promise<StoryPhaseDTO>,

  /** PUT /novels/{novel_id}/story-phase */
  update: (novelId: string, body: StoryPhaseDTO) =>
    apiClient.put<StoryPhaseDTO>(
      `/novels/${novelId}/story-phase`,
      body,
    ) as unknown as Promise<StoryPhaseDTO>,
}

// ─── CharacterPsyche（原 CharacterSoul）───────────────────────

export interface CharacterPsycheDTO {
  name: string
  role: string
  core_belief: string
  taboo: string
  voice_tag: string
  wound: string
  trauma_count: number
}

export interface CharacterPsycheDetailDTO extends CharacterPsycheDTO {
  emotion_ledger: Record<string, unknown>
  mask_summary: string
}

export interface ValidateBehaviorRequest {
  action: string
}

export interface ValidateBehaviorResponse {
  valid: boolean
  warnings: string[]
  suggestions: string[]
}

export const characterPsycheApi = {
  /** GET /novels/{novel_id}/character-psyches */
  list: (novelId: string) =>
    apiClient.get<{ characters: CharacterPsycheDTO[] }>(
      `/novels/${novelId}/character-psyches`,
    ) as unknown as Promise<{ characters: CharacterPsycheDTO[] }>,

  /** GET /novels/{novel_id}/character-psyches/{name} */
  get: (novelId: string, name: string) =>
    apiClient.get<CharacterPsycheDetailDTO>(
      `/novels/${novelId}/character-psyches/${encodeURIComponent(name)}`,
    ) as unknown as Promise<CharacterPsycheDetailDTO>,

  /** POST /novels/{novel_id}/character-psyches/{name}/validate */
  validate: (novelId: string, name: string, body: ValidateBehaviorRequest) =>
    apiClient.post<ValidateBehaviorResponse>(
      `/novels/${novelId}/character-psyches/${encodeURIComponent(name)}/validate`,
      body,
    ) as unknown as Promise<ValidateBehaviorResponse>,
}

// ─── 向后兼容别名（v3.x 保留，v4.0 移除）──────────────────────
/** @deprecated Use CharacterPsycheDTO instead */
export type CharacterSoulDTO = CharacterPsycheDTO
/** @deprecated Use CharacterPsycheDetailDTO instead */
export type CharacterSoulDetailDTO = CharacterPsycheDetailDTO
/** @deprecated Use characterPsycheApi instead */
export const characterSoulApi = characterPsycheApi

// ─── Trace (溯源) ──────────────────────────────────────────────────

export interface TraceDTO {
  trace_id: string
  node_type: string
  operation: string
  input_summary: string
  output_summary: string
  score: number | null
  violations: string[]
  duration_ms: number
  timestamp: string
}

export interface TraceListResponse {
  traces: TraceDTO[]
  total: number
}

export interface TraceStatsDTO {
  total_traces: number
  by_node_type: Record<string, number>
  by_operation: Record<string, number>
  avg_score: number | null
  avg_duration_ms: number
}

export const traceApi = {
  /** GET /novels/{novel_id}/traces */
  list: (novelId: string, params?: { node_type?: string; operation?: string; limit?: number }) =>
    apiClient.get<TraceListResponse>(
      `/novels/${novelId}/traces`,
      { params },
    ) as unknown as Promise<TraceListResponse>,

  /** GET /novels/{novel_id}/traces/stats */
  stats: (novelId: string) =>
    apiClient.get<TraceStatsDTO>(
      `/novels/${novelId}/traces/stats`,
    ) as unknown as Promise<TraceStatsDTO>,
}
