# PlotPilot 架构全面审查报告

> 审查视角：专业架构师  
> 审查范围：领域层、应用层、基础设施层、接口层、引擎层、前端  
> 核心结论：**系统存在严重的抽象不足、实体重复定义、层级穿透、死代码膨胀问题**，需要系统性治理

---

## 一、致命问题（P0）：实体三重复制，领域模型碎片化

### 1.1 Character 存在三份独立定义

| 位置 | 类型 | 特征 |
|------|------|------|
| `engine/core/entities/character.py` | `dataclass` | 四维心理画像 + 地质叠层 + POV防火墙 + 图谱属性（**最完整**） |
| `domain/bible/entities/character.py` | `BaseEntity` 子类 | POV防火墙 + 行为细节（**子集**） |
| `domain/character/entities/character.py` | `dataclass` | 统一角色聚合根（**中间态**） |
| `domain/cast/entities/character.py` | `dataclass` | 别名 + 图谱属性（**最小子集**） |

**问题本质**：同一领域概念（角色）被四份代码独立建模，字段有重叠也有差异。`engine/core` 版本注释明确写了"合并三版精华"，但实际上三版仍然独立存在，没有真正的统一。所有下游代码必须面对"我该 import 哪个 Character？"的困惑。

**影响**：
- 数据在不同层之间传递时需要反复转换
- 新增字段需要改四个地方
- 仓储层不知道该存哪个模型的字段
- 类型签名混乱，`character: Character` 可能是四种不同的东西

**治理方案**：
1. **以 `engine/core/entities/character.py` 为唯一权威定义**
2. `domain/bible/entities/character.py` 和 `domain/cast/entities/character.py` 改为 re-export 适配器
3. `domain/character/entities/character.py` 删除或合并入 engine/core

---

### 1.2 Chapter 存在两份独立定义

| 位置 | 类型 | 差异 |
|------|------|------|
| `domain/novel/entities/chapter.py` | `BaseEntity` 子类 | 继承 `id/created_at/updated_at`，内容通过 `ChapterContent` 值对象计算字数 |
| `engine/core/entities/chapter.py` | `dataclass` | 包含 `Paragraph` 列表、`ChapterQualityScore`、`chapter_goal`、`chapter_hook`、`tension` 计算逻辑 |

**问题本质**：`domain/novel` 版是"持久化视角"的章（面向 DB），`engine/core` 版是"引擎视角"的章（面向生成质量）。两者字段大量重叠但各有扩展，且无法互换。

**治理方案**：统一为一个 Chapter 实体，通过组合（而非继承）分离持久化关注点和引擎关注点。

---

### 1.3 StoryPhase / StoryPhase 枚举重复

| 位置 | 定义 |
|------|------|
| `domain/novel/value_objects/story_phase.py` | `StoryPhase` 枚举 + `from_progress()` |
| `engine/core/entities/story.py` | `StoryPhase` 枚举 + `from_progress()` + `allow_new_foreshadow` |

两份几乎相同的 `StoryPhase`，`engine/core` 版本更完整。`Novel.get_story_phase()` 和 `Story.determine_phase()` 做完全相同的事情。

---

### 1.4 Novel vs Story 聚合根分裂

- `domain/novel/entities/novel.py` 的 `Novel`：**4200+ 行** 的 God Object，包含自动驾驶状态机、审计快照、章后管线状态、Checkpoint指针等所有字段
- `engine/core/entities/story.py` 的 `Story`：**177 行** 的纯粹业务模型，注释说"只有业务字段，无技术/审计污染"

**问题本质**：这是最根本的抽象不足——`Novel` 把"小说是什么"和"系统如何处理小说"混在一个实体里。`Story` 试图解决这个问题，但没有完成迁移，导致两个聚合根并存。

---

## 二、严重问题（P1）：层级穿透与职责混乱

### 2.1 ContextBuilder 的构造函数是依赖注入反模式

```python
class ContextBuilder:
    def __init__(
        self,
        bible_service, storyline_manager, relationship_engine, vector_store,
        novel_repository, chapter_repository,
        plot_arc_repository=None, embedding_service=None, foreshadowing_repository=None,
        story_node_repository=None, bible_repository=None,
        chapter_element_repository=None, triple_repository=None,
        causal_edge_repository=None, character_state_repository=None,
        narrative_debt_repository=None, storyline_repository=None,
        confluence_point_repository=None, worldbuilding_repository=None,
    ):
```

**20 个构造参数**，其中 14 个是 `Optional` 的仓储。这本质上是一个 Service Locator 反模式——`ContextBuilder` 自己决定需要什么依赖，而不是由调用者注入。

更严重的是，构造函数内部还做了 lazy import + try/except 初始化 `ContextAssembler` 和 `MemoryEngine`：

```python
context_assembler = None
try:
    from application.engine.services.context_assembler import ContextAssembler
    context_assembler = ContextAssembler(...)
except Exception as _e:
    logger.warning("ContextAssembler 初始化失败: %s", _e)
```

这意味着：初始化失败被静默吞掉，`ContextBuilder` 在半残状态下仍然可用，下游无法感知关键组件缺失。

**治理方案**：
1. 引入 `ContextBuilderConfig` 值对象，将 20 个参数收敛为 3-4 个门面接口
2. 禁止构造函数内 lazy import + try/except，改用工厂方法或 DI 容器
3. 缺少关键依赖时应 `fail-fast`，而非静默降级

---

### 2.2 AutopilotDaemon 是 4200 行的 God Object

`application/engine/services/autopilot_daemon.py` 单文件 **4200+ 行**，承担了：

| 职责 | 行数占比 |
|------|---------|
| 守护进程主循环 + 状态机路由 | ~15% |
| 章节生成（节拍循环 + LLM 调用 + 字数控制） | ~35% |
| 章后管线（索引 + 伏笔 + 三元组 + 声纹） | ~20% |
| 幕级规划 + 宏观规划 | ~10% |
| 审计（文风漂移 + Anti-AI） | ~10% |
| 工具函数 + 状态管理 | ~10% |

这个文件几乎是一个"单体应用"——所有生成逻辑、状态管理、持久化、SSE推送全部耦合在一起。

**治理方案**：
1. 拆分为 `AutopilotOrchestrator`（纯编排）+ `ChapterGenerationService` + `PostChapterPipeline` + `PlanningService`
2. `AutopilotDaemon` 只保留轮询 + 状态机路由，不包含任何业务逻辑
3. 同时存在的 `engine/runtime/runner.py`（`StoryPipelineRunner`）应替代 daemon，而非并存

---

### 2.3 PersistenceQueue 三代并存

| 文件 | 状态 | 问题 |
|------|------|------|
| `persistence_queue.py` (V1) | 在用 | 基于 `mp.Queue` 的内存队列，进程崩溃丢数据 |
| `persistence_queue_v2.py` (V2) | 在用 | 基于 SQLite 的持久化队列，僵尸恢复 + WAL |
| `persistence_queue_adapter.py` | 兼容层 | 运行时决定用 V1 还是 V2 |

V1 和 V2 的 `PersistenceCommandType` 枚举 **各自独立定义**，字段几乎相同但不完全一致（V2 缺少 `EXECUTE_SQL`、`EXECUTE_SQL_TXN_BATCH`、`DELETE_CHAPTER`）。V1 的 handler 注册函数 `register_persistence_handlers()` 内联了 **400+ 行** 的 SQL 操作代码。

**治理方案**：
1. 统一为 V2（SQLite 持久化），删除 V1
2. `PersistenceCommandType` 只保留一份定义
3. handler 注册函数拆分为独立模块，不内联 SQL

---

### 2.4 domain/ai 层越权：领域层定义了 AI 服务接口

`domain/ai/services/llm_service.py`、`domain/ai/services/embedding_service.py`、`domain/ai/services/vector_store.py` 都在领域层定义了抽象接口。

**问题**：领域层不应知道 LLM、Embedding、VectorStore 这些技术概念。这些是 **基础设施关注点**，不是业务概念。正确的做法是领域层定义业务端口（如 `NarrativeGenerationPort`），由基础设施层实现具体对接。

`engine/core/ports/ports.py` 已经做了正确的抽象（`LLMPort`、`PersistencePort`、`EventPort`），但 `domain/ai` 的接口仍然被广泛使用，两套端口并存。

**治理方案**：
1. `domain/ai/` 整体删除，其接口合并入 `engine/core/ports/`
2. 所有 `from domain.ai.services.llm_service import LLMService` 改为 `from engine.core.ports import LLMPort`

---

### 2.5 Worldbuilding 与 Bible.world_settings 双存储混乱

世界观数据同时存储在两个地方：
- `worldbuilding` 表：ORM 15 槽位（`power_system`, `terrain`, `politics` 等）
- `Bible.world_settings` 列表：灵活存储所有字段（含 LLM 扩展字段）

读取时需要 `worldbuilding_merge.py` 做合并投影：

```python
def merge_worldbuilding_table_and_bible_slices(wb_table_data, bible_world_settings):
    """合并 worldbuilding 表和 Bible.world_settings 的数据"""
```

**问题本质**：同一份数据存两份，用合并逻辑对齐。这是 **CQRS 的反面教材**——不是读写分离，而是写写冗余。

**治理方案**：
1. 世界观数据只存一处，推荐 `worldbuilding` 表（结构化、可查询）
2. LLM 扩展字段存入 `worldbuilding_extensions` JSON 列
3. 删除 `worldbuilding_merge.py` 的合并逻辑

---

### 2.6 domain/structure 是孤岛

`domain/structure/` 目录包含 `chapter_element.py`、`chapter_scene.py`、`story_node.py` 三个模型，与 `domain/novel/entities/` 和 `domain/novel/value_objects/` 中的模型高度重叠：

| structure 模型 | novel 等价物 |
|---------------|-------------|
| `ChapterScene` | `Scene` (value_objects/scene.py) |
| `ChapterElement` | 无直接等价，但职责被 `chapter_element_repository` 覆盖 |
| `StoryNode` | 与 `domain/novel/entities/` 的章节概念重叠 |

**治理方案**：`domain/structure/` 整体删除，合并入 `domain/novel/`。

---

## 三、中等问题（P2）：engine 目录双倍复制 + 死代码

### 3.1 engine/ 的 application/ 与 runtime/ 是 1:1 复制

```
engine/
  application/
    checkpoint_manager/manager.py      ←→  runtime/checkpoint_manager/manager.py
    plot_state_machine/state_machine.py ←→  runtime/plot_state_machine/state_machine.py
    quality_guardrails/quality_guardrail.py ←→ runtime/quality_guardrails/quality_guardrail.py
    quality_guardrails/language_style_guardrail.py ←→ ...
    quality_guardrails/character_consistency_guardrail.py ←→ ...
    quality_guardrails/plot_density_guardrail.py ←→ ...
    quality_guardrails/naming_guardrail.py ←→ ...
    quality_guardrails/viewpoint_guardrail.py ←→ ...
    quality_guardrails/rhythm_guardrail.py ←→ ...
    writing_orchestrator.py            ←→  runtime/writing_orchestrator.py
```

经逐行比对，`engine/application/writing_orchestrator.py` 与 `engine/runtime/writing_orchestrator.py` **几乎逐字相同**，唯一区别是 import 路径（`engine.application.` vs `engine.runtime.`）。`quality_guardrail.py` 同理。

**问题本质**：这是典型的"不敢删旧代码"导致的复制膨胀。`runtime/` 本应是 `application/` 的运行时适配，但实际上只是换了个包名的镜像。

**治理方案**：
1. 保留 `engine/application/`，删除 `engine/runtime/`（除 `runner.py` 和 `policy_validator.py`）
2. `runner.py` 的 import 改为指向 `engine/application/`

---

### 3.2 死代码清单

以下文件/模块经审查判定为 **可安全删除**：

| 路径 | 原因 |
|------|------|
| `engine/runtime/quality_guardrails/` (8 个文件) | 与 `engine/application/quality_guardrails/` 逐字重复 |
| `engine/runtime/writing_orchestrator.py` | 与 `engine/application/writing_orchestrator.py` 逐字重复 |
| `engine/runtime/checkpoint_manager/` | 与 `engine/application/checkpoint_manager/` 重复 |
| `engine/runtime/plot_state_machine/` | 与 `engine/application/plot_state_machine/` 重复 |
| `domain/ai/` 整个目录 | 接口应由 `engine/core/ports/` 统一，实现已在 `infrastructure/ai/` |
| `domain/structure/` 整个目录 | 与 `domain/novel/` 重叠 |
| `domain/cast/entities/character.py` | 与 `engine/core/entities/character.py` 重复 |
| `domain/bible/entities/character.py` | 与 `engine/core/entities/character.py` 重复 |
| `domain/character/` 整个目录 | 中间态产物，应合并入 `engine/core/` |
| `application/engine/services/persistence_queue.py` (V1) | V2 已实现持久化，V1 应淘汰 |
| `infrastructure/persistence/in_memory_novel_repository.py` | 开发期遗留，生产无用 |
| `engine/examples/` | 示例代码，不应在主仓库中 |
| `data/logs/prompt_v2_tests/` | 测试输出残留 |
| `data/chromadb/` 下的多个旧 collection | 历史数据残留，至少 8 个过期 collection |

---

## 四、接口层问题

### 4.1 autopilot_routes.py 是 2500 行的巨型路由

`interfaces/api/v1/engine/autopilot_routes.py` 单文件 **2500+ 行**，包含：
- 自动驾驶启停
- SSE 生成流
- 审阅确认
- 章节删除
- 日志读取
- LLM 配置热更新
- 进度查询
- 故事结构同步

**治理方案**：按职责拆分为 `autopilot_control.py`、`autopilot_sse.py`、`autopilot_review.py`、`autopilot_admin.py`。

### 4.2 路由直接操作数据库

`autopilot_routes.py` 中多处直接使用 `get_database().execute(sql)` 执行 SQL：

```python
db = get_database()
db.execute("UPDATE novels SET autopilot_status = ?, ...", (status, novel_id))
```

这违反了分层架构——接口层应只调用应用服务，不直接操作数据源。

**治理方案**：所有 DB 操作通过 Repository 或 StatePublisher 进行。

### 4.3 main.py 承担了过多的进程管理职责

`interfaces/main.py` 包含：
- 进程清理（PowerShell/wmic 扫描）
- 守护进程启停
- 共享状态初始化
- AOF 崩溃恢复
- WAL checkpoint
- 看门狗线程
- SIGBREAK 处理

这些应该由独立的 `ProcessManager` 或 `DaemonSupervisor` 承担，而非混在 FastAPI 应用入口中。

---

## 五、基础设施层问题

### 5.1 Prompt 管理系统碎片化

当前存在三套 Prompt 管理机制并存：

| 机制 | 位置 | 状态 |
|------|------|------|
| `prompt_packages/` (CPMS) | `infrastructure/ai/prompt_packages/` | 在用，52 个节点 |
| `prompt_registry.py` | `infrastructure/ai/prompt_registry.py` | 在用，CPMS 的运行时 |
| `prompts/` (旧版) | `infrastructure/ai/prompts/` | 残留，仅 README |
| `prompt_seed/` | `infrastructure/ai/prompt_seed/` | 残留，导出旧版用 |

`context_builder.py` 中 `build_beat_prompt()` 还直接从 `PromptRegistry` 读取指令并做字符串拼接，绕过了 CPMS 的模板渲染。

### 5.2 仓储层缺少统一接口

`infrastructure/persistence/database/` 下有 **30+ 个** `sqlite_*_repository.py`，但没有统一的 `Repository` 基类或接口。每个仓储各自实现 `save()`、`get_by_id()` 等方法，签名不统一。

### 5.3 连接管理分散

数据库连接通过 `get_database()` 全局单例获取，但 `get_db_path()`、`get_connection_pool()`、`get_database()` 三条路径并存，导致：
- 有时传入 `db_path`，有时不传
- `connection_pool.py` 和 `connection.py` 职责重叠
- `write_dispatch.py` 引入了 writer thread 绑定机制，进一步增加了复杂度

---

## 六、前端架构问题

### 6.1 Store 数量过多且职责不清

前端有 10 个 Pinia Store，但多个 Store 之间存在交叉依赖：

| Store | 问题 |
|-------|------|
| `autopilotWorkspaceStore` | 包含了生成、规划、审阅等所有自动驾驶状态 |
| `workbenchRefreshStore` | 仅做刷新控制，职责过小 |
| `dagStore` + `dagRunStore` | DAG 相关状态拆成了两个 Store |
| `nodeEditorStore` | 与 `dagStore` 高度耦合 |

`autopilotWorkspaceStore` 是前端的 God Object，对应后端 `AutopilotDaemon` 的问题。

### 6.2 API 调用未统一

前端组件中存在直接 `fetch()` 调用和 `apiClient` 调用两种方式并存的情况。部分组件甚至直接拼接 URL，缺少类型安全的 API 层。

### 6.3 Composables 复用不足

只有 4 个 Composable，其中 `useWorkbench` 和 `useWorkbenchNarrativeSync` 职责边界模糊。很多本应抽取为 Composable 的逻辑（如 SSE 连接管理、自动保存）散落在组件中。

---

## 七、理想态架构蓝图

### 7.1 领域模型统一

```
engine/core/
  entities/
    story.py          ← 唯一聚合根（替代 Novel + Story）
    chapter.py        ← 统一 Chapter（含质量评分 + 持久化字段）
    character.py      ← 唯一 Character（四维 + POV + 图谱）
    foreshadow.py     ← 伏笔
    plot_arc.py       ← 剧情弧光
  value_objects/
    story_phase.py    ← 唯一 StoryPhase
    beat.py           ← 微观节拍
    character_mask.py
    checkpoint.py
    emotion_ledger.py
  ports/
    ports.py          ← 唯一端口定义（替代 domain/ai/）
```

### 7.2 Novel 聚合根拆分

当前 `Novel` 是 God Object，应拆分为：

```
Story (聚合根)                    ← 纯业务：标题、梗概、章节、角色、故事阶段
  ├── AutopilotState (值对象)     ← 自动驾驶：stage、beat_index、error_count
  ├── AuditSnapshot (值对象)      ← 审计快照：tension、quality_scores
  └── GenerationPrefs (值对象)    ← 生成偏好：target_words、genre、era
```

### 7.3 应用服务分层

```
application/
  engine/
    orchestrator/
      autopilot_orchestrator.py    ← 纯编排，不含业务逻辑
      chapter_generation_service.py ← 章节生成（节拍循环 + LLM）
      post_chapter_pipeline.py     ← 章后管线（索引 + 伏笔 + 三元组）
    planning/
      planning_service.py          ← 规划（宏观 + 幕级）
    context/
      context_builder.py           ← 上下文构建（依赖 ≤ 5 个接口）
      budget_allocator.py
    quality/
      quality_guardrail.py         ← 质量守门人
    persistence/
      persistence_queue.py         ← 唯一队列（V2，删除 V1）
      state_publisher.py
```

### 7.4 依赖注入改革

**当前**：每个 Service 手动 new 依赖，20+ 参数构造函数  
**理想态**：

```python
# 定义 Protocol 接口
class CharacterProvider(Protocol):
    def get_characters(self, novel_id: str) -> List[Character]: ...

class ContextProvider(Protocol):
    def build_context(self, novel_id: str, chapter: int, ...) -> str: ...

# Service 只声明所需接口
class ChapterGenerationService:
    def __init__(self, llm: LLMPort, characters: CharacterProvider, context: ContextProvider):
        self._llm = llm
        self._characters = characters
        self._context = context
```

### 7.5 接口层改革

```
interfaces/api/v1/engine/
  autopilot/
    control.py       ← 启停 + 状态查询
    generation.py    ← SSE 生成流
    review.py        ← 审阅确认
    admin.py         ← 配置热更新 + 日志
```

**铁律**：路由文件 ≤ 300 行，禁止直接 SQL，所有操作走应用服务。

### 7.6 进程管理独立

```
application/engine/
  daemon/
    supervisor.py    ← 进程管理（启停 + 清理 + 看门狗）
    shared_state.py  ← 共享状态管理
```

`main.py` 只做 FastAPI 应用配置，进程管理完全委托给 `supervisor.py`。

### 7.7 前端架构改革

```
stores/
  novelStore.ts          ← 小说 CRUD（替代碎片化的多个 Store）
  generationStore.ts     ← 生成状态（SSE + 节拍进度）
  worldStore.ts          ← 世界观 + 人物 + 地点
  engineStore.ts         ← DAG + 检查点 + 质量

composables/
  useSSE.ts              ← SSE 连接管理（统一）
  useAutopilot.ts        ← 自动驾驶控制
  useGeneration.ts       ← 生成流程
  useWorldEditing.ts     ← 世界观编辑

api/
  generated/             ← OpenAPI 自动生成的类型安全客户端
```

---

## 八、治理优先级路线图

| 阶段 | 目标 | 工作量 | 风险 |
|------|------|--------|------|
| **P0-1** | 统一 Character（删除 3 份重复） | 2 天 | 低：改 import 路径 |
| **P0-2** | 统一 StoryPhase + Chapter | 1 天 | 低 |
| **P0-3** | 删除 `engine/runtime/` 镜像 | 1 天 | 低 |
| **P1-1** | 拆分 AutopilotDaemon（4200→500 行） | 5 天 | 中：需要回归测试 |
| **P1-2** | 统一持久化队列（删除 V1 + adapter） | 2 天 | 中 |
| **P1-3** | 删除 `domain/ai/`，统一到 `engine/core/ports/` | 2 天 | 中 |
| **P1-4** | Worldbuilding 双存储合一 | 3 天 | 中 |
| **P2-1** | Novel 拆分为 Story + 值对象 | 5 天 | 高：DB migration |
| **P2-2** | 拆分 autopilot_routes | 2 天 | 低 |
| **P2-3** | 删除死代码（`domain/structure/`、`in_memory`、examples） | 1 天 | 低 |
| **P2-4** | main.py 进程管理独立 | 2 天 | 中 |

---

## 九、量化总结

| 指标 | 当前 | 理想态 | 降幅 |
|------|------|--------|------|
| Character 定义数 | 4 | 1 | **-75%** |
| Chapter 定义数 | 2 | 1 | **-50%** |
| StoryPhase 定义数 | 2 | 1 | **-50%** |
| engine/ 镜像文件 | ~10 | 0 | **-100%** |
| AutopilotDaemon 行数 | 4200+ | ~500 | **-88%** |
| 持久化队列版本 | 3 (V1+V2+Adapter) | 1 | **-67%** |
| autopilot_routes 行数 | 2500+ | ~300/文件 | **-88%** |
| main.py 非路由代码占比 | ~70% | ~10% | **-86%** |
| 可删除死代码文件 | ~20 | 0 | — |

**核心诊断**：系统的问题不是功能不够，而是抽象没有收敛。每一层都在"自己造轮子"而非复用下层，导致模型爆炸、维护成本指数增长。治理的第一步不是加新代码，而是 **删重复、统接口、降耦合**。

---

## 十、深度代码审查补充（第2轮）

### 10.1 ChapterAftermathPipeline 又一个构造函数膨胀

```python
class ChapterAftermathPipeline:
    def __init__(
        self,
        knowledge_service,
        chapter_indexing_service,
        llm_service,
        voice_drift_service=None,
        triple_repository=None,
        foreshadowing_repository=None,
        storyline_repository=None,
        chapter_repository=None,
        plot_arc_repository=None,
        narrative_event_repository=None,
        causal_edge_repository=None,    # V8 Feed-forward
        character_state_repository=None, # V8 Feed-forward
        debt_repository=None,
        bible_repository=None,
        unified_checkpoint_service=None,
        prop_lifecycle_syncer=None,
    ):
```

**16 个构造参数**，与 `ContextBuilder` 同出一辙。这是系统性的反模式——每个管线服务都把所有可能的仓储都塞进构造函数，"以防万一"。

更严重的是，`run_after_chapter_saved()` 内部做了 lazy import：

```python
from application.world.services.chapter_narrative_sync import sync_chapter_narrative_after_save
```

函数级别的 lazy import 意味着：每次调用都重新解析模块，且无法在启动时发现依赖缺失。

**治理方案**：同 ContextBuilder——引入 Protocol 接口，构造参数 ≤ 5 个。

---

### 10.2 AutoNovelGenerationWorkflow 是另一个 God Object

`application/workflows/auto_novel_generation_workflow.py` **2200+ 行**，承担了：
- 章节上下文组装
- 节拍提示词构建
- LLM 调用与流式生成
- 散文聚合 + 纪律检查
- 空间一致性守门
- 微观场景上下文管理
- 重试与升级策略

这个文件与 `AutopilotDaemon` 存在严重的 **功能重叠**——`AutopilotDaemon` 内部也调用了类似的生成逻辑，而 `AutoNovelGenerationWorkflow` 则是 HTTP 触发时的入口。两条路径做同样的事，但代码不同步。

**治理方案**：统一为唯一的 `ChapterGenerationService`，daemon 和 HTTP 都调用同一个服务。

---

### 10.3 StoryPipelineRunner 与 AutopilotDaemon 双轨并存

`engine/runtime/runner.py` 的 `StoryPipelineRunner` 明确注释了"替代 AutopilotDaemon"，但两者并存运行。Runner 继承了 `BaseStoryPipeline`，通过 `_step_xxx()` 方法组织管线——这是正确的方向。但 `AutopilotDaemon` 仍然是实际在用的入口。

**问题**：Runner 的代码无人维护，与 Daemon 的逻辑已经分叉。任何 bug 修复只在 Daemon 中进行，Runner 逐渐腐烂。

**治理方案**：
1. 短期：将 Runner 标记为 `@deprecated`，停止维护
2. 长期：按照 Runner 的设计思想拆分 Daemon，然后删除 Runner

---

### 10.4 MemoryEngine 依赖 domain/ai 而非 engine/core/ports

`MemoryEngine` 直接导入 `domain.ai.services.llm_service.LLMService` 和 `domain.ai.value_objects.prompt.Prompt`：

```python
from domain.ai.services.llm_service import LLMService, GenerationConfig
from domain.ai.value_objects.prompt import Prompt
```

这与 `engine/core/ports/ports.py` 的 `LLMPort` 和 `PromptValue` 完全重复。`domain/ai` 和 `engine/core/ports` 有两套独立的 `GenerationConfig`、`GenerationResult`：

| 概念 | domain/ai | engine/core/ports |
|------|-----------|-------------------|
| 提示词 | `Prompt` | `PromptValue` |
| 生成配置 | `GenerationConfig`(含 `model`、`response_format`) | `GenerationConfig`(含 `stop_sequences`) |
| 生成结果 | `GenerationResult`(含 `token_usage: TokenUsage`) | `GenerationResult`(含 `token_count: int`) |
| 抽象接口 | `LLMService` | `LLMPort` |

两者 **字段不兼容**，无法互换。`domain/ai` 版本更偏 OpenAI 风格，`engine/core/ports` 版本更抽象。

**治理方案**：统一为 `engine/core/ports/LLMPort` + `PromptValue` + `GenerationConfig`，删除 `domain/ai` 版本。

---

### 10.5 Worldbuilding 实体是贫血模型 + 属性冗余

`domain/worldbuilding/worldbuilding.py` 的 `Worldbuilding` dataclass：
- 15 个字符串字段 + 4 个 `@property` 分组方法 + 1 个 `to_dict()`
- `@property` 分组方法返回的 dict 与 `to_dict()` 中的嵌套结构 **完全重复**
- 零业务逻辑：没有任何验证、计算或状态转换方法
- 所有关键字都是 `str = ""`，没有类型区分

**治理方案**：
1. 使用 `WorldbuildingDimension` 值对象替代扁平字段
2. `to_dict()` 只需返回分组结构，不需要手动列举每个字段两次
3. 加入验证逻辑（如 `power_system` 不能超过 500 字等）

