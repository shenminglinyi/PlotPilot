# 百章连贯性解决方案

> 核心问题：AI 生成长篇小说时，写到第 50 章以后常出现"情感失忆""因果链断裂""角色弧光冻结""伏笔挖坑不填""章节间割裂"等连贯性问题。本文档系统性梳理当前系统中已实现的全部连贯性保障机制。

---

## 一、总览：五层连贯性防御体系

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 5 — 章后管线（事后提取 + 反哺）                            │
│  ChapterAftermathPipeline → NarrativeSync → ContextAssembler     │
├─────────────────────────────────────────────────────────────────┤
│  Layer 4 — 上下文预算与注入（生成前组装）                           │
│  ContextBudgetAllocator → T0/T1/T2/T3 槽位优先级注入              │
├─────────────────────────────────────────────────────────────────┤
│  Layer 3 — 章间衔接引擎（跨章桥段）                               │
│  ChapterBridgeService → 5维桥段 + 衔接指令 + 自检修整              │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2 — 节拍间衔接（章内微连贯）                                │
│  BeatTailAnchor → 动态连贯规则 → 节拍过渡指令                     │
├─────────────────────────────────────────────────────────────────┤
│  Layer 1 — 记忆与事实锁（全局不可违背）                            │
│  MemoryEngine → FACT_LOCK / COMPLETED_BEATS / REVEALED_CLUES     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、Layer 1 — 记忆与事实锁（全局不可违背）

### 2.1 问题：AI 长程"遗忘"

写到第 80 章时，AI 可能：
- 让已死亡角色"复活"
- 创造 Bible 中不存在的新角色
- 违背已确立的核心关系
- 重复写已发生过的情节
- 把已揭露的线索当作"新发现"

### 2.2 解决方案：MemoryEngine 三大不可篡改块

**代码位置**：`application/engine/services/memory_engine.py`

#### T0-α：FACT_LOCK（绝对事实边界）

从 Bible + KnowledgeGraph 动态构建，注入 T0 最高优先级槽位（priority=120），绝对不可被裁剪：

| 锁定内容 | 说明 |
|---------|------|
| 角色白名单 | 只可使用 Bible 中有名字的角色，禁止创造新命名角色 |
| 已死亡角色 | 绝对不可复活、不可在当下时间线出现 |
| 核心关系图谱 | 不可更改的角色间关系 |
| 身份锁死 | 角色的真实身份/隐藏身份（随章节进度渐进解锁） |
| 核心事件时间线 | 不可矛盾的关键事件时序 |

#### T0-β：COMPLETED_BEATS（已完成节拍锁）

防止"剧情鬼打墙"——AI 重复写已发生过的情节。格式如：
```
✓ [第10章] 主角在茶馆与赵宇对峙
✓ [第12章] 主角发现了密室中的日记
⚠️ 如需回顾，用角色回忆/一句话带过，禁止重新展开写
```

#### T0-γ：REVEALED_CLUES（已揭露线索清单）

防止前后矛盾——已知的线索不能再当"新发现"写。按类别标记：
- 🔓真相 / 🔗关系 / 🎭身份 / ⚡能力 / 📋信息

---

## 三、Layer 2 — 节拍间衔接（章内微连贯）

### 3.1 问题：节拍间割裂感

一章通常拆分为 4-8 个节拍（Beat），每个节拍独立生成后拼接。若不加约束，节拍之间会出现：
- 对话被截断后无人回应
- 动作进行中突然跳到新场景
- 情绪从紧张瞬间变轻松
- 用"后来""之后"等跳跃词粗暴过渡

### 3.2 解决方案：BeatTailAnchor 三维衔接锚点

**代码位置**：`application/workflows/beat_continuation.py`

从上一节拍末尾 ~300 字提取 3 维衔接锚点（**启发式，零 LLM 调用**）：

