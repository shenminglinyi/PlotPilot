import { apiClient } from './config'

export type InvocationPolicy =
  | 'DIRECT'
  | 'REVIEW_BEFORE_CALL'
  | 'REVIEW_AFTER_CALL'
  | 'FULL_INTERACTIVE'
  | 'INTERACTIVE_WHEN_AVAILABLE'
  | 'AUTOPILOT_PAUSE'

export type InvocationSessionStatus =
  | 'requested'
  | 'spec_resolved'
  | 'context_resolved'
  | 'variables_resolved'
  | 'prompt_compiled'
  | 'awaiting_pre_call_review'
  | 'generating'
  | 'awaiting_acceptance'
  | 'awaiting_commit'
  | 'committing'
  | 'completed'
  | 'blocked'
  | 'failed'
  | 'cancelled'

export interface InvocationPromptSnapshot {
  prompt?: {
    system?: string
    user?: string
  }
  node_key?: string
  node_version_id?: string
  asset_link_set_id?: string
  input_binding_set_id?: string
  output_binding_set_id?: string
  variable_snapshot_hash?: string
  template_hash?: string
  composition_hash?: string
  rendered_prompt_hash?: string
  missing_variables?: string[]
  diagnostics?: string[]
  asset_version_ids?: string[]
}

export interface InvocationVariablePlan {
  aliases?: Record<string, unknown>
  required_missing?: string[]
  diagnostics?: string[]
  lineage?: Record<string, string>
  snapshot_hash?: string
}

export interface InvocationSessionDTO {
  id: string
  operation: string
  node_key: string
  policy: InvocationPolicy | string
  status: InvocationSessionStatus | string
  context?: Record<string, unknown>
  metadata?: Record<string, unknown>
  attempts?: string[]
  prompt_snapshot?: InvocationPromptSnapshot
  variable_plan?: InvocationVariablePlan
}

export interface InvocationAttemptDTO {
  id: string
  session_id: string
  status: string
  content: string
  error?: string
}

export interface AdoptionDecisionDTO {
  id: string
  session_id: string
  attempt_id: string
  decision: string
  accept_content: boolean
  commit_prompt_version: boolean
  commit_variable_outputs: boolean
  commit_variable_bindings: boolean
}

export interface AdoptionCommitStepDTO {
  name: string
  status: string
  result?: Record<string, unknown>
  error?: string
}

export interface AdoptionCommitDTO {
  id: string
  session_id: string
  decision_id: string
  status: string
  steps: AdoptionCommitStepDTO[]
  error?: string
}

export interface InvocationResponseDTO {
  session: InvocationSessionDTO
  attempt?: InvocationAttemptDTO | null
  decision?: AdoptionDecisionDTO | null
  commit?: AdoptionCommitDTO | null
  next_action?: string
}

export interface InvocationCreatePayload {
  operation: string
  node_key: string
  variables?: Record<string, unknown>
  context?: Record<string, unknown>
  policy?: InvocationPolicy
  config?: Record<string, unknown>
  metadata?: Record<string, unknown>
}

export interface InvocationAcceptPayload {
  attempt_id: string
  accepted_by?: string
  commit_prompt_version?: boolean
  commit_variable_outputs?: boolean
  commit_variable_bindings?: boolean
  metadata?: Record<string, unknown>
}

export const aiInvocationApi = {
  create(payload: InvocationCreatePayload) {
    return apiClient.post<InvocationResponseDTO>('/ai-invocations', payload)
  },
  get(sessionId: string) {
    return apiClient.get<InvocationResponseDTO>(`/ai-invocations/${sessionId}`)
  },
  accept(sessionId: string, payload: InvocationAcceptPayload) {
    return apiClient.post<InvocationResponseDTO>(`/ai-invocations/${sessionId}/accept`, payload)
  },
  reject(sessionId: string, payload: InvocationAcceptPayload) {
    return apiClient.post<InvocationResponseDTO>(`/ai-invocations/${sessionId}/reject`, payload)
  },
  commit(sessionId: string, decisionId: string) {
    return apiClient.post<InvocationResponseDTO>(`/ai-invocations/${sessionId}/commits`, {
      decision_id: decisionId,
    })
  },
}
