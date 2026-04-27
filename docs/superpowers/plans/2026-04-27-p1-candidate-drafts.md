# P1 Candidate Drafts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `v1.0.4` 现有章节保存与章后管线基础上，增加“候选稿层 + 主稿采纳门”，让外部模型写回内容先进入候选区，只有采纳时才写入主章节并触发记忆更新。

**Architecture:** 保持 `chapters` 作为主稿真相表，不改现有章后管线的职责。新增 `chapter_candidate_drafts` 存候选稿，新增 repository/service/router 管理候选稿；采纳候选稿时复用现有 `ChapterService.update_chapter_by_novel_and_number`、`ChapterAftermathPipeline` 和 `SnapshotService.create_snapshot`，避免平行链路。

**Tech Stack:** FastAPI, SQLite, Python service/repository pattern, existing ChapterAftermathPipeline, pytest

---

### Task 1: 候选稿表与仓储

**Files:**
- Modify: `infrastructure/persistence/database/schema.sql`
- Create: `infrastructure/persistence/database/sqlite_chapter_candidate_draft_repository.py`
- Test: `tests/unit/infrastructure/persistence/database/test_sqlite_chapter_candidate_draft_repository.py`

- [ ] 设计 `chapter_candidate_drafts` 表：`id / novel_id / chapter_number / source / status / title / content / rationale / metadata_json / created_at / updated_at`
- [ ] 约束唯一行为：同一候选稿按 `id` 唯一，不限制同章多候选
- [ ] 写 repository 的 `create / list_by_chapter / get / update_status / delete`
- [ ] 先写 repository 单测，再实现最小代码

### Task 2: 候选稿 DTO 与应用服务

**Files:**
- Create: `application/core/dtos/chapter_candidate_draft_dto.py`
- Create: `application/core/services/chapter_candidate_draft_service.py`
- Test: `tests/unit/application/services/test_chapter_candidate_draft_service.py`

- [ ] 定义 DTO：对外暴露候选稿基础字段
- [ ] 定义 service：`create_draft / list_drafts / get_draft / reject_draft`
- [ ] 增加 `accept_draft_as_primary`：内部调用现有章节更新能力，不自己重复写主稿逻辑
- [ ] 保持 service 只编排，不直接运行 HTTP 层背景任务

### Task 3: 采纳主稿闭环

**Files:**
- Modify: `application/core/services/chapter_service.py`
- Modify: `interfaces/api/dependencies.py`
- Test: `tests/unit/application/services/test_chapter_service.py`

- [ ] 给 `ChapterService` 增加一个“按章节号更新并返回 domain chapter / dto 所需信息”的复用入口，避免候选稿采纳走重复逻辑
- [ ] 在依赖注入中新增 `get_chapter_candidate_draft_service`
- [ ] 采纳主稿后调用现有 `SnapshotService.create_snapshot`，生成一条 `MANUAL` 快照，名称带章节号与候选稿来源
- [ ] 保持现有普通章节保存接口不变，避免影响上游兼容性

### Task 4: 候选稿 API

**Files:**
- Create: `interfaces/api/v1/core/chapter_candidate_drafts.py`
- Modify: `interfaces/main.py`
- Test: `tests/integration/interfaces/api/v1/test_chapter_candidate_drafts_api.py`

- [ ] 新增接口：
- [ ] `POST /api/v1/novels/{novel_id}/chapters/{chapter_number}/candidate-drafts`
- [ ] `GET /api/v1/novels/{novel_id}/chapters/{chapter_number}/candidate-drafts`
- [ ] `POST /api/v1/novels/{novel_id}/chapters/{chapter_number}/candidate-drafts/{draft_id}/accept`
- [ ] `POST /api/v1/novels/{novel_id}/chapters/{chapter_number}/candidate-drafts/{draft_id}/reject`
- [ ] `accept` 路由中通过 `BackgroundTasks` 复用现有 `ChapterAftermathPipeline`

### Task 5: 最小验证

**Files:**
- Test: `tests/unit/application/services/test_chapter_service.py`
- Test: `tests/unit/application/services/test_chapter_candidate_draft_service.py`
- Test: `tests/unit/infrastructure/persistence/database/test_sqlite_chapter_candidate_draft_repository.py`
- Test: `tests/integration/interfaces/api/v1/test_chapter_candidate_drafts_api.py`

- [ ] 跑 repository 单测
- [ ] 跑 service 单测
- [ ] 跑新增 API 集成测试
- [ ] 回归现有 `tests/unit/application/services/test_chapter_service.py`
- [ ] 如时间允许，补一条“采纳后创建快照”的断言
