export type NovelStage = 'planning' | 'writing' | 'reviewing' | 'completed'
export type NovelStageTagType = 'info' | 'warning' | 'default' | 'success'
export type NovelLengthTier = 'short' | 'standard' | 'epic'

export interface NovelLengthTierOption {
  value: NovelLengthTier
  title: string
  hint: string
}

const NOVEL_STAGE_META: Record<NovelStage, { label: string; tagType: NovelStageTagType }> = {
  planning: { label: '规划中', tagType: 'info' },
  writing: { label: '写作中', tagType: 'warning' },
  reviewing: { label: '审稿中', tagType: 'default' },
  completed: { label: '已完成', tagType: 'success' },
}

export const NOVEL_LENGTH_TIER_OPTIONS: NovelLengthTierOption[] = [
  {
    value: 'short',
    title: 'A · 短篇快穿 / 脑洞文',
    hint: '约 30 万字（按约 2000 字/章推导章数）',
  },
  {
    value: 'standard',
    title: 'B · 标准商业连载',
    hint: '约 100 万字',
  },
  {
    value: 'epic',
    title: 'C · 宏大史诗巨著',
    hint: '约 300 万字',
  },
]

function normalizeNovelStage(stage?: string | null): NovelStage | null {
  const key = String(stage || '').trim()
  return key in NOVEL_STAGE_META ? key as NovelStage : null
}

export function getNovelStageLabel(stage?: string | null): string {
  const normalized = normalizeNovelStage(stage)
  return normalized ? NOVEL_STAGE_META[normalized].label : String(stage || '').trim()
}

export function getNovelStageTagType(stage?: string | null): NovelStageTagType {
  const normalized = normalizeNovelStage(stage)
  return normalized ? NOVEL_STAGE_META[normalized].tagType : 'default'
}
