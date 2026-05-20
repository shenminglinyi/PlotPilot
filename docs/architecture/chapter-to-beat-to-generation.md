# PlotPilot 章节 → 节拍 → 生文 模型设计全景

> 版本：v1.0 · 生成日期：2026-05-19  
> 涵盖范围：从章节大纲到微观节拍拆分，再到逐拍生文的完整架构

---

## 1. 总体架构概览

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          章节生成全景流水线                              │
│                                                                          │
│  ┌─────────┐    ┌──────────────┐    ┌─────────────┐    ┌──────────────┐ │
│  │ 章节大纲 │───▶│  章前规划     │───▶│  节拍放大器  │───▶│  逐拍生文    │ │
│  │ Outline │    │ Planning     │    │  Beat        │    │  Generation  │ │
│  └─────────┘    └──────┬───────┘    │  Magnifier   │    └──────┬───────┘ │
│                        │             └──────┬──────┘           │         │
│                        ▼                    ▼                  ▼         │
│               ChapterExecutionPlan      List[Beat]      ChapterContent   │
│                        │                    │                  │         │
│                        │    ┌───────────────┼──────────────────┘         │
│                        │    ▼               ▼                            │
│                        │  ATG空间绑定   指挥器字数控制                    │
│                        │  场景导演      连贯性中间件                      │
│                        │  主题Agent     拓扑闸门/泄露阻截                 │
│                        │               爽文引擎(能量免疫)                │
│                        └─────────────────────────────────────────────── │
└──────────────────────────────────────────────────────────────────────────┘
```

**核心数据流**：`章节大纲 → ChapterExecutionPlan(Atoms) → List[Beat] → 逐拍LLM流式生成 → 章节正文`

---

## 2. 章前规划层：ChapterExecutionPlan

### 2.1 核心数据模型

| 模型 | 文件 | 职责 |
|------|------|------|
| `PlanningEnvelope` | `application/engine/dag/plan/schema.py` | 章约束信封：novel_id、chapter_number、target_chapter_words、outline_hash |
| `PlanAtomSpec` | 同上 | 最小叙事推进单元（抽象节拍规格），包含 id、intent、weight、extensions |
| `ChapterExecutionPlan` | 同上 | 章前规划根文档，schema_version + envelope + atoms + provenance |

**PlanAtomSpec 关键字段**：

```python
class PlanAtomSpec(BaseModel):
    id: str                    # 原子标识（如 "b1", "b2"）
    intent: str                # 该拍在叙事上要完成什么（事件/推进单元，非句法切分）
    weight: float              # 相对字数权重，供预算分配
    source_hint: Optional[str] # 引用章纲片段（仅调试/溯源）
    extensions: Dict[str, Any] # 扩展字段：focus、location_id、transition_from_prev 等
```

### 2.2 规划策略优先级

```
beat_sheet_json.scenes → 显式条文结构 → (可选)LLM 分解 → 兜底单 atom
```

| 优先级 | 模式 | 说明 | 数据来源 |
|--------|------|------|----------|
| 1 | `beat_sheet` | 上游 BeatSheet 的 scenes 投影为 atoms | `BeatSheetService.generate_beat_sheet()` |
| 2 | `structured_outline` | 用户显式多段结构（编号列表/项目符号/空行段） | `segment_structured_outline()` |
| 3 | `llm_outline_decompose` | LLM 经 CPMS `outline-beat-partition` 节点拆分 | `llm_decompose_outline()` |
| 4 | `fallback_single` | 兜底：整章单 atom | 默认 |

**关键约束**：
- 最大 atom 数：`_MAX_ATOMS = 8`（超出合并尾部）
- 禁止句读硬切：`segment_structured_outline()` 只在用户显式多段时才返回多条
- LLM 提示词由 CPMS 节点 `outline-beat-partition` 统一管理，不在代码中硬编码

### 2.3 DAG 节点映射

| DAG 节点类型 | 显示名 | CPMS 节点 Key | 输出端口 |
|-------------|--------|---------------|---------|
| `planning_outline_partition` | 📑 章纲节拍划分 | `outline-beat-partition` | `chapter_plan_json` |
| `planning_beat_sheet` | 🎵 节拍表拆解 | `beat-sheet-decomposition` | `beat_sheet_json` |
| `planning_act` | 🎭 幕级规划 | `planning-act` | `act_chapters_json` |

---

## 3. 节拍放大器层：Beat Magnifier

### 3.1 Beat 数据模型

```python
@dataclass
class Beat:
    description: str              # 节拍内容描述（含"章纲节选·须落实"标记）
    target_words: int             # 目标字数
    focus: str                    # 聚焦类型
    expansion_hints: List[str]    # 扩写维度提示
    scene_goal: str = ""          # 场景目标
    transition_from_prev: str = ""# 从上一节拍的过渡方式
    location_id: str = ""         # ATG 微观坐标
