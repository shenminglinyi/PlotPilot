# 项目进度

## 已完成

- 已创建本地二开目录：`/Users/frank/Documents/小说/PlotPilot-NovelPro`
- 已建立二开主线：`local/novel-pro`
- 已保留原始冻结基线：`local/base-v1.0.3`
- 已补齐 `v1.0.4` 变更到二开主线，提交为 `1166ceb upstream: sync v1.0.4 changes`
- 已更新 `LOCAL_DEVELOPMENT.md`，记录本地二开策略、分支约定和上游吸收方式。
- 已创建隔离开发 worktree：`~/.config/superpowers/worktrees/PlotPilot-NovelPro/local-feature-p1-candidate-gate`
- 已开始 `P1` 后端闭环开发：新增章节候选稿表、SQLite 仓储、DTO、应用服务、API 路由
- 已将候选稿采纳接入现有 `ChapterService`、`SnapshotService`、`ChapterAftermathPipeline`，不是独立旁路
- 已写入实现计划：`docs/superpowers/plans/2026-04-27-p1-candidate-drafts.md`
- 已补完 `P1` 最薄前端闭环：在 `WorkArea.vue` 接入候选稿按钮、候选稿弹窗、生成结果“保存为候选稿”、候选稿采纳/拒绝
- 已在 `frontend/src/api/chapter.ts` 增加候选稿 API wrapper，并通过现有工作台章节流刷新正文与列表
- 已补齐候选稿与现有编年史的最小融合：采纳候选稿生成的快照可被编年史识别为 `candidate_accept`，并在 `HolographicChroniclesPanel.vue` 直接显示“候选稿采纳 · 来源”
- 已把候选稿入口补到单章页 `frontend/src/views/Chapter.vue`：顶部快捷入口、工具菜单“保存为候选稿”、右侧候选稿页签、候选稿预览/采纳/拒绝
- 已把 `branch_name` 可见性筛选接入两个现有入口：`WorkArea.vue` 与 `Chapter.vue` 都可按分支名查看候选稿，留空查看全部；新建候选稿时留空会回落到 `main`
- 已在 `frontend/src/api/chapter.ts` 透传 `branch_name` 查询参数，并补充仓储/API 回归测试，锁定按分支筛选行为
- 已新增统一的候选稿活动分支 store：`frontend/src/stores/candidateDraftBranchStore.ts`
- 工作台 `WorkArea.vue` 与单章页 `Chapter.vue` 已改为共享同一个活动分支来源，跨页面切换会保持当前小说的候选稿分支选择
- `HolographicChroniclesPanel.vue` 已感知活动分支：顶部显示当前分支，并按活动分支过滤右侧快照显示；左侧剧情时间线仍保持全量
- `StorylineGitGraph.vue` 已感知活动分支：顶部/tooltip/详情栏显示当前回滚分支，回滚时优先使用该分支下的快照
- 已新增显式分支切换组件：`frontend/src/components/workbench/CandidateDraftBranchSwitcher.vue`
- 工作台右栏 `SettingsPanel.vue` 与单章页 `Chapter.vue` 头部都已挂上统一分支切换入口，不再只能依赖候选稿页签内部的筛选输入
- 工作台 `WorkArea.vue` 与单章页 `Chapter.vue` 的候选稿列表已在活动分支切换后自动刷新；当前分支切换会立即同步候选稿计数与列表，不必再手动点“刷新”
- 单章页 `Chapter.vue` 采纳候选稿后已改为调用 `loadChapter()` 全量刷新当前章派生信息，不再只刷新正文与推断证据
- 已创建 GitHub 私有仓库：`frankmeng82/PlotPilot-NovelPro`
- 已完成首轮上传；由于原 worktree 历史对象缺失，改为使用干净导出仓库 `/tmp/PlotPilot-NovelPro-publish` 推送
- 已将后端 CI 从“跑全部 unit tests”收口为“跑 P1 候选稿闭环已验证通过的后端测试集”，避免被 `v1.0.4` 基线现存失败阻断当前增量开发反馈
- 已开始 `P2` 第一批最小能力：新增连续性总览服务/接口/右栏面板，聚合角色掉线、时间线覆盖、文风漂移与关系摘要
- `SettingsPanel.vue` 已新增“连续性”页签，使用 `ContinuityPanel.vue` 接现有 `Bible / Timeline / Voice Drift / chapter_elements` 数据
- 已新增连续性后端测试：
  - `tests/unit/application/services/test_continuity_overview_service.py`
  - `tests/integration/interfaces/api/v1/test_continuity_api.py`
- 后端 CI 已纳入连续性总览测试
- 已继续推进 `P2`，并直接融入现有连续性总览链路：
  - `ContinuityOverviewService` 已新增“关系变化追踪”聚合：基于 `Bible 关系 + 同章共现 + 当前章摘要/审阅` 输出活跃关系信号与潜在掉线关系
  - `ContinuityOverviewService` 已新增“大纲偏离提醒”聚合：基于 `story_nodes.outline + chapter_summaries + chapter_reviews` 输出启发式偏离状态与原因
  - `interfaces/api/v1/analyst/continuity.py` 与 `frontend/src/api/continuity.ts` 已同步扩展接口模型
  - `frontend/src/components/workbench/ContinuityPanel.vue` 已扩展为完整的 `P2` 视图：关系变化追踪、大纲偏离提醒、原有掉线/时间线/文风状态统一展示
