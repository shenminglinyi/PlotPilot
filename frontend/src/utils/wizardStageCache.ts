/**
 * 新书向导 UI 缓存：主线候选、自定义模式与文案、向导完成状态。
 * 服务端已落库的数据仍以 API 为准；缓存仅避免关闭向导后重复触发 LLM 推演。
 */
import type { MainPlotOptionDTO } from '@/api/workflow'

export const WIZARD_UI_CACHE_SCHEMA = 2
const STORAGE_KEY_PREFIX = 'plotpilot:novel-wizard-ui:'
/** 超过此时间不再复用候选（仍保留自定义文案，用户可能还想继续写） */
export const WIZARD_PLOT_OPTIONS_TTL_MS = 7 * 24 * 60 * 60 * 1000

export interface WizardUiCachePayload {
  v: number
  novelId: string
  /** 任意字段写入时间（用于调试或兜底） */
  savedAt: number
  /** 仅在有 plotOptions 时更新，用于候选 TTL */
  plotOptionsSavedAt?: number
  plotOptions?: MainPlotOptionDTO[]
  /** 候选过期后仍可用的 UI */
  customMode?: boolean
  customLogline?: string
  /** 向导是否已完成（用户点"进入工作台"后标记） */
  wizardCompleted?: boolean
  /** 向导最后到达的步骤（1~5），用于下次打开恢复 */
  lastStep?: number
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
    if (Object.prototype.hasOwnProperty.call(patch, 'plotOptions')) {
      if (patch.plotOptions?.length) {
        next.plotOptionsSavedAt = Date.now()
      } else {
        next.plotOptionsSavedAt = undefined
        next.plotOptions = undefined
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

/** plotOptions 是否仍在 TTL 内（过期则不应展示旧候选，避免与书籍现状偏差过大） */
export function isPlotOptionsCacheFresh(payload: WizardUiCachePayload | null): boolean {
  if (!payload?.plotOptions?.length) return false
  const base = payload.plotOptionsSavedAt ?? payload.savedAt
  return Date.now() - base <= WIZARD_PLOT_OPTIONS_TTL_MS
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