| 维度 | 说明 | 示例 |
|------|------|------|
| 尾部状态 | 上一节拍停在哪里 | 对话中 / 动作中 / 叙述中 / 悬念中 / 场景转换 |
| 情绪基调 | 末尾的情绪氛围 | 紧张 / 愤怒 / 悲伤 / 悬疑 / 舒缓 / 日常 |
| 最后画面 | 原文截取最后 ~100 字 | "赵宇正要推门出去——门还没推开" |

### 3.3 动态连贯规则生成

**代码位置**：`application/workflows/auto_novel_generation_workflow.py::_build_dynamic_coherence_rules()`

根据尾部状态，生成精确的衔接约束（而非泛泛的"保持连贯"）：

- **对话中** → 本节拍开头必须先回应/延续该对话，对话结束后再推进新情节
- **动作中** → 本节拍开头必须展示该动作的完成或结果
- **悬念中** → 延续悬念紧张感，不要立刻揭晓答案
- **叙述中** → 承接情绪惯性，用环境细节或角色动作作为过渡
- **场景转换** → 新场景第一段必须有感官细节

情绪惯性规则：紧张不能突然轻松、愤怒余怒未消、悲伤有惯性。

### 3.4 节拍过渡指令

**代码位置**：`application/workflows/beat_continuation.py::build_beat_transition_directive()`

生成精确的过渡指令注入下一节拍的 prompt：

```
【🔗 节拍衔接指令（第3/6节拍）】
上一节拍停在对白中间。本节拍开头必须：
  - 先给出对话的回应或延续（不能跳过不答）
  - 保持对话的弦外之音和情绪张力
  - 对话回合自然结束后再推进新情节
⚠ 情绪基调：紧张。不能突然轻松——紧张感至少延续到本节拍第一段结束。
📍 上一节拍最后画面：……赵宇的手停在门把上，没有推。
→ 本节拍开头必须从这之后自然接续
━━━ 节拍衔接铁律 ━━━
① 本节拍第一句话必须是上一节拍最后一幕的延续
② 节拍之间没有空行跳转——读者看到的是连续的文本
③ 不许用"后来"、"之后"等跳跃词来省略节拍间的过渡
```

### 3.5 节拍间衔接质量检测

**代码位置**：`application/engine/services/chapter_bridge_service.py::check_beat_continuity()`

轻量启发式检测（零 LLM 调用）：
- 跳跃词检测："后来""之后""转眼"等
- 对话断裂：前节拍在对话中，新节拍没有回应
- 情绪断裂：紧张→轻松、愤怒→平静等
- 场景突转：位置不一致

---

## 四、Layer 3 — 章间衔接引擎（跨章桥段）

### 4.1 问题：章与章之间像两个独立故事

AI 写每章开头时"从零开始"，读者翻页后感到割裂。

### 4.2 解决方案：ChapterBridgeService 三层衔接引擎

**代码位置**：`application/engine/services/chapter_bridge_service.py`

#### 第一层：章末桥段提取（extract_bridge）

每章完成后，用轻量 LLM 提取 **5 维桥段**（存入 SQLite）：

| 维度 | 说明 | 示例 |
|------|------|------|
| 悬念钩子 | 章末未解决的悬念 | "赵宇说出了一个名字，但话到嘴边又咽了回去" |
| 情感余韵 | POV 角色的核心情绪 + 强度 | "顾言之：不安与隐约的愤怒，7/10" |
| 场景状态 | 物理环境状态 | "深夜，老街茶馆内，雨势渐小" |
| 角色位置 | 各角色物理位置和行动 | "顾言之：坐在茶馆角落；赵宇：刚起身走向门口" |
| 未完成动作 | 尚未结束的动作/对话 | "赵宇正要推门出去——门还没推开" |

> 这不是"摘要"，而是"导演的转场笔记"——告诉下一章的 AI 上一章结束时"镜头"停在哪里。

#### 第二层：章首衔接约束（build_opening_directive）

下一章写作前，从 DB 读取前章桥段，生成 **T0 强制约束**（不可删减），注入 system prompt：

