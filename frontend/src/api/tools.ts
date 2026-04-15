/**
 * 创作工具类 API
 * 包括：张力弹弓、宏观重构扫描、实体叙事状态
 */
import { apiClient } from './config'

// ── 张力弹弓 ────────────────────────────────────────────────

export interface TensionSlingshotPayload {
  novel_id: string
  chapter_number: number
  stuck_reason?: string
}

export interface TensionDiagnosis {
  diagnosis: string
  tension_level: 'low' | 'medium' | 'high'
  missing_elements: string[]
  suggestions: string[]
}

export const tensionApi = {
  /** POST /api/v1/novels/{novel_id}/writer-block/tension-slingshot */
  slingshot: (novelId: string, payload: TensionSlingshotPayload) =>
    apiClient.post<TensionDiagnosis>(
      `/api/v1/novels/${novelId}/writer-block/tension-slingshot`,
      payload
    ) as unknown as Promise<TensionDiagnosis>,
}

// ── 宏观重构扫描 ────────────────────────────────────────────

export interface LogicBreakpoint {
  event_id: string
  chapter: number
  reason: string
  tags: string[]
}

export interface RefactorProposalPayload {
  event_id: string
  author_intent: string
  current_event_summary: string
  current_tags: string[]
}

export interface RefactorProposal {
  natural_language_suggestion: string
  suggested_mutations: Record<string, unknown>[]
  suggested_tags: string[]
  reasoning: string
}

export interface ApplyMutationPayload {
  event_id: string
  mutations: Record<string, unknown>[]
  reason?: string
}

export interface ApplyMutationResponse {
  success: boolean
  updated_event: Record<string, unknown>
  applied_mutations: Record<string, unknown>[]
}

// 宏观诊断结果
export interface MacroDiagnosisResult {
  id: string
  novel_id: string
  trigger_reason: string
  trait: string
  conflict_tags: string[]
  breakpoints: LogicBreakpoint[]
  breakpoint_count: number
  status: 'pending' | 'completed' | 'failed'
  resolved: boolean
  resolved_at: string | null
  resolved_by: string | null
  error_message: string | null
  created_at: string
}

export const macroRefactorApi = {
  /** GET /api/v1/novels/{novel_id}/macro-refactor/breakpoints */
  scanBreakpoints: (novelId: string, trait: string, conflictTags?: string) =>
    apiClient.get<LogicBreakpoint[]>(
      `/api/v1/novels/${novelId}/macro-refactor/breakpoints`,
      { params: { trait, ...(conflictTags ? { conflict_tags: conflictTags } : {}) } }
    ) as unknown as Promise<LogicBreakpoint[]>,

  /** POST /api/v1/novels/{novel_id}/macro-refactor/proposals */
  generateProposal: (novelId: string, payload: RefactorProposalPayload) =>
    apiClient.post<RefactorProposal>(
      `/api/v1/novels/${novelId}/macro-refactor/proposals`,
      payload
    ) as unknown as Promise<RefactorProposal>,

  /** POST /api/v1/novels/{novel_id}/macro-refactor/apply */
  applyMutations: (novelId: string, payload: ApplyMutationPayload) =>
    apiClient.post<ApplyMutationResponse>(
      `/api/v1/novels/${novelId}/macro-refactor/apply`,
      payload
    ) as unknown as Promise<ApplyMutationResponse>,

  /** GET /api/v1/novels/{novel_id}/macro-refactor/diagnosis/latest */
  getLatestDiagnosis: (novelId: string) =>
    apiClient.get<MacroDiagnosisResult | null>(
      `/api/v1/novels/${novelId}/macro-refactor/diagnosis/latest`
    ) as unknown as Promise<MacroDiagnosisResult | null>,

  /** GET /api/v1/novels/{novel_id}/macro-refactor/diagnosis/history */
  getDiagnosisHistory: (novelId: string, limit = 10) =>
    apiClient.get<MacroDiagnosisResult[]>(
      `/api/v1/novels/${novelId}/macro-refactor/diagnosis/history`,
      { params: { limit } }
    ) as unknown as Promise<MacroDiagnosisResult[]>,

  /** POST /api/v1/novels/{novel_id}/macro-refactor/diagnosis/run */
  runDiagnosis: (novelId: string, traits?: string) =>
    apiClient.post<MacroDiagnosisResult>(
      `/api/v1/novels/${novelId}/macro-refactor/diagnosis/run`,
      null,
      { params: traits ? { traits } : {} }
    ) as unknown as Promise<MacroDiagnosisResult>,

  /** POST /api/v1/novels/{novel_id}/macro-refactor/diagnosis/{diagnosis_id}/resolve */
  resolveDiagnosis: (novelId: string, diagnosisId: string) =>
    apiClient.post<{ success: boolean; message: string }>(
      `/api/v1/novels/${novelId}/macro-refactor/diagnosis/${diagnosisId}/resolve`
    ) as unknown as Promise<{ success: boolean; message: string }>,
}

// ── 实体叙事状态 ────────────────────────────────────────────

export interface EntityState {
  entity_id: string
  [key: string]: unknown
}

export const narrativeStateApi = {
  /** GET /api/v1/novels/{novel_id}/entities/{entity_id}/state?chapter= */
  getState: (novelId: string, entityId: string, chapter: number) =>
    apiClient.get<EntityState>(
      `/api/v1/novels/${novelId}/entities/${entityId}/state`,
      { params: { chapter } }
    ) as unknown as Promise<EntityState>,
}
