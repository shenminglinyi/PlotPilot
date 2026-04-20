# PlotPilot 设计系统（索引）

完整设计令牌、字体、动效与决策日志见仓库根目录 **[DESIGN.md](../DESIGN.md)**。

**摘要：** 默认主题为「墨青 Studio」— 主色 `#0d9488`（teal），UI 字体 **Plus Jakarta Sans** + **Noto Sans SC**，小说正文 **Noto Serif SC**。亮色 / 暗色 / 黑金（anchor）三轨与 `themeStore` 一致；Naive UI 调色板在 `frontend/src/App.vue` 与 `frontend/src/assets/styles/main.css` 中统一。

**布局：** 首页内容宽约 1080px、书目区标题粘性置顶；工作台三栏默认比例约 20% / 58% / 22%；左侧数据侧栏仅中间统计区滚动，底部快捷操作固定。
