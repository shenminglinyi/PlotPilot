# PR3: 输入治理（Plan → Compose → Write）

## 解决的问题

现在PlotPilot的写作流程是"直接写"——AI拿到一个模糊指令就开始创作，结果容易跑偏、容易忘记重要设定、容易踩雷。

## 解决方案

在写作前增加两步"输入治理"，让AI"带着明确意图和受限规则"来写：

```
plan（规划）→ compose（编排）→ write（写作）
     ↓            ↓            ↓
生成意图文档   编译上下文和规则  基于治理后的输入写作
```

## 文件结构

```
enhancement/
├── planner.py              # 规划器（生成chapter-XXXX.intent.md）
├── composer.py             # 编排器（编译context.json + rule-stack.yaml）
├── intent_doc.py           # 意图文档结构
├── context_compiler.py     # 上下文编译
├── rule_stack.py           # 规则栈管理
└── __init__.py
```

## 核心流程

### Step 1: Plan（规划）

输入：书籍ID + 当前指令（如"本章重点写师徒矛盾"）
输出：`story/runtime/chapter-XXXX.intent.md`

```markdown
# Chapter 5 Intent

## 本章必须达成（Must-Keep）
- 师徒矛盾升级（师父发现徒弟偷学禁术）
- 主角陷入两难（遵命还是反抗）
- 埋下下一章冲突的种子

## 本章必须避免（Must-Avoid）
- 不要让师父直接出手惩罚（太早）
- 不要让主角立刻做出选择（需要犹豫）
- 不要有其他势力介入（专注师徒线）

## 本章情感基调
- 压抑、紧张
- 师徒对话要有火药味但不失尊重

## 冲突处理原则
- 如果与已有设定冲突，优先保留下面的新设定
- 如果与前章矛盾，标记出来等人工确认

## 章节字数目标
- 目标：14,000字
- 允许区间：12,600~15,400字
```

### Step 2: Compose（编排）

输入：`chapter-XXXX.intent.md` + 当前真相文件
输出：
- `chapter-XXXX.context.json` — 本章选入的上下文片段
- `chapter-XXXX.rule-stack.yaml` — 规则优先级层叠

```python
# context.json 示例
{
  "chapter": 5,
  "relevant_facts": [
    {
      "type": "character",
      "content": "主角林烬：筑基后期，已偷学禁术3天"
    },
    {
      "type": "relationship", 
      "content": "与师父云清子的关系：敬畏但有裂痕"
    },
    {
      "type": "pending_hook",
      "content": "禁术副作用会在第7章显现（伏笔#12）"
    }
  ],
  "context_sources": [
    "truth_files/current_state.md",
    "truth_files/character_matrix.md",
    "truth_files/pending_hooks.md"
  ]
}
```

### Step 3: Write（写作）

输入：`intent.md` + `context.json` + `rule-stack.yaml`
输出：章节正文

## 使用方式

```python
from planner import ChapterPlanner
from composer import ContextComposer

planner = ChapterPlanner()
composer = ContextComposer()

# Step 1: 规划
intent = planner.plan(
    book_id="吞天魔帝",
    chapter_num=5,
    context="本章重点写师徒矛盾"
)

# Step 2: 编排
compiled = composer.compile(
    intent=intent,
    truth_files_dir="story/truth_files/"
)

# Step 3: 写作（由外部LLM执行，这里只生成Prompt）
writing_prompt = compiled.generate_prompt()
```

## 规则栈优先级

```
layer 1（最高）: 本章意图（chapter-XXXX.intent.md）
layer 2: 书籍规则（book_rules.md）
layer 3: 题材规则（genre_rules.md）
layer 4: 通用规则（common.md）
```

高优先级规则可以覆盖低优先级规则。例如题材规则说"不要写感情戏"，但本章意图说"加入一段感情戏"，则以本章意图为准。

## 与PlotPilot的集成

```
原流程：写章节 → 审计
新流程：规划 → 编排 → 写章节 → 审计 → 修订
```

规划（plan）和编排（compose）不依赖在线LLM，可以离线运行，验证控制输入是否合理后再消耗API调用来写作。
