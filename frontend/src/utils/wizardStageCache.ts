/**
 * 新书向导「第 4 步」UI 缓存：主线候选、自定义模式与文案。
 * 服务端已落库的数据仍以 API 为准；缓存仅避免关闭向导后重复触发 LLM 推演。
 */
import type { MainPlotOptionDTO } from '@/api/workflow'

export const WIZARD_UI_CACHE_SCHEMA = 1
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
    if (!data || data.v !== WIZARD_UI_CACHE_SCHEMA || data.novelId !== novelId) return null
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