```

### 3.2 三路径构建策略

`ContextBuilder.magnify_outline_to_beats()` 实现三级路径：

| 路径 | 条件 | 方法 | 特点 |
|------|------|------|------|
| **A** | `chapter_execution_plan.atoms` 存在 | `_build_beats_from_execution_plan()` | 按原子权重分配字数，继承 extensions 的 focus/transition/location |
| **B** | `beat_sheet.scenes` 存在 | `_build_beats_from_beat_sheet()` | 使用规划阶段预估字数，从 Scene 推断 focus |
| **C** | 无上游数据 | `_build_beats_from_outline()` | 回退：章纲条文拆分 → 开篇黄金法则 → 关键词推断 → 起承转合默认 |

### 3.3 聚焦类型（Focus）体系

| Focus 类型 | 语义 | 场景 |
|-----------|------|------|
| `action` | 动作/战斗/冲突推进 | 战斗、追逐、对抗 |
| `dialogue` | 对话/争吵/谈判 | 人际互动、信息交换 |
| `sensory` | 感官/环境/氛围 | 场景建立、空间描写 |
| `emotion` | 情绪/内心/回忆 | 心理转折、情感爆发 |
| `suspense` | 悬念/谜团/钩子 | 伏笔铺设、章节结尾 |
| `hook` | 开篇冲击/抓人 | 第一章首拍 |
| `character_intro` | 人物出场/特质展示 | 第一章第二拍 |
| `power_reveal` | ★爽点/实力展露 | 玄幻/仙侠核心爽点 |
| `identity_reveal` | ★身份反转/打脸 | 都市/言情核心爽点 |

### 3.4 扩写维度提示（EXPANSION_HINTS）

根据 focus 类型 + 目标字数动态注入扩写方向：

| Focus | 高字数(≥1000) 4条 | 中字数(≥600) 3条 | 低字数(<600) 2条 |
|-------|-------------------|-------------------|-------------------|
| `action` | 招式碰撞、环境破坏、旁观者反应、节奏变化 | 前3条 | 前2条 |
| `dialogue` | 微表情、肢体语言、潜台词、节奏 | 前3条 | 前2条 |
| `sensory` | 光影变化、声音细节、温度触感、气味味道 | 前3条 | 前2条 |
| `emotion` | 内心独白、回忆闪回、身体反应、情绪转变 | 前3条 | 前2条 |
| `suspense` | 心理推演、五官感知、时间拉长、悬念钩子 | 前3条 | 前2条 |

### 3.5 场景模板（回退路径 C）

| 大纲关键词 | 模板 | 拍数 | 节奏分配 |
|-----------|------|------|----------|
| 争吵/冲突/质问 | `_build_conflict_beats` | 4 | sensory(0.9) → dialogue(1.4) → emotion(1.2) → action(0.9) |
| 战斗/打斗/对决 | `_build_battle_beats` | 5 | sensory(0.7) → action(1.0) → action(1.2) → emotion(0.9) → action(0.6) |
| 发现/真相/揭露 | `_build_revelation_beats` | 3 | emotion(1.2) → dialogue(1.8) → emotion(1.3) |
| 默认 | `_build_default_beats` | 4 | 起(sensory)→承(dialogue)→转(action)→合(suspense) |
| 第1章 | 开篇黄金法则 | 4 | hook(1.2) → character_intro(1.5) → sensory(1.3) → suspense(1.0) |
| 第2章 | 承接深化 | 4 | dialogue(1.3) → action(1.8) → emotion(1.0) → suspense(0.8) |
| 第3章 | 高潮前奏 | 4 | sensory(1.0) → action(2.0) → emotion(1.3) → suspense(0.7) |

### 3.6 拍数约束

```python
MAX_BEATS = 8        # 上限：拍数过多时每拍字数太少，模型倾向八股堆满
MIN_BEAT_WORDS = 800 # 下限：低于此值合并相邻拍
```

合并逻辑：`_cap_and_merge_beats()` → `_merge_two_beats()`：相邻拍合并时 description 用 `/` 连接，target_words 相加，expansion_hints 去重取前4。

---

## 4. 主题Agent层：Genre-Specific Beat 策略

### 4.1 Agent 体系

`ThemeIntegrator` 根据小说 genre 分发到对应 Agent，每个 Agent 提供：

| 方法 | 作用 |
|------|------|
| `get_opening_beats(chapter_number)` | 前三章定制节拍（爽点爆发节奏） |
| `get_custom_focus_instructions()` | 类型特化 focus 指令 |
| `get_buffer_chapter_template(outline)` | 缓冲章模板 |
| `get_audit_criteria()` | 审计标准 |

### 4.2 各类型 Agent 开篇策略

所有 Agent 的前三章遵循统一的**「拉仇恨→冲突→爽点爆发→悬念」四拍结构**，但核心爽点类型不同：

| Genre | Agent | 核心爽点 focus | 爽点特征 |
|-------|-------|---------------|---------|
| 玄幻 | `XuanhuanAgent` | `power_reveal` | 实力碾压、旁观者震惊 |
| 都市 | `DushiAgent` | `identity_reveal` | 身份反转、态度180°逆转 |
| 言情 | `RomanceAgent` | `identity_reveal` | CP张力、态度反转 |
| 悬疑 | `SuspenseAgent` | `power_reveal` | 推理碾压、假设推翻 |
| 仙侠 | `XianxiaAgent` | `power_reveal` | 修仙天赋、仙缘爆发 |
| 武侠 | `WuxiaAgent` | `power_reveal` | 以弱胜强、武功展露 |
| 奇幻 | `FantasyAgent` | `power_reveal` | 命运之力、魔法天赋 |
| 历史 | `HistoryAgent` | `power_reveal` | 权谋奇才、以弱制强 |
| 科幻 | `ScifiAgent` | `power_reveal` | 天才洞察、认知突破 |
| 其他 | `OtherAgent` | `power_reveal` | 通用隐藏能力展露 |

**爽点字数占比**：第一章约 56%（1400/2500），第二章约 44%（1100/2500），第三章约 44%（1100/2500）。

---

## 5. 场景导演与空间拓扑层

### 5.1 SceneDirectorService

基于 LLM 分析章节大纲，输出结构化场记数据：

```json
{
  "characters": ["角色1", "角色2"],
  "locations": ["具体微观坐标"],
  "action_types": ["动作类型"],
  "trigger_keywords": ["触发词"],
  "emotional_state": "情绪基调",
  "pov": "视点人物",
  "atg": {
    "nodes": [{"location_id": "精确微观坐标", "initial_props": [], "is_entry_point": false}],
    "transitions": [{"source_location": "", "target_location": "", "required_action": "", "trigger_characters": []}],
    "visit_sequence": ["按叙事顺序列出 location_id"]
  }
}
```

### 5.2 ATG（Action Transition Graph）

| 模型 | 文件 | 职责 |
|------|------|------|
| `ActionTransitionGraph` | `domain/novel/value_objects/action_transition_graph.py` | 章节空间拓扑，含 nodes + transitions + visit_sequence |
| `SceneNode` | 同上 | 微观场景节点（location_id + initial_props + is_entry_point） |
| `TransitionEdge` | 同上 | 空间转移边（source → target + required_action + trigger_characters） |

### 5.3 ATG 与节拍绑定

`_bind_atg_locations_if_present()` 将 `visit_sequence` 映射到各节拍的 `location_id`：

```python
def assign_visit_locations_to_beats(beats, visit_sequence):
    # 均匀采样：将 visit_sequence 按比例分配到各节拍
    for i, b in enumerate(beats):
        idx = min(round(i * (m - 1) / max(n - 1, 1)), m - 1)
        b.location_id = seq[idx]
