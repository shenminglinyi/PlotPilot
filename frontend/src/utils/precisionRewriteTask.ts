export const PRECISION_REWRITE_SOURCE = 'precision-rewrite'

export interface PrecisionRewriteRationaleInput {
  objective: string
  instruction?: string
  targetExcerpt?: string
}

export function buildPrecisionRewriteRationale(input: PrecisionRewriteRationaleInput): string {
  const parts = [
    `精细改稿目标：${input.objective}`,
    input.instruction?.trim() ? `作者要求：${input.instruction.trim()}` : '',
    input.targetExcerpt?.trim() ? `重点片段：${input.targetExcerpt.trim()}` : '',
    '约束：保留主线事实和关键事件，不直接覆盖主稿，先生成候选稿供作者确认。',
  ]

  return parts.filter(Boolean).join('\n')
}