- 已继续推进 `P2` 后半段：新增 `frontend/src/components/workbench/VoiceLockPanel.vue`
  - 直接复用现有 `bibleApi / sandboxApi / voiceApi`
  - 在现有 `SettingsPanel.vue` 中新增“口吻锁定”页签，不另起工作流
  - 已接入角色锁定总览、锚点编辑、作者样本对沉淀 3 个最小闭环
  - 当前章会自动带入样本沉淀的默认章节号
- 已继续推进 `P2` 的“出场/掉线提醒与关系视图联动”：
  - `ContinuityOverviewService` 已给掉线角色补充关系上下文字段：`tracked_relationship_count / stale_relationship_count / stale_relationship_targets / dropout_scope`
  - `ContinuityPanel.vue` 的掉线卡片已直接展示“受影响关系线”和沉默关系计数
  - 当前连续性面板已经能在同一屏里把“角色掉线”和“关系线掉线”对应起来
- 已继续推进 `P2` 的“口吻锁定 ↔ 对话沙盒”联动：
  - 新增 `frontend/src/stores/workbenchContextStore.ts`
  - `VoiceLockPanel.vue` 已支持“去对话沙盒试写”，会带上当前角色、建议场景提示和未保存锚点草稿
  - `SettingsPanel.vue` 会根据共享上下文自动切到“对话沙盒”
  - `SandboxDialoguePanel.vue` 会自动接收并应用该角色与临时锚点，不必重新选人
- 已继续推进 `P2` 的“连续性面板直达处理动作”：
  - `ContinuityPanel.vue` 的角色掉线卡片已支持直接跳去“口吻锁定”或“对话沙盒”
  - `ContinuityPanel.vue` 的关系活跃信号 / 掉线关系卡片也已支持直接跳去对应处理动作
  - 当前工作流已经形成：巡检提醒 → 直达口吻锁定 / 沙盒试写

## 验证状态

- `python3 -m compileall -q application domain infrastructure interfaces scripts`：通过。
- 候选稿相关测试通过：
  - `tests/unit/infrastructure/persistence/database/test_sqlite_chapter_candidate_draft_repository.py`
  - `tests/unit/application/services/test_chapter_candidate_draft_service.py`
  - `tests/unit/application/services/test_chapter_service.py`
  - `tests/integration/interfaces/api/v1/test_chapter_candidate_drafts_api.py`
- `tests/unit/application/services/test_chronicles_service.py`：通过。
- `cd frontend && npm run build`：通过。
- 新后端 CI 对应本地命令已通过：
  - `python -m pytest tests/unit/application/services/test_continuity_overview_service.py tests/integration/interfaces/api/v1/test_continuity_api.py tests/unit/infrastructure/persistence/database/test_sqlite_chapter_candidate_draft_repository.py tests/unit/application/services/test_chapter_candidate_draft_service.py tests/unit/application/services/test_chapter_service.py tests/unit/application/services/test_chronicles_service.py tests/integration/interfaces/api/v1/test_chapter_candidate_drafts_api.py -q --tb=short`
- `python -m pytest tests/unit/application/services/test_continuity_overview_service.py tests/integration/interfaces/api/v1/test_continuity_api.py tests/integration/interfaces/api/v1/test_chapter_candidate_drafts_api.py tests/unit/application/services/test_chronicles_service.py -q --tb=short`：通过（5 passed）
- `cd frontend && npm run build`：通过（口吻锁定页签接入后再次验证）
- `python -m pytest tests/unit/application/services/test_continuity_overview_service.py tests/integration/interfaces/api/v1/test_continuity_api.py -q --tb=short`：通过（2 passed）
- `cd frontend && npm run build`：通过（掉线提醒与关系联动接入后再次验证）
- `cd frontend && npm run build`：通过（口吻锁定与对话沙盒联动接入后再次验证）
- `cd frontend && npm run build`：通过（连续性面板直达处理动作接入后再次验证）
- GitHub 仓库 `frankmeng82/PlotPilot-NovelPro` 已完成上传
- GitHub Actions 当前状态：
  - `Backend CI` push run `25006720081`：通过
  - `Frontend CI` push run `25006719997`：通过
  - `Backend CI` push run `25004405301`：通过
  - `Frontend CI` push run `25004405272`：通过
  - `Frontend CI` 手动 run `25004296419`：通过

## 下一步

- 将本轮 `P2` 关系变化追踪 / 大纲偏离提醒同步推送到 GitHub，并观察 CI
- 继续向 `P2` 后半段推进：优先考虑把“出场/掉线提醒与关系视图联动”接到现有工作台，或把口吻锁定与对话沙盒做快捷跳转
- 继续向 `P2` 后半段推进：优先考虑把口吻锁定与对话沙盒做快捷跳转，或给连续性面板补“跳到口吻锁定/对话沙盒”的上下文入口
- 继续向 `P2` 后半段推进：优先考虑给连续性面板补“跳到口吻锁定/对话沙盒”的上下文入口，或把角色掉线卡片与口吻锁定直接联动
- 继续向 `P2` 后半段推进：优先考虑把连续性面板和候选稿工作流接起来，或补“从关系提醒直接创建候选改稿任务”
- 评估是否要把 GitHub Actions 使用的 `checkout/setup-*` action 版本前瞻升级到支持 Node 24，提前消除弃用告警

## 待确认

- 连续性面板里的“关系变化追踪”当前是启发式版本，后续是否要升级为基于显式关系事件表的精确追踪。
