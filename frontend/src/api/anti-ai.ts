/**
 * Anti-AI 防御系统 — API 接口
 */
import type {
  ScanResult,
  PromptCategory,
  AntiAIRule,
  AllowlistScene,
  AllowlistUpdateRequest,
  AntiAIStats,
} from '../types/anti-ai'

const API_BASE = '/api/v1/anti-ai'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    throw new Error(`Anti-AI API error: ${res.status} ${res.statusText}`)
  }
  return res.json()
}

/** 扫描章节 AI 味 */
export function scanChapter(content: string, chapterId?: string): Promise<ScanResult> {
  return request<ScanResult>('/scan', {
    method: 'POST',
    body: JSON.stringify({ content, chapter_id: chapterId || '' }),
  })
}

/** 获取提示词分类信息 */
export function getCategories(): Promise<PromptCategory[]> {
  return request<PromptCategory[]>('/categories')
}

/** 获取正向行为映射规则 */
export function getRules(): Promise<AntiAIRule[]> {
  return request<AntiAIRule[]>('/rules')
}

/** 获取白名单场景列表 */
export function getAllowlistScenes(): Promise<AllowlistScene[]> {
  return request<AllowlistScene[]>('/allowlist/scenes')
}

/** 更新白名单 */
export function updateAllowlist(data: AllowlistUpdateRequest): Promise<{ status: string; scene_type: string }> {
  return request('/allowlist', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

/** 获取 Anti-AI 系统统计 */
export function getAntiAIStats(): Promise<AntiAIStats> {
  return request<AntiAIStats>('/stats')
}
