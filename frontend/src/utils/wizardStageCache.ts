/**
 * 新书向导 UI 缓存：剧情总纲预览与向导完成状态。
 * 服务端已落库的数据仍以 API 为准；缓存仅避免关闭向导后重复触发 LLM 生成。
 */
import type { PlotOutlineDTO } from '@/api/workflow'

export const WIZARD_UI_CACHE_SCHEMA = 4
const STORAGE_KEY_PREFIX = 'plotpilot:novel-wizard-ui:'
export const WIZARD_PLOT_OUTLINE_TTL_MS = 7 * 24 * 60 * 60 * 1000

export interface WizardUiCachePayload {
  v: number
  novelId: string
  /** 任意字段写入时间（用于调试或兜底） */
  savedAt: number
  /** 仅在有 plotOutline 时更新，用于总纲 TTL */
  plotOutlineSavedAt?: number
  plotOutline?: PlotOutlineDTO
  invocationSessionId?: string
  /** 向导是否已完成（用户点"进入工作台"后标记） */
  wizardCompleted?: boolean
  /** 向导最后到达的步骤（1~5），用于下次打开恢复 */
  lastStep?: number
  /** 世界观字段的本地 UI 自定义标题；不影响底层 schema key */
  worldbuildingFieldLabels?: Record<string, string>
}

function key(novelId: string): string {
  return `${STORAGE_KEY_PREFIX}${novelId}`
}

export function readWizardUiCache(novelId: string): WizardUiCachePayload | null {
  if (!novelId || typeof localStorage === 'undefined') return null
  try {
    const raw = localStorage.getItem(key(novelId))
    if (!raw) return null
    const data = JSON.parse(raw) as WizardUiCachePayload
    if (!data || data.novelId !== novelId) return null
    // 兼容 v1 缓存：schema 升级但数据仍可用
    return data
  } catch {
    return null
  }
}

export function writeWizardUiCache(novelId: string, patch: Partial<Omit<WizardUiCachePayload, 'v' | 'novelId'>>): void {
  if (!novelId || typeof localStorage === 'undefined') return
  try {
    const prev = readWizardUiCache(novelId) || {
      v: WIZARD_UI_CACHE_SCHEMA,
      novelId,
      savedAt: Date.now(),
    }
    const next: WizardUiCachePayload = {
      ...prev,
      ...patch,
      v: WIZARD_UI_CACHE_SCHEMA,
      novelId,
      savedAt: Date.now(),
    }
    if (Object.prototype.hasOwnProperty.call(patch, 'plotOutline')) {
      if (patch.plotOutline) {
        next.plotOutlineSavedAt = Date.now()
      } else {
        next.plotOutlineSavedAt = undefined
        next.plotOutline = undefined
      }
    }
    if (Object.prototype.hasOwnProperty.call(patch, 'invocationSessionId')) {
      if (!patch.invocationSessionId) {
        next.invocationSessionId = undefined
      }
    }
    localStorage.setItem(key(novelId), JSON.stringify(next))
  } catch {
    /* 私密模式或配额满时忽略 */
  }
}

export function clearWizardUiCache(novelId: string): void {
  if (!novelId || typeof localStorage === 'undefined') return
  try {
    localStorage.removeItem(key(novelId))
  } catch {
    /* ignore */
  }
}

export function isPlotOutlineCacheFresh(payload: WizardUiCachePayload | null): boolean {
  if (!payload?.plotOutline) return false
  const base = payload.plotOutlineSavedAt ?? payload.savedAt
  return Date.now() - base <= WIZARD_PLOT_OUTLINE_TTL_MS
}

/** 向导是否已完成（完成 = 用户点过"进入工作台"） */
export function isWizardCompleted(novelId: string): boolean {
  const cached = readWizardUiCache(novelId)
  return cached?.wizardCompleted === true
}

/** 标记向导为已完成 */
export function markWizardCompleted(novelId: string): void {
  writeWizardUiCache(novelId, { wizardCompleted: true })
}

/** 获取向导最后到达的步骤 */
export function getWizardLastStep(novelId: string): number | undefined {
  const cached = readWizardUiCache(novelId)
  return cached?.lastStep
}

/** 记录向导当前步骤 */
export function setWizardLastStep(novelId: string, step: number): void {
  writeWizardUiCache(novelId, { lastStep: step })
}
