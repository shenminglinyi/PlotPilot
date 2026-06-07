/**
 * 市场向「文风公约」预设（用户不可自填底层 Prompt，仅选模板）。
 * 与后端生成链路配合时，梗概 + 赛道/世界观已在建档时写入 novel.premise。
 */
export interface MarketStylePreset {
  label: string
  value: string
  body: string
  icon: string
  aliases: string[]
  keywords: string[]
}

function normalizeStyleText(text: string): string {
  return (text || '').replace(/\s+/g, '').trim()
}

function styleHeading(text: string): string {
  const t = (text || '').trim()
  const bracket = t.match(/^【文风公约[·:：-]?([^】]+)】/)
  if (bracket?.[1]) return bracket[1].trim()
  const plain = t.match(/^文风(?:承袭|采用|偏向|定位)?([^：:；;，,。]{2,12})/)
  return plain?.[1]?.trim() || ''
}

function scorePreset(styleNotes: string, preset: MarketStylePreset): number {
  const normalized = normalizeStyleText(styleNotes)
  const heading = styleHeading(styleNotes)
  const body = normalizeStyleText(preset.body)
  if (!normalized) return 0
  if (normalized === body) return 1000
  if (normalized.startsWith(body.slice(0, Math.min(body.length, 30)))) return 900

  let score = 0
  for (const alias of preset.aliases) {
    const a = normalizeStyleText(alias)
    if (!a) continue
    if (normalizeStyleText(heading).includes(a)) score += 120
    if (normalized.includes(a)) score += 45
  }
  for (const keyword of preset.keywords) {
    const k = normalizeStyleText(keyword)
    if (k && normalized.includes(k)) score += 18
  }
  return score
}

export const MARKET_STYLE_PRESETS: MarketStylePreset[] = [
  {
    label: '修仙·升级打脸',
    value: 'xianxia_hot',
    icon: '仙',
    aliases: ['修仙爽文', '修仙', '仙侠', '古典仙侠'],
    keywords: ['仙门', '道统', '因果', '轮回', '修真', '山海', '天道', '古典'],
    body:
      '【文风公约·修仙爽文】第三人称有限视角；节奏快，章末留钩。冲突外化，升级与打脸交替；系统/机缘仅作推进器，忌说明书式设定堆砌。对话口语化，战斗场面分镜清晰。禁止圣母拖戏、禁止同一信息重复三章。',
  },
  {
    label: '赛博·冷峻群像',
    value: 'cyberpunk',
    icon: '械',
    aliases: ['赛博朋克', '赛博', '冷峻群像'],
    keywords: ['巨企', '义体', '信息战', '冷色调', '科技', '道德灰度'],
    body:
      '【文风公约·赛博朋克】冷色调叙事；巨企、义体、信息战为舞台。短句与名词堆叠营造窒息感，偶用长句收束情绪。科技细节服务情节，不炫技。道德灰度，反派有动机。禁止中二口号滥用。',
  },
  {
    label: '悬疑·线索回收',
    value: 'mystery',
    icon: '疑',
    aliases: ['悬疑', '线索回收', '推理'],
    keywords: ['线索', '伏笔', '反转', '调查', '真凶', '信息控制'],
    body:
      '【文风公约·悬疑】视角控制信息：读者与主角同步知情。伏笔显性埋、合理回收；反转需前文有锚点。节奏张弛：调查—受挫—突破。环境描写参与氛围，不单为写景。禁止机械降神、禁止真凶无铺垫。',
  },
  {
    label: '都市·爽点直给',
    value: 'urban_power',
    icon: '都',
    aliases: ['都市爽文', '都市', '爽点直给'],
    keywords: ['强代入', '身份反转', '资源碾压', '职场', '家族线', '反馈'],
    body:
      '【文风公约·都市爽文】强代入、强反馈；身份反转与资源碾压要「事出有因」。职场/家族线可并行，主线不漂移。对话带梗但不过密。感情线服务主线时可写，忌喧宾夺主。禁止连续水文复盘。',
  },
  {
    label: '玄幻·热血史诗',
    value: 'xuanhuan_epic',
    icon: '玄',
    aliases: ['玄幻', '热血史诗', '史诗'],
    keywords: ['世界观分层', '地图', '势力', '战斗', '成长', '群像', '战力'],
    body:
      '【文风公约·玄幻】世界观分层展开，地图与势力随剧情解锁。战斗有代价与成长。群像可有配角弧，主角动机始终清晰。辞藻可华丽但句意须清。禁止战力崩坏、禁止无限叠盒子无剧情。',
  },
  {
    label: '言情·甜宠克制',
    value: 'romance_sweet',
    icon: '情',
    aliases: ['言情甜宠', '言情', '甜宠'],
    keywords: ['情绪细腻', '误会', '甜', '亲密戏', '恋爱', '双方'],
    body:
      '【文风公约·言情甜宠】情绪细腻，误会不过三；甜与爽点交替。双方有独立人格与目标，不单为恋爱工具人。亲密戏点到为止、平台合规。禁止为虐而虐、禁止降智推动剧情。',
  },
]

export function matchPresetValue(styleNotes: string): string | null {
  const scored = MARKET_STYLE_PRESETS
    .map(preset => ({ preset, score: scorePreset(styleNotes, preset) }))
    .sort((a, b) => b.score - a.score)
  const best = scored[0]
  return best && best.score >= 45 ? best.preset.value : null
}

export function getMarketStylePresetIcon(value?: string | null): string {
  return MARKET_STYLE_PRESETS.find(preset => preset.value === value)?.icon || '文'
}