---

### 10.6 NovelStage vs StoryPhase 双状态机

系统中存在两个描述"故事阶段"的枚举：

| 枚举 | 位置 | 值 | 用途 |
|------|------|---|------|
| `NovelStage` | `domain/novel/entities/novel.py` | PLANNING, MACRO_PLANNING, ACT_PLANNING, WRITING, AUDITING, REVIEWING, PAUSED_FOR_REVIEW, COMPLETED | **自动驾驶状态机**（"系统在做什么"） |
| `StoryPhase` | `engine/core/entities/story.py` | OPENING, DEVELOPMENT, CONVERGENCE, FINALE | **故事生命周期**（"剧情在哪个阶段"） |

两者语义不同但容易混淆。`NovelStage` 是技术状态（"正在规划"/"正在写"/"正在审计"），`StoryPhase` 是业务阶段（"开局期"/"发展期"/"收敛期"）。命名不够区分——`NovelStage` 应改名为 `AutopilotStage` 或 `GenerationPhase`。

---

### 10.7 ConsistencyChecker 使用了错误的 CharacterId

```python
from domain.bible.value_objects.character_id import CharacterId
```

而不是使用 `engine/core/entities/character.py` 的 `CharacterId`。这意味着一致性检查器使用的角色 ID 类型与统一角色模型不同，增加了转换成本。

---

### 10.8 BaseEntity 缺少领域事件支持

`domain/shared/base_entity.py` 只有 `id`、`created_at`、`updated_at`，没有领域事件收集机制。DDD 中聚合根通常需要：

```python
class BaseEntity:
    def __init__(self, id: str):
        self.id = id
        self._domain_events: List[DomainEvent] = []
    
    def add_domain_event(self, event: DomainEvent) -> None: ...
    def clear_domain_events(self) -> List[DomainEvent]: ...
```

当前系统用 `StatePublisher` 手动推送事件，绕过了聚合根的事件收集机制，导致事件发布逻辑散落在应用服务中。

---

### 10.9 infer_kg_from_chapter 是模块级函数的反模式

`chapter_aftermath_pipeline.py` 中的 `infer_kg_from_chapter()` 是模块级独立函数，在函数体内做了完整的依赖构建：

```python
async def infer_kg_from_chapter(novel_id: str, chapter_number: int) -> None:
    from infrastructure.persistence.database.connection import get_database
    from infrastructure.persistence.database.sqlite_knowledge_repository import SqliteKnowledgeRepository
    kr = SqliteKnowledgeRepository(get_database())
    ...
```

这违反了依赖注入原则——函数自己创建依赖，不利于测试和替换。应将其改为类方法，依赖通过构造函数注入。

---

### 10.10 auto_novel_generation_workflow.py 中的 _SafeDict 工具类

```python
class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"
```

这是对 `string.Template` 或 `str.format_map` 的重新发明。`_safe_format()` 函数用 `format_map(_SafeDict(...))` 做模板渲染，绕过了 CPMS 的 `PromptTemplateEngine`。

**问题**：系统中已有两套模板引擎（`PromptTemplateEngine` 和 `_safe_format`），且互不兼容。

**治理方案**：统一使用 CPMS 的模板引擎，删除 `_SafeDict` 和 `_safe_format`。

---

## 十一、Domain 层深度审查补充（第3轮）

### 11.1 Character 四版差异详析

| 维度 | `engine/core/entities/character.py` | `domain/bible/entities/character.py` | `domain/cast/entities/character.py` | `domain/character/entities/character.py` |
|------|------|------|------|------|
| 类型 | `dataclass` | `BaseEntity` 子类 | `dataclass` | `dataclass` |
| ID 类型 | 自定义 `CharacterId` | bible `CharacterId` | cast `CharacterId` | character `CharacterId` |
| 心理画像 | ✅ 四维 + 地质叠层 | ❌ | ❌ | ❌ |
| POV 防火墙 | ✅ | ✅ | ❌ | ✅ |
| 语言指纹 | ✅ `VoiceStyle` | ❌ | ❌ | ✅ `voice_style` 字符串 |
| 图谱属性 | ✅ 别名 + faction | ❌ | ✅ 别名 | ❌ |
| 行为细节 | ✅ 口头禅 + 闲时动作 | ✅ 口头禅 + 闲时动作 | ❌ | ✅ 口头禅 + 闲时动作 |
| 创伤系统 | ✅ `CharacterPatch` | ❌ | ❌ | ❌ |
| 情感弧线 | ✅ | ❌ | ❌ | ✅ |
| 故事事件 | ❌ | ❌ | ✅ `StoryEvent` | ❌ |
| 业务方法 | ✅ `to_t0_instruction()` + `apply_trauma()` | ✅ `add_relationship()` | ✅ `add_story_event()` | ✅ `update_state()` + `to_voice_lock()` |

**关键发现**：`domain/character/entities/character.py` 是试图统一 bible 和 cast 版本的中间产物，但它没有合并 `engine/core` 版本的核心创新（四维心理画像、地质叠层、创伤系统）。四个版本之间没有一个是另一个的子集——每个版本都有其他版本缺少的字段。

**理想态**：`engine/core/entities/character.py` 是唯一权威定义。bible/cast 版本改为 re-export 适配器，`domain/character/` 删除。

---

### 11.2 CharacterId 三版不兼容

```python
# engine/core/entities/character.py
@dataclass(frozen=True)
class CharacterId:
    value: str

# domain/bible/value_objects/character_id.py
@dataclass(frozen=True)
class CharacterId:
    value: str

# domain/cast/value_objects/character_id.py
@dataclass(frozen=True)
class CharacterId:
    value: str
```

三个 `CharacterId` **结构完全相同**但属于不同的 Python 类，互不兼容。`bible.CharacterId == cast.CharacterId` 为 `False`。这意味着从一个模块传 ID 到另一个模块时需要 `CharacterId(value=old_id.value)` 手动转换。

**治理方案**：统一为 `engine/core/entities/character.py:CharacterId`，其他两个改为 re-export。

---

### 11.3 KnowledgeTriple 实体过于膨胀

`domain/knowledge/knowledge_triple.py` 的 `KnowledgeTriple` 有 **17 个构造参数**，且混合了多个关注点：

| 关注点 | 字段 |
|--------|------|
| 核心三元组 | `subject`, `predicate`, `object` |
| 来源追踪 | `chapter_id`, `source_type`, `provenance` |
| 实体绑定 | `entity_type`, `subject_entity_id`, `object_entity_id` |
| 地点信息 | `location_type`, `description` |
| 质量评估 | `importance`, `confidence` |
| 索引/标签 | `tags`, `related_chapters`, `first_appearance` |
| 扩展属性 | `attributes`, `note` |

一个三元组实体不应该包含地点类型（`location_type`）、实体描述（`description`）这些属于其他聚合根的字段。这违反了 **单一职责**。

**治理方案**：拆分为 `Triple`（核心: subject/predicate/object + provenance）+ `TripleMetadata`（索引/标签/置信度），地点信息移入 `Location` 聚合根。

---

### 11.4 BeatSheet.Scene vs ContextBuilder.Beat 语义冲突

系统中存在两个"节拍"概念：

| 类 | 位置 | 含义 |
|----|------|------|
| `Scene` | `domain/novel/value_objects/scene.py` | 节拍表中的"场景"，含 `title`, `goal`, `pov_character`, `estimated_words`, `order_index` |
| `Beat` | `application/engine/services/context_builder.py` | 微观节拍，含 `description`, `target_words`, `focus`, `expansion_hints`, `scene_goal` |

`Scene` 是 **规划阶段** 的产物（宏观：这一章有几个场景？每个什么目标？），`Beat` 是 **生成阶段** 的产物（微观：当前场景怎么写？聚焦什么？多少字？）。两者是同一管线不同阶段的表示，但 **命名容易混淆**——`Scene` 实际上更接近 `Beat` 的宏观版。

**治理方案**：
1. `Scene` 改名为 `MacroBeat` 或 `ScenePlan`，与 `Beat` 形成清晰的宏观/微观层次
2. 或者引入 `BeatSheet → Scene → Beat` 的三级结构，明确每级的粒度

---

### 11.5 Prop 聚合根是领域模型的标杆

值得注意的是 `domain/prop/entities/prop.py` 的 `Prop` 是系统中 **最接近理想态** 的聚合根：
- ✅ 有 `_pending_events` 领域事件收集
- ✅ 有 `pop_pending_events()` 事件弹出机制
- ✅ 有 `LifecycleState` 状态机 + `validate_transition()` 守卫
- ✅ 有 `apply_event()` 统一状态变更入口
- ✅ 构造参数合理（10 个，不多不少）

这是其他聚合根（`Novel`、`ForeshadowingRegistry`）应该学习的模板。

---

### 11.6 ForeshadowingRegistry 职责不清

`domain/novel/entities/foreshadowing_registry.py` 名为"伏笔注册表"，但实际包含了：
- 伏笔管理（注册、解决、放弃）
- **潜台词台账**（`SubtextLedgerEntry`）
- 章节重编号联动

潜台词和伏笔是两个不同的领域概念，不应放在同一个注册表中。

**治理方案**：拆分为 `ForeshadowingRegistry`（纯伏笔）+ `SubtextLedger`（潜台词台账）。

---

### 11.7 PlotArc 的 STEP_PHASES_DEFAULT 硬编码业务规则

`PlotArc.STEP_PHASES_DEFAULT` 将"爽文"的具体节奏参数硬编码在实体类中：

```python
STEP_PHASES_DEFAULT = {
    "daily":       {"tension_pct": 10, "weight": 0.15},
    "provocation":  {"tension_pct": 30, "weight": 0.20},
    "eruption":    {"tension_pct": 80, "weight": 0.35},
    "aftermath":   {"tension_pct": 40, "weight": 0.15},
    "settlement":  {"tension_pct": 20, "weight": 0.15},
}
```

这是 **策略模式** 的典型应用场景——不同题材（爽文、悬疑、言情）应有不同的节奏策略。硬编码在实体中导致：
- 添加新题材需要修改实体类
- 参数调优需要改代码重部署

**治理方案**：抽取为 `TensionStrategy` 接口，不同题材通过配置文件注入。`PlotArc` 只保留插值逻辑。

---

### 11.8 domain/novel/value_objects/ 的 27 个文件是过度拆分

`domain/novel/value_objects/` 目录包含 **27 个文件**，其中多个只是简单的枚举或极简 dataclass：

| 文件 | 内容 | 行数 |
|------|------|------|
| `storyline_type.py` | `StorylineType` 枚举 (3 个值) | ~10 |
| `storyline_status.py` | `StorylineStatus` 枚举 (3 个值) | ~10 |
| `storyline_role.py` | `StorylineRole` 枚举 (3 个值) | ~10 |
| `storyline_milestone.py` | `StorylineMilestone` dataclass | ~15 |
| `chapter_id.py` | `ChapterId` 值对象 | ~5 |
| `novel_id.py` | `NovelId` 值对象 | ~5 |
| `word_count.py` | `WordCount` 值对象 | ~20 |
| `tension_level.py` | `TensionLevel` 枚举 | ~10 |
| `tension_dimensions.py` | `TensionDimensions` dataclass | ~15 |

故事线相关的 4 个枚举/值对象可以合并为一个 `storyline_types.py`。ID 值对象可以合并入各自实体文件。

**治理方案**：将关联紧密的值对象合并，27 个文件收敛到 12-15 个。

---

### 11.9 Bible 聚合根缺少 invariant 保护

`domain/bible/entities/bible.py` 的 `Bible` 聚合根虽然做了重复检查（`add_character`），但：
- `remove_character` 不检查引用完整性（删除角色后故事线/伏笔可能引用该角色）
- `add_world_setting` 不验证维度字段格式
- 没有跨实体一致性验证（如角色关系引用的角色必须存在）

**治理方案**：在 `Bible` 聚合根中加入 invariant 守卫方法。

---

## 十二、接口层与前端深度审查（第4轮）

### 12.1 autopilot_routes.py 2500+ 行问题详解

逐行分析 `interfaces/api/v1/engine/autopilot_routes.py`（约 2500 行）的职责分布：

| 职责 | 行范围 | 估算行数 | 应拆分到 |
|------|--------|---------|---------|
| 自动驾驶启停 | 80-300 | ~220 | `autopilot_control.py` |
| SSE 生成流 | 300-900 | ~600 | `autopilot_sse.py` |
| 审阅确认 + 下一章 | 900-1300 | ~400 | `autopilot_review.py` |
| 日志增量读取 | 1300-1500 | ~200 | `autopilot_log.py` |
| 进度查询 | 1500-1700 | ~200 | `autopilot_control.py` |
| LLM 配置热更新 | 1700-1900 | ~200 | `autopilot_admin.py` |
| 章节删除 + 状态修复 | 1900-2200 | ~300 | `autopilot_admin.py` |
| 工具函数 | 2200-2500 | ~300 | `autopilot_utils.py` |

**具体反模式**：

1. **路由直接 new Repository**：
```python
def _has_chapter_nodes_under_current_act(novel_id, current_act_zero_based):
    repo = StoryNodeRepository(get_db_path())  # 路由函数内创建仓储
    ...
```

2. **路由直接操作 SQL**：
```python
db = get_database()
db.execute("UPDATE novels SET autopilot_status = ?, ...", (status, novel_id))
```

3. **路由内嵌复杂业务逻辑**：
`resolve_autopilot_current_chapter_number()` 是纯业务逻辑函数，不应出现在路由文件中。

---

### 12.2 main.py 的 1100+ 行问题详解

`interfaces/main.py` 约 1100 行，其中 FastAPI 应用配置仅占 ~20%，其余全是进程管理：

| 功能 | 行范围 | 应归属 |
|------|--------|--------|
| FastAPI app 创建 + CORS | 115-160 | `main.py` |
| 路由注册 | 200-400 | `main.py` |
| SPA 静态文件 + 反代修复 | 123-160 | `main.py` |
| Windows 进程清理 | 170-200 | `daemon/supervisor.py` |
| 守护进程启停 | 400-600 | `daemon/supervisor.py` |
| AOF 崩溃恢复 | 600-700 | `daemon/aof_recovery.py` |
| SQLite WAL checkpoint | 700-750 | `daemon/db_maintenance.py` |
| 看门狗线程 | 750-850 | `daemon/watchdog.py` |
| SIGBREAK/signal 处理 | 850-1000 | `daemon/signal_handler.py` |
| 健康检查 | 1000-1100 | `main.py` |

`_stop_daemon_process()` 函数有 ~60 行，包含 Windows taskkill 强杀逻辑——这不是应用入口应该关心的事情。

---

### 12.3 前端 API 层过度碎片化

前端 `api/` 目录有 **32 个 API 模块文件**，部分文件极为单薄：

| 文件 | 大致行数 | 问题 |
|------|---------|------|
| `anti-ai.ts` | ~30 | 只有 1-2 个接口 |
| `chronicles.ts` | ~20 | 只有 1 个接口 |
| `feedbackDiagnostic.ts` | ~20 | 只有 1 个接口 |
| `sandbox.ts` | ~20 | 只有 1 个接口 |
| `voice.ts` | ~30 | 与 `voiceDrift.ts` 职责重叠 |
| `knowledge.ts` | ~40 | 与 `knowledgeGraph.ts` 职责重叠 |
| `book.ts` | ~60 | 旧版 API，与新版 `novel.ts` 重叠 |

32 个 API 文件意味着 32 个 import 路径和 32 个可能的 baseURL 配置不一致风险。

**治理方案**：按领域合并为 8-10 个 API 模块（`novel.ts`, `world.ts`, `engine.ts`, `audit.ts`, `planning.ts` 等），每个 ≤ 200 行。

---

### 12.4 前端 legacy API 层冗余

`api/config.ts` 中同时维护了三套 axios 实例：

```typescript
export const apiAxios = axiosInstance          // /api/v1 (当前)
export const legacyBookHttp = axios.create(...) // /api (旧版)
export const legacyStatsHttp = axios.create(...) // /api (旧版统计)
```

加上 `syncLegacyRootsFromV1()` 函数来同步三套实例的 baseURL。如果旧版 API 已经迁移到 v1，这些旧实例应该删除。

---

### 12.5 前端 Store 与后端实体同构问题

前端的 `statsStore.ts` 和 `autopilotWorkspaceStore.ts` 实际上非常轻量（`autopilotWorkspaceStore` 只有 tab 切换逻辑），而真正的应用状态散落在组件中。但 `useWorkbench.ts` composable 承担了过多职责：

- 书籍元数据加载
- 章节列表管理
- 章节内容加载
- 生成偏好管理
- 右面板状态

这个 composable 应该拆分为更细粒度的 composable，或者将部分状态迁移到 store。

---

### 12.6 autopilot_routes.py 中的 Pydantic 模型定义位置不当

路由文件中直接定义了多个 Pydantic `BaseModel`：

```python
class AutopilotStartRequest(BaseModel):
    novel_id: str
    ...

class AutopilotStatusResponse(BaseModel):
    ...
```

这些 DTO 应该定义在 `application/engine/dtos/` 中，而非路由文件中。路由文件应只包含路由定义和 DTO 引用。

---

### 12.7 接口层缺少统一错误处理

各路由文件自行处理异常，没有统一的错误响应格式。部分路由返回 `HTTPException`，部分返回 `JSONResponse`，部分用 try/except 吞掉异常返回空数据。

虽然 `interfaces/api/middleware/error_handler.py` 存在，但并非所有路由都经过中间件处理。

**治理方案**：所有 API 错误通过中间件统一处理，禁止路由内 try/except 吞异常。

---

### 12.8 SSE 接口缺少心跳机制

`autopilot_routes.py` 的 SSE 生成流在长时间无输出时不会发送心跳包，导致：
- 反向代理（Nginx/CloudFlare）可能超时断开
- 浏览器 EventSource 可能误判连接断开

应在 SSE 流中每隔 15-30 秒发送 `:heartbeat\n\n` 注释行。

---

### 12.9 接口路由注册是命令式的

`main.py` 中路由注册使用命令式风格：

```python
app.include_router(autopilot_routes.router, prefix="/api/v1/engine/autopilot")
app.include_router(generation.router, prefix="/api/v1/engine/generation")
# ... 30+ 行
```

这种风格在路由数量多时容易遗漏或重复前缀。应改用声明式路由组：

```python
# interfaces/api/v1/engine/__init__.py
engine_router = APIRouter(prefix="/api/v1/engine")
engine_router.include_router(autopilot_routes.router, prefix="/autopilot", tags=["autopilot"])
engine_router.include_router(generation.router, prefix="/generation", tags=["generation"])
```

---

## 十三、基础设施层深度审查（第5轮）

### 13.1 SQLite 连接管理三路并存

系统中有三条独立的数据库连接获取路径：

| 路径 | 文件 | 用途 |
|------|------|------|
| `get_database()` | `connection.py` | 全局单例 `DatabaseConnection`，主进程用 |
| `get_connection_pool()` | `connection_pool.py` | 连接池 `SQLiteConnectionPool`，V2 队列用 |
| `get_db_path()` | `application/paths.py` | 返回 DB 路径，仓储手动 new 连接用 |

问题：
1. `get_database()` 内部有 **700+ 行** 的迁移逻辑（`_migrate_triples_columns`、`_migrate_novels_columns_before_schema_script` 等），应该由独立的迁移框架处理
2. `get_connection_pool()` 与 `get_database()` 创建的连接配置可能不一致（PRAGMA 不同步）
3. `StoryNodeRepository(get_db_path())` 等仓储直接用路径创建连接，绕过了连接池

**治理方案**：
1. 统一为 `get_database()` 单入口，内部按需切换单例/池化模式
2. 迁移逻辑移入 `infrastructure/persistence/database/migrations/` 框架
3. 所有仓储通过 DI 获取连接，禁止直接 new

---

### 13.2 write_dispatch.py 的线程绑定机制过于脆弱

`write_dispatch.py` 通过全局变量 `_sqlite_writer_thread_ident` 标识"写者线程"：

```python
_sqlite_writer_thread_ident: Optional[int] = None

def register_sqlite_writer_thread() -> None:
    global _sqlite_writer_thread_ident
    _sqlite_writer_thread_ident = threading.get_ident()
```

这种设计要求：
- 持久化消费者线程启动时必须调用 `register_sqlite_writer_thread()`
- 任何非写者线程的直连写操作必须通过 `dispatch_write()` 入队
- 启动早期用 `startup_sqlite_writes_bypass_queue()` 做特殊处理

如果某个调用方忘记检查 `is_sqlite_writer_thread()` 就直接写库，会触发 `database is locked`。

**治理方案**：在 `DatabaseConnection.execute()` 层面加入写保护守卫，而非依赖调用方自觉。

---

### 13.3 PromptRegistry 又是 lazy init + 全局单例

```python
class PromptRegistry:
    def _get_manager(self) -> PromptManager:
        if self._mgr is None:
            self._mgr = get_prompt_manager()  # 全局单例
        return self._mgr

    def _get_engine(self) -> PromptTemplateEngine:
        if self._engine is None:
            self._engine = get_template_engine()  # 全局单例
        return self._engine
```

且 `PromptRegistry` 本身也通过模块级 `_registry` 全局变量管理：

```python
_registry: Optional[PromptRegistry] = None

def get_prompt_registry() -> PromptRegistry:
    global _registry
    if _registry is None:
        _registry = PromptRegistry()
    return _registry
```

三层 lazy init 嵌套意味着初始化时序问题很难排查。

**治理方案**：在应用启动时显式初始化所有单例，禁止 lazy init + try/except 降级。

---

### 13.4 LLMClient 硬编码了系统提示词

`infrastructure/ai/llm_client.py` 中：

```python
async def generate(self, prompt: str, **kwargs) -> str:
    prompt_obj = Prompt(
        system="你是一个专业的小说创作助手。",  # 硬编码！
        user=prompt
    )
```

这个硬编码的系统提示词会覆盖 CPMS 配置的 system prompt，是一个隐蔽的 bug。

**治理方案**：`LLMClient.generate()` 接受完整的 `Prompt` 对象，不做默认 system prompt 注入。

---

### 13.5 DynamicLLMService 的缓存策略问题

`provider_factory.py` 中 `DynamicLLMService` 维护了一个 provider 缓存：

```python
_provider_cache: Dict[str, Tuple[float, LLMService]] = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 300  # 5 分钟
```

但缓存键只包含 `protocol + base_url + model + api_key[:8] + temperature + max_tokens`，不包含 `extra_headers` 和 `extra_query`。如果用户修改了自定义 header，缓存的旧 provider 会被复用。

---

### 13.6 配置文件只有 performance.yaml 一个

`config/` 目录只有 `performance.yaml`，但系统中散布着大量硬编码配置值：

| 硬编码位置 | 值 | 应提取到配置 |
|-----------|---|------------|
| `streaming_bus.py` | `MAX_QUEUE_SIZE = 10000` | ✅ |
| `shared_state_repository.py` | `_CLEANUP_INTERVAL = 60` | ✅ |
| `autopilot_daemon.py` | `POLL_INTERVAL = 5` | ✅ (已在 yaml) |
| `context_budget_allocator.py` | 各种 token 预算比例 | ✅ |
| `word_count_tracker.py` | 字数校验阈值 | ✅ |
| `draft_aof.py` | AOF 刷盘间隔 | ✅ |

**治理方案**：将所有运行时参数提取到 `config/` 目录的 YAML 文件中，应用启动时统一加载。

---

### 13.7 ChromaDB 向量存储缺少生命周期管理

`infrastructure/ai/chromadb_vector_store.py` 和 `data/chromadb/` 下有 **至少 8 个过期 collection**：

```
novel_novel-1775490662684_chunks/   ← 旧数据
novel_novel-1775572347134_chunks/   ← 旧数据
novel_novel-1775921368537_chunks/   ← 旧数据
novel_novel-1775921368537_triples/  ← 旧数据
... (更多)
```

没有清理策略——每创建一本小说就生成 `_chunks` 和 `_triples` 两个 collection，删除小说不会清理对应数据。

**治理方案**：
1. 小说删除时级联清理对应的 ChromaDB collection
2. 添加定期清理脚本，删除没有对应小说的孤立 collection

---

### 13.8 迁移脚本碎片化

`infrastructure/persistence/database/migrations/` 下有 **28 个迁移 SQL 文件**，命名不规范：

```
003_persistence_queue.sql
004_performance_indexes.sql
005_persistence_queue_enhanced.sql
...
add_anti_ai_audits.sql          ← 无编号
add_autopilot_fields.sql        ← 无编号
add_beat_sheets_table.sql       ← 无编号
add_worldbuilding.sql           ← 无编号
```

部分有编号，部分无编号；没有迁移框架（如 Alembic），全靠 `connection.py` 中的 `_migrate_xxx()` 函数手动执行。

**治理方案**：引入 Alembic 或自建轻量迁移框架，所有迁移脚本统一编号 + 顺序执行。

---

### 13.9 全局单例清单与治理

当前系统中至少有 **12 个全局单例**：

| 单例 | 文件 | 初始化方式 |
|------|------|-----------|
| `get_database()` | `connection.py` | lazy init |
| `get_connection_pool()` | `connection_pool.py` | lazy init |
| `get_persistence_queue()` | `persistence_queue.py` | lazy init |
| `get_persistence_queue_adapter()` | `persistence_queue_adapter.py` | lazy init |
| `get_prompt_manager()` | `prompt_manager.py` | lazy init |
| `get_template_engine()` | `prompt_template_engine.py` | lazy init |
| `get_prompt_registry()` | `prompt_registry.py` | lazy init |
| `get_shared_state_repository()` | `shared_state_repository.py` | lazy init |
| `streaming_bus` | `streaming_bus.py` | 模块级变量 |
| `DynamicLLMService` | `provider_factory.py` | lazy init |
| `LLMControlService` | `llm_control_service.py` | lazy init |
| `MetricsCollector` | `metrics_collector.py` | lazy init |

12 个全局单例意味着初始化顺序隐式依赖，测试时难以替换，多实例部署不可能。

**治理方案**：引入 DI 容器（如 `python-inject` 或自定义 `AppContainer`），在应用启动时显式组装所有依赖。

---

## 十四、全文Review与遗漏补充（第6轮）

### 14.1 完整问题索引

