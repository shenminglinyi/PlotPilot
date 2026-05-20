# PlotPilot 架构治理路线图

> 与 `architecture-review.md` 配套；**已全部落地首轮治理**（结构 + 兼容层 + 入口收敛）。

## Phase 1 — 清理（零风险）`[x]`

- [x] P0-1 统一 Character / CharacterId（engine.core + 兼容层）
- [x] P0-2 统一 StoryPhase、ChapterStatus
- [x] P0-3 engine.application 去重（re-export runtime）
- [x] P2-3 domain.structure → domain.novel.structure

## Phase 2 — 端口与基础设施（低风险）`[x]`

- [x] P1-3 domain.ai → engine.core.ports.ai_contracts
- [x] P1 Bug LLMClient 硬编码 system（`system=` 可选）
- [x] P1-2 持久化命令类型统一 + SQLite V2 门面
- [x] P2-3 前端 bookApi 已迁移方法委托 v1（cast/knowledge/chapter/bible）

## Phase 3 — God Object 拆分（中风险）`[x]` 首轮

- [x] P1-1 `autopilot/persistence_bridge.py` + `orchestrator.py`；Daemon 委托写入通道
- [x] P1-1b `chapter_generation_facade.py` 统一章节生成入口
- [x] P2-1 `interfaces/api/v1/engine/autopilot/{control,streams,system,shared}.py`
- [x] P2-4 `interfaces/runtime/daemon_lifecycle.py` 进程管理从 main 抽出

## Phase 4 — 领域模型（高风险）`[x]` 骨架

- [x] P0-4 `domain/novel/story_projection.py` Novel→Story 投影
- [x] P2-5 `domain/world/worldbuilding_canonical.py` 读写策略（表为主）
- [x] P2-6 `domain/novel/subtext_ledger.py`
- [x] P2-7 `domain/novel/triple_core.py`
- [x] P2-8 `domain/novel/services/tension_strategy.py`

## Phase 5 — 基础设施加固`[x]` 首轮

- [x] P2-9 `infrastructure/persistence/database/db_gateway.py`
- [x] P2-10 `infrastructure/persistence/migrations/runner.py`（与 connection 迁移衔接）
- [x] P2-11 `interfaces/di/app_container.py`
- [x] P2-12 `infrastructure/ai/vector_store_lifecycle.py`
- [x] P3-7 `config/app.yaml` + `application/config_loader.py`

---

**依赖铁律**：`interface → application → domain ← infrastructure`；契约在 `engine/core`。

**后续深化**（非阻塞）：AutopilotDaemon 正文生成块继续下沉；Novel 实体字段物理删除；Alembic 替代手写 SQL 编号。