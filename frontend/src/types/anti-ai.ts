/**
 * Anti-AI 防御系统 — 前端类型定义
 *
 * 七层纵深防御体系类型：
 * L1 正向行为映射 → L2 协议规则 → L3 白名单 → L4 角色状态锁
 * L5 上下文配额 → L6 Token拦截 → L7 章后审计
 */

// ─── 扫描结果 ───

export interface ClicheHit {
  pattern: string
  text: string
  start: number
  end: number
  severity: 'critical' | 'warning' | 'info'
  category: string
  replacement_hint: string
}

export interface ScanResult {
  total_hits: number
  critical_hits: number
  warning_hits: number
  severity_score: number
  overall_assessment: '纯净' | '轻微' | '中等' | '严重' | '未检测'
  category_distribution: Record<string, number>
  top_patterns: string[]
  recommendations: string[]
  improvement_suggestions: string[]
  hits: ClicheHit[]
}

// ─── 分类信息 ───

export interface PromptCategory {
  key: string
  name: string
  icon: string
  description: string
  color: string
  sort_order: number
  prompt_count: number
}

// ─── 规则信息 ───

export interface AntiAIRule {
  key: string
  anti_pattern: string
  positive_action: string
  category: string
  severity: 'critical' | 'warning' | 'info'
}

// ─── 白名单 ───

export interface AllowlistScene {
  scene_type: string
  allowed_categories: string[]
  allowed_patterns: string[]
  max_density_per_1000: number
  description: string
}

export interface AllowlistUpdateRequest {
  scene_type: string
  allowed_categories?: string[]
  allowed_patterns?: string[]
  max_density_per_1000?: number
  description?: string
}

// ─── 系统统计 ───

export interface AntiAIStats {
  total_prompts: number
  anti_ai_prompts: number
  categories_count: number
  cliche_patterns: number
  layers: {
    L1_positive_framing: number
    L2_protocol_rules: number
    L3_allowlist_scenes: number
    L4_state_vector: string
    L5_context_quota: string
    L6_token_guard: string
    L7_audit: string
  }
}

// ─── 严重性颜色映射 ───

export const SEVERITY_COLORS: Record<string, string> = {
  critical: '#dc2626',
  warning: '#f59e0b',
  info: '#3b82f6',
}

export const ASSESSMENT_COLORS: Record<string, string> = {
  '纯净': '#22c55e',
  '轻微': '#84cc16',
  '中等': '#f59e0b',
  '严重': '#dc2626',
  '未检测': '#6b7280',
}

// ─── 场景类型中文映射 ───

export const SCENE_TYPE_LABELS: Record<string, string> = {
  default: '默认',
  battle: '战斗',
  suspense: '悬疑',
  horror: '恐怖',
  confession: '告白',
  revelation: '揭秘/反转',
}