```

### 5.4 微观场景上下文（MicroSceneContext）

节拍间传递的运行时快照，跟踪在场角色和道具：

```python
@dataclass
class MicroSceneContext:
    location_id: str
    active_characters: Set[str]   # 当前在场角色
    active_props: Set[str]        # 当前在场道具
```

每完成一个节拍后通过 `refresh_micro_scene_context_after_beat()` 更新。

---

## 6. 章节指挥器：字数控制哲学

### 6.1 三阶段收束模型

```
UNFURL(铺陈) ──▶ CONVERGE(收束) ──▶ LAND(着陆)
   0%~75%            75%~92%          92%~100%+
```

| 阶段 | 阈值 | 创作指令 | 行为 |
|------|------|---------|------|
| **UNFURL** | 0%~75% | 📖 铺陈阶段 | 尽情展开，冲突充分碰撞，对话你来我往，感官细节细腻 |
| **CONVERGE** | 75%~92% | ⚡ 收束阶段 | 场景转换加速、对话精炼、叙述紧凑、支线一笔带过 |
| **LAND** | 92%~100%+ | 🎯 着陆阶段 | 最后一个完整场景收束，绝不开启新场景，必须完整句子结尾 |

### 6.2 高能节拍免疫（爽文引擎）

```python
HIGH_ENERGY_FOCUSES = {"action", "power_reveal", "identity_reveal", "hook", "cultivation"}
```

- 高能节拍锁定 UNFURL，绝对不在打脸高潮处触发 CONVERGE
- 高能节拍超支的字数缺口，转嫁到后续 sensory/dialogue 节拍中压缩

### 6.3 截断安全网

| 方式 | 条件 | 行为 |
|------|------|------|
| 自然收束 | 字数 ≤ hard_cap | 由 LLM 按 Prompt 指令自然完成 |
| 智能截断 | `smart_truncate_enabled=True` | 按 focus 类型保留关键内容，截断到完整句子 |
| 硬截断 | `smart_truncate_enabled=False` | 在 hard_cap 处字符级截断（到完整句子） |

---

## 7. 节拍连贯性增强体系

### 7.1 BeatCoherenceEnhancer

**核心职责**：检测和修复节拍间连贯性问题

| 分析维度 | 方法 | 检测内容 |
|---------|------|---------|
| 角色连贯 | `_check_character_coherence` | 角色出现/消失的合理性 |
| 场景连贯 | `_check_scene_coherence` | 场景切换的过渡合理性 |
| 情绪连贯 | `_check_mood_coherence` | 情绪转变的渐进性 |
| 动作连贯 | `_check_action_coherence` | 未完成动作的延续性 |

**上下文提取**（`BeatContext`）：characters、scene、mood、ongoing_actions、unresolved_tensions

### 7.2 ATG 空间约束指令

`build_atg_transition_directive()` 根据节拍间的空间关系生成三种指令：

| 场景 | 指令 | 内容 |
|------|------|------|
| 同一位置 | 空间锁定 | 维持当前微观场景，禁止无过渡切换 |
| 有过场边 | 强制物理过渡 | 指定执行者、动作锚点、路径，禁止瞬移 |
| 无过场边 | 拓扑告警 | 提示补充合理过渡描写 |

### 7.3 拓扑闸门与泄露阻截

| 组件 | 文件 | 职责 |
|------|------|------|
| `DraftTopologyCommitGate` | `spatial_coherence.py` | 校验正文中的角色出场是否合规 |
| `StreamingSceneLeakGuard` | 同上 | 流式生成时实时阻截角色泄露 |
| `EscalatingBeatRetryDirector` | 同上 | 递增重试策略：修改 → 重写 → 放宽 |

---

## 8. 节拍中间件协议

### 8.1 中间件架构

```python
class BeatMiddleware(Protocol):
    def pre_beat(self, beat_prompt, adjusted_target, ctx) -> Tuple[str, int]
    def post_beat(self, beat_content, ctx) -> BeatMiddlewareContext