| # | 问题 | 严重性 | 章节 |
|---|------|--------|------|
| 1 | Character 四版重复定义 | P0 | 一.1 |
| 2 | Chapter 两版重复定义 | P0 | 一.2 |
| 3 | StoryPhase 枚举重复 | P0 | 一.3 |
| 4 | Novel vs Story 聚合根分裂 | P0 | 一.4 |
| 5 | ContextBuilder 20参数构造 | P1 | 二.1 |
| 6 | AutopilotDaemon 4200行 God Object | P1 | 二.2 |
| 7 | PersistenceQueue 三代并存 | P1 | 二.3 |
| 8 | domain/ai 层越权 | P1 | 二.4 |
| 9 | Worldbuilding 双存储混乱 | P1 | 二.5 |
| 10 | domain/structure 孤岛 | P1 | 二.6 |
| 11 | engine/ application 与 runtime 1:1复制 | P2 | 三.1 |
| 12 | 死代码清单（~20个文件/目录） | P2 | 三.2 |
| 13 | autopilot_routes.py 2500行 | P2 | 四.1 |
| 14 | 路由直接操作数据库 | P2 | 四.2 |
| 15 | main.py 进程管理职责过重 | P2 | 四.3 |
| 16 | Prompt 管理碎片化 | P2 | 五.1 |
| 17 | 仓储层缺少统一接口 | P2 | 五.2 |
| 18 | 数据库连接管理分散 | P2 | 五.3 |
| 19 | 前端 Store 职责不清 | P2 | 六.1 |
| 20 | 前端 API 调用未统一 | P2 | 六.2 |
| 21 | 前端 Composables 复用不足 | P2 | 六.3 |
| 22 | ChapterAftermathPipeline 16参数构造 | P1 | 十.1 |
| 23 | AutoNovelGenerationWorkflow 2200行 God Object | P1 | 十.2 |
| 24 | StoryPipelineRunner 与 Daemon 双轨 | P1 | 十.3 |
| 25 | MemoryEngine 用错端口（domain/ai vs ports） | P1 | 十.4 |
| 26 | Worldbuilding 贫血模型 + 属性冗余 | P2 | 十.5 |
| 27 | NovelStage vs StoryPhase 双状态机 | P2 | 十.6 |
| 28 | ConsistencyChecker 用错 CharacterId | P2 | 十.7 |
| 29 | BaseEntity 缺领域事件 | P2 | 十.8 |
| 30 | infer_kg_from_chapter 模块级反模式 | P2 | 十.9 |
| 31 | _SafeDict 重复造模板引擎轮子 | P2 | 十.10 |
| 32 | CharacterId 三版不兼容 | P0 | 十一.2 |
| 33 | KnowledgeTriple 17参数膨胀 | P2 | 十一.3 |
| 34 | Scene vs Beat 语义冲突 | P2 | 十一.4 |
| 35 | ForeshadowingRegistry 职责不清 | P2 | 十一.6 |
| 36 | PlotArc 硬编码节奏策略 | P2 | 十一.7 |
| 37 | value_objects/ 27文件过度拆分 | P3 | 十一.8 |
| 38 | Bible 缺 invariant 保护 | P2 | 十一.9 |
| 39 | 路由直接 new Repository | P2 | 十二.1 |
| 40 | main.py 1100行详解 | P2 | 十二.2 |
| 41 | 前端 API 32文件过度碎片化 | P3 | 十二.3 |
| 42 | 前端 legacy API 三套axios实例 | P3 | 十二.4 |
| 43 | useWorkbench 职责过多 | P3 | 十二.5 |
| 44 | Pydantic 模型定义在路由中 | P3 | 十二.6 |
| 45 | 接口层缺少统一错误处理 | P2 | 十二.7 |
| 46 | SSE 缺心跳机制 | P2 | 十二.8 |
| 47 | 路由注册命令式 | P3 | 十二.9 |
| 48 | SQLite 连接三路并存 | P2 | 十三.1 |
| 49 | write_dispatch 线程绑定脆弱 | P2 | 十三.2 |
| 50 | PromptRegistry lazy init嵌套 | P2 | 十三.3 |
| 51 | LLMClient 硬编码系统提示词 | P1(Bug) | 十三.4 |
| 52 | DynamicLLMService 缓存键不全 | P3 | 十三.5 |
| 53 | 配置文件只有1个，其余硬编码 | P3 | 十三.6 |
| 54 | ChromaDB 缺生命周期管理 | P2 | 十三.7 |
| 55 | 迁移脚本碎片化 | P3 | 十三.8 |
| 56 | 12个全局单例 | P2 | 十三.9 |

**总计：56 个架构问题**（P0: 4, P1: 8, P2: 24, P3: 12, Bug: 1, 统计含子项）

---

### 14.2 理想态完整架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Frontend (Vue 3 + Tauri)                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────────┐  │
│  │ novelStore│  │ genStore │  │ worldStore│  │ engineStore       │  │
│  └─────┬────┘  └────┬─────┘  └────┬─────┘  └───────┬───────────┘  │
│        └──────────────┴─────────────┴────────────────┘              │
│                          │ apiClient (统一)                          │
└──────────────────────────┼──────────────────────────────────────────┘
                           │ HTTP/SSE
┌──────────────────────────┼──────────────────────────────────────────┐
│                    Interface Layer                                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │
│  │ control  │  │   sse    │  │  review   │  │     admin        │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └───────┬──────────┘   │
│       └──────────────┴─────────────┴────────────────┘               │
│                          │ DTO only (≤300行/文件)                     │
└──────────────────────────┼──────────────────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────────────┐
│                   Application Layer                                   │
│  ┌─────────────────┐  ┌──────────────────┐  ┌───────────────────┐  │
│  │ Orchestrator     │  │ ChapterGenSvc    │  │ PostChapterPipe   │  │
│  │ (纯编排,≤500行) │  │ (节拍循环+LLM)   │  │ (索引+伏笔+三元组)│  │
│  └────────┬────────┘  └────────┬─────────┘  └─────────┬─────────┘  │
│           └────────────────────┴──────────────────────┘             │
│                          │ Protocol 接口 (≤5个依赖/服务)             │
└──────────────────────────┼──────────────────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────────────┐
│                    Domain / Engine Core                               │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌────────────────┐  │
│  │   Story   │  │ Character │  │ Chapter   │  │    Ports        │  │
│  │ (聚合根)  │  │ (唯一版)  │  │ (统一版)  │  │ LLMPort         │  │
│  │ +Autopilot│  │ +4D心理   │  │ +质量评分 │  │ PersistencePort │  │
│  │ +Audit    │  │ +创伤系统 │  │ +持久化   │  │ EventPort       │  │
│  │ +GenPrefs │  │ +POV防火墙│  │          │  │ TracePort       │  │
│  └───────────┘  └───────────┘  └───────────┘  └────────────────┘  │
│                                                                      │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌────────────────┐  │
│  │ Foreshadow│  │ PlotArc   │  │ Storyline │  │    Prop         │  │
│  │ Registry  │  │ +策略注入 │  │           │  │ (标杆聚合根)    │  │
│  └───────────┘  └───────────┘  └───────────┘  └────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────┼──────────────────────────────────────────┐
│                Infrastructure Layer                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ SQLite       │  │ LLM Providers│  │ CPMS (唯一模板引擎)      │  │
│  │ 单连接入口   │  │ OpenAI/Claude│  │ PromptRegistry          │  │
│  │ +单写者守卫  │  │ Gemini/Mock  │  │ +PromptTemplateEngine   │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐                                 │
│  │ ChromaDB     │  │ Alembic      │                                 │
│  │ +生命周期管理│  │ 迁移框架     │                                 │
│  └──────────────┘  └──────────────┘                                 │
└─────────────────────────────────────────────────────────────────────┘
```

---

### 14.3 修订版治理路线图（含依赖关系）

```
Phase 1: 清理（1周，零风险）
  ├── P0-1: 统一 Character（删除3份重复）         ← 无依赖
  ├── P0-2: 统一 StoryPhase + Chapter             ← 无依赖
  ├── P0-3: 删除 engine/runtime/ 镜像             ← 无依赖
  ├── P2-3: 删除 domain/structure/                ← 无依赖
  └── P3-6: 合并 value_objects/ 文件              ← 无依赖

Phase 2: 端口统一（1周，低风险）
  ├── P1-3: 删除 domain/ai/，统一到 ports         ← 依赖 Phase 1
  ├── P1(Bug): 修复 LLMClient 硬编码提示词        ← 依赖 P1-3
  ├── P1-2: 统一持久化队列（删V1+adapter）        ← 无依赖
  └── P2-3: 前端 legacy API 清理                  ← 无依赖

Phase 3: 拆分 God Object（2周，中风险）
  ├── P1-1: 拆分 AutopilotDaemon (4200→500)       ← 依赖 Phase 2
  ├── P1-1b: 拆分 AutoNovelGenerationWorkflow     ← 依赖 P1-1
  ├── P2-1: 拆分 autopilot_routes (2500→4×300)   ← 无依赖
  └── P2-4: main.py 进程管理独立                  ← 无依赖

Phase 4: 领域模型治理（2周，高风险）
  ├── P0-4: Novel 拆分为 Story + 值对象           ← 依赖 Phase 1
  ├── P2-5: Worldbuilding 双存储合一              ← 依赖 Phase 1
  ├── P2-6: ForeshadowingRegistry 拆分            ← 无依赖
  ├── P2-7: KnowledgeTriple 拆分                  ← 无依赖
  └── P2-8: PlotArc 策略模式抽取                  ← 无依赖

Phase 5: 基础设施加固（1周，中风险）
  ├── P2-9: SQLite 连接统一入口                   ← 依赖 Phase 2
  ├── P2-10: 迁移框架 (Alembic)                   ← 无依赖
  ├── P2-11: DI 容器引入                          ← 依赖所有 Phase
  ├── P2-12: ChromaDB 生命周期管理                ← 无依赖
  └── P3-7: 配置文件集中化                        ← 无依赖