```
【🔗 章节衔接指令（T0 强制约束，不可删减）】
上一章（第 15 章）结束时：

⚠ 悬念钩子：赵宇说出了一个名字，但话到嘴边又咽了回去
→ 本章开头必须呼应此悬念：或直接回应、或侧面映射、或加深谜团。绝不能装作没发生过。

💭 情感余韵：顾言之：不安与隐约的愤怒（强烈，7/10）
→ 本章首段 POV 角色的情绪必须从「不安与隐约的愤怒」延续或演变。情绪有惯性——不会瞬间切换。

🏔 场景状态：深夜，老街茶馆内，雨势渐小
→ 本章开头的物理环境必须与前章末尾一致或自然过渡。

👤 角色位置：顾言之：坐在茶馆角落；赵宇：刚起身走向门口
→ 人不会瞬移——如果角色在门口，下一章他要么进门、要么转身。

🎬 未完成动作：赵宇正要推门出去——门还没推开
→ 本章必须延续此动作的完成过程，或解释为何中断。

━━━ 首段衔接铁律 ━━━
① 本章首段必须是上一章的延续，而非新的开始
② 前三句话之内必须出现与前章结尾的连接点
③ 如果场景转换，必须用过渡句，不能用空行跳转
④ 不许用"第二天"开头然后当上一章没发生过
```

#### 第三层：衔接度自检（check_continuity + auto_fix_opening）

章节生成后，用轻量 LLM 检查首段与前章桥段的衔接度：

| 分数区间 | 含义 |
|---------|------|
| 0.9-1.0 | 完美衔接，首段直接呼应前章 |
| 0.7-0.9 | 良好衔接，有明确过渡 |
| 0.5-0.7 | 弱衔接，过渡生硬 |
| 0.3-0.5 | 割裂感明显，像两个独立故事 |
| 0-0.3 | 完全断裂 |

**衔接度 < 0.6 → 自动修整首段**（最多 2 轮），由 `auto_fix_opening` 方法实现。

### 4.3 自动驾驶中的集成

**代码位置**：`application/engine/services/autopilot_daemon.py::_continuity_self_check()`

在自动驾驶流程中，每章完成后自动触发衔接自检：
```python
if chapter_num > 1:
    chapter_content = await self._continuity_self_check(
        novel_id, chapter_num, chapter_content
    )
```

---

## 五、Layer 4 — 上下文预算与优先级注入

### 5.1 问题：上下文窗口有限

百章小说的全量上下文远超 LLM 窗口上限，必须做取舍。但取舍不当会导致关键信息被裁剪，引发连贯性问题。

### 5.2 解决方案：ContextBudgetAllocator 优先级沙漏

**代码位置**：`application/engine/services/context_budget_allocator.py`

四级优先级槽位体系：

| 优先级 | 层级 | 内容 | 可否裁剪 |
|--------|------|------|----------|
| T0 | CRITICAL | 生命周期准则、主线锚点、FACT_LOCK、伤疤执念、实体记忆、叙事债务、卷摘要 | **绝对不可** |
| T1 | HIGH | 因果链、已完结卷摘要、BeatSheet | 极少裁剪 |
| T2 | STANDARD | 前章原文、当前幕大纲 | 可裁剪 |
| T3 | LOW | 向量检索补充 | 优先裁剪 |

### 5.3 Feed-forward 上下文反哺管线

**代码位置**：`application/engine/services/context_assembler.py`

核心思想：**把章后管线产生的高质量资产，高优先级投喂给下一章的生成上下文。**

| T0 槽位 | 优先级 | 内容来源 | 作用 |
|---------|--------|---------|------|
| STORY_ANCHOR | 125 | Bible 核心前提 | 全书主线锚点 ≤300 字，防止偏离主线 |
| SCARS_AND_MOTIVATIONS | 118 | CharacterStateRepository | 角色伤疤与执念，防止情感失忆 |
| ACTIVE_ENTITY_MEMORY | 112 | CausalEdgeRepository | 活跃实体因果链，防止因果断裂 |
| DEBT_DUE | 108 | NarrativeDebtRepository | 叙事债务到期提醒，强迫填坑 |
| PREVIOUSLY_ON | 107 | StoryNodeRepository | 卷级动态摘要，时空基石 |