```

### 8.2 四大核心中间件

| 中间件 | 职责 | pre_beat 行为 | post_beat 行为 |
|--------|------|---------------|----------------|
| **CoherenceMiddleware** | 连贯性注入 | 注入连贯性指令到 beat_prompt | 分析 BeatContext 供下一拍使用 |
| **TransitionMiddleware** | 过渡方式推断 | 自动推断 transition_from_prev | — |
| **EnergyImmunityMiddleware** | 高能节拍免疫 | 高能 focus 跳过压缩 | — |
| **StepTensionMiddleware** | ★爽文引擎 STEP 阶跃张力 | 张力注入 | 情绪趋势追踪 |

### 8.3 中间件上下文（BeatMiddlewareContext）

```python
@dataclass
class BeatMiddlewareContext:
    novel_id: str
    chapter_number: int
    beat_index: int
    beat: Optional[Beat]
    total_beats: int
    phase: str                         # conductor 阶段
    prev_beat_content: str = ""        # 前一拍正文
    prev_beat_context: Optional[BeatContext] = None
    prev_beat_focus: str = ""
    accumulated_content: str = ""      # 已累积的章节正文
    original_adjusted_target: int = 0
```

---

## 9. 逐拍生文层

### 9.1 生成流程

```
for each beat:
  1. 指挥器信号 → 铺陈/收束/着陆阶段判断
  2. 空间拓扑 → ATG 过渡指令 + 泄露阻截闸门
  3. 连贯性分析 → 注入连贯性修复指令
  4. 中间件 pre_beat → 修改 prompt / 目标字数
  5. 指挥器指令注入 → beat_instruction + chapter_ending_hint
  6. LLM 流式生成 → max_tokens = adjusted_target × 1.3
  7. 截断安全网 → 智能截断 or 硬截断
  8. 拓扑闸门校验 → 递增重试（最多3次）
  9. 中间件 post_beat → 提取上下文
  10. 微观场景上下文刷新
