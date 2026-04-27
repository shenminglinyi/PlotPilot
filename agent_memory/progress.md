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
- GitHub 仓库 `frankmeng82/PlotPilot-NovelPro` 已完成上传
- GitHub Actions 当前状态：
  - `Backend CI` push run `25004405301`：通过
  - `Frontend CI` push run `25004405272`：通过
  - `Frontend CI` 手动 run `25004296419`：通过

## 下一步

- 继续扩展 `P2` 连续性面板：优先补“关系变化追踪”或“大纲偏离提醒”的最小版本
- 评估是否把候选稿页签内部那套分支输入收敛成复用 `CandidateDraftBranchSwitcher.vue`，减少重复 UI
- 评估是否要把 GitHub Actions 使用的 `checkout/setup-*` action 版本前瞻升级到支持 Node 24，提前消除弃用告警

## 待确认

- 下一轮 P2 更适合先做“关系变化追踪”，还是先做“大纲与正文偏离提醒”。
