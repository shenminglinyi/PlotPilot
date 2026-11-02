/**
 * 工作台与全局 UI 密度常量（TypeScript 消费侧）。
 *
 * CSS 壳层排版变量见 `src/assets/styles/tokens-layout.css`。
 * 调整密度时请两边对照，保持观感一致。
 */

/** 工作台横向 n-split（0–1 比例），避免在视图中散装 magic number */
export const WORKBENCH_SPLIT = {
  /** 左栏：章节列表 / 叙事树 */
  sidebarDefault: 0.165,
  sidebarMin: 0.12,
  sidebarMax: 0.28,
  /** 中栏：主编辑区所占「中+右」区域的比例 */
  mainDefault: 0.615,
  mainMin: 0.42,
  mainMax: 0.78,
} as const

/**
 * Naive UI 形体基准 px（再配合 `scaledUiPx` 与用户字体档位）
 * —— 整体上较早期默认值略紧凑，适配「信息密度偏高」的写作台。
 */
export const NAIVE_DENSITY_BASE = {
  borderRadius: 9,
  borderRadiusSmall: 7,
  fontSize: 13,
  fontSizeMedium: 14,
  lineHeight: '1.5',
  heightMedium: 32,
  cardBorderRadius: 12,
  cardPaddingMedium: 14,
  scrollbarWidth: 6,
} as const