| T1 槽位 | 内容来源 | 作用 |
|---------|---------|------|
| CAUSAL_CHAINS | CausalEdgeRepository | 未闭环因果链 |
| COMPLETED_VOLUME_SUMMARIES | StoryNodeRepository | 已完结卷摘要 |

---

## 六、Layer 5 — 章后管线（事后提取 + 反哺）

### 6.1 ChapterAftermathPipeline

**代码位置**：`application/engine/services/chapter_aftermath_pipeline.py`

每章保存后执行完整管线：
1. **叙事同步**（narrative_sync）：单次 LLM 调用同时提取——
   - 三元组（实体-关系-实体）→ 知识图谱
   - 伏笔（planted / consumed）→ 伏笔账本
   - 故事线推进 → 故事线状态
   - 张力曲线 → tension 标记
   - 对话分析 → 对话质量
   - 因果边 → 因果图谱
   - 人物状态突变 → 角色状态机
   - 叙事债务更新 → 债务账本

2. **向量存储**：正文切块存入 ChromaDB，供后续向量检索

3. **衔接引擎**：提取章末桥段 → 存入 `chapter_bridges` 表

### 6.2 叙事债务系统

**代码位置**：`domain/novel/value_objects/narrative_debt.py`

百章级长篇的"挖坑不填"问题终结者。四种债务类型：

| 债务类型 | 说明 | 示例 |
|---------|------|------|
| foreshadowing | 伏笔债务 | 第5章埋的悬念到第30章还没回收 |
| causal_chain | 因果债务 | 因果链未闭环 |
| storyline | 故事线债务 | 支线未完结 |
| character_arc | 角色弧债务 | 角色发展未收束 |

**生命周期**：`created → overdue → resolved / abandoned`

**TTL 机制**：每笔债务有 `due_chapter`（预期偿还章节），到期后标记 `is_overdue`，在下一章生成时通过 `DEBT_DUE` 槽位强制注入 `[MUST_RESOLVE]` 块，强迫 AI 填坑。

### 6.3 因果图谱

**代码位置**：`domain/novel/value_objects/causal_edge.py`

超越静态关系三元组，追踪事件的因果链：

```
传统知识图谱：(主角)-[属于]->(宗门)         —— 静态关系，不懂"因果"
因果图谱：     (宗门被灭)-[导致]->(仇恨MAX)-[目标]->(复仇)  —— 因果链
```

五种因果类型：`causes / motivates / triggers / prevents / resolves`

关键能力：AI 写第 80 章时，能查到"上次主角与该反派见面是在第 10 章，主角战败并立下三年之约"。

### 6.4 人物可变状态机

**代码位置**：`domain/novel/value_objects/character_state.py`

三大连贯性问题的解决方案：

| 问题 | 解决机制 | 说明 |
|------|---------|------|
| 情感失忆症 | Scars（伤疤） | 记录角色经历过什么，AI 不会忘记 |
| 因果链断裂 | Motivations（执念） | 记录角色当前驱动力 |
| 人物弧光冻结 | Emotional Arc | 追踪情感变化，区分 OOC 和 Breakout |

注入文本示例：
```
【💔 角色伤疤与执念（写作此角色时必须参考）】
  顾言之:
    伤疤: [第8章] 雨夜车祸 → 负罪感(8/10)
           敏感触发词: 雨天/车祸/死亡
    执念: [第15章] 查明真相(优先级9)
    当前状态: 伤疤: 负罪感(8/10) | 执念: 查明真相(P9)
    ⚠️ 注意：此角色的偏离行为不是OOC，而是伤疤被触发后的应激反应——这是高光时刻
```

### 6.5 卷级摘要服务

**代码位置**：`application/blueprint/services/volume_summary_service.py`

金字塔层级压缩，提供不可撼动的时空与逻辑基石：

