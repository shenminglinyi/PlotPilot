# 项目风险与易错点

## 仍需注意

- GitHub 网络访问不稳定，git/zip/raw 下载都可能超时；后续补上游更新时，优先用 GitHub compare API 或小批量文件同步。
- 本地 `v1.0.4` 中少量 Tauri 图标由 `icon-source-1024.png` 重新生成，不保证与上游二进制逐字节一致；如后续需要发行安装包，再单独复核图标资源。
- 上游更新策略是“选择性吸收”，不要直接 merge/rebase 上游分支到 `local/novel-pro`。
- 番茄字体混淆已支持当前 `dc027189e0ba4cd` 字体映射；如果番茄更换字体文件或映射表，仍需重新补映射或切到更稳定的 JSON/API 来源。
- 宝塔旧库可能缺少最新 `topic_ideas` 列；已在 `DatabaseConnection` 启动前迁移中补齐当前列。后续新增选题表列时，应同步补启动前迁移，避免 `CREATE INDEX` 或仓储保存时被旧库阻断。
- 线上 AI 章节生成当前依赖 LLM 控制台配置；API Key/模型名为空时会回退 MockProvider，接口可以返回 SSE，但内容可能是测试 JSON 而不是小说正文。已改为 Kimi + DS profile，地址与模型名已配置；补 API Key 前不要把试写结果判断为真实模型质量。
- Kimi `coding-intl.dashscope.aliyuncs.com/v1` 网关支持 `/chat/completions`，但不支持 `/models`，拉模型列表会 404；后端已对该类网关做模型列表兜底，测试连接结果比模型列表更能代表真实可用性。
- 真实 LLM 选题生成可用，但 `logline` 可能直接拼入过多市场信号原文，导致一句话卖点过长。后续优化应从 prompt 约束和保存前字段压缩入手，不影响当前链路可用性。
- 新增全局悬浮 UI 组件后必须确认已在 `App.vue` 或路由根组件挂载；仅存在组件文件不代表生产构建会显示。右侧 AI 控制台/提示词广场 FAB 已恢复全局挂载。
- 高频采集/全链路测试后曾出现 SQLite `database is locked`，重启 `plotpilot-novelpro.service` 后解除。后续若复现，需要优先检查是否有长事务或后台采集与章节生成并发写入。
- NovelPro 测试区曾停留在 `local/feature-p1-candidate-gate` 分支，没有进入线上部署分支；排查“右侧新功能缺失”时必须同时检查当前部署分支、来源分支和线上 API/构建包。
- NovelPro 候选稿、连续性、口吻锁定、战力系统、模型分工等右栏重面板依赖异步组件和新增 API；合并后验证要同时跑前端构建、后端编译和对应聚焦测试，避免只看页面入口。
- NovelPro Obsidian 有两类服务：主记忆读取器不依赖 KnowledgeService，写入/同步器必须依赖 PP SQLite Knowledge 缓存。手动同步接口不能直接复用只读服务，否则会因 `knowledge_service=None` 报错。
- macOS LaunchAgent 直接执行 `~/Documents/小说/...` 下脚本会遇到 TCC/路径编码问题；定时同步类任务优先使用 `~/.local/bin` 里的 ASCII 启动脚本，把项目目录仅作为数据路径。

## 已解除

- `v1.0.3` 基线落后于上游 `v1.0.4` 的问题已处理，本地二开主线当前同步到 `v1.0.4`。
