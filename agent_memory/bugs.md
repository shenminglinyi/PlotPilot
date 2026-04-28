# 项目风险与易错点

## 仍需注意

- GitHub 网络访问不稳定，git/zip/raw 下载都可能超时；后续补上游更新时，优先用 GitHub compare API 或小批量文件同步。
- 本地 `v1.0.4` 中少量 Tauri 图标由 `icon-source-1024.png` 重新生成，不保证与上游二进制逐字节一致；如后续需要发行安装包，再单独复核图标资源。
- 上游更新策略是“选择性吸收”，不要直接 merge/rebase 上游分支到 `local/novel-pro`。
- 候选稿采纳已经复用现有 `ChapterAftermathPipeline`；后续任何 A/B、精修、外部模型写回都不要绕开这个入口，否则会再次出现“正文更新了但结构化记忆没更新”的双轨问题。
- API 集成测试会触发现有向量存储初始化；当前 worktree 只安装了 `requirements.txt`，未装 `requirements-local.txt`，因此会看到 `faiss` 缺失告警。现阶段不影响候选稿闭环测试，但后续如果要测向量相关能力，需要补本地依赖或显式 mock 掉向量层。
- 新建 worktree 默认没有 `frontend/node_modules`；前端改动验证前需要先在 worktree 下执行 `cd frontend && npm ci`，否则 `npm run build` 会因为缺少 `vue-tsc` 直接失败。
- 当前 `tests/integration/interfaces/api/v1/conftest.py` 使用 `DatabaseConnection(\":memory:\")`，而连接对象内部又按线程缓存 SQLite 连接；如果测试先在主线程手动写库、再通过 `TestClient` 走请求线程读取，容易出现“主线程有表，请求线程 no such table” 的假失败。此类用例优先写成纯单元测试，或把数据创建动作也放到请求线程侧完成。
- 连续性面板现在已有结构化关系事件和大纲节点状态入口，候选稿采纳后也会做启发式自动沉淀；但精度仍有限。后续若要更准，优先复用 `relationship_changes` 和章节审阅结果，避免另起一套抽取逻辑。
- 外部模型任务台账已有后端持久表，工作台和单章页都会同步写入；浏览器本地存储仍保留为兜底。
- 前端主流程已收束为 PP 当前 AI 单线；不要再把“复制外部提示 / 导入外部稿 / 写作模型和审稿模型分线”作为默认入口恢复。旧外部模型台账接口仅保留兼容历史数据。
- Obsidian 长期记忆现在是优先回读的主记忆层，PP SQLite Knowledge 是运行缓存。注意写后导出必须走 cache-only KnowledgeService，不能复用 Obsidian 优先读取链路，否则刚保存/采纳的新章节记忆可能被旧 Markdown 视角遮挡。
- 前端路由和 vendor 已拆包，当前构建已无大包 warning；后续继续加重面板时仍应优先懒加载，避免重新把大依赖带回首包。
- 全量后端测试已能完成收集并跑完，但仍有大量 v1.0.4 既有失败：`faiss` 缺失导致向量测试错误、旧 API 测试期待 `detail` 但当前中间件返回不同格式、旧 workflow mock 缺 `estimate_tokens`、部分 provider 测试会误触真实网络。不要把全量测试失败误判为本轮候选稿/模型分工功能失败。

## 已解除

- `v1.0.3` 基线落后于上游 `v1.0.4` 的问题已处理，本地二开主线当前同步到 `v1.0.4`。
- GitHub Actions 的 `checkout/setup-node/setup-python` 已升级到 `v6`，用于消除旧版 action 运行在 Node.js 20 兼容层的弃用告警。
- FastAPI `on_event` 生命周期弃用告警已通过 lifespan 迁移处理。
- `HTTP_422_UNPROCESSABLE_ENTITY` 常量弃用告警已改为无告警兼容写法。