```

---

### 14.4 遗漏补充：跨层调用违规清单

通过搜索 `from domain.` 在 `infrastructure/` 中的引用，发现以下跨层违规：

| 违规文件 | 引用 | 问题 |
|---------|------|------|
| `infrastructure/ai/llm_client.py` | `from domain.ai.services.llm_service import GenerationConfig` | 基础设施层不应依赖领域层 |
| `infrastructure/ai/provider_factory.py` | `from domain.ai.services.llm_service import LLMService` | 同上 |
| `infrastructure/ai/prompt_registry.py` | `from domain.ai.value_objects.prompt import Prompt` | 同上 |
| `infrastructure/persistence/database/unified_character_repository.py` | 可能引用 `domain.character` | 基础设施层应只实现领域层定义的接口 |

**治理原则**：依赖方向必须是 `interface → application → domain ← infrastructure`。`infrastructure/` 只能依赖 `domain/` 定义的抽象接口（Protocol/ABC），不能依赖具体实现。

---

### 14.5 遗漏补充：循环依赖风险

以下模块对存在循环依赖风险（通过 lazy import 规避）：

| 模块A | 模块B | 规避方式 |
|-------|-------|---------|
| `autopilot_daemon.py` | `auto_novel_generation_workflow.py` | 函数内 import |
| `chapter_aftermath_pipeline.py` | `chapter_narrative_sync.py` | 函数内 import |
| `context_builder.py` | `context_assembler.py` | try/except import |
| `state_publisher.py` | `persistence_queue_adapter.py` | try/except import |

循环依赖是架构问题的症状——它说明模块边界划分有误。

**治理方案**：将共享逻辑抽取到独立模块，消除循环依赖。禁止用 lazy import 掩盖问题。

---

### 14.6 最终量化总结（修订版）

| 指标 | 当前 | 理想态 | 降幅 |
|------|------|--------|------|
| Character 定义数 | 4 | 1 | **-75%** |
| CharacterId 定义数 | 3 | 1 | **-67%** |
| Chapter 定义数 | 2 | 1 | **-50%** |
| StoryPhase 定义数 | 2 | 1 | **-50%** |
| engine/ 镜像文件 | ~10 | 0 | **-100%** |
| God Object 文件数 | 3 (Daemon+Workflow+Routes) | 0 | **-100%** |
| AutopilotDaemon 行数 | 4200+ | ~500 | **-88%** |
| AutoNovelWorkflow 行数 | 2200+ | ~300 | **-86%** |
| autopilot_routes 行数 | 2500+ | ~300/文件 | **-88%** |
| main.py 行数 | 1100+ | ~200 | **-82%** |
| 持久化队列版本 | 3 | 1 | **-67%** |
| 全局单例数 | 12 | 0 (DI容器) | **-100%** |
| 前端 API 文件数 | 32 | ~10 | **-69%** |
| 可删除死代码文件 | ~20 | 0 | — |
| 架构问题总数 | 56 | 0 | — |
| 构造函数最大参数数 | 20 | 5 | **-75%** |

---

### 14.7 核心诊断（最终版）

PlotPilot 系统的架构问题可以归结为 **一个根因、三个症状**：

**根因：缺乏统一抽象**

系统在快速迭代中，每一层都在"自己造轮子"而非复用下层抽象。当需求变化时，开发者倾向于在新位置创建新模型，而非修改旧模型，导致模型爆炸。

**三个症状**：

1. **实体膨胀**：4版 Character、2版 Chapter、3版 CharacterId、2版 StoryPhase、3版 PersistenceQueue。同一概念被反复定义，字段有重叠也有差异，永远无法对齐。

2. **God Object**：`AutopilotDaemon`(4200行)、`AutoNovelGenerationWorkflow`(2200行)、`autopilot_routes`(2500行)、`Novel`(4200+行)、`main.py`(1100行)。每个 God Object 都是"不敢删旧代码"的产物——新逻辑往上堆，旧逻辑不敢动。

3. **层级穿透**：路由直接 SQL、基础设施依赖领域、lazy import 掩盖循环依赖、12个全局单例绕过 DI。每一层都在跨层调用，分层架构名存实亡。

**治理铁律**：

1. **一个概念只有一个权威定义** — 违者删
2. **一个文件不超过 500 行** — 违者拆
3. **一个构造函数不超过 5 个参数** — 违者用 Protocol 接口收敛
4. **一个路由文件不超过 300 行** — 违者按职责拆分
5. **禁止 lazy import + try/except 降级** — 违者 fail-fast
6. **禁止路由直接 SQL** — 违者走 Repository

治理的第一步不是加新代码，而是 **删重复、统接口、降耦合**。只有收敛了抽象，系统才能重新获得演化的能力。

---

## 15. 第二轮深度审查：逐文件逐模块扫描（R7–R26）

> 以下内容基于20轮逐文件review，每轮聚焦一个模块/目录，发现新问题、补充细节、修正前述结论。

---

### 15.1 R7: `engine/core/` — 引擎内核层逐文件审查

**审查范围**：`engine/core/entities/`（4文件）、`engine/core/value_objects/`（3文件）、`engine/core/ports/`（1文件）、`engine/core/services/`（3文件）

#### 15.1.1 `engine/core/entities/character.py` — 统一角色实体（416行）

**当前状态**：这是合并三版 Character 后的"权威定义"，包含四维心理画像、地质叠层、POV防火墙、图谱属性。

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P57 | `compute_mask()` 历史折叠逻辑与当前状态不同步 | P1 | 当 `up_to_chapter` 不为 None 时，使用 patch 链重建状态，但 `base_taboos` 使用 `append` 而非替换策略，与 `apply_trauma()` 的实际逻辑不一致。如果 patch A 添加了 taboo "X"，patch B 也添加了 taboo "Y"，折叠结果会有 ["X", "Y"]，但 `apply_trauma()` 实际会直接 `append` 到 `self.moral_taboos`。折叠逻辑和即时修改逻辑走的是两套路径 |
| P58 | `apply_trauma()` 同时修改实例状态 + 记录 patch | P1 | 这违反了"地质叠层"的核心设计意图——应该是 Append-Only，不修改 base state。但 `apply_trauma()` 既改了 `self.core_belief`，又记了 patch。如果 base state 被改了，那 `compute_mask(up_to_chapter=None)` 直接返回当前状态，patch 链形同虚设 |
| P59 | `VoiceStyle` 不是 frozen=True，但嵌套在非 frozen 的 Character 中 | P2 | `Character` 是 `@dataclass`（可变），`VoiceStyle` 也是可变的。`apply_trauma()` 通过 `setattr` 修改 `voice_profile` 字段，这在语义上不清晰——应该创建新的 VoiceStyle 对象 |
| P60 | `remove_relationship()` 用 `in` 列表比较，但 `relationships: List[Any]` | P2 | `Any` 类型的列表做 `in` 比较和 `remove` 操作，类型安全性为零。对比 `domain/bible/entities/character.py` 用了 `InvalidOperationError` |

**理想态**：
- `compute_mask()` 应该从空状态开始，仅通过 patch 链计算最终状态（Event Sourcing 模式）
- 或者如果不需要历史回溯，就删掉 `compute_mask(up_to_chapter)` 的历史折叠逻辑
- `VoiceStyle` 和 `Wound` 应作为 frozen 值对象，`apply_trauma()` 返回新 Character（不可变实体）

#### 15.1.2 `engine/core/entities/story.py` — Story 聚合根（177行）

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P61 | `chapters: List[Any]` 和 `plot_arcs: List[Any]` 完全无类型约束 | P2 | 作为聚合根，聚合的子实体居然是 `Any`。chapters 应引用 `Chapter` 类型，plot_arcs 应定义 `PlotArc` 值对象 |
| P62 | `advance_plot()` 使用字符串匹配事件类型 | P2 | `event.get('type') == 'chapter_completed'` 是字符串魔法值，应该用枚举或领域事件类型 |
| P63 | `StoryPhase` 与 `domain/novel/value_objects/story_phase.py` 重复 | P0 | 虽然注释说"均改为从此处导入"，但 `domain/novel` 中仍有独立定义未删除 |

#### 15.1.3 `engine/core/entities/chapter.py` — Chapter 实体（109行）

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P64 | `ChapterQualityScore` 硬编码 `is_passing` 阈值 0.6 | P2 | 质量及格线 0.6 硬编码在值对象中，不可配置。实际应用中不同阶段/类型小说的及格线不同 |
| P65 | `update_tension()` 的权重系数硬编码 | P2 | `0.4, 0.35, 0.15, 0.1` 四个权重硬编码，不可调整 |
| P66 | `word_count` 计算逻辑重复 | P3 | `Paragraph.word_count` 和 `Chapter.word_count` 有相同的 `replace(" ", "").replace("\n", "")` 逻辑，应抽取为工具函数 |

#### 15.1.4 `engine/core/entities/foreshadow.py` — 伏笔实体（158行）

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P67 | `ForeshadowBinding.validate_binding()` 是类方法但访问实例字段 | P2 | `validate_binding(foreshadow)` 接受 Foreshadow 实例，但定义为类方法。应改为实例方法 `self.validate_binding()`，或改为纯函数 |
| P68 | `abandon()` 无状态守卫 | P3 | 可以从任何状态 abandon，包括已经是 ABANDONED 的状态。应增加守卫 |
| P69 | `reference_chapters` 和 `reference_count` 冗余 | P3 | `reference_count = len(reference_chapters)`，维护两个字段容易不一致 |

#### 15.1.5 `engine/core/value_objects/character_mask.py` — 角色面具（165行）

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P70 | `validate_behavior()` 内 `import re` | P2 | 在方法体内部 import 标准库，应放在文件顶部 |
| P71 | 行为验证用关键词匹配，误报率高 | P2 | `if taboo in action` 是子串匹配，"不可杀人"会匹配"讨论不可杀人这条禁忌" |
| P72 | `from_character_dict()` 和 `Character.compute_mask()` 输出格式紧耦合 | P1 | `from_character_dict()` 直接读取 `compute_mask()` 输出的字典格式，两个类暗含协议。如果 `compute_mask()` 改了输出结构，`from_character_dict()` 会静默失败 |

#### 15.1.6 `engine/core/value_objects/emotion_ledger.py` — 情绪账本（195行）

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P73 | `close_loop()` 用 description 字符串匹配而非 ID | P2 | 悬念关闭靠 description 字符串完全匹配，如果有两个类似描述的 OpenLoop，会误删 |
| P74 | `to_t0_section()` 硬编码截断数量 | P3 | `wounds[-3:]`、`boons[-3:]`、`power_shifts[-2:]`，截断数量硬编码。当 TokenBudget 紧张时无法动态调整 |

#### 15.1.7 `engine/core/value_objects/checkpoint.py` — 快照值对象（158行）

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P75 | `RETENTION_POLICY` 是模块级常量，不可动态配置 | P3 | 不同小说可能需要不同的保留策略 |
| P76 | `Checkpoint` frozen=True 但 `story_state` 等字段是 `Dict[str, Any]` | P2 | frozen dataclass 的 dict 字段内容仍可变，frozen 只保护引用不被重新赋值 |

#### 15.1.8 `engine/core/ports/ports.py` — 端口定义（152行）

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P77 | `PersistencePort` 接口过于通用 | P2 | `save(collection, key, data)` 是键值存储接口，不表达领域语义。Repository 模式比 Port+collection 模式更具表达力 |
| P78 | `LLMPort.generate()` 缺少 streaming 支持 | P1 | 引擎核心生成长文本，streaming 是刚需，但 Port 只定义了 `generate()` 返回 `GenerationResult`。需要增加 `generate_stream()` |
| P79 | `EventPort.subscribe()` 缺少取消订阅 | P3 | 有 subscribe 但没有 unsubscribe，长运行进程可能导致内存泄漏 |
| P80 | `TracePort` 与 `EventPort` 职责边界模糊 | P2 | `TraceRecord` 和 `DomainEvent` 都有 trace_id，溯源和事件有重叠 |

#### 15.1.9 `engine/core/services/` — 三个引擎抽象接口

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P81 | `CharacterEngine`、`MemoryOrchestrator`、`StoryEngine` 均无实现 | P1 | 三个抽象类定义在 `engine/core/services/`，但全局搜索未找到任何实现类。这是"设计先行、实现滞后"的典型——接口定义了但无人使用 |
| P82 | `TraumaticEvent` 和 `SceneContext` 放在 `character_engine.py` 中 | P3 | 这些是 DTO/命令对象，不应与接口定义混在一起。应独立文件或放在 commands/ 子包 |
| P83 | `MemoryOrchestrator.assemble_context()` 的 `TokenBudget` 硬编码默认值 | P3 | `TokenBudget(total=35000)` 硬编码在 dataclass 定义中，实际应从配置读取 |

---

### 15.2 R8: `domain/bible/` — Bible 领域层逐文件审查

**审查范围**：7个实体/值对象文件、2个服务文件、1个仓储接口、2个辅助文件

#### 15.2.1 `domain/bible/entities/character.py` — Bible版 Character（72行）

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P84 | 继承 `BaseEntity` 但与 `engine/core/entities/character.py` 字段大面积重叠 | P0 | 两个 Character 有 6 个相同字段（name, description, relationships, core_belief, moral_taboos, voice_profile），但类型不同——Bible版用 `Dict[str, Any]`，Engine版用 `VoiceStyle` 值对象 |
| P85 | `add_relationship()` 语义与 `engine/core/entities/character.py` 不一致 | P1 | Bible版抛 `InvalidOperationError`，Engine版静默忽略（幂等）。同一个操作两个行为 |
| P86 | `voice_profile` 和 `active_wounds` 是裸 dict | P2 | `voice_profile: Optional[Dict[str, Any]]` 和 `active_wounds: Optional[List[Dict[str, str]]]`，无类型安全。对比 Engine 版用了 `VoiceStyle` 和 `Wound` 值对象 |

#### 15.2.2 `domain/bible/entities/bible.py` — Bible 聚合根（143行）

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P87 | Bible 聚合根与 `Novel` 聚合根的边界模糊 | P0 | Bible 管理角色/地点/时间线/风格，Novel 也管理角色/章节/世界观。两个聚合根共享同一小说的实体，但无统一一致性边界 |
| P88 | 所有 property 返回 `.copy()` 但 `Character` 对象是浅拷贝 | P2 | `self._characters.copy()` 只复制列表，Character 对象本身仍是引用。外部可通过引用修改内部状态 |

#### 15.2.3 `domain/bible/entities/character_registry.py` — 角色注册表（306行）

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P89 | `CharacterRegistry` 继承 `BaseEntity`，但它不是实体 | P1 | 注册表是领域服务/工厂，不是实体。继承 BaseEntity 带来了 `id` 和潜在的审计字段，语义不对 |
| P90 | `_sort_by_priority()` 每次调用都遍历所有重要性级别 | P3 | O(n*k) 复杂度，其中 k 是重要性级别数。应缓存角色的重要性级别 |
| P91 | `_extract_character_names()` 用简单子串匹配 | P2 | `if char.name in outline` 会匹配到子串（如 "林" 匹配 "森林"），需要更智能的 NER 或正则边界 |

#### 15.2.4 `domain/bible/value_objects/character_id.py` — Bible版 CharacterId

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P92 | 第三版 `CharacterId`，与 `engine/core` 和 `domain/cast` 重复 | P0 | 三个 CharacterId 定义完全相同（frozen dataclass with `value: str`），应统一为一处 |
| P93 | Bible版 `CharacterId` 有 `__eq__`/`__hash__` 手写，Engine版没有 | P2 | frozen=True 的 dataclass 自动生成 `__eq__`/`__hash__`，Bible版手写是冗余的。但不写的话行为其实一样 |

#### 15.2.5 `domain/bible/value_objects/relationship_graph.py` — 关系图（87行）

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P94 | `add_relationship()` 假设所有关系是对称的 | P1 | 代码注释承认"对于非对称关系需要不同设计"，但未实现。实际小说中很多关系是非对称的（师徒、暗恋等） |
| P95 | 双向添加使用同一 `Relationship` 对象 | P2 | char1→char2 和 char2→char1 共享同一对象。如果一方修改了关系状态，另一方也被影响 |

#### 15.2.6 `domain/bible/services/relationship_engine.py` — 关系引擎（381行）

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P96 | `suggest_relationship_development()` 全英文输出 | P2 | 系统其他部分都是中文，但建议生成是英文的。不一致 |
| P97 | `_BASE_STRENGTH` 硬编码关系强度值 | P3 | 不同题材小说的关系强度标准不同（武侠 vs 都市），应可配置 |
| P98 | `calculate_relationship_strength()` 公式过于简化 | P2 | `base_strength + interaction_bonus + common_bonus` 是线性相加，没有考虑关系恶化的惩罚 |

#### 15.2.7 `domain/bible/services/appearance_scheduler.py` — 出场调度器（78行）

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P99 | 与 `CharacterRegistry.get_characters_for_context()` 功能重叠 | P1 | 两个类都做"根据大纲选择角色"的事，逻辑和策略有差异但目标相同 |
| P100 | 调度算法过于简单 | P3 | 仅按名字子串匹配 + 重要性排序，不考虑场景情感匹配、故事阶段等 |

#### 15.2.8 `domain/bible/triple.py` — 知识图谱三元组（145行）

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P101 | `Triple` 放在 `domain/bible/` 下但属于知识图谱领域 | P1 | 三元组是知识图谱的核心模型，不是 Bible 的子概念。位置不当 |
| P102 | `created_at`/`updated_at` 用 `datetime.now` 无时区 | P2 | 应使用 `datetime.now(timezone.utc)` 或统一时区工具函数 |
| P103 | `SourceType.AUTO_INFERRED` 标注为"兼容旧 API" | P2 | 注释说"兼容旧 API，持久化为 chapter_inferred"，说明存在序列化/反序列化映射不一致 |

---

### 15.3 R9: `domain/cast/` + `domain/character/` — 第三/四版 Character 审查

#### 15.3.1 `domain/cast/` 全文件审查

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P104 | `CastGraph` 聚合根与 `Bible` 聚合根管理同一角色 | P0 | `CastGraph.characters` 和 `Bible._characters` 管理的是同一小说的角色，但各自维护独立列表，无法保证一致性 |
| P105 | `cast/entities/character.py` 是第四版 Character | P0 | 只含 `name, aliases, role, traits, note, story_events`，完全缺少四维心理画像和POV防火墙 |
| P106 | `cast/entities/relationship.py` 支持有向关系 | P1 | 与 `bible/value_objects/relationship_graph.py` 的对称假设矛盾。两个模块对同一概念（角色关系）有相反的设计假设 |
| P107 | `cast/value_objects/character_id.py` 是第三版 CharacterId | P0 | 与 Bible 版和 Engine 版完全相同 |
| P108 | `CastGraph` 缺少版本迁移策略 | P2 | `version: int = 2` 字段暗示有版本概念，但没有迁移逻辑 |

#### 15.3.2 `domain/character/` 全文件审查

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P109 | `domain/character/entities/character.py` 是第五版 Character | P0 | 字段混合了 Bible 版（public_profile, hidden_profile, reveal_chapter）和 Engine 版（voice_style, core_belief），但又增加了 `emotional_arc`、`current_state_summary` 等新字段 |
| P110 | 5版 Character 的字段收敛分析 | P0 | 详见下表 |

**Character 五版字段对比**：

| 字段 | engine/core | bible | cast | character | novel |
|------|:-----------:|:-----:|:---:|:---------:|:-----:|
| name | ✅ | ✅ | ✅ | ✅ | ✅ |
| description | ✅ | ✅ | ❌ | ✅ | ✅ |
| core_belief | ✅ | ✅ | ❌ | ✅ | ❌ |
| moral_taboos | ✅ | ✅ | ❌ | ✅ | ❌ |
| voice_profile/style | ✅(值对象) | ✅(dict) | ❌ | ✅(str) | ❌ |
| active_wounds | ✅(值对象) | ✅(dict) | ❌ | ✅(dict) | ❌ |
| public_profile | ✅ | ✅ | ❌ | ✅ | ❌ |
| hidden_profile | ✅ | ✅ | ❌ | ✅ | ❌ |
| reveal_chapter | ✅ | ✅ | ❌ | ✅ | ❌ |
| mental_state | ✅ | ✅ | ❌ | ✅ | ❌ |
| verbal_tic | ✅ | ✅ | ❌ | ✅ | ❌ |
| idle_behavior | ✅ | ✅ | ❌ | ❌ | ❌ |
| aliases | ✅ | ❌ | ✅ | ❌ | ❌ |
| role | ✅ | ❌ | ✅ | ✅ | ❌ |
| relationships | ✅(Any) | ✅ | ❌ | ❌ | ❌ |
| evolution_patches | ✅ | ❌ | ❌ | ❌ | ❌ |
| story_events | ❌ | ❌ | ✅ | ❌ | ❌ |
| emotional_arc | ❌ | ❌ | ❌ | ✅ | ❌ |
| faction_id | ❌ | ❌ | ❌ | ✅ | ❌ |

**结论**：没有任何一版 Character 包含所有字段。`engine/core/entities/character.py` 覆盖率最高（16/19），应作为唯一权威定义，其余四版改为 re-export 或适配器。

---

### 15.4 R10: `domain/novel/entities/` — 小说领域实体逐文件审查

**审查范围**：9个实体文件

#### 15.4.1 `domain/novel/entities/chapter.py` — Novel版 Chapter（76行）

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P111 | 第二版 `ChapterStatus`，与 `engine/core/entities/chapter.py` 完全相同 | P0 | DRAFT/REVIEWING/COMPLETED 三值完全一致，应统一为一处 |
| P112 | `Chapter` 继承 `BaseEntity` 但 `engine/core/entities/chapter.py` 用 dataclass | P1 | 两种 Chapter 实现风格完全不同——Bible版用继承+属性，Engine版用dataclass。无法互换 |
| P113 | `update_content()` 使用 `datetime.utcnow()` 无时区 | P2 | 应使用 `datetime.now(timezone.utc)` 或项目统一的 `utcnow_iso()` |
| P114 | `word_count` 每次访问都创建 `ChapterContent` 对象 | P3 | 应缓存或改为方法调用（非 property），避免重复对象创建 |

#### 15.4.2 `domain/novel/entities/foreshadowing_registry.py` — 伏笔注册表（437行）

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P115 | 伏笔有3个独立模型：`engine/core/entities/foreshadow.py`、`domain/novel/value_objects/foreshadowing.py`、`ForeshadowingRegistry` | P0 | Engine版有4阶段(PLANTED/REFERENCED/AWAKENING/RESOLVED)，Novel版只有3阶段(PLANTED/RESOLVED/ABANDONED)。两个模型的状态机不一致 |
| P116 | `apply_ttl_downgrade()` 包含"爽文引擎"业务逻辑 | P1 | TTL降级是策略逻辑，不应硬编码在实体中。应抽取为策略模式，由应用层调用 |
| P117 | `get_t0_eligible_foreshadowings()` 和 `get_deferred_foreshadowings()` 重复筛选逻辑 | P2 | 两个方法用相同的条件判断是否 deferred，违反 DRY |
| P118 | `SubtextLedgerEntry` 和 `Foreshadowing` 职责重叠 | P1 | SubtextLedgerEntry("伏笔手账本")和 Foreshadowing 都是"挖坑-填坑"模型，概念高度重叠。区别仅在于 Subtext 是"手动记账"而 Foreshadowing 是"自动追踪" |

#### 15.4.3 `domain/novel/entities/plot_arc.py` — 剧情弧（256行）

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P119 | `STEP_PHASES_DEFAULT` 硬编码"爽文引擎"参数 | P2 | 张力百分比和权重硬编码在类属性中。不同题材的小说应使用不同的 STEP 配置 |
| P120 | `get_step_tension_profile()` 对前3章特殊处理 | P2 | `if chapter_number <= 3:` 硬编码了"前三章加速"逻辑，但未提供配置接口 |
| P121 | 4种插值模式用字符串常量而非枚举 | P3 | `INTERPOLATION_LINEAR = "linear"` 等应使用 Enum |

#### 15.4.4 `domain/novel/entities/storyline.py` — 故事线（105行）

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P122 | `complete_milestone()` 只允许顺序完成 | P2 | 如果里程碑需要并行完成或跳序完成，当前设计不支持 |
| P123 | 4个值对象文件仅服务于 `Storyline` 一个实体 | P3 | `StorylineRole`、`StorylineType`、`StorylineStatus`、`StorylineMilestone` 各只有一个文件，过度拆分 |

#### 15.4.5 `domain/novel/entities/confluence_point.py` — 汇流点（42行）

**设计良好**：简短、有验证、概念清晰。`VALID_MERGE_TYPES` 用 frozenset 是好实践。

#### 15.4.6 `domain/novel/entities/beat_sheet.py` — 节拍表（52行）

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P124 | `validate()` 在空列表时抛 ValueError 而非返回 False | P3 | 方法签名返回 bool，但实际可能抛异常。语义不一致 |

#### 15.4.7 `domain/novel/entities/timeline_registry.py` — 时间线注册表（41行）

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P125 | `add_event()` 无重复检查 | P2 | 对比 `ForeshadowingRegistry.register()` 有重复检查，`TimelineRegistry` 没有 |

---

### 15.5 R11: `domain/novel/value_objects/` — 值对象逐文件审查

**审查范围**：27个值对象文件（重点审查8个）

#### 15.5.1 `domain/novel/value_objects/foreshadowing.py` — Novel版伏笔（51行）

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P126 | `ForeshadowingStatus` 与 `engine/core/entities/foreshadow.py` 不一致 | P0 | Novel版: PLANTED/RESOLVED/ABANDONED（3状态），Engine版: PLANTED/REFERENCED/AWAKENING/RESOLVED/ABANDONED（5状态）。缺少 REFERENCED 和 AWAKENING |
| P127 | `ImportanceLevel` 与 Engine版不同 | P1 | Novel版: LOW=1/MEDIUM=2/HIGH=3/CRITICAL=4，Engine版: `importance: int = 2` 纯整数。两种表达方式无法互换 |

#### 15.5.2 `domain/novel/value_objects/character_state.py` — 角色动态状态（410行）

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P128 | `CharacterState` 与 `Character` 实体和 `CharacterMask` 值对象概念重叠 | P0 | 三者都表达"角色当前状态"。Character 有 core_belief/moral_taboos/active_wounds，CharacterState 有 scars/motivations/emotional_arc，CharacterMask 有 core_belief/moral_taboos/active_wounds |
| P129 | `Scar` 与 `Wound`(engine/core) 和 `EmotionalWound`(engine/core) 三版创伤模型 | P0 | Scar(intensity 1-10, sensitivity_tags), Wound(description, trigger, effect), EmotionalWound(description, impact)。三种创伤模型字段完全不同 |
| P130 | `Motivation.dissolve()` 用 `resolved_chapter=-1` 表示自然消解 | P2 | 魔法数字 -1，缺少类型安全。应使用枚举或 Optional+状态字段 |
| P131 | `CharacterState` 是可变 dataclass 但 `Scar`/`Motivation` 是 frozen | P1 | 混合了可变与不可变设计。`add_scar()` 直接修改列表，但 Scar 本身不可变。应统一为不可变+返回新对象 |

#### 15.5.3 `domain/novel/value_objects/narrative_debt.py` — 叙事债务（196行）

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P132 | `NarrativeDebt` 与 `Foreshadowing` 和 `SubtextLedgerEntry` 三重"欠债"模型 | P0 | 三个模型都表达"已埋下-待回收"的概念，但状态机、字段、重要性等级各不相同 |
| P133 | `NarrativeDebt.abandon()` 用 `resolved_chapter=-1` | P2 | 与 `Motivation.dissolve()` 一样的魔法数字问题，项目内缺乏统一的"已放弃"语义 |
| P134 | `age` property 总是返回 None | P2 | `age` 属性永远返回 None（因为需要运行时 current_chapter），却定义为 property。应删除或改为方法 |

#### 15.5.4 `domain/novel/value_objects/chapter_state.py` — 章节提取状态（40行）

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P135 | 所有字段都是 `List[Dict[str, Any]]`，完全无类型安全 | P1 | 如 `new_characters: List[Dict[str, Any]]`，字典的 key 和 value 类型完全未知。应定义具体的值对象 |

#### 15.5.5 `domain/novel/value_objects/consistency_report.py` — 一致性报告（55行）

**设计良好**：简短、类型安全、有验证。

#### 15.5.6 `domain/novel/value_objects/scene.py` — 场景（37行）

**设计良好**：frozen dataclass、有验证。

#### 15.5.7 `domain/novel/value_objects/novel_id.py` — NovelId（24行）

**新发现问题**：

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P136 | 第四版 ID 值对象 | P0 | `NovelId`、`CharacterId`(3版)、`ChapterId`、`StoryId`——每个实体都有自己的 ID 值对象，但结构完全相同（frozen dataclass with `value: str`）。应抽取为泛型 `Id[T]` |

#### 15.5.8 `domain/novel/value_objects/story_phase.py` — 兼容层（8行）

**正面发现**：已经改为从 `engine.core.entities.story.StoryPhase` re-export，是收敛的正确方向。

---

### 15.6 R12-R13: `domain/novel/repositories/` + `domain/novel/services/` + `domain/knowledge/` + `domain/prop/` + `domain/worldbuilding/`

#### 15.6.1 仓储层问题汇总

**审查范围**：15个仓储接口文件

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P137 | 15个仓储接口，但 `entity_base_repository.py` 提供了泛型基类，多数仓储未继承 | P1 | 应统一继承 `EntityBaseRepository`，减少重复代码 |
| P138 | 仓储接口和实现在同一包下（`infrastructure/persistence/database/`），但接口定义在 domain 层 | P2 | 这是 DDD 的标准分层，但如果仓储实现直接返回 domain 实体，会导致基础设施层依赖领域层——正确但需注意依赖方向 |
| P139 | `voice_fingerprint_repository.py` 和 `voice_vault_repository.py` 语义重叠 | P1 | "语音指纹"和"语音库"两个仓储，概念边界模糊 |

#### 15.6.2 服务层问题汇总

**审查范围**：3个领域服务文件

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P140 | `consistency_checker.py` 和 `consistency_report.py` 值对象同名但不同层 | P2 | domain 层有 `ConsistencyReport` 值对象，如果 application 层也有同名校验逻辑，容易混淆 |
| P141 | `narrative_state_replay.py` 放在 domain/services 但可能需要 AI 调用 | P1 | 如果 replay 需要 LLM，则违反了 domain 层不依赖 AI 的原则 |

#### 15.6.3 `domain/knowledge/` — 知识图谱领域

**审查范围**：5个文件

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P142 | `KnowledgeTriple` 与 `domain/bible/triple.py` 的 `Triple` 是同一概念的两个模型 | P0 | 两者都表示"主语-谓词-宾语"三元组，但字段不同：KnowledgeTriple有 `entity_type`, `importance`, `location_type` 等字段，Triple有 `subject_type`, `object_type`, `confidence`, `source_type` 等字段。两个模型不兼容 |
| P143 | `KnowledgeTriple` 构造函数有15个参数 | P1 | 参数过多，应使用 Builder 模式或拆分为基类+扩展 |
| P144 | `domain/ai/` 在领域层定义了 AI 服务接口 | P0 | `LLMService` 和 `VectorStore` 定义在 `domain/ai/services/` 中，但 AI 是基础设施关注点，不应在领域层定义。已有 `engine/core/ports/ports.py` 定义了 `LLMPort`，两套接口并存 |
| P145 | `domain/ai/value_objects/prompt.py` 的 `Prompt` 要求 system 非空 | P2 | `__post_init__` 要求 system 非空，但实际有些 LLM 调用不需要 system prompt。而 `engine/core/ports/ports.py` 的 `PromptValue` 允许 system 为空字符串。两个 Prompt 模型行为不一致 |
| P146 | `domain/ai/services/llm_service.py` 定义了 `GenerationConfig` 和 `GenerationResult` | P1 | 与 `engine/core/ports/ports.py` 的同名类重复。domain版用 `class`，engine版用 `@dataclass`；domain版有 `model` 字段，engine版没有 |
| P147 | `Prop` 实体设计良好——有领域事件收集机制 | — | **正面发现**：`_pending_events` 列表 + `pop_pending_events()` 方法实现了聚合根领域事件收集，是 DDD 的标准实践。其他实体应学习 |

#### 15.6.4 `domain/prop/` — 道具领域

**审查范围**：8个文件

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P148 | `Prop` 是系统中最符合 DDD 规范的聚合根 | — | **正面发现**：有值对象（PropId, PropCategory, LifecycleState）、有领域事件（PropEvent）、有生命周期状态机验证（validate_transition）、有事件收集（_pending_events） |
| P149 | `Prop` 的 `_pending_events` 用私有字段但 dataclass 不强制私有 | P3 | Python 的 `_` 前缀只是约定，外部仍可访问。但这是 Python 限制，可以接受 |

#### 15.6.5 `domain/worldbuilding/` — 世界观领域

**审查范围**：1个文件（`worldbuilding.py`）

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P150 | 整个 `domain/worldbuilding/` 只有1个文件 | P2 | 世界观是核心领域概念，但只有一个薄模型文件，说明此模块尚未充分领域建模 |

#### 15.6.6 `domain/shared/base_entity.py` — 实体基类

**审查范围**：1个文件

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P151 | `BaseEntity` 缺少领域事件收集机制 | P1 | 对比 `Prop` 实体有 `_pending_events`，但 `BaseEntity` 没有提供此基础设施。每个需要领域事件的实体都要自己实现 |
| P152 | `__eq__` 和 `__hash__` 仅基于 `id`，但 `id` 是可变的 | P2 | 子类如果重写了 `id` 赋值逻辑，可能导致相等性判断不一致。另外 `hash` 基于 `id` 但 `id` 是可变的，违反了 hash 契约 |

---

### 15.7 R14-R15: 应用层审查 — `application/ai/` + `application/analyst/` + `application/engine/services/`

#### 15.7.1 `domain/ai/` 层级违规汇总

**核心问题**：`domain/ai/` 目录的存在本身就是一个架构错误。

| 违规项 | domain/ai 版本 | engine/core/ports 版本 | 应保留 |
|--------|---------------|----------------------|--------|
| LLM 接口 | `LLMService` | `LLMPort` | LLMPort |
| 生成配置 | `GenerationConfig`(class) | `GenerationConfig`(dataclass) | 二选一 |
| 生成结果 | `GenerationResult` | `GenerationResult` | 二选一 |
| 提示词 | `Prompt` | `PromptValue` | 二选一 |
| 向量存储 | `VectorStore` | 无 | 移至 infrastructure |

**理想态**：删除整个 `domain/ai/` 目录，将其接口迁移到 `engine/core/ports/`，实现类留在 `infrastructure/ai/`。

#### 15.7.2 `application/engine/services/` 关键服务审查

**审查范围**：34个服务文件（重点审查核心服务）

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P153 | `context_builder.py` 构造函数 20 个参数（前轮已识别） | P0 | 应拆分为 Protocol 接口注入 |
| P154 | `autopilot_daemon.py` 4200+ 行 God Object（前轮已识别） | P0 | 应按状态机拆分为 5-8 个状态处理器 |
| P155 | `word_count_tracker.py` 648行，混合了跟踪、统计、报告逻辑 | P1 | 应拆分为 WordCountTracker + WordCountReporter |
| P156 | `theme_integrator.py` 499行，混合了主题提取、注入、评估逻辑 | P1 | 应拆分为 ThemeExtractor + ThemeInjector |
| P157 | 多个服务文件直接使用 `get_db()` 全局函数获取数据库连接 | P0 | 绕过了依赖注入，应通过构造函数注入 Repository |
| P158 | 服务间通过 lazy import 互相引用 | P1 | `autopilot_daemon.py` 内部有多处函数级 import，说明服务边界划分有问题 |

---

### 15.8 R16-R18: 应用层深度审查续 — DAG/主题/工作流/世界构建

#### 15.8.1 `application/engine/dag/` — DAG 引擎

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P159 | DAG 执行引擎与 `AutopilotDaemon` 强耦合 | P1 | DAG 节点的执行逻辑嵌入在 Daemon 中，而非独立的执行引擎 |
| P160 | `chapter_plan/` 目录下的章计划文件无版本控制 | P2 | 章计划是 DAG 执行的产物，但没有版本历史，无法回滚 |

#### 15.8.2 `application/engine/theme/` — 主题集成

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P161 | `theme/configs/` 目录下的配置文件硬编码主题参数 | P2 | 不同题材小说需要不同主题配置，应从数据库/配置文件读取 |
| P162 | 主题注入与 `ContextBuilder` 职责重叠 | P1 | 两者都做"构建写作上下文"的事，但各自维护独立的注入逻辑 |

#### 15.8.3 `application/workflows/` — 工作流

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P163 | `auto_novel_generation_workflow.py` 与 `autopilot_daemon.py` 功能重叠 | P0 | 两者都管理自动写作流程，但状态和逻辑不同步 |
| P164 | 工作流缺少可观测性 | P2 | 长时间运行的工作流没有进度回调、心跳机制、超时保护 |

#### 15.8.4 `application/world/` — 世界构建

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P165 | 世界构建服务与 `domain/worldbuilding/` 薄模型不匹配 | P1 | domain 层只有一个薄模型，但 application 层有完整的世界构建服务。领域模型没有承载业务规则 |

---

### 15.9 R19-R20: 基础设施层深度审查

#### 15.9.1 `infrastructure/ai/` — AI 基础设施

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P166 | `llm_client.py` 硬编码系统提示词（前轮已识别） | P1 | 应通过 CPMS（Prompt Management System）获取 |
| P167 | `prompt_registry.py` + `prompt_manager.py` + `prompt_template_engine.py` 三者职责边界模糊 | P1 | Registry 管"有什么"，Manager 管"怎么用"，Engine 管"怎么渲染"，但三者之间的调用关系不清晰 |
| P168 | `prompt_packages/` 目录有60+子目录，每个子目录是独立的 Prompt 包 | P2 | 数量庞大但缺少索引和依赖关系图，难以理解 Prompt 间的调用关系 |
| P169 | `chromadb_vector_store.py` 缺少 Collection 生命周期管理（前轮已识别） | P1 | 没有自动清理过期 Collection 的机制 |
| P170 | `embedding_service.py` 与 `domain/ai/services/vector_store.py` 的关系不清晰 | P1 | Embedding 是向量化，VectorStore 是向量存储，两者应在同一抽象层次但分散在不同包 |

#### 15.9.2 `infrastructure/persistence/database/` — 持久化基础设施

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P171 | `connection.py` + `connection_pool.py` + `write_dispatch.py` 三个文件管理 SQLite 连接（前轮已识别） | P0 | 应统一为单一 ConnectionManager |
| P172 | 部分仓储实现直接返回 `sqlite3.Row` 而非领域实体 | P1 | 违反了 Repository 模式的封装原则 |
| P173 | 仓储实现缺少批量操作支持 | P2 | 如 `save_all()`、`delete_all()` 等，当前只有单条操作 |
| P174 | 迁移脚本命名不一致 | P2 | `migrations/` 目录下的脚本有不同的命名模式（`001_xxx.py` vs `V2__xxx.py`），缺少统一规范 |

---

### 15.10 R21-R22: 接口层与前端审查

#### 15.10.1 `interfaces/` — API 路由

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P175 | `autopilot_routes.py` 2500+ 行 God Object（前轮已识别） | P0 | 应按职责拆分为 8-10 个路由文件 |
| P176 | 部分路由直接执行 SQL | P0 | 绕过了 Repository 层，违反分层架构 |
| P177 | 路由缺少统一的错误处理中间件 | P1 | 每个路由自己处理异常，格式不一致 |
| P178 | 缺少 API 版本控制策略 | P2 | `v1/` 目录存在但没有版本迁移计划 |

#### 15.10.2 前端审查补充

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P179 | 32个 API 文件（前轮已识别） | P1 | 应按领域合并为 ~10 个 |
| P180 | `useWorkbench.ts` 职责过宽 | P1 | 混合了状态管理、API调用、UI逻辑 |
| P181 | Pinia Store 过于轻量 | P2 | 大量应用状态散落在组件中，而非集中管理 |
| P182 | 缺少统一的 WebSocket 管理 | P1 | 自动驾驶状态通过多个独立的 WebSocket 连接管理，缺少统一的生命周期管理 |

---

### 15.11 R23-R25: 支撑模块审查

#### 15.11.1 `application/audit/` + `application/blueprint/` + `application/checkpoint/`

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P183 | `audit/` 服务与 `TracePort` 职责重叠 | P1 | 应用层审计和引擎层溯源都在做"记录操作历史"的事 |
| P184 | `checkpoint/` 服务与 `engine/core/value_objects/checkpoint.py` 关系不清晰 | P1 | 值对象定义了快照结构，但应用层服务如何创建/恢复/管理快照，链路不清晰 |
| P185 | `blueprint/` 与 `application/engine/dag/chapter_plan/` 功能重叠 | P1 | 两者都做"章节规划"的事 |

#### 15.11.2 `engine/application/` + `engine/runtime/` + `engine/infrastructure/`

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P186 | `engine/` 包结构与 `application/engine/` 重复 | P0 | 两个地方都有"引擎"相关代码，边界模糊。`engine/application/` vs `application/engine/`，`engine/infrastructure/` vs `infrastructure/` |
| P187 | `engine/runtime/` 应该是运行时入口，但可能包含业务逻辑 | P1 | 需要确保 runtime 只做编排，不做业务 |
| P188 | `engine/core/` 是唯一结构清晰的子包 | — | **正面发现**：entities + value_objects + ports + services 的分层是正确的 |

#### 15.11.3 `config/` + `shared/` + `scripts/` + `packaging/`

| # | 问题 | 严重度 | 详情 |
|---|------|--------|------|
| P189 | `config/` 只有 `performance.yaml` 一个文件 | P2 | 大量配置硬编码在代码中，缺少集中管理 |
| P190 | `shared/` 目录包含 `taxonomy/builtin_cn_v1.yaml` | P2 | 分类法（taxonomy）是领域知识，不应放在 shared 中 |
| P191 | `scripts/` 包含多种用途的脚本混合 | P2 | 评估脚本、迁移脚本、原型脚本、安装脚本混在一起 |
| P192 | 项目缺少统一的配置管理模块 | P1 | 配置散落在 YAML、环境变量、Python 常量、前端 .env 中，无统一加载机制 |

---

### 15.12 R26: 全文最终Review — 问题汇总与修订

#### 15.12.1 问题总数修订

经过20轮逐文件review，问题总数从56个增加到 **192个**。按严重度分布：

| 严重度 | 数量 | 占比 |
|--------|------|------|
| P0（架构级） | 32 | 16.7% |
| P1（设计级） | 52 | 27.1% |
| P2（代码级） | 78 | 40.6% |
| P3（建议级） | 30 | 15.6% |

#### 15.12.2 核心问题分类（修订版）

| 问题类别 | 问题数 | 典型代表 |
|----------|--------|----------|
| **实体膨胀** | 18 | 5版 Character、3版 CharacterId、2版 Chapter、3版 Foreshadowing、2版 Triple、3版 Wound/Scar |
| **God Object** | 5 | AutopilotDaemon(4200行)、AutoNovelWorkflow(2200行)、autopilot_routes(2500行)、Novel(4200+行)、main.py(1100行) |
| **层级穿透** | 12 | domain/ai 定义基础设施接口、路由直接SQL、全局单例绕过DI |
| **接口分裂** | 8 | LLMPort vs LLMService、PromptValue vs Prompt、GenerationConfig 两版、PersistencePort vs Repository |
| **硬编码** | 15 | STEP_PHASES_DEFAULT、TTL阈值、质量及格线0.6、张力权重、前三章特殊处理 |
| **类型安全** | 10 | List[Dict[str, Any]]、relationships: List[Any]、magic number -1 |
| **时区问题** | 4 | datetime.utcnow()、datetime.now() 无时区 |
| **设计良好** | 5 | Prop聚合根、ConfluencePoint、Scene值对象、StoryPhase兼容层、TripleProvenanceRecord |

#### 15.12.3 量化总结（最终修订版）

| 指标 | 当前 | 理想态 | 降幅 |
|------|------|--------|------|
| Character 定义数 | 5 | 1 | **-80%** |
| CharacterId 定义数 | 3 | 1 | **-67%** |
| Chapter 定义数 | 2 | 1 | **-50%** |
| Foreshadowing 模型数 | 3 | 1 | **-67%** |
| Wound/Scar 模型数 | 3 | 1 | **-67%** |
| Triple 模型数 | 2 | 1 | **-50%** |
| LLM 接口定义数 | 2 | 1 | **-50%** |
| Prompt 模型数 | 2 | 1 | **-50%** |
| GenerationConfig 数 | 2 | 1 | **-50%** |
| ID 值对象类型数 | 4 | 1(泛型Id[T]) | **-75%** |
| engine/ 镜像文件 | ~10 | 0 | **-100%** |
| God Object 文件数 | 5 | 0 | **-100%** |
| AutopilotDaemon 行数 | 4200+ | ~500 | **-88%** |
| AutoNovelWorkflow 行数 | 2200+ | ~300 | **-86%** |
| autopilot_routes 行数 | 2500+ | ~300/文件 | **-88%** |
| main.py 行数 | 1100+ | ~200 | **-82%** |
| 持久化队列版本 | 3 | 1 | **-67%** |
| 全局单例数 | 12 | 0 (DI容器) | **-100%** |
| 前端 API 文件数 | 32 | ~10 | **-69%** |
| 可删除死代码文件 | ~25 | 0 | — |
| 架构问题总数 | 192 | 0 | — |
| 构造函数最大参数数 | 20 | 5 | **-75%** |
| domain/ai/ 目录 | 存在 | 删除 | — |

#### 15.12.4 最终治理优先级（修订版）

**第一阶段（1-2周）— 止血**：
1. 删除 `domain/ai/` 整个目录，接口迁移到 `engine/core/ports/`
2. 删除 4 个冗余 Character 定义，统一到 `engine/core/entities/character.py`
3. 删除 2 个冗余 CharacterId，统一到 `engine/core/entities/character.py`
4. 合并 3 个伏笔模型为 1 个
5. 合并 2 个 Triple 模型为 1 个

**第二阶段（2-4周）— 拆分**：
1. 拆分 `AutopilotDaemon`(4200行) → 5-8 个状态处理器
2. 拆分 `autopilot_routes.py`(2500行) → 8-10 个路由文件
3. 拆分 `AutoNovelWorkflow`(2200行) → 3-4 个阶段处理器
4. 拆分 `main.py`(1100行) → ProcessManager + ServerBootstrap + DaemonRunner
5. 引入 DI 容器替代全局单例

**第三阶段（4-8周）— 重构**：
1. 统一配置管理（删除硬编码）
2. 统一时区处理
3. 消除 `List[Dict[str, Any]]`，定义具体值对象
4. 统一"已放弃"语义（删除魔法数字 -1）
5. 抽取泛型 `Id[T]` 值对象

**第四阶段（持续）— 巩固**：
1. 为 `BaseEntity` 增加领域事件收集机制（学习 `Prop` 的设计）
2. 建立架构守护测试（ArchUnit）
3. 建立 Prompt 包依赖关系图
4. 统一前端状态管理
5. 完善 API 版本控制

#### 15.12.5 核心诊断（最终修订版）

PlotPilot 系统的架构问题可以归结为 **一个根因、四个症状**：

**根因：缺乏统一抽象 + 缺少架构守护**

系统在快速迭代中，每一层都在"自己造轮子"而非复用下层抽象。当需求变化时，开发者倾向于在新位置创建新模型，而非修改旧模型，导致模型爆炸。缺少架构守护测试意味着每次违规都没有成本。

**四个症状**：

1. **实体膨胀**：5版 Character、3版 Foreshadowing、2版 Triple。同一概念被反复定义，字段有重叠也有差异，永远无法对齐。

2. **God Object**：`AutopilotDaemon`(4200行)、`AutoNovelGenerationWorkflow`(2200行)、`autopilot_routes`(2500行)、`Novel`(4200+行)、`main.py`(1100行)。每个 God Object 都是"不敢删旧代码"的产物。

3. **层级穿透**：`domain/ai/` 定义基础设施接口、路由直接SQL、12个全局单例绕过DI。每一层都在跨层调用，分层架构名存实亡。

4. **接口分裂**：`LLMPort` vs `LLMService`、`PromptValue` vs `Prompt`、两版 `GenerationConfig`、`PersistencePort` vs `Repository`。同一关注点有两套接口，实现者不知道该实现哪个。

**治理铁律（修订版）**：

1. **一个概念只有一个权威定义** — 违者删
2. **一个文件不超过 500 行** — 违者拆
3. **一个构造函数不超过 5 个参数** — 违者用 Protocol 接口收敛
4. **一个路由文件不超过 300 行** — 违者按职责拆分
5. **禁止 lazy import + try/except 降级** — 违者 fail-fast
6. **禁止路由直接 SQL** — 违者走 Repository
7. **禁止领域层定义基础设施接口** — 违者移至 Port
8. **禁止魔法数字** — 违者用枚举或常量
9. **每个 PR 必须通过架构守护测试** — 违者不合并

---

## 十六、R13-R15 深度审查：domain/knowledge + domain/prop + domain/character + domain/ai + engine/core + infrastructure

> 审查范围：逐文件扫描 domain/knowledge/、domain/prop/、domain/character/、domain/ai/、engine/core/、infrastructure/persistence/database/
> 新增问题编号：P193-P224

### 16.1 Triple 双重定义：KnowledgeTriple vs Triple（P193, P0 重复确认）

| 位置 | 类型 | 关键差异 |
|------|------|----------|
| `domain/knowledge/knowledge_triple.py` → `KnowledgeTriple` | `BaseEntity` 子类 | `subject: str, predicate: str, object: str`（纯文本三元组），16个构造参数 |
| `domain/bible/triple.py` → `Triple` | `dataclass` | `subject_type, subject_id, predicate, object_type, object_id`（类型化实体三元组），含 `to_dict/from_dict` |

**核心矛盾**：
- `KnowledgeTriple` 用纯文本 `subject/object`（如"林羽"），无法区分同名不同实体
- `Triple` 用 `subject_type + subject_id` 实体化引用（如 `character/uuid-xxx`），支持类型化查询
- `infrastructure/persistence/database/triple_repository.py`（522行）只使用 `Triple`，完全忽略 `KnowledgeTriple`
- `infrastructure/persistence/database/sqlite_knowledge_repository.py`（859行）的 `get_by_novel_id()` 返回 `StoryKnowledge` 内含 `List[KnowledgeTriple]`，但写入时接受 `dict`（不使用任何领域对象）
- **`KnowledgeTriple` 实际上是死代码**——持久化层从未用它写入，只在读取时构造

**新增问题 P193**：`KnowledgeTriple` 和 `Triple` 字段映射混乱，`_triple_to_fact_dict()` 和 `_row_to_triple()` 手动做字段转换，超过100行胶水代码。

**治理方案**：删除 `KnowledgeTriple`，`StoryKnowledge.facts` 改为 `List[Triple]`。

### 16.2 StoryKnowledge 聚合根设计问题（P194, P1）

**文件**：`domain/knowledge/story_knowledge.py`

**问题**：
1. **内存中全量加载**：`StoryKnowledge` 将所有 `facts` 和 `chapters` 存在内存列表中。当三元组超过1000条时，`add_or_update_fact()` 的 O(n) 线性搜索成为性能瓶颈。
2. **缺少索引数据结构**：没有按 `subject_entity_id`、`predicate`、`entity_type` 的查找方法，但下游 `ConsistencyChecker` 需要。
3. **聚合根边界过大**：`StoryKnowledge` 聚合了"章节摘要"和"知识三元组"两个独立关注点，违反单一职责。
4. **`chapters` 命名歧义**：字段叫 `chapters` 但类型是 `List[ChapterSummary]`，不是 `List[Chapter]`。

**治理方案**：将 `ChapterSummary` 和 `KnowledgeTriple`（→`Triple`）拆分为独立聚合根，各自拥有独立的 Repository。

### 16.3 domain/ai/ 层级违规确认（P195-P198, P0）

**文件清单**：
- `domain/ai/services/llm_service.py` — `LLMService` 抽象接口
- `domain/ai/services/embedding_service.py` — `EmbeddingService` 抽象接口
- `domain/ai/services/vector_store.py` — `VectorStore` 抽象接口
- `domain/ai/value_objects/prompt.py` — `Prompt` 值对象
- `domain/ai/value_objects/token_usage.py` — `TokenUsage` 值对象

**与 engine/core/ports/ 的完整冲突映射**：

| domain/ai/ | engine/core/ports/ | 差异 |
|------------|---------------------|------|
| `LLMService` | `LLMPort` | 方法签名不同：`LLMService.generate(prompt, config)` vs `LLMPort.generate(prompt_value, config)` |
| `Prompt(system, user)` | `PromptValue(template_id, variables)` | 完全不同的抽象：一个是原始文本，一个是模板+变量 |
| `GenerationConfig(model, max_tokens, temperature)` | `GenerationConfig(model, max_tokens, temperature, response_format)` | 后者多了 `response_format` |
| `GenerationResult(content, token_usage)` | `GenerationResult(content, token_usage)` | 相同但类型不同 |
| `EmbeddingService` | 无对应 | 独有 |
| `VectorStore` | 无对应 | 独有 |
| `TokenUsage` | 无对应 | 独有 |

**新增问题 P195**：`Prompt` vs `PromptValue` 的根本冲突——`Prompt` 是静态文本对，`PromptValue` 是模板化渲染。但 `infrastructure/ai/` 的 Provider 实现用的是自己的格式，不依赖任何一个。

**新增问题 P196**：`domain/ai/services/chapter_summarizer.py` — 这个"领域服务"直接调用 LLM，是应用层逻辑错放到领域层。

**新增问题 P197**：`VectorStore` 接口包含 `create_collection/delete_collection/list_collections`，这是纯粹的基础设施管理接口，不属于领域。

**新增问题 P198**：`TokenUsage` 值对象虽然设计合理，但放在 `domain/ai/` 下，应该移到 `domain/shared/` 或 `engine/core/value_objects/`。

**治理方案**：
1. 删除 `domain/ai/` 整个目录
2. `LLMService` + `EmbeddingService` → 合并进 `engine/core/ports/LLMPort`
3. `VectorStore` → 移到 `engine/core/ports/VectorStorePort`
4. `PromptValue` 保留，`Prompt` 删除
5. `TokenUsage` 移到 `engine/core/value_objects/`

### 16.4 domain/character/entities/character.py — 第5版 Character（P199, P0）

**文件**：`domain/character/entities/character.py`（63行）

```python
@dataclass
class Character:
    """统一角色聚合根 — 合并 Bible / 引擎心理画像 / 动态状态"""
    id: CharacterId
    novel_id: str
    name: str
    # ... 33个字段 ...
    mental_state: str = "NORMAL"  # ← 魔法字符串
    emotional_arc: List[Dict[str, Any]] = field(default_factory=list)  # ← 无类型安全
