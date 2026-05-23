import { apiClient } from './config'

export interface EvolutionSnapshot {
  snapshot_id: string
  novel_id: string
  branch_id: string
  chapter_number: number
  schema_version: string
  status: 'active' | 'stale' | 'blocked'
  opening_state: Record<string, unknown>
  delta_actions: Array<Record<string, any>>
  machine_state: Record<string, unknown>
  human_override_patches: Array<Record<string, unknown>>
  ending_state: Record<string, any>
  source_refs: Array<Record<string, unknown>>
  conflicts: Array<Record<string, any>>
  created_at: string
  updated_at: string
}

export interface EvolutionSnapshotList {
  novel_id: string
  branch_id: string
  snapshots: EvolutionSnapshot[]
  counts: Record<string, number>
}

export interface EvolutionGateReport {
  is_pass: boolean
  violations: Array<{
    level: string
    type: string
    message: string
    suggestion?: string
  }>
  required_continuations: string[]
  repair_plan: string[]
  governance_budget?: {
    chapter_number: number
    max_new_storylines: number
    max_debt_closures: number
    allowed_reveal_level: string
    must_serve_promise_tags: string[]
    carry_over_debt_ids: string[]
    notes: string[]
  } | null
  governance_context_request?: Record<string, unknown>
}

export const evolutionApi = {
  listSnapshots: (novelId: string, branchId = 'main') =>
    apiClient.get<EvolutionSnapshotList>(
      `/novels/${novelId}/evolution/snapshots`,
      { params: { branch_id: branchId } },
    ) as unknown as Promise<EvolutionSnapshotList>,

  gate: (novelId: string, payload: {
    chapter_number: number
    branch_id?: string
    outline_content?: string
    pov_character_id?: string | null
    tags?: string[]
  }) =>
    apiClient.post<EvolutionGateReport>(
      `/novels/${novelId}/evolution/gate`,
      payload,
    ) as unknown as Promise<EvolutionGateReport>,

  applyOverrides: (novelId: string, chapterNumber: number, patches: Array<Record<string, unknown>>, branchId = 'main') =>
    apiClient.post<EvolutionSnapshot>(
      `/novels/${novelId}/evolution/snapshots/${chapterNumber}/overrides`,
      { branch_id: branchId, patches },
    ) as unknown as Promise<EvolutionSnapshot>,

  replayFrom: (novelId: string, chapterNumber: number, branchId = 'main') =>
    apiClient.post<Record<string, unknown>>(
      `/novels/${novelId}/evolution/replay-from/${chapterNumber}`,
      { branch_id: branchId },
    ) as unknown as Promise<Record<string, unknown>>,
}