```

### 9.2 两种运行模式

| 模式 | 入口 | 特点 |
|------|------|------|
| **API 流式** | `AutoNovelGenerationWorkflow.generate_chapter_stream()` | SSE 事件流，支持前端实时渲染 |
| **Autopilot 守护进程** | `AutopilotDaemon._write_chapter()` | 轮询驱动，节拍级幂等断点续写 |

### 9.3 Prompt 组装

**CPMS 提示词节点**：

| 节点 Key | 变量 | 用途 |
|---------|------|------|
| `workflow-chapter-generation` | planning_section, voice_block, behavior_protocol, character_state_lock, context, fact_lock, length_rule, beat_extra, outline, prior_draft, beat_section | 章节主 prompt |
| `autopilot-stream-beat` | — | 节拍级精简 system prompt |
| `beat-focus-instructions` | beat_index, total_beats, target_words, focus, instruction, description, anchor_line, obligation | 节拍聚焦指令集 |

### 9.4 Anti-AI 行为协议

嵌入在 `workflow-chapter-generation` 的 system_template 中：

| 规则 | 说明 |
|------|------|
| 禁止情绪标签 | "他感到愤怒" → 写动作"他端起杯子又放下了" |
| 禁止比喻 | "仿佛/宛如/犹如" → 写感官细节"那片皮肤是热的" |
| 禁止微表情 | "嘴角上扬/眼里闪过" → 写完整姿态变化或不写 |
| 禁止纠正式对照 | "不是…而是…" → 拆成两句平叙或写动作 |
| 情绪惯性 | 上一段愤怒这一段不能突然平静 |
| 角色差异化 | 读书人先考虑逃跑，用刀的人先摸刀 |
| 禁止AI式总结句 | "一切才刚刚开始" 等禁用 |
| 段落聚合铁律 | 同一视觉焦点/动作链的句子必须合并，一句独段 ≤15% |

---

## 10. 前端交互与状态管理

### 10.1 SSE 事件类型

| 事件类型 | 数据 | 时机 |
|---------|------|------|
| `phase` | planning / context / outline_planning / prose / post | 阶段切换 |
| `beats_generated` | beats 列表 | 节拍拆分完成 |
| `llm_chunk` | {stage: "outline_partition", text} | 节拍划分 LLM 流式增量 |
| `chunk` | {text, stats: {chars, chunks, estimated_tokens}} | 正文流式增量 |
| `done` | {content, consistency_report, token_count} | 章节生成完成 |
| `error` | {message} | 错误 |

### 10.2 前端组件

| 组件 | 职责 |
|------|------|
| `ChapterWriterStream.vue` | 流式正文渲染（增量追加 + 自动滚动） |
| `CustomNode.vue` | DAG 节点可视化（状态徽章 + 进度指示） |
| `consumeGenerateChapterStream()` | SSE 消费器（节拍/阶段/正文/完成 事件分发） |

### 10.3 守护进程实时状态

通过共享状态 + SSE 日志流向前端推送：

```python
_update_shared_state(
    novel_id,
    current_beat_index=i,
    writing_substep="llm_calling",
    beat_focus=...,
    beat_target_words=...,
    accumulated_words=...,
    chapter_target_words=...,
    beat_phase=signal.phase.value,
    beat_hard_cap=...,
    beat_remaining_budget=...,
)
```

---

## 11. 关键设计决策总结

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| 节拍拆分方式 | A.硬切 B.LLM C.混合 | **C.混合优先级** | BeatSheet > 显式结构 > LLM > 兜底，兼顾准确性与覆盖度 |
| 字数控制 | A.事后精简 B.截断 C.渐进收束 | **C.渐进收束** | 不毁灭文本质量，不割裂读者体验，Prompt 指引自然收束 |
| 空间一致性 | A.后校验 B.前置约束 C.双层 | **C.双层** | ATG 前置约束 + 闸门后校验 + 递增重试 |
| 爽点保护 | A.无保护 B.权重调整 C.免疫压缩 | **C.免疫压缩** | 高能节拍绝对不压缩，超支转嫁到低能节拍 |
| Prompt 管理 | A.硬编码 B.配置文件 C.CPMS | **C.CPMS** | 提示词广场统一管理，支持用户编辑与三级降级 |
| 连贯性 | A.全量重写 B.简单拼接 C.中间件增强 | **C.中间件增强** | 低侵入式 pre/post 钩子，可组合、可扩展 |

---

## 12. 核心文件索引

| 层次 | 文件 | 核心类/函数 |
|------|------|------------|
| 规划模型 | `application/engine/dag/plan/schema.py` | `ChapterExecutionPlan`, `PlanAtomSpec`, `PlanningEnvelope` |
| 规划逻辑 | `application/engine/dag/plan/outline_beat_planner.py` | `build_chapter_execution_plan_async()`, `segment_structured_outline()` |
| 节拍放大器 | `application/engine/services/context_builder.py` | `magnify_outline_to_beats()`, `_build_beats_from_*()` |
| 字数指挥器 | `application/engine/services/word_count_tracker.py` | `ChapterConductor`, `ConductorPhase`, `ConductorSignal` |
| 连贯性增强 | `application/engine/services/beat_coherence_enhancer.py` | `BeatCoherenceEnhancer`, `BeatContext`, `CoherenceIssue` |
| 空间拓扑 | `application/engine/services/spatial_coherence.py` | `assign_visit_locations_to_beats()`, `DraftTopologyCommitGate` |
| 场景导演 | `application/engine/services/scene_director_service.py` | `SceneDirectorService` |
| 节拍中间件 | `application/engine/services/beat_middleware.py` | `BeatMiddleware`, `CoherenceMiddleware`, `EnergyImmunityMiddleware` |
| 工作流 | `application/workflows/auto_novel_generation_workflow.py` | `generate_chapter_stream()`, `_spatial_topology_bundle_for_beat()` |
| 守护进程 | `application/engine/services/autopilot_daemon.py` | `_write_chapter()`, `_stream_llm_with_stop_watch()` |
| 主题Agent | `application/engine/theme/agents/*.py` | 各类型 Agent 的 `get_opening_beats()` |
| ATG领域模型 | `domain/novel/value_objects/action_transition_graph.py` | `ActionTransitionGraph`, `SceneNode`, `TransitionEdge` |
| DAG 节点 | `application/engine/dag/nodes/planning_nodes.py` | `BeatSheetNode`, `ActPlanningNode` |
| DAG 节点 | `application/engine/dag/nodes/execution_nodes.py` | `WriterNode`, `SceneNode` |
| DAG 节点 | `application/engine/dag/nodes/planning_chapter_outline_node.py` | `ChapterOutlineNode` |
| CPMS 节点 | `infrastructure/ai/prompt_packages/nodes/*/package.yaml` | 各提示词包的元数据与模板 |
| 前端 | `frontend/src/api/workflow.ts` | `consumeGenerateChapterStream()` |
| 前端 | `frontend/src/components/autopilot/ChapterWriterStream.vue` | 流式正文渲染组件 |