| 层级 | 触发时机 | 目标 Token | 内容 |
|------|---------|-----------|------|
| 幕摘要 | 每写完一幕 | ~200 | 核心危机 + 弧光偏移 + 高潮落点 |
| 卷摘要 | 每写完一卷（Map-Reduce） | ~500 | 主轴推进 + 生态变迁 + 卷末余震 |
| 部摘要 | 每写完一部 | ~300 | 三部曲定位 + 主角弧光 + 核心冲突 |
| 检查点摘要 | 每 20 章 | - | 强制摘要，防止长程遗忘 |

### 6.6 双轨融合规划

**代码位置**：`application/blueprint/services/continuous_planning_service.py`

生成下一幕时，注入双轨上下文：

| 轨道 | 内容 | 作用 |
|------|------|------|
| 宏观摘要线 | 前一卷/前一部的高浓缩摘要 | 提供时空基石，防止时间线错乱 |
| 微观高亮线 | 待回收伏笔 + 角色当前状态锚点 | 确保伏笔回收和角色状态连续 |

---

## 七、完整数据流：从第 N 章到第 N+1 章

```
第 N 章写作完成
    │
    ▼
┌─ ChapterAftermathPipeline ──────────────────────────────────┐
│  1. narrative_sync (单次 LLM)                               │
│     ├─ 三元组 → 知识图谱                                     │
│     ├─ 伏笔 planted/consumed → 伏笔账本                      │
│     ├─ 因果边 → 因果图谱                                     │
│     ├─ 人物状态突变 → CharacterState (Scars/Motivations)     │
│     ├─ 叙事债务更新 → NarrativeDebt                          │
│     └─ 张力/对话/故事线 → 各仓库                              │
│  2. 向量存储 → ChromaDB                                      │
│  3. ChapterBridgeService.extract_bridge()                   │
│     └─ 5维桥段 → chapter_bridges 表                          │
│  4. VolumeSummaryService (幕/卷完结时)                       │
│     └─ 幕摘要/卷摘要 → story_node.metadata                  │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
第 N+1 章生成前
    │
    ▼
┌─ ContextBudgetAllocator._collect_all_slots() ──────────────┐
│  T0 (不可裁剪):                                             │
│    ├─ lifecycle_directive (priority=130)                    │
│    ├─ story_anchor (priority=125)                          │
│    ├─ FACT_LOCK (priority=120)                             │
│    ├─ scars_and_motivations (priority=118)                 │
│    ├─ active_entity_memory (priority=112)                  │
│    ├─ debt_due (priority=108)                              │
│    └─ previously_on (priority=107)                         │
│  T1:                                                        │
│    ├─ causal_chains                                         │
│    └─ completed_volume_summaries                            │
│  T2: 前章原文 + 当前幕大纲                                   │
│  T3: 向量检索补充                                            │
│                                                             │
│  + ChapterBridgeService.build_opening_directive()          │
│    └─ 前章5维桥段 → T0 强制衔接指令                          │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
第 N+1 章节拍生成
    │
    ▼
┌─ Beat 级衔接保障 ──────────────────────────────────────────┐
│  每个节拍生成前：                                            │
│  1. extract_beat_tail_anchor() → 3维锚点                    │
│  2. _build_dynamic_coherence_rules() → 动态连贯规则          │
│  3. build_beat_transition_directive() → 过渡指令             │
│  4. BeatCoherenceEnhancer → 角色场景情绪动作连贯指导          │
│  5. BeatMiddleware → 铺陈/收束/着陆信号                      │
│                                                             │
│  首节拍特殊：强调与前章衔接                                    │
│  末节拍特殊：强调章节收尾 + 悬念钩子                           │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
第 N+1 章生成完成
    │
    ▼
┌─ 衔接自检 ─────────────────────────────────────────────────┐
│  _continuity_self_check()                                   │
│  ├─ check_continuity() → 衔接度评分 (0-1)                   │
│  └─ score < 0.6 → auto_fix_opening() (最多2轮)             │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
进入审计阶段 → 审计完成后再次触发 AftermathPipeline → 循环
```

