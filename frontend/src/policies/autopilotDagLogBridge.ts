/**
 * 全托管日志流 → DAG 节点 type 桥接策略（声明式，与后端 primary_node_policy 语义对齐）
 *
 * 仅用于 SSE 旁路的日志事件兜底；权威状态以后端 GET /dag/.../status 与 SSE 投影为准。
 * 规则表在模块加载时编译为 Map，高频日志路径 O(1) 查表。
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

/** 顺序即优先级（编译进 Map 时保留先声明者优先） */
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

function buildSubstepLookup(): ReadonlyMap<string, string> {
  const m = new Map<string, string>()
  for (const row of AUTOPILOT_SUBSTEP_PRIMARY_RULES) {
    for (const s of row.substeps) {
      if (!m.has(s)) m.set(s, row.primaryNodeType)
    }
  }
  return m
}

function buildStageLookup(): ReadonlyMap<string, string | null> {
  const m = new Map<string, string | null>()
  for (const row of AUTOPILOT_STAGE_PRIMARY_RULES) {
    for (const s of row.stages) {
      if (!m.has(s)) m.set(s, row.primaryNodeType)
    }
  }
  return m
}

/** 子步 → 主节点 type（首次 resolve 前初始化） */
const SUBSTEP_TO_PRIMARY_TYPE = buildSubstepLookup()
/** 阶段 → 主节点 type（含 null） */
const STAGE_TO_PRIMARY_TYPE = buildStageLookup()

/**
 * 从日志元数据解析要高亮的 DAG 节点 type；无匹配返回 null。
 */
export function resolveAutopilotLogToNodeType(stage: string, substep: string): string | null {
  const ws = (substep || '').trim()
  if (ws && ws !== 'undefined') {
    const hit = SUBSTEP_TO_PRIMARY_TYPE.get(ws)
    if (hit !== undefined) return hit
  }
  const st = (stage || '').trim()
  if (!st || st === 'undefined') {
    return null
  }
  if (STAGE_TO_PRIMARY_TYPE.has(st)) {
    return STAGE_TO_PRIMARY_TYPE.get(st) ?? null
  }
  return null
}
