/**
 * 全托管日志流 → DAG 节点 type 桥接策略（声明式，与后端 primary_node_policy 语义对齐）
 *
 * 仅用于 SSE 旁路的日志事件兜底；权威状态以后端 GET /dag/.../status 与 SSE 投影为准。
 */

export interface SubstepPrimaryRule {
  readonly substeps: readonly string[]
  readonly primaryNodeType: string
}

export interface StagePrimaryRule {
  readonly stages: readonly string[]
  /** null：阶段存在但不在此映射主节点（如 completed 由调用方单独处理） */
  readonly primaryNodeType: string | null
}

/** 顺序即优先级 */
export const AUTOPILOT_SUBSTEP_PRIMARY_RULES: readonly SubstepPrimaryRule[] = [
  { substeps: ['macro_planning'], primaryNodeType: 'ctx_blueprint' },
  { substeps: ['act_planning'], primaryNodeType: 'ctx_memory' },
  { substeps: ['llm_calling'], primaryNodeType: 'exec_writer' },
  { substeps: ['chapter_found', 'context_assembly', 'beat_magnification'], primaryNodeType: 'exec_beat' },
  {
    substeps: ['soft_landing', 'persisting', 'continuity_check', 'chapter_persist'],
    primaryNodeType: 'exec_writer',
  },
  { substeps: ['audit_voice_check'], primaryNodeType: 'val_style' },
  { substeps: ['audit_tension'], primaryNodeType: 'val_tension' },
  { substeps: ['audit_aftermath'], primaryNodeType: 'val_narrative' },
  { substeps: ['audit_anti_ai'], primaryNodeType: 'val_anti_ai' },
] as const

export const AUTOPILOT_STAGE_PRIMARY_RULES: readonly StagePrimaryRule[] = [
  { stages: ['macro_planning', 'planning'], primaryNodeType: 'ctx_blueprint' },
  { stages: ['act_planning'], primaryNodeType: 'ctx_memory' },
  { stages: ['writing'], primaryNodeType: 'exec_writer' },
  { stages: ['auditing'], primaryNodeType: 'val_style' },
  { stages: ['paused_for_review'], primaryNodeType: 'gw_review' },
  { stages: ['completed'], primaryNodeType: null },
] as const

/**
 * 从日志元数据解析要高亮的 DAG 节点 type；无匹配返回 null。
 */
export function resolveAutopilotLogToNodeType(stage: string, substep: string): string | null {
  const ws = (substep || '').trim()
  if (ws && ws !== 'undefined') {
    for (const row of AUTOPILOT_SUBSTEP_PRIMARY_RULES) {
      if (row.substeps.includes(ws)) {
        return row.primaryNodeType
      }
    }
  }
  const st = (stage || '').trim()
  if (!st || st === 'undefined') {
    return null
  }
  for (const row of AUTOPILOT_STAGE_PRIMARY_RULES) {
    if (row.stages.includes(st)) {
      return row.primaryNodeType
    }
  }
  return null
}