---

## 八、关键设计决策

### 8.1 为什么用"桥段"而不是"摘要"？

摘要会丢失关键的结构信息（悬念、情绪、位置），而桥段是"导演的转场笔记"——它关心的不是"这一章讲了什么"，而是"上一章结束时镜头停在哪里，下一章镜头该从哪里接"。

### 8.2 为什么衔接自检是轻量 LLM 而不是重模型？

~200 token 的轻量调用，仅必要时触发（非第1章、且衔接度可能有问题时）。性能开销极小，但能有效防止明显的衔接断裂。

### 8.3 为什么叙事债务有 TTL？

百章小说中，第5章埋的伏笔如果到第80章还没回收，读者早已忘记，此时再回收反而突兀。TTL 机制确保伏笔在"黄金回收窗口"内被强制注入到写作上下文中。

### 8.4 为什么 FACT_LOCK 是动态构建而不是硬编码？

Bible 中的角色、关系、时间线会随创作迭代更新，FACT_LOCK 每次 generation 前从 Bible + KnowledgeGraph 实时构建，确保永远是最新的不可违背事实。

---

## 九、核心组件索引

| 组件 | 文件路径 | 核心职责 |
|------|---------|---------|
| ChapterBridgeService | `application/engine/services/chapter_bridge_service.py` | 章间5维桥段提取 + 衔接指令 + 自检修整 |
| BeatTailAnchor | `application/workflows/beat_continuation.py` | 节拍3维锚点提取 + 过渡指令生成 |
| BeatCoherenceEnhancer | `application/engine/services/beat_coherence_enhancer.py` | 节拍间角色/场景/情绪/动作连贯增强 |
| ContextAssembler | `application/engine/services/context_assembler.py` | 上下文反哺管线（Feed-forward） |
| ContextBudgetAllocator | `application/engine/services/context_budget_allocator.py` | 上下文预算分配 + T0/T1/T2/T3 槽位 |
| MemoryEngine | `application/engine/services/memory_engine.py` | FACT_LOCK / BEATS / CLUES 三大锁 |
| NarrativeDebt | `domain/novel/value_objects/narrative_debt.py` | 叙事债务值对象 |
| CausalEdge | `domain/novel/value_objects/causal_edge.py` | 因果边值对象 |
| CharacterState | `domain/novel/value_objects/character_state.py` | 人物可变状态（Scars/Motivations） |
| VolumeSummaryService | `application/blueprint/services/volume_summary_service.py` | 卷级金字塔摘要 |
| ChapterAftermathPipeline | `application/engine/services/chapter_aftermath_pipeline.py` | 章后完整管线 |
| ContinuousPlanningService | `application/blueprint/services/continuous_planning_service.py` | 双轨融合规划 |
| AutoNovelGenerationWorkflow | `application/workflows/auto_novel_generation_workflow.py` | 自动生成主工作流 |
| AutopilotDaemon | `application/engine/services/autopilot_daemon.py` | 自动驾驶守护进程 |

---

## 十、已知局限与未来方向

### 当前局限

1. **跨卷衔接**：卷与卷之间的衔接目前依赖卷摘要，但摘要的信息密度有限，可能遗漏细节
2. **远期伏笔回收**：超过 TTL 的伏笔可能被标记为 abandoned，但读者未必能接受"挖坑不填"
3. **多人协作场景**：当前系统假设单人写作，未考虑多人协作时的连贯性冲突
4. **长程时间线验证**：没有显式的时间线推理引擎，复杂时间线（倒叙/插叙/平行时间线）可能出错

### 未来方向

1. **时间线推理引擎**：显式建模时间线，自动检测时间矛盾
2. **角色关系演化追踪**：动态追踪角色关系的变化轨迹，防止关系回退
3. **读者感知模型**：基于读者视角的连贯性评估（读者能感知到的不连贯才需要修）
4. **跨卷桥段升级**：在卷摘要基础上增加卷间桥段提取，强化跨卷衔接
