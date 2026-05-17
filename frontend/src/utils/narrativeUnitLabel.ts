import type { GenerationPrefsDTO } from '@/api/novel'

/** 与后端缺省一致：未带字段时视为阶段模式 */
export function isPhaseDisplayMode(prefs?: Partial<GenerationPrefsDTO> | null): boolean {
  if (prefs == null) return true
  if (!Object.prototype.hasOwnProperty.call(prefs, 'phase_display_mode')) return true
  return Boolean(prefs.phase_display_mode)
}

export function narrativeUnitNoun(prefs?: Partial<GenerationPrefsDTO> | null): '章' | '阶段' {
  return isPhaseDisplayMode(prefs) ? '阶段' : '章'
}

/**
 * 侧栏/标题用序数标签：阶段模式为「第 N 阶段」（阿拉伯数字）；章模式为「第 N 章」。
 */
export function narrativeOrdinalLabel(n: number, prefs?: Partial<GenerationPrefsDTO> | null): string {
  if (!Number.isFinite(n) || n < 1) {
    return isPhaseDisplayMode(prefs) ? `第${n}阶段` : `第${n}章`
  }
  if (isPhaseDisplayMode(prefs)) {
    return `第${n}阶段`
  }
  return `第${n}章`
}

/** 结构树：节点 `number` 为全书章号，固定用「第 N 章」，避免与「阶段模式」下的叙事单元文案
 * 及节拍/故事阶段混淆；侧栏列表等仍服从 {@link narrativeOrdinalLabel}。 */
export function narrativeTreeChapterLine(
  n: number,
  title: string,
  _prefs?: Partial<GenerationPrefsDTO> | null
): string {
  const head = narrativeOrdinalLabel(n, { phase_display_mode: false })
  const t = (title || '').trim()
  return t ? `${head} ${t}` : head
}
