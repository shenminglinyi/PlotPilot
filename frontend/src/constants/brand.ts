export const BRAND = {
  productName: 'PlotPilot',
  chineseName: '墨枢',
  displayName: 'PlotPilot · 墨枢',
  tagline: '作者的领航员',
  descriptor: 'AI 小说创作平台',
  team: 'PlotPilot（墨枢）团队',
  credit: '由 PlotPilot（墨枢）团队倾力开发',
  douyinLabel: '抖音：林亦 91472902104',
  douyinUrl: 'https://www.douyin.com/user/MS4wLjABAAAA91472902104',
  liveSchedule: '每晚 9 点随缘直播',
} as const

export const BRAND_COPY = {
  short: BRAND.displayName,
  compact: `${BRAND.chineseName} · ${BRAND.tagline}`,
  full: `${BRAND.displayName}｜${BRAND.credit}`,
  social: `${BRAND.douyinLabel}｜${BRAND.liveSchedule}`,
} as const