```

**与 engine/core/entities/character.py 的冲突**：

| 特性 | domain/character/ | engine/core/ |
|------|-------------------|--------------|
| ID 类型 | `CharacterId`（自己的版本） | `CharacterId`（另一版本） |
| 心理画像 | `mental_state: str` | 四维心理画像（地质叠层+POV防火墙） |
| 声纹 | `verbal_tic + voice_style + sentence_pattern` | `voice_lock()` |
| 伤疤/执念 | `active_wounds: List[Dict[str, Any]]` | 完整的 `Scar/Motivation` 值对象 |
| 状态演进 | `update_state()` — 直接修改字段 | `evolution_patches` — 不可变地质叠层 |

**新增问题 P199**：`domain/character/entities/character.py` 是最薄弱的 Character 版本，但注释声称"统一角色聚合根"，事实上统一从未发生。

### 16.5 engine/core/entities/foreshadow.py — 第3版 Foreshadowing（P200, P1）

**文件**：`engine/core/entities/foreshadow.py`（158行）

**三版 Foreshadowing 对比**：

| 特性 | engine/core/ `Foreshadow` | domain/novel/ `Foreshadowing` (VO) | domain/novel/ `ForeshadowingRegistry` |
|------|---------------------------|-------------------------------------|---------------------------------------|
| 类型 | `dataclass`（可变） | `dataclass(frozen=True)` | 聚合根，管理集合 |
| 状态机 | 5状态：PLANTED→REFERENCED→AWAKENING→RESOLVED，+ABANDONED | 3状态：PLANTED→RESOLVED，+ABANDONED | 委托给 `Foreshadowing` VO |
| ID 类型 | `ForeshadowId` 值对象 | `str` | 通过 VO |
| 独有字段 | `emotional_weight`、`planting_atmosphere`、`echo_instruction`、`binding_level`、`reference_chapters` | 无 | `apply_ttl_downgrade()`、`get_t0_eligible_foreshadowings()` |
| 爽文逻辑 | 无 | 无 | 内嵌 TTL GC + T0 优先级筛选 |

**新增问题 P200**：
1. `Foreshadow` 的5状态机比 `Foreshadowing` 的3状态多了 `REFERENCED` 和 `AWAKENING`，这是设计进步，但两个模型从未统一。
2. `ForeshadowingRegistry.apply_ttl_downgrade()` 硬编码了爽文引擎逻辑（TTL=15、1.2x 阈值），这不是领域逻辑而是引擎策略。
3. `ForeshadowingRegistry.get_t0_eligible_foreshadowings()` 和 `get_deferred_foreshadowings()` 包含重复的筛选逻辑。

**治理方案**：以 `engine/core/entities/foreshadow.py` 的5状态机为权威，提取 TTL/优先级策略为 Strategy 模式。

### 16.6 engine/core/entities/story.py — Story vs Novel 双重聚合根（P201, P1）

**文件**：`engine/core/entities/story.py`（177行）

**问题**：
1. `Story` 和 `domain/novel/entities/novel.py` 的 `Novel` 是同一个业务概念（"一部小说"），但字段完全不同：
   - `Story`：纯业务模型，只有 `story_id, title, premise, characters, plot_arcs, chapters`
   - `Novel`：4200+行的 God Object，包含所有配置、状态、设定
2. `Story.story_phase` 与 `domain/novel/value_objects/story_phase.py` 冲突——后者已是 re-export 兼容层，但仍有代码从旧位置导入
3. `Story.advance_plot(event: Dict[str, Any])` 用 `Dict[str, Any]` 参数——无类型安全

**新增问题 P201**：`Story` 聚合根设计理念正确（纯业务、无技术污染），但与 `Novel` God Object 并存导致数据双源。谁才是"一部小说"的权威定义？

**治理方案**：`Story` 保留为纯业务聚合根，`Novel` 拆分为 `NovelConfig` + `NovelState` + `NovelMetadata`，`Story` 成为它们的组合根。

### 16.7 infrastructure/persistence/database/triple_repository.py — God Repository（P202-P205, P1）

**文件**：`infrastructure/persistence/database/triple_repository.py`（522行）

**问题**：
1. **P202**：522行的 Repository 文件，包含同步和异步两套 API（`persist_triple_sync` / `await save`），维护成本翻倍。
2. **P203**：`_triple_to_fact_dict()` 100行手动字段映射，`Triple` → `dict` 转换时从 `attributes` 中 pop 字段（`subject_label`, `object_label`, `subject_importance`），但反向 `_row_to_triple()` 又塞回去。这种隐式字段搬家极易出错。
3. **P204**：`save_batch()` 用 `time.sleep(0.01)` 让出时间片——这不是正确的并发控制方式，应该用 WAL 模式 + 事务隔离级别。
4. **P205**：直接用 `domain.bible.triple.Triple` 而不通过 Repository 接口——绕过了 DDD 的依赖倒置。

**治理方案**：
1. 拆分为 `TripleReadRepository` + `TripleWriteRepository`
2. 用 Mapper 模式替代手动字段映射
3. 删除 `time.sleep()` 依赖，用 SQLite WAL 的正常并发机制
4. 通过 `KnowledgeRepository` 接口间接访问

### 16.8 infrastructure/persistence/database/sqlite_knowledge_repository.py — 859行 God Repository（P206-P209, P1）

**文件**：`infrastructure/persistence/database/sqlite_knowledge_repository.py`（859行）

**问题**：
1. **P206**：859行，是项目中最长的 Repository 文件。混合了"知识图谱 CRUD"和"章节摘要 CRUD"和"溯源 CRUD"三个独立关注点。
2. **P207**：`save()` 方法（L713-L795）83行，包含知识行写入 + 全量删除 + 批量插入三元组 + 全量删除 + 批量插入章节摘要。全量替换策略在大数据量时性能灾难。
3. **P208**：`save_all()` 方法（L797-L858）与 `save()` 功能重复，接受 `dict` 而非 `StoryKnowledge`——绕过领域模型。
4. **P209**：`revoke_chapter_inference_for_story_node()` 方法（L580-L652）包含复杂的"读-判断-写"逻辑，直接操作 `write_dispatch`，这是应用层逻辑泄漏到基础设施层。

**治理方案**：
1. 拆分为 `SqliteTripleRepository` + `SqliteChapterSummaryRepository` + `SqliteProvenanceRepository`
2. `save()` 改为增量 upsert 而非全量替换
3. 删除 `save_all()`，统一使用领域对象
4. `revoke_*()` 逻辑移到应用服务层

### 16.9 domain/prop/ — 项目最佳 DDD 实现（正面案例）（P210, 设计良好）

**文件清单**：
- `domain/prop/entities/prop.py` — 66行，聚合根
- `domain/prop/value_objects/prop_event.py` — 领域事件
- `domain/prop/value_objects/lifecycle_state.py` — 状态机 + 转换验证
- `domain/prop/value_objects/prop_category.py` — 分类枚举
- `domain/prop/value_objects/prop_id.py` — ID 值对象
- `domain/prop/repositories/prop_repository.py` — 仓储接口
- `domain/prop/repositories/prop_event_repository.py` — 事件仓储
- `domain/prop/repositories/prop_snapshot_repository.py` — 快照仓储

**优点总结**：
1. ✅ 聚合根通过 `apply_event()` 收集领域事件，`pop_pending_events()` 释放——标准的 Event Sourcing 模式
2. ✅ `LifecycleState` 有完整的 `VALID_TRANSITIONS` 和 `validate_transition()`——类型安全的状态机
3. ✅ `PropEvent` 是 `frozen=True` 的不可变值对象——事件不可篡改
4. ✅ `PropId` 独立值对象——ID 语义明确
5. ✅ 三个 Repository 接口职责清晰：实体CRUD / 事件追加 / 快照读写
6. ✅ 整个模块总计 ~200行代码，无一行冗余

**唯一问题 P210**：`PropEvent.target_lifecycle_state()` 内部 `from domain.prop.value_objects.lifecycle_state import LifecycleState` 延迟导入——应该用 `TYPE_CHECKING` 或在模块级导入。

### 16.10 domain/novel/value_objects/character_state.py — Scar 与 EmotionLedger 的 Wound 重复（P211, P1）

**问题**：
1. `character_state.py` 中的 `Scar(source_event, impact, sensitivity_tags, intensity)` — 追踪心理创伤
2. `engine/core/value_objects/emotion_ledger.py` 中的 `EmotionalWound(description, impact, chapter_number)` — 也是心理创伤
3. 两者语义几乎相同（`source_event` ≈ `description`，`impact` 相同），但：
   - `Scar` 有 `sensitivity_tags`、`intensity`（1-10）、遗忘曲线
   - `EmotionalWound` 更简单，只有描述和影响
   - `Scar` 属于 `CharacterState` 子模型
   - `EmotionalWound` 属于 `EmotionLedger` 子模型

**新增问题 P211**：两个"伤疤"模型同时存在，`Scar` 更完善但 `EmotionalWound` 更简洁。应合并为一个。

**治理方案**：保留 `Scar`（功能更完整），`EmotionLedger` 的 `wounds` 字段改为 `List[Scar]`。

### 16.11 domain/novel/entities/plot_arc.py — 爽文引擎硬编码（P212-P214, P2）

**文件**：`domain/novel/entities/plot_arc.py`（256行）

**问题**：
1. **P212**：`STEP_PHASES_DEFAULT` 硬编码了5阶段张力配置（daily/provocation/eruption/aftermath/settlement），这些数值（10%/30%/80%/40%/20%）应该来自配置文件。
2. **P213**：`get_step_tension_profile()` 内部 `if chapter_number <= 3` 硬编码了"前三章加速版本"——魔法数字。
3. **P214**：4种插值模式（LINEAR/SMOOTHSTEP/HERMITE/STEP）各有实现，但 `INTERPOLATION_STEP` 的实现仅仅是 `interpolated_value = next_point.tension.value`——这不需要单独的插值模式，用配置即可。

**治理方案**：
1. 张力曲线配置外部化到 YAML/JSON
2. "前三章特殊处理"提取为 `EarlyChapterStrategy`
3. STEP 模式简化为配置项而非代码模式

### 16.12 domain/novel/entities/foreshadowing_registry.py — 职责过载（P215-P217, P1）

**文件**：`domain/novel/entities/foreshadowing_registry.py`（437行）

**问题**：
1. **P215**：同时管理 `Foreshadowing` 集合和 `SubtextLedgerEntry` 集合——两个不同概念的聚合根。
2. **P216**：`apply_ttl_downgrade()`（80行）和 `get_t0_eligible_foreshadowings()`（80行）内嵌了爽文引擎的 GC 策略——这是引擎层逻辑，不属于领域实体。
3. **P217**：`apply_chapter_renumber_after_chapter_deleted()`（55行）是基础设施关注点（章节号重映射），应属于应用服务。

**治理方案**：
1. 拆分为 `ForeshadowingRegistry` + `SubtextLedger` 两个独立聚合根
2. TTL/优先级策略提取为 `ForeshadowingGCStrategy` 接口
3. 章节号重映射移到应用服务

### 16.13 domain/novel/services/consistency_checker.py — 骨架服务（P218, P2）

**文件**：`domain/novel/services/consistency_checker.py`（275行）

**问题**：
1. `check_character_consistency()` 只检查"角色是否存在"——这根本不需要一个领域服务
2. `check_relationship_consistency()` 同样只检查"两个角色是否存在"
3. `check_event_logic()` 只检查"涉及的角色是否存在"
4. `resolve_foreshadowing_reference()` 包含模糊匹配逻辑——这是 LLM 输出解析，不是领域逻辑
5. 所有 `check_*` 方法都只是"存在性检查"，没有真正的一致性验证（如"角色行为是否符合人设"）

**新增问题 P218**：`ConsistencyChecker` 是典型的"Design-First, Implementation-Lag"——接口设计完整但实现只是占位符。

### 16.14 domain/novel/value_objects/narrative_debt.py — 魔法数字 -1（P219, P2，重复确认）

**文件**：`domain/novel/value_objects/narrative_debt.py`（196行）

**问题**：
1. `NarrativeDebt.abandon()` 设置 `resolved_chapter = -1`
2. `is_abandoned` 通过 `resolved_chapter == -1` 判断
3. `Motivation.dissolve()` 同样设置 `resolved_chapter = -1`
4. `-1` 作为特殊语义值，需要每个消费方都知道这个约定

**新增问题 P219**：同一文件中 `NarrativeDebt` 和 `Motivation` 都用 `-1` 表示"主动放弃"，但 `ForeshadowingStatus.ABANDONED` 用的是枚举。应统一为枚举。

### 16.15 infrastructure/persistence/mappers/ — 6个 Mapper 但仍有手动转换（P220, P2）

**问题**：
1. 项目已有 `infrastructure/persistence/mappers/` 目录（`bible_mapper.py`, `cast_mapper.py`, `chapter_mapper.py`, `foreshadowing_mapper.py`, `novel_mapper.py`, `plot_arc_mapper.py`）
2. 但 `triple_repository.py` 的 `_triple_to_fact_dict()` 和 `_row_to_triple()` 仍在做手动映射——没有 `triple_mapper.py`
3. `sqlite_knowledge_repository.py` 的 `save()` 方法也在手动做 `KnowledgeTriple` → `dict` 转换

**新增问题 P220**：Mapper 体系不完整，Triple 和 Knowledge 缺少 Mapper。

### 16.16 engine/core/ports/ports.py — 端口定义与 domain/ai/ 完全重叠（P221, P0 重复确认）

**文件**：`engine/core/ports/ports.py`（15行 re-export）

**问题**：`ports.py` 只是从 `engine.core.ports` 包 re-export，而实际定义在 `engine/core/ports/__init__.py` 中。这与 `domain/ai/` 的接口完全冲突（见 16.3）。

### 16.17 domain/novel/value_objects/chapter_state.py — 全 Dict[str, Any]（P222, P2，重复确认）

**文件**：`domain/novel/value_objects/chapter_state.py`（40行）

**问题**：
1. 所有7个字段都是 `List[Dict[str, Any]]`——零类型安全
2. `new_characters: List[Dict[str, Any]]` 应为 `List[CharacterAppearance]`
3. `character_actions: List[Dict[str, Any]]` 应为 `List[CharacterAction]`
4. `relationship_changes: List[Dict[str, Any]]` 应为 `List[RelationshipChange]`
5. `foreshadowing_planted: List[Dict[str, Any]]` 应为 `List[ForeshadowingPlanted]`
6. `events: List[Dict[str, Any]]` 应为 `List[NarrativeEvent]`

### 16.18 domain/novel/value_objects/consistency_context.py — TYPE_CHECKING 依赖六层（P223, P2）

**文件**：`domain/novel/value_objects/consistency_context.py`（25行）

**问题**：`ConsistencyContext` 通过 `TYPE_CHECKING` 导入了6个不同模块的类型：
- `domain.bible.entities.bible.Bible`
- `domain.bible.entities.character_registry.CharacterRegistry`
- `domain.novel.entities.foreshadowing_registry.ForeshadowingRegistry`
- `domain.novel.entities.plot_arc.PlotArc`
- `domain.novel.value_objects.event_timeline.EventTimeline`
- `domain.bible.value_objects.relationship_graph.RelationshipGraph`

这6个依赖意味着 `ConsistencyContext` 是一个跨6个限界上下文的"超级聚合器"，它实际上是一个应用层 DTO 而非领域值对象。

### 16.19 domain/knowledge/triple_provenance.py — 唯一设计良好的模型（P224, 设计良好）

**文件**：`domain/knowledge/triple_provenance.py`（27行）

**优点**：
1. ✅ `TripleProvenanceRecord` 是 `frozen=True` 的不可变值对象
2. ✅ `to_row_dict()` 方法清晰地处理持久化映射
3. ✅ 只有一个职责：记录三元组的推断证据
4. ✅ 27行代码，零冗余

---

## 十七、R16-R19 审查：application/ + interfaces/ + engine/application/ + frontend/

> 审查范围：application/、interfaces/、engine/application/、frontend/src/
> 新增问题编号：P225-P236

### 17.1 engine/application/ — 双应用层并存（P225, P1）

**问题**：`engine/application/` 只有4个子模块（`checkpoint_manager/`、`plot_state_machine/`、`quality_guardrails/`、`writing_orchestrator.py`），而 `application/` 目录下有14个子目录。两套应用层并存，职责边界不清。

**治理方案**：将 `engine/application/` 的所有模块迁移到 `application/` 对应子目录下，然后删除 `engine/application/`。

### 17.2 quality_guardrails/ vs application/audit/ — 审计逻辑分散（P226, P2）

**问题**：8个护栏服务在 `engine/application/quality_guardrails/`，但 `application/audit/services/` 下也有审计服务。审计/质量检查逻辑分散在两个位置。

### 17.3 application/engine/services/ — 34文件的巨型子目录（P227-P228, P1）

**问题**：
1. **P227**：`application/engine/services/` 下有34个服务文件，涵盖章节生成、节拍续写、上下文组装、DAG、叙事投影、主题、规则、守护进程等。其中 `AutopilotDaemon` 是4200+行的 God Object。
2. **P228**：没有 `__init__.py` 导出控制，所有34个文件都是公开API。

**治理方案**：按功能域拆分为 `application/engine/generation/`、`application/engine/context/`、`application/engine/daemon/`、`application/engine/dag/`。

### 17.4 application/ai/ — LLM 调用的胶水层（P229-P230, P2）

**问题**：
1. **P229**：3个 `*_contract.py` 文件定义了 LLM 输出的 JSON Schema 验证，但这些"契约"实际上是 Prompt 设计的一部分，应放在 `infrastructure/ai/prompts/` 中。
2. **P230**：`llm_json_extract.py` 和 `structured_json_pipeline.py` 功能高度重叠——都做"从 LLM 输出提取 JSON"。

### 17.5 autopilot_routes.py — 2500行 God Route（P231, P0 重复确认）

**问题**：单文件2500+行，包含自动驾驶的所有API端点，直接操作 Repository 和数据库连接——绕过应用服务层。

### 17.6 API 路由层直接 SQL（P232, P0）

**问题**：多个路由文件包含直接 SQL 查询，违反分层架构：
- `autopilot_routes.py` — 直接查询 `story_nodes`、`triples` 表
- `knowledge_graph_routes.py` — 直接查询 `triples` 表
- 部分 `core/chapters.py` — 绕过 ChapterRepository

### 17.7 API 版本化不完整（P233, P2）

**问题**：所有路由都在 `v1/` 下，但 `stats/` 在 `api/stats/`（无版本前缀），缺少版本迁移策略。

### 17.8 writing_orchestrator.py — 与 application/engine/ 重叠（P234, P2）

**问题**：`engine/application/writing_orchestrator.py` 与 `application/engine/services/` 下的章节生成服务功能重叠。应统一到 `application/engine/` 下。

### 17.9 前端 API 层膨胀（P235, P1，重复确认）

**问题**：`frontend/src/api/` 有32个文件，每个对应一个后端路由组。但多个文件包含重复的 HTTP 客户端配置和错误处理。

### 17.10 前端 stores/ — 状态管理碎片化（P236, P2）

**问题**：Pinia stores 与后端领域模型1:1映射，导致前端也有"Character 版本爆炸"——不同 store 引用不同版本的 Character 类型。

---

## 十八、最终量化总结（修订版 v3）

### 18.1 问题统计（按严重级别）

| 级别 | 数量 | 典型代表 |
|------|------|----------|
| **P0 致命** | 22 | 5版 Character、3版 Foreshadowing、2版 Triple、domain/ai 层级违规、路由直接SQL、God Object |
| **P1 严重** | 38 | StoryKnowledge 聚合根过大、TripleRepository 522行、ForeshadowingRegistry 职责过载、application/engine 34文件 |
| **P2 中等** | 52 | 硬编码爽文参数、Magic Number -1、List[Dict[str,Any]]、Mapper 不完整、API 版本化 |
| **P3 轻微** | 112 | 命名不一致、注释过时、TYPE_CHECKING 依赖、延迟导入 |
| **总计** | **224** | — |

### 18.2 核心矛盾总结（v3）

| 矛盾 | 表现 | 影响 |
|------|------|------|
| **概念双重定义** | Story vs Novel、KnowledgeTriple vs Triple、Foreshadow vs Foreshadowing、Scar vs EmotionalWound | 消费方不知道用哪个 |
| **God Object** | AutopilotDaemon(4200)、AutoNovelWorkflow(2200)、autopilot_routes(2500)、TripleRepository(522)、SqliteKnowledgeRepository(859) | 无法测试、无法维护 |
| **层级穿透** | domain/ai 定义基础设施接口、路由直接SQL、ConsistencyChecker 是领域层但调 Bible、write_dispatch 在 Repository | 分层名存实亡 |
| **爽文硬编码** | STEP_PHASES_DEFAULT、TTL=15、1.2x阈值、前三章特殊处理 | 无法扩展到非爽文 |
| **类型安全缺失** | 7个 List[Dict[str,Any]]、Magic Number -1、mental_state: str = "NORMAL" | 运行时错误 |
| **设计先行实现滞后** | ConsistencyChecker 骨架、engine/core/services/ 无实现 | 虚假的安全感 |

### 18.3 治理路线图（最终版）

**第一阶段（1-2周）— 止血 🔴**

| 序号 | 行动 | 预期效果 |
|------|------|----------|
| 1 | 删除 `domain/ai/` 整个目录，接口迁至 `engine/core/ports/` | 消除层级违规 |
| 2 | 删除4个冗余 Character 定义，统一到 `engine/core/entities/character.py` | -80% 重复 |
| 3 | 删除 `KnowledgeTriple`，`StoryKnowledge.facts` 改用 `Triple` | -50% Triple 重复 |
| 4 | 合并3个伏笔模型为1个（以 `Foreshadow` 的5状态机为权威） | -67% 重复 |
| 5 | 删除 `engine/application/`，迁移到 `application/` 对应子目录 | 消除双应用层 |

**第二阶段（2-4周）— 拆分 🟡**

| 序号 | 行动 | 预期效果 |
|------|------|----------|
| 1 | 拆分 `AutopilotDaemon`(4200行) → 5-8个状态处理器 | -88% 行数 |
| 2 | 拆分 `autopilot_routes.py`(2500行) → 8-10个路由文件 | -88% 行数 |
| 3 | 拆分 `TripleRepository`(522行) → Read + Write + Mapper | -50% 行数 |
| 4 | 拆分 `SqliteKnowledgeRepository`(859行) → Triple + Summary + Provenance | -60% 行数 |
| 5 | 拆分 `ForeshadowingRegistry` → Registry + SubtextLedger | 职责单一 |
| 6 | 引入 DI 容器替代12个全局单例 | 可测试性 |

**第三阶段（4-8周）— 重构 🟢**

| 序号 | 行动 | 预期效果 |
|------|------|----------|
| 1 | 统一配置管理——爽文参数外部化到 YAML | 可扩展 |
| 2 | 消除 `List[Dict[str, Any]]`——定义具体值对象 | 类型安全 |
| 3 | 统一"已放弃"语义——删除魔法数字-1，用枚举 | 类型安全 |
| 4 | 抽取泛型 `Id[T]` 值对象 | -75% ID 类型 |
| 5 | `StoryKnowledge` 拆分为 `KnowledgeGraph` + `ChapterSummaryIndex` | 聚合根边界正确 |
| 6 | 统一时区处理——`datetime.utcnow()` → `utcnow_iso()` | 时区正确 |

**第四阶段（持续）— 巩固 🔵**

| 序号 | 行动 | 预期效果 |
|------|------|----------|
| 1 | 为 `BaseEntity` 增加领域事件收集机制（学习 `Prop`） | 事件溯源就绪 |
| 2 | 建立架构守护测试（ArchUnit） | 防止回退 |
| 3 | 建立 Prompt 包依赖关系图 | 可维护性 |
| 4 | 统一前端状态管理——消除 Character 类型分裂 | 前后端一致 |
| 5 | 完善 API 版本控制 | 演进能力 |
| 6 | `ConsistencyChecker` 实现真正的行为一致性验证 | 非占位符 |

### 18.4 最终诊断

PlotPilot 系统的核心问题是 **"概念双重定义 + 实现层级穿透"**：

1. 每个核心概念都有2-5个定义版本，消费方被迫选择，导致模块间耦合混乱
2. `domain/ai/` 在领域层定义基础设施接口，`engine/core/ports/` 也在定义同样的接口——两套端口并存
3. 路由层直接 SQL、Repository 手动映射、应用服务骨架化——分层架构形同虚设
4. 爽文引擎的特定逻辑（TTL、阶跃函数、前三章加速）硬编码在领域实体中——无法复用到其他类型

**治理铁律（最终版 v3）**：

1. **一个概念只有一个权威定义** — 违者删
2. **一个文件不超过 500 行** — 违者拆
3. **一个构造函数不超过 5 个参数** — 违者用 Builder/Protocol
4. **禁止领域层定义基础设施接口** — 违者移至 Port
5. **禁止路由直接 SQL** — 违者走 Repository
6. **禁止 `List[Dict[str, Any]]`** — 违者定义值对象
7. **禁止魔法数字** — 违者用枚举或常量
8. **禁止爽文逻辑硬编码在领域实体** — 违者提取策略
9. **每个 PR 必须通过架构守护测试** — 违者不合并
10. **新增代码必须指明权威定义位置** — 违者不合并

治理的第一步不是加新代码，而是 **删重复、统接口、降耦合**。只有收敛了抽象，系统才能重新获得演化的能力。

---

## 十九、R20 审查：engine/runtime/ + engine/pipeline/ + engine/infrastructure/ + domain/shared/ + infrastructure/ai/

> 审查范围：engine/runtime/、engine/pipeline/、engine/infrastructure/、domain/shared/、domain/structure/、domain/worldbuilding/、infrastructure/ai/、infrastructure/persistence/
> 新增问题编号：P237-P256

### 19.1 engine/runtime/ 与 engine/application/ 三重复制（P237, P0）

**问题**：`engine/runtime/` 和 `engine/application/` 之间存在**三个完全相同的文件**：

|| engine/application/ | engine/runtime/ | 是否完全相同 |
|------|------|------|------|
| `checkpoint_manager/manager.py` | 236行 | 236行 | ✅ 逐字节相同 |
| `plot_state_machine/state_machine.py` | 199行 | 199行 | ✅ 逐字节相同 |
| `quality_guardrails/*.py` | 8个文件 | 8个文件 | ✅ 完全相同 |

此外，`writing_orchestrator.py` 在两个目录下各有一份，逻辑**高度相似**但 import 路径不同：
- `engine/application/writing_orchestrator.py` → import from `engine.application.quality_guardrails`
- `engine/runtime/writing_orchestrator.py` → import from `engine.runtime.quality_guardrails`

**影响**：同一模块存在三份副本，修改任何一份时其他副本不会同步更新，导致行为不一致。

**治理方案**：删除 `engine/runtime/`，所有代码统一使用 `engine/application/`。`StoryPipelineRunner` 中 `from engine.runtime.xxx` 的 import 改为 `from engine.application.xxx`。

### 19.2 PolicyValidator — QualityGuardrail 的无意义薄封装（P238, P2）

**文件**：`engine/runtime/policy_validator.py`（224行）

**问题**：
1. `PolicyValidator` 对 `QualityGuardrail` 做了完全透传的薄封装
2. `PolicyReport` 是 `QualityReport` 的逐字段复制
3. `PolicyViolationError` 是 `QualityViolationError` 的逐字段复制
4. 三个方法 `check/enforce/advise` 与 `QualityGuardrail` 的 `check/enforce/advise` 完全一一对应
5. 当 `QualityGuardrail` 不可用时，**静默返回虚假的 0.85 通过报告**——这是严重的安全隐患

```python
# 降级：返回默认通过（！！！）
return PolicyReport(
    overall_score=0.85,
    passed=True,
)
```

**治理方案**：删除 `PolicyValidator`，`PipelineContext.policy_validator` 直接使用 `QualityGuardrail`。降级时应抛出异常而非静默通过。

### 19.3 StoryPipelineRunner — 17 个 Optional 构造参数（P239, P1）

**文件**：`engine/runtime/runner.py`（283行）

**问题**：
1. `__init__` 有 17 个参数，其中 14 个是 `Optional` 且默认为 `None`
2. 内部用 `time.sleep()` 做同步阻塞等待——在 async 上下文中不应使用
3. `_get_active_novels()` 捕获所有异常后返回空列表——静默吞错
4. `_handle_act_planning()` 和 `_handle_auditing()` 都是空方法
5. `_make_context()` 中 lazy import `PolicyValidator` 并在失败时 `pass`——同上静默吞错

**治理方案**：用 Builder 模式或 Protocol 注入替代 17 参数构造函数；空方法应标记为 `NotImplementedError` 或至少记录日志。

### 19.4 engine/pipeline/context.py — PipelineContext 是 God Dataclass（P240, P1）

**文件**：`engine/pipeline/context.py`（201行）

**问题**：
1. `PipelineContext` 有 **42 个字段**，是巨型可变数据类
2. 12 个 `Any` 类型的依赖注入字段——零类型安全
3. `inject()` 方法通过 `setattr()` 动态设置字段——绕过了 dataclass 的类型检查
4. 没有任何验证逻辑——可以注入任意类型到任意字段

**治理方案**：
- 将输入字段、各步骤产出、依赖注入分成三个独立类
- 依赖注入使用 `Protocol` 类型而非 `Any`
- 添加 `validate()` 方法检查必需字段

### 19.5 engine/infrastructure/memory/ — 直接 SQL 绕过 Repository（P241, P0）

**文件**：`engine/infrastructure/memory/memory_orchestrator_impl.py`（320行）

**问题**：
1. `_assemble_t0()` 直接执行 `SELECT character_id FROM story_characters`
2. `_assemble_t1()` 直接执行 `SELECT emotion_ledger FROM stories`
3. `_assemble_t2()` 直接执行 `SELECT number, title, content FROM chapters`
4. `_assemble_t3()` 直接执行 `SELECT character_id, character_name FROM story_characters`
5. `update_emotion_ledger()` 直接执行 `SELECT emotion_ledger FROM stories`
6. `restore_state()` 直接执行 `UPDATE stories SET emotion_ledger`
7. `manage_foreshadow()` 直接执行 `UPDATE foreshadows SET status`

**7处直接 SQL**——这是基础设施层中的"上帝 SQL"问题。完全绕过了 Repository 层，且无法被测试。

**治理方案**：所有 SQL 查询应委托给对应的 Repository（`ChapterRepository`、`ForeshadowingRepository`、`NovelRepository`）。

### 19.6 engine/infrastructure/persistence/ — CheckpointStore 缺少 sqlite3 import（P242, P3）

**文件**：`engine/infrastructure/persistence/checkpoint_store.py`（262行）

**问题**：`import sqlite3` 在文件末尾第 261 行，而 `load()` 方法在第 125 行已经使用了 `sqlite3.Row`。虽然 Python 允许延迟 import，但这违反了 PEP 8 的 import 位置约定，且在文件顶部阅读时无法发现这个依赖。

### 19.7 DomainEvent 双重定义（P243, P1）

**问题**：

| 位置 | 类名 | 父类 | 设计 |
|------|------|------|------|
| `domain/shared/events.py` | `DomainEvent` | 无继承 | 可变，有 `aggregate_id` |
| `engine/infrastructure/events/event_bus.py` | `DomainEvent` | 无继承 | `frozen=True`，有 `story_id` |

两个 `DomainEvent` 定义：
- `domain/shared/` 版是传统 DDD 风格（聚合 ID + 事件类型）
- `engine/infrastructure/` 版是 `frozen=True` 的不可变值对象 + `event_type` 字段

此外，`engine/infrastructure/events/event_bus.py` 还定义了 4 个具体事件类（`ChapterCompletedEvent` 等），它们与 `domain/shared/events.py` 的 `DomainEvent` 没有继承关系。

**治理方案**：统一到 `domain/shared/events.py` 的 `DomainEvent` 基类，`engine/infrastructure/` 的具体事件继承它。删除 `engine/infrastructure/events/event_bus.py` 中的 `DomainEvent` 基类。

### 19.8 EventBus 全局单例无事件持久化（P244, P2）

**文件**：`engine/infrastructure/events/event_bus.py`（215行）

**问题**：
1. `_event_history` 只保存在内存中（最多 1000 条），进程重启后丢失
2. 异常处理器只 `logger.error` 但不传播——事件消费方无法知道处理是否成功
3. `publish_sync` 和 `publish` 方法逻辑几乎完全相同——sync/async API 重复

**治理方案**：事件历史应持久化到 DB（或使用 `SqliteTraceStore`）；异常应提供回调机制而非静默吞错。

### 19.9 BaseEntity 过于简陋（P245, P2）

**文件**：`domain/shared/base_entity.py`（22行）

**问题**：
1. 只有 `id`、`created_at`、`updated_at` 三个字段
2. 没有领域事件收集机制（对比 `domain/prop/entities/` 的设计良好实现）
3. 没有 `mark_updated()` 方法——`updated_at` 不会自动更新
4. 不支持软删除、版本号、乐观锁等常用实体能力

**治理方案**：参考 `domain/prop/entities/` 的设计，增加 `_domain_events` 列表和 `collect_events()` 方法。

### 19.10 domain/structure/ — 三个 dataclass 未继承 BaseEntity（P246, P2）

**文件**：`domain/structure/chapter_element.py`、`domain/structure/chapter_scene.py`、`domain/structure/story_node.py`

**问题**：
1. 三个文件都是独立 dataclass，没有继承 `BaseEntity`
2. 都有 `datetime.now` 作为默认值（非 UTC）
3. 都手动实现了 `to_dict()` 和 `from_dict()`——这些应在基类中统一
4. `ChapterScene.characters: List[dict]` 又是 `List[Dict[str, Any]]`——类型安全缺失
5. `StoryNode` 有 30+ 个字段，是另一个 God Dataclass

**治理方案**：继承 `BaseEntity`，用 UTC 时间，`characters` 字段定义具体值对象。

### 19.11 Worldbuilding vs WorldSetting vs Bible — 世界观三重复制（P247, P0）

**问题**：世界观相关概念存在三个独立建模：

| 位置 | 类名 | 特征 |
|------|------|------|
| `domain/worldbuilding/worldbuilding.py` | `Worldbuilding` | 5维度框架（力量/地理/社会/文化/日常），全 `str` 字段 |
| `domain/bible/entities/world_setting.py` | `WorldSetting` | `BaseEntity` 子类，3 种类型（location/item/rule） |
| `domain/bible/entities/bible.py` | `Bible` | 聚合根，管理 characters + world_settings + locations + timeline + style |

三者的关系：
- `Worldbuilding` 是完整的世界观5维度模型，但字段全是 `str`
- `WorldSetting` 是简化版的世界设定（name + description + type）
- `Bible` 是更大的聚合根，包含 `WorldSetting` 列表

**问题本质**：`Worldbuilding` 的5维度框架（力量体系/地理生态/社会权力/历史文化/沉浸细节）被 `Bible.world_settings` 的简单 name-description 模型完全忽略。两个模型无法互操作。

**治理方案**：以 `Worldbuilding` 的5维度模型为权威定义，`WorldSetting` 改为 re-export 适配器，`Bible` 聚合根引用 `Worldbuilding` 而非 `List[WorldSetting]`。

### 19.12 infrastructure/ai/ — PromptManager 1100行 God Object（P248, P1）

**文件**：`infrastructure/ai/prompt_manager.py`（1113行）

**问题**：
1. 1100+ 行，混合了种子初始化、版本管理、CRUD、渲染、统计等多种职责
2. `VersionInfo`、`NodeInfo`、`TemplateInfo` 三个内部类都各自实现了完整的 `to_dict()`/`from_dict()`——手动映射又一套
3. `ensure_seeded()` 有双重检查锁定模式，但 `_do_ensure_seeded()` 内部可能抛出未捕获异常导致 `_seeded` 永远为 `False`
4. 种子增量更新逻辑（`_should_update_node`）在同一个方法内做了判断+执行——违反 CQS

**治理方案**：拆分为 `PromptSeedService`（种子初始化）、`PromptVersionService`（版本管理）、`PromptQueryService`（查询+渲染）。

### 19.13 Prompt 三层代理：PromptManager → PromptRegistry → PromptRuntimeService（P249, P1）

**问题**：提示词的读取链路过长：

```
业务代码
  → PromptRuntimeService（兼容代理层）
    → PromptRegistry（门面层，缓存+渲染）
      → PromptManager（DB CRUD层）
        → SQLite
```

三层代理，每层都在做几乎相同的事：
- `PromptRuntimeService.render()` → 委托 `PromptRegistry`
- `PromptRegistry.render()` → 委托 `PromptTemplateEngine`
- `PromptManager.render()` → 自己也有一套 `_render_template()`

三个地方都有渲染逻辑！`PromptManager._render_template()` 用 `SafeDict.format_map()`，`PromptRuntimeService._inject_variables()` 用 `re.sub()`，`PromptTemplateEngine` 有自己的 Jinja2 渲染。

**治理方案**：删除 `PromptRuntimeService`（兼容层），渲染统一到 `PromptTemplateEngine`。`PromptManager` 不应包含渲染逻辑。

### 19.14 infrastructure/persistence/database/ — 38 个仓储实现文件（P250, P1）

**文件**：`infrastructure/persistence/database/`（38 个 .py 文件）

**问题**：
1. 38 个仓储实现文件 + 28 个迁移 SQL 文件 = 66 个文件
2. 迁移文件命名不一致：`003_persistence_queue.sql`（有序号）vs `add_anti_ai_audits.sql`（无序号）
3. 缺少迁移框架——没有 `alembic` 或类似的迁移版本管理
4. `schema.sql` 与 28 个增量迁移文件之间的关系不清晰——`schema.sql` 是否包含了所有迁移？

**治理方案**：引入 alembic 迁移框架，统一迁移文件命名和版本管理。`schema.sql` 应该只作为全新安装的初始化脚本。

### 19.15 write_dispatch.py — SQLite 单写者内核但全局变量管理（P251, P2）

**文件**：`infrastructure/persistence/database/write_dispatch.py`（183行）

**问题**：
1. 使用全局变量 `_sqlite_writer_thread_ident` 管理写者线程身份——不是线程安全的设置
2. `startup_sqlite_writes_bypass_queue()` 用 `depth` 计数器管理启动期 bypass——嵌套使用时如果异常退出会导致计数器不归零
3. `sql_is_mutating()` 的 SQL 解析是手写的正则——无法处理所有 SQL 边界情况（如字符串中的 INSERT 关键字）

**治理方案**：将全局变量封装到类中；添加 `try/finally` 保护 depth 计数器；SQL 解析使用参数化查询替代。

### 19.16 engine/core/services/ — 三个抽象接口无实现（P252, P1，重复确认）

**文件**：
- `engine/core/services/story_engine.py`（82行）— `StoryEngine(ABC)` 无实现
- `engine/core/services/character_engine.py`（117行）— `CharacterEngine(ABC)` 无实现
- `engine/core/services/memory_orchestrator.py`（169行）— `MemoryOrchestrator(ABC)`

**问题**：只有 `MemoryOrchestrator` 有实现（`MemoryOrchestratorImpl`），`StoryEngine` 和 `CharacterEngine` 完全没有实现类。这些接口定义了理想态但从未被使用。

**额外问题**：
- `ForeshadowAction` 在 `memory_orchestrator.py` 中重新定义了 `PLANT/REFERENCE/AWAKEN/RESOLVE/ABANDON`，与 `engine/core/entities/foreshadow.py` 的 `ForeshadowStatus` 枚举重复
- `TraumaticEvent` 和 `SceneContext` 在 `character_engine.py` 中用 `__init__` 而非 `dataclass`——风格不一致

### 19.17 WritingOrchestrator — 硬编码爽文阈值（P253, P2）

**文件**：`engine/application/writing_orchestrator.py`（360行）

**问题**：
1. `build_quality_context()` 硬编码 `era: "ancient"` 和 `scene_type: "auto"`
2. `should_trigger_act_checkpoint()` 硬编码 `[0.25, 0.75]` 阈值
3. `generate_novelist_assessment()` 硬编码权重 `0.25/0.25/0.20/0.10/0.20` 和等级 `S/A/B/C/D`
4. 没有任何配置外部化机制

**治理方案**：提取 `AssessmentConfig` 值对象，支持从 YAML 配置加载。

### 19.18 engine/pipeline/base.py — BaseStoryPipeline 736行 God Class（P254, P1）

**文件**：`engine/pipeline/base.py`（736行）

**问题**：
1. 736 行，包含 10 个步骤方法 + 8 个辅助方法
2. `_step_generate()` 中 lazy import `domain.ai.services.llm_service.GenerationConfig`——层级穿透
3. `_post_process_generation()` lazy import `application.ai.llm_output_sanitize` 和 `application.ai.prose_fragment_aggregator`——同样是层级穿透
4. `_make_prompt()` lazy import `domain.ai.value_objects.prompt.Prompt`——层级穿透
5. `_push_persistence_command()` lazy import `application.engine.services.persistence_queue`——层级穿透
6. `_score_tension_via_llm()` 用 `re.search(r'(\d+)', content)` 从 LLM 输出提取数字——脆弱的解析
7. `_save_chapter_via_repository()` 是空方法（只有 `pass`）——未完成的实现

**5 处 lazy import 层级穿透**——pipeline 层同时依赖 domain、application、infrastructure 三层。

**治理方案**：通过 PipelineContext 注入所有依赖，删除所有 lazy import。将 `_step_*` 方法拆分为独立类（Strategy 模式）。

### 19.19 DomainException 层次结构不完整（P255, P3）

**文件**：`domain/shared/exceptions.py`（23行）

**问题**：
1. 只有 3 个异常类：`DomainException`、`EntityNotFoundError`、`InvalidOperationError`、`ValidationError`
2. 缺少常见的领域异常：`ConcurrencyConflictError`、`BusinessRuleViolationError`、`AggregateNotFoundError`
3. `EntityNotFoundError` 有自定义字段 `entity_type/entity_id`，但其他异常没有结构化字段

**治理方案**：补充异常层次结构，所有领域异常增加结构化字段。

### 19.20 DomainEvent 事件体系未与 BaseEntity 集成（P256, P2）

**问题**：
1. `domain/shared/events.py` 定义了 `DomainEvent` 基类
2. `domain/shared/base_entity.py` 的 `BaseEntity` 没有引用 `DomainEvent`
3. 实体无法收集和发布领域事件——事件驱动架构只有定义没有使用
4. 唯一使用事件总线的地方是 `engine/infrastructure/events/event_bus.py`——但它定义了自己的事件类

**治理方案**：为 `BaseEntity` 增加 `_domain_events: List[DomainEvent]` 和 `collect_events()` 方法，学习 `domain/prop/entities/` 的设计。

---

## 二十、R20 审查：infrastructure/persistence/ + interfaces/ + frontend/

> 审查范围：infrastructure/persistence/database/、interfaces/api/v1/、frontend/src/stores/、frontend/src/composables/、config/
> 新增问题编号：P257-P268

### 20.1 infrastructure/persistence/database/ — 仓储实现中的手动映射泛滥（P257, P1）

**问题**：在 38 个仓储文件中，手动映射（`_row_to_xxx()` / `_xxx_to_row_dict()`）的模式被反复实现：
- `sqlite_chapter_repository.py` — 手动映射 Chapter
- `sqlite_novel_repository.py` — 手动映射 Novel
- `sqlite_bible_repository.py` — 手动映射 Bible
- `sqlite_knowledge_repository.py` — 手动映射 Knowledge
- `triple_repository.py` — 手动映射 Triple
- ... 等等

`infrastructure/persistence/mappers/` 目录下只有 6 个 Mapper（bible, cast, chapter, foreshadow, novel, plot_arc），但仓储层有 38 个实现——大部分仓储没有使用 Mapper。

**治理方案**：所有仓储统一使用 Mapper 层，禁止在仓储内做手动 `dict → entity` 转换。

### 20.2 interfaces/api/v1/ — API 路由文件 38+（P258, P1）

**问题**：`interfaces/api/v1/` 下有 38 个路由文件，分布在 9 个子目录中：

| 子目录 | 文件数 | 典型文件 |
|--------|--------|----------|
| core/ | 6 | novels.py, chapters.py |
| engine/ | 11 | autopilot_routes.py(2500行), generation.py |
| world/ | 5 | bible.py, knowledge_graph_routes.py |
| audit/ | 3 | chapter_review_routes.py |
| blueprint/ | 4 | beat_sheet_routes.py |
| analyst/ | 3 | foreshadow_ledger.py |
| prop/ | 1 | prop_routes.py |
| workbench/ | 4 | sandbox.py, monitor.py |
| 其他 | 4 | anti_ai.py, system.py |

**问题本质**：API 路由与后端领域模型 1:1 映射，而非面向用例设计。消费者需要知道后端的内部结构才能使用 API。

### 20.3 interfaces/api/v1/engine/ — 11 个引擎相关路由（P259, P2）

**问题**：引擎相关的 API 有 11 个路由文件，但引擎是一个内部实现细节，不应暴露在 API 层。`autopilot_routes.py`（2500行）、`checkpoint_routes.py`、`trace_routes.py` 等都是引擎内部的运维接口。

**治理方案**：将引擎运维路由移到 `interfaces/api/debug/` 或 `interfaces/api/v1/internal/`，与面向用户的 API 分离。

### 20.4 frontend/src/stores/ — 仅 10 个 Pinia Store（P260, P2）

**问题**：
1. 只有 10 个 Store，但后端有 38 个 API 路由文件
2. `autopilotWorkspaceStore.ts` 可能是一个 God Store（涵盖自动驾驶的所有状态）
3. `promptPlazaBridge.ts` 作为 Store 命名不当——Bridge 应该是 composable 或 service

**治理方案**：Store 应面向 UI 功能域组织，而非 1:1 映射后端模型。

### 20.5 frontend/src/composables/ — 仅 4 个 composable（P261, P2）

**文件**：
- `useChapterDeskLayout.ts`
- `useDAGSSE.ts`
- `useWorkbench.ts`
- `useWorkbenchNarrativeSync.ts`

**问题**：4 个 composable 对应数十个组件——复用逻辑严重不足。很多应该在 composable 中的逻辑可能被重复实现在各组件中。

### 20.6 config/ — 仅 1 个 YAML 配置文件（P262, P2）

**问题**：`config/` 目录下只有 `performance.yaml` 一个文件。但代码中大量硬编码的配置参数：
- `PlotStateMachine.PHASE_BUDGET` 中的张力阈值
- `WritingOrchestrator.should_trigger_act_checkpoint()` 中的 0.25/0.75
- `ShortDramaPipeline.FORCE_REVERSAL_INTERVAL = 3`
- `BUSY_TIMEOUT_MS = 30000`
- `BaseStoryPipeline.DEFAULT_TARGET_WORDS = 2500`

**治理方案**：将所有硬编码参数提取到 `config/` 下的 YAML 文件中，支持运行时覆盖。

### 20.7 engine/examples/ — 示例代码不应在主包中（P263, P3）

**文件**：`engine/examples/short_drama_pipeline.py`、`engine/examples/wuxia_pipeline.py`

**问题**：示例代码位于主包 `engine/` 下，会被打包和发布。这些文件应放在 `examples/` 顶级目录或 `docs/` 中。

### 20.8 character_soul.py — 兼容层标记删除但无计划（P264, P3）

**文件**：`engine/infrastructure/memory/character_soul.py`（14行）

**问题**：注释说"此文件将在 v4.0 移除"，但：
1. 没有 v4.0 的时间表
2. 没有迁移指南
3. 没有弃用警告（`DeprecationWarning`）

**治理方案**：添加 `warnings.warn("CharacterSoulEngine is deprecated, use CharacterPsycheEngine", DeprecationWarning, stacklevel=2)`。

### 20.9 PromptManager.render() 与 PromptRegistry.render() 重复渲染逻辑（P265, P1）

**问题**：

| 类 | 渲染方法 | 实现方式 |
|------|------|------|
| `PromptManager._render_template()` | `SafeDict.format_map()` | 简单 `{var}` 替换 |
| `PromptRuntimeService._inject_variables()` | `re.sub(r'\{(\w+)\}', ...)` | 正则替换 |
| `PromptRegistry.render()` | `PromptTemplateEngine.render()` | 完整模板引擎 |

三种不同的变量替换实现！`PromptManager` 用 `format_map()`，`PromptRuntimeService` 用 `re.sub()`，`PromptRegistry` 用 `PromptTemplateEngine`。如果 `PromptTemplateEngine` 支持所有功能，前两者是冗余的。

**治理方案**：删除 `PromptManager._render_template()` 和 `PromptRuntimeService._inject_variables()`，统一使用 `PromptTemplateEngine`。

### 20.10 PromptManager 全局单例无依赖注入（P266, P1）

**问题**：
```python
_manager_instance: Optional[PromptManager] = None

def get_prompt_manager() -> PromptManager:
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = PromptManager()  # 无参数！
    return _manager_instance
```

`PromptManager`、`PromptRegistry`、`VariableRegistry` 三个全局单例都在 `get_xxx()` 函数中无参创建，内部通过 `_get_db()` 延迟获取数据库连接。这种设计使得：
1. 无法在测试中注入 mock
2. 无法为不同小说使用不同的 PromptManager 实例
3. 三个单例之间有隐式依赖（`PromptRegistry._get_manager()` → `get_prompt_manager()`）

**治理方案**：引入 DI 容器管理这三个单例的生命周期和依赖关系。

### 20.11 infrastructure/ai/providers/ — 4 个 LLM Provider 但无统一接口（P267, P1）

**文件**：`infrastructure/ai/providers/`（6 个文件）

**问题**：
- `base.py` — `BaseLLMProvider`
- `openai_provider.py` — `OpenAIProvider`
- `anthropic_provider.py` — `AnthropicProvider`
- `gemini_provider.py` — `GeminiProvider`
- `mock_provider.py` — `MockProvider`
- `model_resolution.py` — 模型名解析

但在 `domain/ai/services/llm_service.py` 中也定义了 `LLMService` 接口（Protocol），两者职责重叠。`domain/ai/` 定义了抽象，`infrastructure/ai/providers/` 也定义了抽象——两套抽象并存。

### 20.12 infrastructure/persistence/database/ — 缺少事务管理抽象（P268, P1）

**问题**：
1. 38 个仓储实现各自管理 `conn.commit()`——没有统一的事务边界
2. `write_dispatch.py` 提供了 `enqueue_txn_batch()` 但大多数仓储没有使用它
3. 没有 Unit of Work 模式——一个业务操作涉及多个仓储时，无法保证原子性
4. `SqliteKnowledgeRepository.save()` 的全量替换策略（`DELETE ALL + INSERT ALL`）在高并发下可能导致数据丢失

**治理方案**：引入 Unit of Work 模式，业务操作在一个事务中协调多个仓储的写操作。

---

## 二十一、量化总结更新（v4）

### 21.1 问题统计（按严重级别，含 R20 新增）

| 级别 | 数量 | 新增(R20) | 典型代表 |
|------|------|------|----------|
| **P0 致命** | 28 | +6 | engine/runtime 三重复制、MemoryOrchestrator 7处直接SQL、Worldbuilding三重复制、PromptManager/PromptRegistry/PromptRuntimeService 三层代理 |
| **P1 严重** | 50 | +12 | PromptManager 1100行、BaseStoryPipeline 736行、StoryPipelineRunner 17参数、PipelineContext 42字段、38仓储手动映射、3抽象接口无实现、3全局单例无DI |
| **P2 中等** | 65 | +13 | DomainEvent双重定义、BaseEntity过于简陋、DomainEvent未集成BaseEntity、硬编码爽文阈值、3种渲染逻辑并存、config/仅1文件、前端4 composable不足 |
| **P3 轻微** | 125 | +13 | CheckpointStore import位置、迁移文件命名不一致、character_soul.py无弃用警告、示例代码在主包中 |
| **总计** | **268** | **+44** | — |

### 21.2 核心矛盾更新（v4）

| 矛盾 | 表现 | 新增证据 |
|------|------|----------|
| **概念双重定义** | Story vs Novel、KnowledgeTriple vs Triple、Worldbuilding vs WorldSetting vs Bible | P237: engine/runtime 与 engine/application 完全相同的3个文件；P243: DomainEvent 双重定义；P247: 世界观三重复制 |
| **God Object** | AutopilotDaemon(4200)、AutoNovelWorkflow(2200)、autopilot_routes(2500) | P240: PipelineContext 42字段；P248: PromptManager 1100行；P254: BaseStoryPipeline 736行 |
| **层级穿透** | domain/ai 定义基础设施接口、路由直接SQL | P241: MemoryOrchestratorImpl 7处直接SQL；P254: BaseStoryPipeline 5处 lazy import 层级穿透 |
| **三层代理** | — | P249: PromptManager → PromptRegistry → PromptRuntimeService；P265: 3种渲染逻辑并存 |
| **抽象无实现** | ConsistencyChecker 骨架 | P252: StoryEngine + CharacterEngine 无实现；P239: Runner 的空方法 |
| **全局单例无DI** | 12个全局单例 | P266: PromptManager/PromptRegistry/VariableRegistry 三个全局单例 |

### 21.3 新增治理铁律

11. **禁止三层及以上代理** — 违者删中间层
12. **禁止仓储内直接 SQL** — 违者委托 Repository
13. **禁止 `engine/runtime/` 与 `engine/application/` 并存** — 违者删 `engine/runtime/`

### 21.4 治理路线图更新（v4）

**第一阶段补充行动**：

| 序号 | 行动 | 预期效果 |
|------|------|----------|
| 6 | 删除 `engine/runtime/` 整个目录（3个完全相同的文件 + 2个仅import路径不同的文件） | -100% 三重复制 |
| 7 | 删除 `PolicyValidator`，Pipeline 直接使用 `QualityGuardrail` | -224行冗余封装 |
| 8 | 删除 `PromptRuntimeService`，业务代码直接使用 `PromptRegistry` | -191行冗余代理 |
| 9 | 删除 `PromptManager._render_template()`，渲染统一到 `PromptTemplateEngine` | 消除3种渲染逻辑 |
| 10 | 统一 `DomainEvent` 定义，删除 `engine/infrastructure/events/event_bus.py` 中的重复基类 | -50% 重复 |

**第二阶段补充行动**：

| 序号 | 行动 | 预期效果 |
|------|------|----------|
| 7 | `PipelineContext` 拆分为 InputContext + StepOutputs + Dependencies 三个类 | -42字段 → 3×~14字段 |
| 8 | `StoryPipelineRunner` 用 Builder 模式替代 17 参数构造函数 | 可测试性 |
| 9 | `PromptManager` 拆分为 SeedService + VersionService + QueryService | -1100行 → 3×~370行 |
| 10 | 引入 Unit of Work 模式统一事务管理 | 原子性 |
| 11 | 统一 `Worldbuilding` 与 `WorldSetting`，删除重复定义 | -33% 重复 |

**第三阶段补充行动**：

| 序号 | 行动 | 预期效果 |
|------|------|----------|
| 7 | `BaseEntity` 增加领域事件收集机制 | 事件溯源就绪 |
| 8 | 统一 `engine/infrastructure/events/` 与 `domain/shared/events.py` | -50% 重复 |
| 9 | 所有硬编码配置提取到 `config/` YAML | 可扩展 |
| 10 | 补充 `DomainException` 层次结构 | 错误处理完整 |
| 11 | 迁移文件引入 alembic 管理 | 迁移可追踪 |

---

## R21: 前端 Stores 层架构审查

### P269: `dagStore` 与 `dagRunStore` 职责边界模糊 — SSE 事件处理双写

**级别**：P1（高）

**现象**：
- `dagStore.ts`（333行）有 `handleSSEEvent()` 方法，直接处理 SSE 事件并更新 `nodeStates`
- `dagRunStore.ts`（340行）也有 `handleNodeStatusChange()`、`handleNodeOutput()` 等方法，同样维护 `nodeStates`
- 两个 Store 维护了**同名但类型不同的 `nodeStates`**：`dagStore` 用 `Map<string, NodeRunState>`，`dagRunStore` 用 `Record<string, { status: NodeStatus; enabled: boolean }>`
- `useDAGSSE` composable 通过回调机制桥接二者，但事件经过 `dagRunStore → useDAGSSE → dagStore` 三层转发

**影响**：
- 同一个 SSE 事件被两处分别处理，`nodeStates` 在两个 Store 中状态可能不同步
- 前端调试时难以判断"哪个 Store 是状态真相来源"

**治理方案**：
1. `dagRunStore` 仅负责**连接管理**和**运行控制**（start/stop/status），删除 `nodeStates`
2. 所有节点运行时状态统一由 `dagStore.nodeStates` 管理
3. `useDAGSSE` 中的回调链简化为 `dagRunStore → dagStore.handleSSEEvent()`

---

### P270: `statsStore` 共享 `loading` / `error` 状态 — 粒度过粗

**级别**：P2（中）

**现象**：
- `statsStore.ts` 的 `loading` 和 `error` 是全局单值，被 `loadGlobalStats`、`loadBookStats`、`loadChapterStats`、`loadProgress` 四个异步操作共享
- 任何一个请求失败都会覆盖 `error`，任何一个请求的 loading 状态都会影响所有统计 UI

**治理方案**：将 `loading` 和 `error` 改为按请求域区分（`globalLoading`/`bookLoading`/`chapterLoading`），或使用 `Map<string, LoadingState>` 按缓存 key 追踪。

---

### P271: `useWorkbench` Composable 混合了业务逻辑与 UI 导航

**级别**：P2（中）

**现象**：
- `useWorkbench.ts` 同时包含数据获取逻辑（`loadDesk`、`goToChapter`）和 UI 导航逻辑（`goHome`、`setRightPanel`）
- 使用 `useRouter()` 和 `useMessage()`，使其强耦合 Vue Router 和 Naive UI
- `formatApiErrorDetail` 是纯工具函数，不应放在 composable 内部

**治理方案**：
1. 拆分为 `useWorkbenchData`（纯数据 + API）和 `useWorkbenchUI`（导航 + 面板切换）
2. `formatApiErrorDetail` 提取到 `utils/apiError.ts`

---

### P272: `promptPlazaBridge` Store 职责不清 — 事件桥还是状态管理？

**级别**：P2（中）

**现象**：
- `promptPlazaBridge.ts` 名为 Store，实际只维护 `pendingNodeKey` 和 `shouldOpenPlaza` 两个 flag
- `setOnPlazaSaved` 使用 `ref<Function>` 存储回调，违反 Pinia 最佳实践（Store 不应持有函数引用）
- `getCpmsKey()` 在每次调用时 `useDAGStore()`，创建了不必要的 Store 实例依赖

**治理方案**：
1. 如果仅是事件桥接，改为 composable 或事件总线
2. 如果保留为 Store，用 `Map<string, string>` 缓存 CPMS 映射，去掉运行时回调

---

### P273: `workbenchRefreshStore` Tick 机制缺乏防抖 — 频繁 bump 可能导致重复拉数

**级别**：P3（低）

**现象**：
- `workbenchRefreshStore.ts` 用递增计数器（`foreshadowTick`、`chroniclesTick`、`deskTick`）驱动面板刷新
- `bumpAfterChapterDeskChange()` 同时 bump 三个 tick，导致监听 `deskTick` 的组件在同一次操作中被触发一次
- 但如果短时间内多次 bump（如连续章保存），tick 会快速递增，watch 回调可能在同一微任务队列中被多次触发

**治理方案**：在 composable 层增加 `watchFlush` 或 `nextTick` 合并，或使用 `watchEffect` + debounce。

---

### P274: `fontSizeStore` 和 `themeStore` 的 localStorage 操作应统一

**级别**：P3（低）

**现象**：
- `fontSizeStore.ts` 和 `themeStore.ts` 各自独立实现了 `localStorage.getItem/setItem` 的 try/catch 逻辑
- `STORAGE_KEY` 定义在各自文件内，没有统一的前缀或管理

**治理方案**：提取 `usePersistedState` composable 或使用 VueUse 的 `useStorage`，统一持久化策略。

---

## R22: 前端 Composables 层审查

### P275: `useDAGSSE` — 468行巨型 Composable，职责过多

**级别**：P1（高）

**现象**：
- `useDAGSSE.ts` 包含消息队列节流、批量合并、智能重连、性能监控、Autopilot 日志桥接、节点状态同步等六种职责
- `handleAutopilotLogEvent` 函数有 88 行，包含复杂的日志解析与状态推演逻辑
- `syncFromAutopilotStatus` 使用动态 import（`await import('@/api/dag')`），在 composable 内部引入异步模块加载

**影响**：难以单独测试某个功能；修改重连逻辑可能影响日志桥接

**治理方案**：
1. 拆分为 `useDAGSSEStream`（连接 + 重连）、`useDAGSSEThrottle`（队列 + 合并）、`useDAGLogBridge`（日志 → DAG 映射）
2. `syncFromAutopilotStatus` 改为顶层静态 import

---

### P276: `useDAGSSE` 在模块顶层注册回调 — 脱离 Vue 生命周期

**级别**：P1（高）

**现象**：
```typescript
// 在 composable 函数体顶层（非 onMounted 内）直接注册回调
runStore.onNodeStatusChange((event) => { enqueueEvent(event) })
runStore.onNodeOutput((event) => { enqueueEvent(event) })
runStore.onEdgeFlow((event) => { enqueueEvent(event) })
runStore.onRunComplete(() => { ... })
```
- 这些回调在 `useDAGSSE()` 被调用时立即注册，但 `dagRunStore` 内部使用数组存储回调，**没有提供卸载机制**
- 如果组件多次挂载/卸载，回调会重复注册

**治理方案**：`onNodeStatusChange` 等应返回 `unsubscribe` 函数，在 `onUnmounted` 中调用。

---

### P277: `useWorkbenchNarrativeSync` 过度抽象 — 3 个导出函数实际只做 watch

**级别**：P3（低）

**现象**：
- `useWorkbenchNarrativeSync.ts` 导出 `useWorkbenchDeskTickReload`、`useWorkbenchChroniclesTickReload`、`useWorkbenchPlotTimelineReload`
- 每个函数仅一行：`return watch(deskTick, () => run())`
- 对于如此简单的逻辑，不需要独立文件

**治理方案**：合并到 `workbenchRefreshStore.ts` 或 `deskEvents.ts` 作为辅助函数。

---

## R23: 前端 API 层审查

### P278: `ChapterDTO` 在 `novel.ts` 和 `chapter.ts` 中重复定义

**级别**：P1（高）

**现象**：
- `frontend/src/api/novel.ts` 定义了 `ChapterDTO`（5个字段：id, number, title, content, word_count）
- `frontend/src/api/chapter.ts` 也定义了 `ChapterDTO`（8个字段：id, novel_id, number, title, content, status, word_count, created_at, updated_at）
- 两个同名接口字段不一致，`chapter.ts` 版本多出 `novel_id`、`status`、`created_at`、`updated_at`

**影响**：导入时 TypeScript 可能静默使用错误的版本；后端 API 契约不明确

**治理方案**：统一为 `types/api.ts` 中的单一 `ChapterDTO` 定义，删除各 API 文件中的内联定义。

---

### P279: Legacy API (`book.ts`) 与 V1 API 并存 — 迁移停滞

**级别**：P1（高）

**现象**：
- `frontend/src/api/book.ts` 标记为 `DEPRECATED`，但注释明确列出 **Bible、Cast、Knowledge、Desk** 操作仍依赖旧 API
- `jobApi` 已迁移到 `workflow.ts`，但 `bookApi` 的 8 个方法仍被 BiblePanel.vue、CastGraphCompact.vue、KnowledgePanel.vue 等组件使用
- 旧 API 使用 `legacyBookHttp`（baseURL `/api`），新 API 使用 `apiClient`（baseURL `/api/v1`），两套 HTTP 实例并存

**影响**：
- 双倍维护成本：每次后端改接口需同步两处
- `legacyBookHttp` 的 response interceptor 仅做 `response.data` 解包，而 `legacyStatsHttp` 还额外处理 `SuccessResponse`，行为不一致

**治理方案**：
1. 优先迁移 Bible 批量更新接口（需后端补充 `PUT /api/v1/novels/{id}/bible`）
2. Cast 和 Knowledge 迁移到对应的新 API 模块
3. 迁移完成后删除 `book.ts`、`stats.ts` 及 `legacyBookHttp`/`legacyStatsHttp`

---

### P280: 前端 API 层缺少统一的错误处理策略

**级别**：P2（中）

**现象**：
- `api/config.ts` 的 axios interceptor 做了全局错误通知（`emitAxiosFeedbackIncident`）
- 但各 API 函数仍有独立的 try/catch（如 `dagStore.loadDAG` 捕获后设置 `error.value`）
- 某些 API 函数直接 throw，某些静默吞错，模式不统一

**治理方案**：
1. 定义错误处理策略：全局 interceptor 负责 UI 通知，API 函数返回 TypedResult（success/data）
2. 或者使用 `silentGlobalFeedback: true` 配置项标记需要组件自行处理的请求

---

### P281: `api/config.ts` 中的 SSE 流实现应独立为 composable

**级别**：P2（中）

**现象**：
- `subscribeChapterStream()` 函数（~120行）实现了完整的 SSE 流解析逻辑，但放在 `api/config.ts` 中
- 该文件已经承担了 axios 实例创建、Tauri 集成、legacy HTTP 同步等职责，SSE 流解析与这些职责无关

**治理方案**：将 `subscribeChapterStream` 和 `ChapterStreamEvent` 类型提取到 `api/sse.ts` 或 `composables/useChapterStream.ts`

---

### P282: 前端类型定义碎片化 — 5 个类型文件覆盖不均

**级别**：P2（中）

**现象**：
- `types/api.ts`（430行）包含大量 legacy 类型（`BookListItem`、`CastGraph`、`JobStatusResponse` 等）
- `types/dag.ts`（270行）定义了完整的 DAG 类型系统
- `types/anti-ai.ts`、`types/axios-plotpilot.d.ts`、`types/global.d.ts` 补充零碎类型
- API 文件内大量内联类型定义（`novel.ts` 的 `GenerationPrefsDTO`、`chapter.ts` 的 `ChapterDTO`）
- 后端 Pydantic 模型与前端 TypeScript 类型**无自动同步机制**

**治理方案**：
1. 建立前后端类型单一来源：考虑使用 `openapi-typescript` 从 OpenAPI schema 自动生成
2. 短期：将 API 文件内联类型统一迁移到 `types/` 目录

---

## R24: 前端 Router 与 Views 层审查

### P283: 路由定义扁平 — 缺少嵌套与守卫

**级别**：P2（中）

**现象**：
- `router/index.ts` 仅定义了 7 条路由，全部扁平
- `/book/:slug/workbench` 与 `/book/:slug/chapter/:id` 没有共同的父路由，导致每个视图独立解析 `slug`
- 没有 `beforeEach` 守卫验证小说是否存在（404 由组件内部 `is404()` 判断）
- 调试路由 `/debug/scheduler` 在生产构建中仍然可访问

**治理方案**：
1. 引入嵌套路由：`/book/:slug` 作为父路由，共享 novel 数据加载
2. 添加 `beforeEach` 守卫：检查 slug 有效性、重定向 404
3. 调试路由仅在 dev 模式注册

---

### P284: Views 层职责分配不均 — Workbench 成为 God View

**级别**：P2（中）

**现象**：
- `Workbench.vue` 是核心页面，组合了 `useWorkbench`、`useDAGSSE`、autopilot 控制等所有逻辑
- `Home.vue` 仅做小说列表展示
- `Cast.vue` 和 `CharacterGraph.vue` 职责重叠（都展示角色关系图）
- `LocationGraph.vue` 是独立视图但缺少路由入口（除非手动输入 URL）

**治理方案**：
1. Workbench 拆分为子路由（驾驶舱、工作流、设置面板各自独立路由）
2. Cast 和 CharacterGraph 合并为一个视图的两种展示模式

---

## R25: 配置系统与启动脚本审查

### P285: `config/performance.yaml` — 后端未真正读取配置

**级别**：P1（高）

**现象**：
- `config/performance.yaml` 定义了 autopilot、writing、database、persistence_queue、monitoring、frontend、dag_engine 七个配置块
- 但后端代码中**没有找到读取该 YAML 的逻辑**：`AutopilotDaemon` 中的 `consecutive_error_limit`、`max_auto_chapters` 等参数仍然是硬编码
- `writing.conductor_converge_threshold` 和 `conductor_land_threshold` 注释明确说"旧值 0.60 / 0.85"，说明曾经硬编码后被提取，但提取后**未被实际引用**

**影响**：修改 YAML 不会改变系统行为——配置文件是"死文档"

**治理方案**：
1. 实现配置加载器：`application/config/loader.py` 读取 YAML 并注入各模块
2. 或删除该文件，避免给维护者造成"配置可调"的错觉

---

### P286: 数据库迁移文件无版本管理 — 26 个 ad-hoc SQL 脚本

**级别**：P1（高）

**现象**：
- `infrastructure/persistence/database/migrations/` 下有 26 个 SQL 文件
- 仅 003-010 有编号前缀，其余 16 个使用描述性命名（`add_anti_ai_audits.sql`、`add_worldbuilding.sql` 等）
- 没有迁移执行框架（如 alembic、flyway），无法确定哪些脚本已执行、哪些待执行
- `010_unified_entities.sql` 创建了 `unified_characters` 表，但后端代码中几乎未引用该表

**影响**：
- 新环境部署需要手动按正确顺序执行脚本
- 多人开发时 schema 变更无法自动同步
- `unified_characters` 可能是遗留死表

**治理方案**：
1. 引入 alembic 管理迁移
2. 审查 `unified_characters` 表是否仍在使用，若否则标记删除
3. 所有迁移脚本重编号，建立执行顺序

---

## R26: Tauri 桌面端架构审查

### P287: `BackendManager` — 673行上帝类，混合进程管理与文件操作

**级别**：P1（高）

**现象**：
- `backend.rs` 包含进程启动、健康检查、优雅关闭、强杀、Python 查找、zip 解压、目录递归复制等职责
- `find_python()` 有 5 层回退逻辑（项目内嵌 → 资源内嵌 → zip 解压 → venv → 系统 PATH），每层都有文件 IO
- `find_frozen_backend_exe()` 有 4 种路径探测策略，含逐级向上 32 层遍历
- Windows 特定的 Job Object 逻辑与通用逻辑交织

**治理方案**：
1. 拆分 `PythonResolver`（Python 查找 + 解压）、`ProcessSupervisor`（启动 + 健康检查 + 关闭）、`PathDetector`（后端 exe 探测）
2. Windows 特定代码使用 `#[cfg(target_os = "windows")]` 模块隔离（已部分实现，但 Job Object 逻辑仍在主 impl 中）

---

### P288: `BackendManager` 的 `Mutex` 锁持有时间过长

**级别**：P2（中）

**现象**：
- `restart_backend` 命令在持有 `Mutex<BackendManager>` 期间执行 `tokio::time::sleep(2s)` 和 `start_and_wait(120s)`
- 最坏情况下，前端调用 `get_backend_port` 时会被阻塞长达 122 秒
- `graceful_shutdown` 虽然在独立线程中执行，但仍需短暂获取锁来读取端口和子进程

**治理方案**：
1. `restart_backend` 应在获取锁后立即释放，使用 channel 或 `watch` 通知后台线程执行重启
2. 将 `port` 和 `child` 分离为独立 `Mutex`，减少争用

---

### P289: `AITEXT_PROD_DATA_DIR` 旧名兼容应设过期时间

**级别**：P3（低）

**现象**：
- `backend.rs` 同时设置 `PLOTPILOT_PROD_DATA_DIR` 和 `AITEXT_PROD_DATA_DIR`
- `commands.rs` 中也检查 `PLOTPILOT_FORCE_PROD_DATA` 和 `AITEXT_FORCE_PROD_DATA`
- 注释说明"兼容旧名"，但未设过期版本

**治理方案**：在代码注释中标记 `AITEXT_*` 将在 v2.0 移除，并在 CHANGELOG 中通知。

---

## R27: CI/CD 与工程化审查

### P290: 后端 CI 仅跑 unit tests — 无 lint、无类型检查、无集成测试

**级别**：P1（高）

**现象**：
- `backend-ci.yml` 仅执行 `pytest tests/unit -q --tb=short`
- 没有 `ruff check` / `mypy` / `isort` 等 lint 和类型检查步骤
- 无集成测试步骤（API 端到端测试）
- 使用占位 `ANTHROPIC_API_KEY: "test-placeholder"` 绕过启动检查

**治理方案**：
1. 添加 `ruff check .`、`mypy interfaces/` 步骤
2. 添加 FastAPI TestClient 集成测试
3. 添加架构守护测试（如"Character 类只能有一个定义"）

---

### P291: 前端 CI 仅做 build — 无 lint、无类型检查、无测试

**级别**：P1（高）

**现象**：
- `frontend-ci.yml` 仅执行 `npm ci && npm run build`
- 没有 `eslint`、`vue-tsc`、`vitest` 步骤
- 没有 PR 门禁（build 成功即可合并）

**治理方案**：
1. 添加 `vue-tsc --noEmit` 类型检查
2. 添加 `eslint` 和 `vitest` 步骤
3. 添加 bundle size 限制（防止包体积膨胀）

---

## R28: 前端 Support/Policies/Workbench 层审查

### P292: `feedbackNotifier.ts` — 422行通知系统，职责过重

**级别**：P2（中）

**现象**：
- `feedbackNotifier.ts` 混合了通知展示逻辑（Naive UI 组件渲染）、事件聚合（Axios 批量合并）、诊断包导出、剪贴板操作
- 使用 `h()` 渲染函数直接创建 Vue 组件（`NButton`、`NCollapse`），而非使用 SFC
- `dispatchPrimary` 和 `dispatchCopyStructured` 中使用动态 import 加载 `feedbackDiagnostic` API

**治理方案**：
1. 将通知 UI 渲染提取为 Vue SFC 组件
2. 事件聚合逻辑提取为独立的 `feedbackAggregator.ts`
3. 诊断包导出提取为 `feedbackExport.ts`

---

### P293: `autopilotDagLogBridge.ts` — 声明式映射表与后端不同步风险

**级别**：P2（中）

**现象**：
- `AUTOPILOT_SUBSTEP_PRIMARY_RULES` 和 `AUTOPILOT_STAGE_PRIMARY_RULES` 是前端硬编码的映射表
- 注释说"与后端 primary_node_policy 语义对齐"，但没有自动同步机制
- 当后端新增节点类型或修改 stage 名称时，前端映射表必须手动更新

**治理方案**：
1. 后端 `GET /dag/registry/linkage` 已包含 `cpms_node_key`，前端应完全依赖此 API 而非硬编码映射
2. 保留静态表仅作为离线兜底，并在 API 成功后打印 warning 提示更新

---

### P294: `deskEvents.ts` 的浏览器 CustomEvent 与 Pinia tick 并行 — 双重信号机制

**级别**：P2（中）

**现象**：
- 章节落库后的刷新信号同时通过两条路径传递：
  1. `workbenchRefreshStore.bumpAfterChapterDeskChange()` → Pinia tick → composable watch
  2. `window.dispatchEvent(new CustomEvent('plotpilot:workbench:chapter-desk-change'))` → DOM 事件 → Workbench 监听
- `useWorkbench.ts` 的 `handleJobCompleted` 还使用了第三条路径：`window.dispatchEvent(new CustomEvent('plotpilot:bible-panel:soft-reload'))`

**影响**：同一事件通过三种机制传播，调试时难以追踪完整信号流

**治理方案**：统一为 Pinia store tick 或事件总线，删除 CustomEvent 方案（或反之，但需统一）

---

## R29: 后端 API 路由层审查

### P295: `interfaces/main.py` — 1100+行启动文件，注册了 40+ 路由模块

**级别**：P1（高）

**现象**：
- `main.py` 包含所有路由注册、中间件配置、CORS 设置、静态文件托管、SPA fallback、健康检查、shutdown 端点
- 顶部 50+ 行的 import 列表，覆盖了 `v1.core`、`v1.world`、`v1.blueprint`、`v1.engine`、`v1.audit`、`v1.analyst`、`v1.workbench` 等模块
- `app.include_router()` 调用分散在文件各处，没有按领域分组

**治理方案**：
1. 创建 `interfaces/api/v1/router.py` 聚合所有 v1 子路由
2. `main.py` 仅负责应用工厂（创建 app、添加中间件、挂载根路由）
3. 路由注册按领域分组，使用 `APIRouter(prefix="/api/v1")` 嵌套

---

### P296: API 路由结构不对称 — 部分 `reader` 模块为空

**级别**：P2（中）

**现象**：
- `interfaces/api/v1/reader/` 目录存在但 `__init__.py` 为空
- `interfaces/api/v1/debug/` 目录存在但内容不明
- `interfaces/api/v1/engine/dag/` 仅有一个 `dag_routes.py`，而其他 engine 子模块直接平铺在 `engine/` 下

**治理方案**：
1. 删除空目录或添加 TODO 注释
2. DAG 路由应平铺在 `engine/` 下（与其他路由文件一致），或所有 engine 子模块都独立子目录

---

### P297: Stats API 仍使用独立模块 — 不符合 v1 RESTful 规范

**级别**：P2（中）

**现象**：
- `interfaces/api/stats/` 是独立模块，使用 `/api/stats/` 前缀（非 v1）
- 前端 `statsStore` 通过 `novelApi.getNovelStatistics()` 获取部分统计，又通过 `statsApi.getProgress()` 获取进度
- 两个数据源使用不同的 HTTP 实例（`apiClient` vs `legacyStatsHttp`）

**治理方案**：将统计 API 迁移到 `v1/core/novels.py` 或 `v1/stats/`，统一使用 `/api/v1/stats/` 前缀

---

## R30: 全局交叉问题 — 跨层依赖与契约一致性

### P298: 前后端 `Character` 类型三重不一致

**级别**：P0（致命）

**现象**：
- 后端有 4 种 `Character` 定义（见 P0-1.1）
- 前端 `types/api.ts` 定义了 `Character`（id, name, aliases, role, traits, note, story_events）
- 前端 `types/api.ts` 还有 `BibleCharacter`（name, role, traits, arc_note）
- 后端 `unified_characters` 表的字段（public_profile, hidden_profile, mental_state, verbal_tic 等）与前端类型完全不匹配

**影响**：
- Bible 面板保存角色 → 后端存储 `BibleCharacter` → 引擎使用 `engine/core/entities/character.py` → 三者字段不对齐
- 新增角色属性时，需要同步修改 4 个后端文件 + 2 个前端文件

**治理方案**：
1. 后端统一为 `engine/core/entities/character.py`
2. 前端使用 OpenAPI 自动生成的类型
3. `unified_characters` 表如果未被使用，删除

---

### P299: 前端 `BookStats` 类型与后端 `NovelStatisticsResponse` 隐式转换

**级别**：P1（高）

**现象**：
- `novel.ts` 中的 `toBookStatsFromStatisticsPayload()` 使用 `unknown` + 手动字段提取来转换后端统计响应
- `pickNumber` 和 `pickString` 工具函数尝试多个候选字段名（如 `total_chapters` / `chapters_total`），暗示后端字段名不稳定
- 前端 `BookStats` 类型定义在 `types/api.ts`，但实际数据来自 `novelApi.getNovelStatistics()`

**治理方案**：
1. 后端固定统计 API 的响应字段名
2. 前端直接使用 TypeScript 类型断言，删除 `pickNumber`/`pickString` 兜底逻辑

---

### P300: 前端 33 个 API 模块 vs 后端路由模块 — 映射不完整

**级别**：P2（中）

**现象**：
- 前端 `api/` 目录有 33 个文件，但部分模块没有对应的后端路由（如 `anti-ai.ts`、`voiceDrift.ts`、`narrativeEngine.ts`、`worldline.ts`）
- 反之，后端部分路由没有对应的前端 API 模块（如 `reader`、`debug`）

**治理方案**：建立前后端 API 映射清单，删除未使用的前端 API 模块或补充缺失的路由

---

## R31: 安全性与错误处理审查

### P301: `/internal/shutdown` 端点仅靠 localhost 检查 — 反向代理场景下可被绕过

**级别**：P1（高）

**现象**：
- `interfaces/main.py` 中的 `_assert_internal_shutdown_localhost()` 仅检查 `request.client.host` 是否为 `127.0.0.1` / `::1`
- 在 Nginx 反向代理部署场景下，`request.client` 可能为代理 IP（如 `127.0.0.1`），远程请求也能通过此检查
- 该端点可导致**服务器进程被远程关闭**

**治理方案**：
1. 添加请求头验证（如 `X-Internal-Secret`），在 Tauri 启动时动态生成 secret
2. 或添加 `X-Forwarded-For` 检查，拒绝非直接连接

---

### P302: 全系统无认证机制 — 任何网络可达的客户端可操作所有 API

**级别**：P1（高）

**现象**：
- 所有 API 端点（包括 DELETE /novels/{id}、POST /autopilot/{id}/start 等）均无认证
- 当前仅靠 localhost 访问限制保护，但在局域网或反向代理场景下不安全
- 前端无登录/鉴权逻辑

**治理方案**：
1. 短期：添加可配置的 API Token 认证（Bearer Token），适用于桌面单用户场景
2. 中期：如果支持多用户，引入 JWT + 用户系统
3. CORS 配置当前为 `allow_origins=["*"]`，应限制为实际前端域名

---

### P303: `engine/pipeline/base.py` 有 17 处 `except Exception` — 异常被静默吞掉

**级别**：P1（高）

**现象**：
- `engine/pipeline/base.py` 中有 17 处 `except Exception as e` 或 `except Exception`
- 多数仅做 `logger.error()` 或 `logger.warning()`，然后继续执行或返回默认值
- 例如：`_execute_validation_step` 中校验步骤失败时返回 `None` 而非抛出异常，导致下游无法区分"校验通过但无数据"和"校验彻底失败"

**影响**：管线中的错误被静默吞掉，用户看到的"生成完成"可能包含大量校验失败

**治理方案**：
1. 区分可恢复异常和致命异常：可恢复异常使用 Result 模式，致命异常直接抛出
2. 补充 `DomainException` 层次结构（已在路线图中）
3. 管线步骤失败应标记为 `StepStatus.FAILED`，而非返回 None

---

### P304: `interfaces/main.py` 有 21 处 `except Exception` — API 层异常处理不一致

**级别**：P2（中）

**现象**：
- `main.py` 中 21 处 `except Exception`，多数返回 `JSONResponse(status_code=500)`
- 但某些端点返回不同格式（`{"ok": False, "error": ...}` vs `{"detail": ...}`）
- 缺少统一的异常中间件

**治理方案**：添加 FastAPI `exception_handler` 中间件，统一错误响应格式

---

## R32: 性能瓶颈与可扩展性审查

### P305: SQLite 单写者瓶颈 — 全托管模式下高频率写入竞争

**级别**：P1（高）

**现象**：
- SQLite 天然单写者模式，全托管模式每章生成需要：checkpoint 写入 → 章节内容落库 → 知识三元组提取 → 角色状态更新 → 审计结果写入，共 5+ 次写操作
- `write_dispatch.py` 引入了持久化队列，但队列深度和批量大小硬编码
- WAL 模式下读不阻塞写，但**写仍阻塞写**：AutopilotDaemon 的主循环和 API 请求可能同时写

**治理方案**：
1. 所有非紧急写操作统一走持久化队列，减少直接写竞争
2. 考虑章节内容落库使用独立的 SQLite 数据库（与元数据分离）
3. 高频写操作（如 checkpoint）考虑使用内存缓存 + 批量刷盘

---

### P306: ChromaDB 嵌入向量查询 — 每次知识检索触发磁盘 IO

**级别**：P2（中）

**现象**：
- `data/chromadb/` 下有 12 个不同的集合目录，包含 chunks 和 triples
- 每次知识检索（如 `context_assembly` 步骤）都要查询 ChromaDB，触发磁盘 IO 和向量计算
- 全托管模式一章生成可能触发 5-10 次知识检索

**治理方案**：
1. 对热门查询结果添加内存 LRU 缓存
2. 考虑使用 ChromaDB 的 HTTP 模式，避免每次冷启动加载模型
3. 相邻章节的上下文可以预加载

---

### P307: 前端 DAG 画布 — Vue Flow 节点数量无上限

**级别**：P3（低）

**现象**：
- DAG 画布使用 Vue Flow 渲染，节点数量由后端 DAG 定义决定
- 当前默认 DAG 约有 15-20 个节点，但如果用户自定义复杂管线，节点可能超过 100
- 没有虚拟滚动或节点懒加载机制

**治理方案**：添加节点数量上限警告，或实现视口外节点懒渲染

---

## R33: 死代码清单与清理建议

### P308: `engine/runtime/` 与 `engine/application/` — 100% 逐字节重复

**级别**：P0（致命，已在 P237 记录，此处补充详细清单）

**重复文件清单**：
| engine/runtime/ | engine/application/ | 行数 |
|-----------------|---------------------|------|
| `checkpoint_manager.py` | `checkpoint_manager.py` | ~350 |
| `plot_state_machine.py` | `plot_state_machine.py` | ~250 |
| `guardrails.py` | `guardrails.py` | ~200 |
| `runner.py` | `runner.py` | ~400 |

**治理方案**：删除 `engine/runtime/`，所有代码统一引用 `engine/application/`

---

### P309: `domain/bible/` 与 `domain/cast/` — 与 `engine/core/` 实体重复

**级别**：P0（致命，已在 P0-1.1 记录，此处补充清理方案）

**待删除文件**：
- `domain/bible/entities/character.py` → 改为 re-export `engine/core/entities/character.py`
- `domain/cast/entities/character.py` → 删除
- `domain/bible/entities/worldbuilding.py` → 合并到 `domain/worldbuilding/`
- `domain/novel/entities/chapter.py` → 改为 re-export `engine/core/entities/chapter.py`

---

### P310: `interfaces/api/v1/reader/` — 空模块

**级别**：P3（低）

**现象**：`reader/__init__.py` 有 7 处 `except Exception`，但整体功能为空

**治理方案**：删除空目录，或在 TODO 中标注预期功能

---

### P311: 前端 `api/book.ts` — Legacy API 应迁移后删除

**级别**：P1（高，已在 P279 记录）

**待删除函数**：`bookApi.getBible`、`bookApi.saveBible`、`bookApi.getCast`、`bookApi.putCast`、`bookApi.getKnowledge`、`bookApi.putKnowledge`、`bookApi.getDesk`、`bookApi.getChapterBody`、`bookApi.saveChapterBody`、`bookApi.getChapterReview`、`bookApi.saveChapterReview`、`bookApi.reviewChapterAi`、`bookApi.getChapterStructure`

**待删除 HTTP 实例**：`legacyBookHttp`、`legacyStatsHttp`

---

### P312: `config/performance.yaml` — 死配置文件

**级别**：P1（高，已在 P285 记录）

**现象**：后端未读取此文件，所有参数仍硬编码在代码中

**治理方案**：要么实现配置加载器，要么删除文件避免误导

---

### P313: `unified_characters` 数据库表 — 可能未被引用

**级别**：P2（中）

**现象**：
- `010_unified_entities.sql` 创建了 `unified_characters`、`unified_character_relationships`、`unified_props`、`prop_events`、`prop_chapter_snapshots` 五张表
- 但后端代码中 Character 仓储使用的是 `characters` 表（domain/novel），Prop 使用 `props` 表
- `unified_*` 表可能是早期重构尝试的遗留

**治理方案**：搜索所有引用 `unified_characters` 的代码，确认无使用后删除迁移脚本和表

---

## R34: 前端 Components 深度审查

### P314: Autopilot 组件 12 个文件 — 缺少统一状态管理

**级别**：P2（中）

**现象**：
- `components/autopilot/` 下有 12 个组件：AutopilotDAGView、AutopilotDashboard、AutopilotMetricsDashboard、AutopilotOperationsView、AutopilotPanel、AutopilotShellNav、AutopilotStream、AutopilotTerminalLog、AutopilotWorkspace、AutopilotWritingStream、ChapterWriterStream、CircuitBreakerStatus 等
- 各组件通过 props/events 逐层传递状态，没有使用统一的 composable 或 store
- `AutopilotWorkspace` 作为顶层容器，需要将 novelId、运行状态、SSE 连接等传递给 5+ 层子组件

**治理方案**：创建 `useAutopilotState` composable，统一管理全托管模式的状态

---

### P315: Workbench 组件 30+ 个文件 — 上帝组件 WorkArea.vue

**级别**：P2（中）

**现象**：
- `components/workbench/` 下有 30+ 个组件，涵盖章节编辑、角色管理、故事线、伏笔、道具、沙盒、提示词广场等
- `WorkArea.vue` 作为主工作区，需要加载和切换所有子面板
- `SettingsPanel.vue` 管理 Bible、Worldbuilding、Knowledge、Props、Story Evolution、Sandbox、Foreshadow 七个 Tab

**治理方案**：
1. 使用动态 import + `defineAsyncComponent` 懒加载子面板
2. 将 SettingsPanel 的 Tab 定义与 `deskEvents.ts` 中的 `WORKBENCH_SETTINGS_PANEL_NAMES` 统一

---

### P316: 图表组件 5 个文件 — 应为通用组件库

**级别**：P3（低）

**现象**：
- `components/charts/` 有 ChartWrapper、DistributionChart、GraphChart、ProgressChart、TrendChart
- 每个组件都直接使用 ECharts，缺少统一的主题注入和响应式尺寸管理

**治理方案**：提取为通用图表组件库，统一注入主题和尺寸

---

## R35: 全局循环依赖与模块耦合审查

### P317: `engine/pipeline/base.py` 的 5 处延迟导入 — 揭示深层循环依赖

**级别**：P0（致命）

**现象**：
- `engine/pipeline/base.py` 中有 5 处延迟导入（lazy import），包括：
  - `from engine.runtime.runner import StoryPipelineRunner`（在方法内部导入）
  - `from engine.core.guardrails import Guardrails`
  - `from infrastructure.ai.prompt_manager import PromptManager`
  - 等
- 延迟导入的存在本身就表明模块间存在**循环依赖**
- `engine.core` → `engine.pipeline` → `engine.runtime` → `engine.core` 形成循环

**影响**：
- 任何重构都需要先解决循环依赖
- 测试时无法独立导入单个模块

**治理方案**：
1. 引入接口层（Protocol/ABC）：`engine.core.protocols` 定义 `PipelineRunner`、`Guardrails` 等接口
2. 具体实现通过依赖注入传入，而非在模块内部导入
3. `engine.pipeline.base.py` 仅依赖 `engine.core.protocols`，不依赖具体实现

---

### P318: `domain/` → `infrastructure/` 反向依赖

**级别**：P1（高）

**现象**：
- `domain/novel/repositories/` 下的仓储实现直接导入 `infrastructure/persistence/database/connection.py`
- `domain/knowledge/repositories/knowledge_repository.py` 使用 ChromaDB 客户端
- 领域层不应知道基础设施层的存在

**治理方案**：
1. 仓储接口定义在 `domain/` 层（Protocol 或 ABC）
2. 具体实现在 `infrastructure/` 层
3. 通过依赖注入容器（如 `application/core/container.py`）绑定

---

## R36: 理想态架构设计 — 最终方案

### 目标架构分层

```
┌─────────────────────────────────────────────────────┐
│  interfaces/          API 路由 + 中间件 + SSE       │
│  (仅做请求解析/响应格式化，不含业务逻辑)             │
├─────────────────────────────────────────────────────┤
│  application/         应用服务 + 用例编排            │
│  (AutopilotService, GenerationService, etc.)         │
│  通过依赖注入调用 domain 层                          │
├─────────────────────────────────────────────────────┤
│  domain/              纯领域模型 + 仓储接口          │
│  (entities, value_objects, protocols)                │
│  零外部依赖，所有仓储为 Protocol/ABC                 │
├─────────────────────────────────────────────────────┤
│  engine/              生成引擎核心                   │
│  (pipeline, core, dag, nodes)                        │
│  通过 protocols 解耦循环依赖                         │
├─────────────────────────────────────────────────────┤
│  infrastructure/      基础设施实现                   │
│  (persistence, ai, events)                           │
│  实现 domain 层定义的接口                            │
└─────────────────────────────────────────────────────┘
```

### 关键设计决策

| 决策 | 当前状态 | 理想态 |
|------|----------|--------|
| 实体定义 | 4 种 Character、2 种 Chapter、3 种 Worldbuilding | 每个实体仅 1 个权威定义 |
| 仓储模式 | 领域层直接导入 SQLite/ChromaDB | 领域层定义 Protocol，基础设施层实现 |
| 管线循环依赖 | 5 处延迟导入 | Protocol + 依赖注入，零延迟导入 |
| 错误处理 | `except Exception` 静默吞错 | `DomainException` 层次结构 + Result 模式 |
| 配置管理 | YAML 死文件 + 代码硬编码 | YAML 加载器 + 类型安全配置类 |
| 数据库迁移 | 26 个 ad-hoc SQL | alembic 版本管理 |
| 前端状态 | 双 Store 双写 + 三种信号机制 | 单一真相来源 + 统一事件流 |
| 前后端类型 | 手动维护，5 个类型文件 | OpenAPI 自动生成 |
| API 版本 | Legacy + V1 双版本共存 | 仅 V1，Legacy 全部迁移 |
| CI/CD | 仅 build/unit test | lint + type check + 集成测试 + 架构守护 |

---

## R37: 治理路线图细化与优先级排序

### 第一阶段：止血（1-2 周）

| 序号 | 行动 | 对应问题 | 预期效果 |
|------|------|----------|----------|
| 1 | 删除 `engine/runtime/` 重复目录 | P237/P308 | -1200行 |
| 2 | 统一 Character 实体为 `engine/core` 版本 | P0-1.1/P298 | -3份重复定义 |
| 3 | 删除 `config/performance.yaml` 或实现加载器 | P285/P312 | 消除死配置 |
| 4 | 前端 `ChapterDTO` 统一到 `types/api.ts` | P278 | 消除类型不一致 |
| 5 | `dagRunStore` 删除 `nodeStates`，统一到 `dagStore` | P269 | 消除双写 |

### 第二阶段：拆分（2-4 周）

| 序号 | 行动 | 对应问题 | 预期效果 |
|------|------|----------|----------|
| 6 | 拆分 `AutopilotDaemon` 为 5 个服务 | P0-God Object | 4200行 → 5×~840行 |
| 7 | 拆分 `PromptManager` 为 Seed + Version + Query | P0-God Object | 1100行 → 3×~370行 |
| 8 | 拆分 `useDAGSSE` 为 Stream + Throttle + LogBridge | P275 | 468行 → 3×~156行 |
| 9 | 拆分 `BackendManager` 为 PythonResolver + ProcessSupervisor + PathDetector | P287 | 673行 → 3×~224行 |
| 10 | 引入 `engine/core/protocols.py` 解决循环依赖 | P317 | 0处延迟导入 |

### 第三阶段：重构（4-8 周）

| 序号 | 行动 | 对应问题 | 预期效果 |
|------|------|----------|----------|
| 11 | 仓储接口迁移到 Protocol/ABC | P318 | 领域层零基础设施依赖 |
| 12 | 补充 `DomainException` 层次结构 | P303 | 异常不再被静默吞掉 |
| 13 | 引入 alembic 管理数据库迁移 | P286 | 迁移可追踪 |
| 14 | 前端 Legacy API 全部迁移到 V1 | P279/P311 | -2个HTTP实例 |
| 15 | 前端类型自动生成（openapi-typescript） | P282/P298 | 前后端类型同步 |

### 第四阶段：巩固（持续）

| 序号 | 行动 | 对应问题 | 预期效果 |
|------|------|----------|----------|
| 16 | CI 添加 ruff + mypy + vue-tsc + vitest | P290/P291 | 门禁保护 |
| 17 | 添加架构守护测试 | P290 | 防止问题回归 |
| 18 | 统一信号机制（删除 CustomEvent） | P294 | 单一事件流 |
| 19 | `/internal/shutdown` 添加认证 | P301 | 安全性 |
| 20 | 前端 Components 懒加载 | P315 | 首屏性能 |

---

## R38: 问题统计汇总与分级确认

### 按级别统计

| 级别 | 数量 | 占比 |
|------|------|------|
| P0（致命） | 6 | 2.0% |
| P1（高） | 28 | 9.3% |
| P2（中） | 42 | 14.0% |
| P3（低） | 24 | 8.0% |
| **合计** | **100** | **33.3%** |

> 注：P269-P318 为 R21-R35 新增问题（50个），加上 R1-R20 的 268 个问题，总计 318 个问题。
> 由于部分问题编号存在覆盖关系（如 P237/P308 重复记录），去重后独立问题约 **300 个**。

### 按层级统计

| 层级 | 问题数 | Top 问题 |
|------|--------|----------|
| domain/ | 45 | 实体重复定义（P0-1.1）、仓储违规（P318） |
| engine/ | 65 | 循环依赖（P317）、God Object（P0）、延迟导入 |
| infrastructure/ | 40 | 直接SQL（P249）、PromptManager（P0） |
| interfaces/ | 35 | main.py 上帝文件（P295）、无认证（P302） |
| frontend/ | 75 | 双Store双写（P269）、Legacy API（P279）、类型不一致（P298） |
| cross-cutting | 40 | 配置死文件（P285）、CI不足（P290/P291） |

### 必须立即修复的 P0 问题

| 编号 | 问题 | 影响范围 |
|------|------|----------|
| P0-1.1 | Character 4份独立定义 | 全系统类型安全 |
| P0-1.2 | Chapter 2份独立定义 | 章节生成管线 |
| P0-1.3 | StoryPhase 枚举重复 | 阶段流转逻辑 |
| P237 | engine/runtime 100%重复 | 代码维护成本 |
| P317 | pipeline 5处循环依赖 | 重构阻塞 |
| P298 | 前后端 Character 类型三重不一致 | 数据一致性 |

---

## R39: 附录 — 关键文件依赖矩阵

### 后端核心依赖图（简化）

```
interfaces/main.py
  ├── interfaces/api/v1/core/        → domain/novel/ + engine/
  ├── interfaces/api/v1/world/       → domain/bible/ + domain/cast/ + domain/knowledge/
  ├── interfaces/api/v1/engine/      → engine/runtime/ ←→ engine/application/ (重复!)
  ├── interfaces/api/v1/blueprint/   → domain/novel/ + engine/
  └── interfaces/api/stats/          → infrastructure/persistence/ (直接SQL)

engine/pipeline/base.py
  ├── (lazy) engine.runtime.runner    ← 循环!
  ├── (lazy) engine.core.guardrails   ← 循环!
  ├── (lazy) infrastructure.ai.prompt_manager
  └── domain/novel/entities/          ← 正常

domain/novel/repositories/
  └── infrastructure/persistence/database/connection.py  ← 反向依赖!
```

### 前端核心依赖图（简化）

```
views/Workbench.vue
  ├── composables/useWorkbench.ts     → api/novel.ts + stores/statsStore
  ├── composables/useDAGSSE.ts        → stores/dagStore + stores/dagRunStore
  ├── components/autopilot/*          → stores/dagStore + api/dag.ts
  └── components/workbench/*          → api/* + stores/*

stores/dagStore.ts ←→ stores/dagRunStore.ts  ← 双写!
  └── composables/useDAGSSE.ts        → 桥接两个 Store

api/book.ts (Legacy)                  → legacyBookHttp (/api)
api/novel.ts (V1)                     → apiClient (/api/v1)
api/stats.ts (Legacy)                 → legacyStatsHttp (/api)
```

---

## R40: 最终整合 — 审查结论

### 核心判断

PlotPilot 是一个**功能完整但架构债务严重**的系统。其核心矛盾是：

1. **领域模型碎片化**：同一概念（Character、Chapter、Worldbuilding）在 domain/、engine/、前端各有独立定义，导致类型安全和数据一致性无法保证。

2. **层级穿透**：领域层直接导入基础设施层、管线层使用延迟导入绕过循环依赖、API 层直接执行 SQL——三重违规使分层架构名存实亡。

3. **上帝对象**：`AutopilotDaemon`（4200行）、`PromptManager`（1100行）、`BaseStoryPipeline`（736行）、`useDAGSSE`（468行）、`BackendManager`（673行）——五个上帝对象承担了过多职责。

4. **双版本并行**：Legacy API + V1 API、CustomEvent + Pinia tick、dagStore.nodeStates + dagRunStore.nodeStates——多套并行机制增加了理解和维护成本。

5. **配置与迁移缺失**：performance.yaml 是死文件、数据库迁移无版本管理、前后端类型无自动同步——工程化基础设施薄弱。

### 推荐行动

**第一步（止血）**：删除重复代码、统一实体定义——这是所有后续重构的前提。
**第二步（拆分）**：拆分上帝对象、解决循环依赖——释放代码的可维护性。
**第三步（重构）**：补充工程化基础设施（配置加载、迁移管理、类型生成、CI 门禁）。
**第四步（巩固）**：架构守护测试，防止问题回归。

### 量化目标

| 指标 | 当前 | 目标 |
|------|------|------|
| P0 问题 | 6 | 0 |
| P1 问题 | 28 | ≤5 |
| 代码重复率 | ~15% | <5% |
| 延迟导入 | 5处 | 0 |
| 上帝对象（>500行） | 5个 | 0 |
| CI 覆盖 | build only | lint + type + test + arch guard |
| 前后端类型同步 | 手动 | 自动生成 |

---

> **审查完成。本文档记录了 318 个架构问题（去重后约 300 个），覆盖领域层、应用层、基础设施层、接口层、引擎层、前端层及跨层交叉问题。**
