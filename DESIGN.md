# Design System — PlotPilot（墨枢）

## Product Context

- **What this is:** AI 驱动的长篇叙事工作台，整合 Story Bible、知识图谱、自动驾驶章节生成、伏笔台账与文风监控。
- **Who it's for:** 网文/长篇作者、连载创作者、需要结构化叙事资产与后台管线的小说写作者。
- **Space / industry:** 创作工具 / 垂直写作 IDE，对标「专业作者工作室」而非通用聊天框。
- **Project type:** 高密度 Web 应用（Vue 3 + Naive UI），多面板工作台 + 数据可视化。

## Aesthetic Direction

- **Direction:** **墨青 Studio（Ink Teal Studio）** — 以墨色纸感为底、青绿为导航与主行动色，强调长时间阅读的冷静与专注；黑金（anchor）主题保留为品牌限定奢华变体。
- **Decoration level:** flat — **不使用装饰性 CSS 渐变**（顶栏、卡片、悬浮按钮、图谱节点等一律纯色 / 半透明实色）；图表区域填充亦为单色半透明，避免纵向色带渐变。
- **Mood:** 像一间灯光明亮的写作间：层级清晰、不抢正文，操作反馈短促明确。
- **Differentiation:** 主色采用 **青绿（teal）** 而非通用靛紫，与「墨」字语义一致；正文与小说预览保留 **衬线（Noto Serif SC）** 与宽松行高。

## Typography

| Role | Font | Rationale |
|------|------|-----------|
| UI / 界面 | **Plus Jakarta Sans** + **Noto Sans SC** | 现代几何无衬线 + 中文黑体回退，避免 Inter 作为第一选择。 |
| 小说正文 / `.novel-content` | **Noto Serif SC** | 中文长篇阅读舒适，与 UI 无衬线形成层次。 |
| Mono / 数据 / 代码 | **JetBrains Mono** | 等宽、tabular nums。 |

- **Loading:** `frontend/index.html` 经 `fonts.loli.net` 引入（国内可用）。
- **Scale:** `--font-size-xs` 12px → `--font-size-xl` 18px；正文 14px，小说区 16px。

## Color

- **Approach:** balanced — 品牌色克制，语义色（成功/警告/危险）保持独立可读性。
- **Primary（亮色）:** `#0d9488`（teal-600）— 主按钮、链接、聚焦环、图谱主色。
- **Primary（暗色）:** `#2dd4bf`（teal-400）— 暗底上保证对比。
- **Neutrals:** 沿用 `--app-text-*` 与 `--app-surface-*` slate 系，页面底 `#eef1f6`（亮）/ `#121826`（暗）。
- **Semantic:** success / warning / danger / info 见 `main.css` 中 `--color-*`。
- **Anchor（黑金）:** 仍以 `--color-anchor` 金铜为主品牌，不与默认墨青混用。

## Spacing

- **Base unit:** 4px。
- **Density:** comfortable（写作场景避免过密）。
- **Scale:** 2 / 4 / 8 / 16 / 24 / 32 / 48 / 64（与现有 `--app-radius-*` 一致）。

## Layout

- **Approach:** hybrid — 工作台内多栏网格对齐；营销式首页可用居中 hero，但以现有 StatsSidebar + 容器为准。
- **Max content width:** 首页主列 `max-width: 1080px`（`--layout-content-max`），副标题约 `46ch` 行长。
- **首页：** 主内容区使用 `clamp` 页边距；「我的书目」区标题条 `position: sticky`，长列表时仍可操作搜索与批量。
- **工作台：** 左栏章节列表默认约 20% 宽，中间写作区约 58%，右侧设置约 22%（`n-split` 可调）。
- **侧栏：** 数据概览区单独滚动，快捷操作与页脚固定在侧栏底部。
- **Border radius:** sm 8 / md 10 / lg 14 / xl 20。

## Motion

- **Approach:** minimal-functional。
- **Duration:** 微交互 150–250ms；主题切换约 300ms（见 `main.css` View Transition / `.theme-transitioning`）。
- **Easing:** `cubic-bezier(0.4, 0, 0.2, 1)`。

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-20 | 默认品牌由靛蓝改为墨青（teal），统一 Naive UI 与 CSS 变量 | 消除 `#2563eb` / `#4f46e5` 分叉，贴合「墨枢」命名并减少通用 AI 紫蓝审美 |
| 2026-04-20 | UI 主字体采用 Plus Jakarta Sans | design-consultation：避免 Inter 作为首选展示字体 |
| 2026-04-20 | 保留 light / dark / anchor 三轨主题 | 与现有 `themeStore` 与黑金主播场景兼容 |
| 2026-04-20 | 全站 UI 去渐变，统一实色令牌 | 与「墨青」冷静写作间一致；张力条等语义条改为单色（如琥珀）而非多色渐变带 |

---

**维护约定：** 新增 UI 须使用 `var(--color-brand)`、`var(--app-text-primary)` 等令牌；禁止新增硬编码靛紫作为品牌色。可视化（ECharts / 关系图）默认节点浅色底使用与 brand 一致的青色系。
