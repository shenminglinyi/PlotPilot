# 防 AI 味指令穿透诊断与工程化治理指南

> **版本**: v1.0  
> **日期**: 2026-05-09  
> **定位**: AI 架构师 + 专业小说家双视角  
> **适用范围**: PlotPilot / aitext 全栈生成管线  
> **前置依赖**: `prompts_defaults.json` / `cliche_scanner.py` / `context_budget_allocator.py` / `autopilot_daemon.py`

---

## 目录

1. [核心问题：指令穿透的底层机制](#1-核心问题指令穿透的底层机制)
2. [指令穿透失效频率热力图](#2-指令穿透失效频率热力图)
3. [七层纵深防御架构](#3-七层纵深防御架构)
4. [Layer 1: 正向行为映射（Positive Framing）](#4-layer-1-正向行为映射positive-framing)
5. [Layer 2: 结构化机器可读规则（YAML Protocol）](#5-layer-2-结构化机器可读规则yaml-protocol)
6. [Layer 3: Token 级硬拦截（Logit Bias + AC 自动机）](#6-layer-3-token-级硬拦截logit-bias--ac-自动机)
7. [Layer 4: 生成后流式扫描与实时回滚](#7-layer-4-生成后流式扫描与实时回滚)
8. [Layer 5: 角色状态向量注入（State Management）](#8-layer-5-角色状态向量注入state-management)
9. [Layer 6: 文风指纹闭环（Voice Fingerprint）](#9-layer-6-文风指纹闭环voice-fingerprint)
10. [Layer 7: 章后审计双刀（OOC + AI 味）](#10-layer-7-章后审计双刀ooc--ai-味)
11. [提示词重构工程](#11-提示词重构工程)
12. [系统架构集成设计](#12-系统架构集成设计)
13. [附录：禁用词库与规则清单](#13-附录禁用词库与规则清单)
14. [工程落地优先级与实施路线图](#14-工程落地优先级与实施路线图)
15. [进阶专题：长上下文生成中的指令穿透专项治理](#15-进阶专题长上下文生成中的指令穿透专项治理)
16. [跨模型适配指南](#16-跨模型适配指南)
17. [总结与核心洞察](#17-总结与核心洞察)
18. [架构综合评估与优化策略](#18-架构综合评估与优化策略)

---

## 1. 核心问题：指令穿透的底层机制

### 1.1 否定指令的诅咒（Negative Prompt Curse）

LLM 底层是基于概率的 Token 预测引擎。当 System Prompt 中大量堆砌"严禁""禁止""不要"时：

```
注意力权重分布：
┌────────────────────────────────────────────────┐
│  "严禁生理性泪水" → 激活 [生理性][泪水] Token  │
│  "不要用比喻"     → 激活 [仿佛][宛如][犹如]    │
│  "禁止破折号"     → 激活 [——] Token            │
└────────────────────────────────────────────────┘
```

**根因**：在 Transformer 的 Self-Attention 机制中，被禁止的 Token 作为输入序列的一部分参与了 QKV 计算。即使最终输出被约束抑制，其在深层网络中的激活模式已被"预热"，在长上下文生成的后段极易突破防线。

**量化表现**：
- 短上下文（< 4K tokens）：遵循率约 85-92%
- 中上下文（4K-16K tokens）：遵循率下降至 60-75%
- 长上下文（> 16K tokens）：遵循率骤降至 35-50%
- 超长生成（> 4000 输出 tokens）：尾段遵循率不足 30%

### 1.2 抽象约束与具象生成的冲突

当前规则集中大量指令属于"抽象约束"：

| 抽象约束 | 模型理解难度 | 执行边界 |
|----------|-------------|---------|
| "少写扁平化" | ★★★★★ | 完全模糊 |
| "人物要有血有肉" | ★★★★ | 模糊 |
| "禁止用微表情" | ★★★ | 部分可执行 |
| "禁止用'一丝'" | ★ | 精确可执行 |

**核心矛盾**：模型需要的是 `condition → action` 的确定性映射，而非文学性的祈使句。

### 1.3 注意力稀释（Attention Dilution）

当规则集超过 2000 tokens 时，关键约束的注意力权重被稀释：

```
Token Budget 35000 的注意力分配：
┌─────────────────────────────┬───────┐
│ 系统 Prompt + 规则集         │  8%   │  ← 规则越密，单条权重越低
│ 大纲 & 上下文                │ 35%   │
│ 前情/Bible/设定              │ 25%   │
│ 最近章节                     │ 20%   │
│ 角色锚点 & 伏笔              │ 12%   │
└─────────────────────────────┴───────┘
```

---

## 2. 指令穿透失效频率热力图

基于当前规则集在 PlotPilot 管线中的实际表现，按失效频率从高到低排列：

### 2.1 失效频率分级

| 频率等级 | 规则类别 | 失效率 | 典型表现 | 根因分析 |
|---------|---------|--------|---------|---------|
| 🔴 P0 极高 | 比喻禁令（"仿佛""宛如"） | 65-80% | 生成 3000 字后必现比喻 | 否定指令激活 + 比喻是模型默认修辞策略 |
| 🔴 P0 极高 | 情绪降级（"不能大哭大闹"） | 55-70% | 冲突场景仍写出"撕心裂肺" | 模型训练数据中高烈度情绪关联极强 |
| 🔴 P0 极高 | 微表情禁令（"嘴角上扬""眼里闪过"） | 50-65% | 几乎每个情绪场景必现 | 这类表达是模型"情绪→外在表现"最高概率路径 |
| 🟠 P1 高 | "不是…而是…"句式 | 40-55% | 解释性段落频繁出现 | 模型倾向先否定再肯定的双重确认模式 |
| 🟠 P1 高 | 破折号禁令 | 35-50% | 对话中频繁出现"——" | 破折号是模型表示停顿/转折的默认标点 |
| 🟠 P1 高 | 角色全理性/机器人感 | 40-60% | 高智商角色变成"分析机器" | 模型将"聪明"映射为"逻辑化表达" |
| 🟡 P2 中 | 台词口吻区分度 | 30-45% | 不同角色说话方式雷同 | 缺乏具体的口吻参数注入 |
| 🟡 P2 中 | 情绪连贯性（跨节拍） | 25-40% | 节拍间情绪突然重置 | 节拍独立生成，上下文窗口未包含前节拍尾部 |
| 🟡 P2 中 | 角色专属紧张习惯 | 20-35% | 所有人紧张时都"攥拳" | `verbal_tic`/`idle_behavior` 锚点在长上下文中被遗忘 |
| 🟢 P3 低 | 数字比喻（"三分讥笑"） | 10-20% | 偶尔出现 | 训练数据中此类表达较少 |
| 🟢 P3 低 | 戏剧化过度（突然晕倒） | 10-15% | 罕见 | 非主流模式 |
| 🟢 P3 低 | 生理性液体 | 5-10% | 极少出现 | 已被现有 ClicheScanner 部分覆盖 |

### 2.2 失效的时间分布

```
生成位置 vs 遵循率
遵循率%
100 │████████
 90 │███████
 80 │██████
 70 │█████
 60 │████
 50 │███
 40 │██
 30 │█
 20 │
    └────────────────────────────────→
    开头   1/4    1/2    3/4    结尾
           ↑                ↑
        注意力峰值      注意力衰减区（指令穿透高发）
```

**关键发现**：
1. 生成的后 1/3 是指令穿透的高发区
2. 多轮对话/多节拍连续生成时，穿透率逐轮递增
3. 当上下文窗口接近极限时，规则集被挤出注意力核心区

---

## 3. 七层纵深防御架构

```
                    ┌─────────────────────────┐
                    │   Layer 7: 章后审计双刀   │  ← OOC + AI味双刀检测
                    │   (Chapter Aftermath)    │
                    ├─────────────────────────┤
                    │   Layer 6: 文风指纹闭环   │  ← 采血→指纹→抗体
                    │   (Voice Fingerprint)    │
                    ├─────────────────────────┤
                    │   Layer 5: 角色状态向量   │  ← 强制前置条件
                    │   (State Injection)      │
                    ├─────────────────────────┤
                    │   Layer 4: 流式扫描回滚   │  ← 实时拦截
                    │   (Stream Scanner)       │
                    ├─────────────────────────┤
                    │   Layer 3: Token硬拦截    │  ← Logit Bias + AC自动机
                    │   (Token Guard)          │
                    ├─────────────────────────┤
                    │   Layer 2: 结构化规则      │  ← YAML Protocol
                    │   (Machine Rules)        │
                    ├─────────────────────────┤
                    │   Layer 1: 正向行为映射   │  ← Positive Framing
                    │   (Positive Framing)     │
                    └─────────────────────────┘
```

**设计哲学**：不依赖任何单一防线，每层只负责自己最擅长的维度。

---

## 4. Layer 1: 正向行为映射（Positive Framing）

### 4.1 核心原则

将"禁止 X"重构为"当遇到场景 Y 时，必须执行 Z"。

### 4.2 转换规则库

```python
# application/engine/rules/positive_framing_rules.py

POSITIVE_FRAMING_MAP = {
    # ─── 情绪表达 ───
    "禁止直接陈述情绪": {
        "condition": "角色情绪波动时",
        "action": "必须通过以下方式之一映射：① 对周遭物体的物理作用力改变 ② 语速/停顿的改变 ③ 体温/触感变化 ④ 对话内容的偏移",
        "examples": [
            "❌ '他感到非常愤怒'",
            "✅ '他端起杯子，又放下了。指节磕在桌面上，声音比他想的要响。'",
            "❌ '她心中一阵悲伤'",
            "✅ '她低头看手背。有一滴水落在上面，她愣了一下才反应过来。'",
        ]
    },
    "禁止微表情标签": {
        "condition": "需要展现角色内在状态时",
        "action": "写完整动作链而非面部快照。将'嘴角上扬'替换为整个人的姿态变化，或干脆不写，让对白本身传递情绪",
        "examples": [
            "❌ '嘴角勾起一丝冷笑'",
            "✅ '他往后靠了靠，把手插进口袋。'",
            "❌ '眼里闪过一丝怒意'",
            "✅ '她没说话，把菜单翻到了最后一页。'",
        ]
    },
    "情绪降级": {
        "condition": "角色面对负面事件时",
        "action": "强制执行至少一档的行为降级：大哭→沉默、崩溃→转移话题、暴怒→说话变慢变清楚",
        "examples": [
            "❌ '她崩溃地大哭起来'",
            "✅ '她笑了一下，然后低头系鞋带。系了两次才系好。'",
            "❌ '他愤怒地拍桌而起'",
            "✅ '他说话变得很慢，每个字都咬得很清楚。'",
        ]
    },
    
    # ─── 句式替换 ───
    "禁止不是而是句式": {
        "condition": "需要对比或转折时",
        "action": "转为直接叙述、因果句或递进句",
        "examples": [
            "❌ '他不是在害怕，而是在等待'",
            "✅ '他在等。手指按在桌面，一下，又一下。'",
            "❌ '这不是勇气，只是无知'",
            "✅ '他不知道那意味着什么，所以没停。'",
        ]
    },
    "禁止破折号转折": {
        "condition": "需要语义转折或停顿时（正文中）",
        "action": "用句号断句，或用动作/环境描写代替转折。仅在对话中表示尾音拖长时可用",
        "examples": [
            "❌ '他向前一步——又停住了'",
            "✅ '他向前一步。又停住了。'",
            "❌ '答案只有一个——死'",
            "✅ '答案只有一个。死。'",
        ]
    },
    
    # ─── 比喻替换 ───
    "禁止比喻": {
        "condition": "需要修辞增强时",
        "action": "用感官细节替代：体温、光线角度、衣料触感、具体距离、材质描述",
        "examples": [
            "❌ '宛如阳光般温暖'",
            "✅ '她碰到他的手背。那片皮肤是热的。'",
            "❌ '声音像刀子一样'",
            "✅ '她一字一字说的，每个字之间都留了空。'",
        ]
    },
    
    # ─── 角色塑造 ───
    "禁止全理性机器人": {
        "condition": "高智商/冷静角色思考问题时",
        "action": "思维必须包含直觉跳跃、经验碎片、犹豫或灵光一闪。禁止写成'首先…其次…最后…综合以上'",
        "examples": [
            "❌ '他分析变量1、变量2，得出结论：成功率73%'",
            "✅ '他总觉得哪里不对。想了两秒，突然明白了。'",
            "❌ '在0.3秒内分析完局势'",
            "✅ '他停了一下。那个停顿比回答本身更说明问题。'",
        ]
    },
    "禁止统一情绪模板": {
        "condition": "不同角色面对相同事件时",
        "action": "反应必须贴着角色本人来写——会用刀的人先摸刀，读书人先考虑逃跑，嘴硬的人说反话",
        "examples": [
            "❌ '所有人都震惊地看着他'",
            "✅ '赵四的手下意识摸向腰间。小六往后退了半步。只有老陈没动，但他把茶杯放下了。'",
        ]
    },
}
```

### 4.3 Prompt 注入模板

在 `prompts_defaults.json` 的 `chapter-generation-main` 中，将规则集从"禁令清单"重构为"行为协议"：

```python
def build_positive_framing_block(rules: dict) -> str:
    """将正向行为映射规则组装为 Prompt 片段"""
    parts = ["【行为协议 — 当你遇到以下场景时，必须执行对应动作】\n"]
    for rule_name, rule in rules.items():
        parts.append(f"场景：{rule['condition']}")
        parts.append(f"动作：{rule['action']}")
        # 只注入1个示例（节省 Token），正反各一行
        if rule.get('examples'):
            parts.append(f"  {rule['examples'][0]}")
            parts.append(f"  {rule['examples'][1]}")
        parts.append("")
    return "\n".join(parts)
```

---

## 5. Layer 2: 结构化机器可读规则（YAML Protocol）

### 5.1 设计原则

将文学诉求转化为去拟人化的机器执行规则，提升模型的指令遵循率。

### 5.2 规则定义

```yaml
# application/engine/rules/anti_ai_protocol.yaml

Output_Protocol: "Show, Don't Tell"

Execution_Rules:
  - rule: "感官隔离"
    id: "SENSE_ISOLATE"
    condition: "涉及情绪波动与心理活动时"
    action: "阻断情绪词汇输出。强制调用[环境物理交互]、[肢体不协调动作]或[台词停顿]进行映射。"
    severity: "critical"
    check: "扫描输出是否包含直接情绪标签（愤怒/悲伤/恐惧/厌恶/惊讶/喜悦作为形容词修饰角色）"
    
  - rule: "去全知视角"
    id: "POV_GUARD"
    condition: "角色应对突发事件时"
    action: "输出反应必须受限于角色的[即时体能]与[专业认知]。允许生成误判、动作变形或短暂的信息处理延迟。"
    severity: "critical"
    check: "扫描POV角色是否感知到其视角不可能获取的信息"
    
  - rule: "非标准衰减"
    id: "EMOTION_DECAY"
    condition: "激烈冲突结束后的场景过渡"
    action: "保留前序事件的物理或心理残余（如：持续的肌肉应激、对特定声音的过敏）。禁止状态瞬间归零。"
    severity: "warning"
    check: "对比相邻段落的情绪烈度差，差值>2级则标记"
    
  - rule: "反比喻强制"
    id: "NO_METAPHOR"
    condition: "任何修辞增强需求时"
    action: "禁止使用X像Y、X仿佛Y、X犹如Y结构。替换为[具体距离/温度/材质/光线]描写。"
    severity: "critical"
    check: "正则匹配比喻句式"
    
  - rule: "反八股句式"
    id: "NO_CLICHE_SYNTAX"
    condition: "任何解释/转折场景"
    action: "禁止'不是A而是B'结构。禁止连续3个以上破折号。替换为直接叙述/因果句/递进句。"
    severity: "warning"
    check: "正则匹配句式模式"
    
  - rule: "差异化反应"
    id: "CHAR_DIFF"
    condition: "多角色在场时"
    action: "至少2个角色的反应方式不同。禁止'所有人都XX'的统一模板。"
    severity: "warning"
    check: "统计同一场景中角色反应的词汇重合度"

Constraint_Overrides:
  - "禁止生成完美逻辑链，思维过程需包含直觉跳跃与验证空白。"
  - "禁止情绪表现直接匹配事件烈度，强制执行至少一档的行为降级。"
  - "禁止连续2段使用同一身体部位表达情绪。"
  - "禁止角色出场3次后仍无口头禅或习惯动作。"

Severity_Levels:
  critical: "必须阻断，生成后若检测到必须重写"
  warning: "应当避免，检测到后标记但不强制重写"
  info: "建议优化，仅做记录"
```

### 5.3 场景化白名单机制（Allowlist Exception）

> **⚠️ 架构评估结论**：极其严格的比喻禁令和破折号禁令可能导致文本走向干瘪的说明文风格。部分高级的通感比喻是文学张力的重要来源，一刀切的硬拦截会扼杀文本的灵气（详见 [18.2.4 文学死角](#1824-文学死角过度去修辞化风险)）。本节建立基于场景的白名单机制，在特定叙事节点临时挂起部分规则。

#### 5.3.1 白名单设计原则

1. **场景触发**：白名单不是全局豁免，而是在特定叙事场景下自动激活
2. **规则悬停而非删除**：被挂起的规则在场景结束后自动恢复
3. **窄窗口**：白名单的作用范围严格限定在触发场景内
4. **可审计**：每次白名单触发都记录在章后审计结果中

#### 5.3.2 场景化白名单定义

```yaml
# application/engine/rules/anti_ai_allowlist.yaml

Allowlist_Exceptions:
  
  # ─── 梦境/幻觉场景 ───
  - id: "DREAM_SEQUENCE"
    trigger:
      scene_type: ["梦境", "幻觉", "闪回", "意识流"]
      detection: "大纲中标记为 dream/hallucination/flashback 的节拍"
    suspended_rules:
      - "B3"    # 比喻句式 — 梦境中比喻是核心叙事手段
      - "B6"    # 破折号 — 意识流需要长停顿
      - "B7"    # 动物比喻 — 梦境象征允许
    extra_instruction: |
      梦境/幻觉中：允许使用比喻和意识流手法。
      但比喻必须服务于梦境的象征逻辑，不可使用俗套意象（心湖/涟漪/藤蔓等仍然禁止）。
    still_forbidden:
      - "投入心湖"
      - "泛起涟漪"
      - "像小兔子/小鹿/小兽"
  
  # ─── 精神极端状态 ───
  - id: "EXTREME_MENTAL_STATE"
    trigger:
      character_state: ["精神崩溃", "极度恐惧", "濒死体验", "高烧谵妄"]
      detection: "角色状态向量中 physical_condition 或 current_emotion 匹配"
    suspended_rules:
      - "B3"    # 比喻 — 极端精神状态下比喻是必要的表达
      - "B1"    # 情绪标签 — 极端状态可以直接命名（如"他疯了"）
    extra_instruction: |
      角色处于精神极端状态：允许直接表达和比喻。
      但比喻必须体现主观扭曲感，不可使用客观化的陈旧意象。
    still_forbidden:
      - "嘴角上扬/眼里闪过"  # 微表情在极端状态下仍然不合适
      - "不是…而是…"          # 理性句式与极端状态矛盾
  
  # ─── 高维/超自然现象描述 ───
  - id: "SUPERNATURAL_DESCRIPTION"
    trigger:
      content_type: ["超自然现象", "高维空间", "无法解释的事件"]
      detection: "大纲中标记为 supernatural/otherworldly 的节拍"
    suspended_rules:
      - "B3"    # 比喻 — 超自然现象只能用比喻来描述
      - "B6"    # 破折号 — 超自然现象的断裂感需要破折号
    extra_instruction: |
      描述超自然/高维现象：比喻是唯一的表达手段。
      但比喻必须创造新意象，禁止使用已知的AI俗套意象。
    still_forbidden:
      - "心湖/涟漪/藤蔓"     # 这些仍然是俗套
      - "像小兔子/小鹿"       # 动物比喻仍然禁止
  
  # ─── 文学性独白/内心戏 ───
  - id: "LITERARY_MONOLOGUE"
    trigger:
      narrative_mode: ["第一人称独白", "内心戏", "意识独白"]
      detection: "大纲中标记为 monologue/inner_voice 的节拍"
    suspended_rules:
      - "B3"    # 比喻 — 独白中通感比喻是文学性的来源
      - "B5"    # 不是…而是 — 独白允许自我否定的思维过程
    extra_instruction: |
      文学性独白中：允许使用通感比喻和思维转折。
      但必须体现角色的个人视角和语言习惯，不可使用通用化表达。
    still_forbidden:
      - "微表情标签"          # 独白中不会观察自己的微表情
      - "声线描述"            # 独白中没有声线
```

#### 5.3.3 白名单运行时解析

```python
# application/engine/rules/allowlist_manager.py

import yaml
from typing import List, Set, Optional
from dataclasses import dataclass
from enum import Enum

class SceneType(Enum):
    DREAM = "dream"
    HALLUCINATION = "hallucination"
    FLASHBACK = "flashback"
    MONOLOGUE = "monologue"
    SUPERNATURAL = "supernatural"
    NORMAL = "normal"

@dataclass
class AllowlistContext:
    """白名单上下文 — 当前生成场景的白名单状态"""
    active_exceptions: List[str]        # 激活的白名单ID
    suspended_rules: Set[str]           # 被挂起的规则ID
    still_forbidden: Set[str]           # 仍然禁止的模式
    extra_instructions: List[str]       # 额外指令

class AllowlistManager:
    """场景化白名单管理器"""
    
    def __init__(self, yaml_path: str):
        with open(yaml_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        self.exceptions = self.config.get("Allowlist_Exceptions", [])
    
    def evaluate_context(
        self,
        scene_type: SceneType,
        beat_description: str,
        character_states: dict,
    ) -> AllowlistContext:
        """评估当前场景的白名单状态
        
        Args:
            scene_type: 场景类型
            beat_description: 节拍描述
            character_states: 角色状态向量字典
        """
        active = []
        suspended = set()
        still_forbidden = set()
        extra = []
        
        for exc in self.exceptions:
            if self._should_activate(exc, scene_type, beat_description, character_states):
                active.append(exc["id"])
                for rule in exc.get("suspended_rules", []):
                    suspended.add(rule)
                for pattern in exc.get("still_forbidden", []):
                    still_forbidden.add(pattern)
                if exc.get("extra_instruction"):
                    extra.append(exc["extra_instruction"])
        
        return AllowlistContext(
            active_exceptions=active,
            suspended_rules=suspended,
            still_forbidden=still_forbidden,
            extra_instructions=extra,
        )
    
    def _should_activate(self, exception: dict, scene_type, beat_desc, char_states) -> bool:
        """判断白名单是否应该激活"""
        trigger = exception.get("trigger", {})
        
        # 场景类型匹配
        scene_types = trigger.get("scene_type", [])
        if scene_type.value in [s.lower() for s in scene_types]:
            return True
        
        # 角色状态匹配
        char_conditions = trigger.get("character_state", [])
        for state in char_states.values():
            if any(cond in str(state) for cond in char_conditions):
                return True
        
        return False
    
    def get_modified_protocol(self, base_protocol: str, context: AllowlistContext) -> str:
        """根据白名单上下文修改行为协议
        
        在协议中标注哪些规则被临时挂起，并添加额外指令
        """
        if not context.active_exceptions:
            return base_protocol
        
        # 标注挂起的规则
        modifications = []
        for rule_id in context.suspended_rules:
            modifications.append(f"⚠ 规则 {rule_id} 在当前场景中临时挂起")
        
        # 添加额外指令
        for instruction in context.extra_instructions:
            modifications.append(f"\n{instruction}")
        
        # 在协议末尾追加
        suffix = "\n\n【场景化豁免 · 当前激活】\n" + "\n".join(modifications)
        return base_protocol + suffix
```

#### 5.3.4 与 AC 自动机和 ClicheScanner 的集成

```python
# 在 StreamACScanner.scan_chunk() 中集成白名单

class StreamACScanner:
    
    def __init__(self, allowlist_manager: Optional[AllowlistManager] = None):
        self._allowlist = allowlist_manager
        # ... 原有初始化 ...
    
    def scan_chunk(
        self,
        chunk: str,
        position_offset: int = 0,
        allowlist_context: Optional[AllowlistContext] = None,
    ) -> List[StreamViolation]:
        """扫描流式 chunk — 支持白名单豁免"""
        violations = []
        
        # AC 自动机精确匹配
        for end_pos, (word, meta) in self._automaton.iter(chunk):
            # 白名单检查：如果该违规模式仍在禁止列表中，才记录
            if allowlist_context and word in allowlist_context.still_forbidden:
                # 仍然禁止 → 记录违规
                pass
            elif allowlist_context and self._is_rule_suspended(word, allowlist_context):
                # 规则被挂起 → 跳过
                continue
            
            start_pos = end_pos - len(word) + 1
            violations.append(StreamViolation(
                pattern=word,
                position=start_pos + position_offset,
                severity=meta["severity"],
                replacement_hint=meta["hint"],
            ))
        
        # 正则模式匹配（同样需要白名单过滤）
        for pattern, name, severity in self._regex_patterns:
            rule_id = self._pattern_to_rule_id(name)
            if allowlist_context and rule_id in allowlist_context.suspended_rules:
                continue  # 规则被挂起，跳过
            
            for match in pattern.finditer(chunk):
                violations.append(StreamViolation(
                    pattern=f"{name}: {match.group()}",
                    position=match.start() + position_offset,
                    severity=severity,
                    replacement_hint="参见行为协议",
                ))
        
        return violations
    
    def _is_rule_suspended(self, word: str, context: AllowlistContext) -> bool:
        """检查该违规词汇对应的规则是否被白名单挂起"""
        # 词汇到规则ID的映射
        WORD_TO_RULE = {
            "嘴角上扬": "B2", "眼里闪过": "B2", "指尖泛白": "B2",
            "仿佛": "B3", "宛如": "B3", "犹如": "B3",
            "——": "B6",
            "像小兔子": "B7", "像小鹿": "B7", "像小兽": "B7",
        }
        rule_id = WORD_TO_RULE.get(word)
        return rule_id in context.suspended_rules if rule_id else False
```

### 5.4 运行时解析与注入

```python
# application/engine/rules/rule_parser.py

import yaml
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class ExecutionRule:
    rule_id: str
    name: str
    condition: str
    action: str
    severity: str  # "critical" | "warning" | "info"
    check: str

class AntiAIRuleParser:
    """将 YAML 规则解析为运行时可执行的结构"""
    
    def __init__(self, yaml_path: str):
        with open(yaml_path, 'r', encoding='utf-8') as f:
            self.protocol = yaml.safe_load(f)
        self.rules: List[ExecutionRule] = []
        self._parse_rules()
    
    def _parse_rules(self):
        for r in self.protocol.get("Execution_Rules", []):
            self.rules.append(ExecutionRule(
                rule_id=r["id"],
                name=r["rule"],
                condition=r["condition"],
                action=r["action"],
                severity=r["severity"],
                check=r.get("check", ""),
            ))
    
    def build_prompt_block(self, severity_filter: str = "critical") -> str:
        """生成可注入 Prompt 的规则文本块
        
        关键：只注入 critical 级别规则到 Prompt，
        warning 级别规则仅用于生成后检测
        """
        filtered = [r for r in self.rules if r.severity == severity_filter]
        parts = [f"[执行协议 · {severity_filter} 级]\n"]
        for r in filtered:
            parts.append(f"当 {r.condition}：")
            parts.append(f"  → {r.action}")
            parts.append("")
        return "\n".join(parts)
    
    def get_post_check_rules(self) -> List[ExecutionRule]:
        """获取用于生成后检查的规则"""
        return self.rules
```

---

## 6. Layer 3: Token 级硬拦截（Logit Bias + AC 自动机）

### 6.1 为什么需要 Token 级拦截

Prompt 层的规则遵循率有限（尤其长上下文），必须从推理侧进行硬拦截。

### 6.2 Logit Bias 方案

```python
# application/engine/services/token_guard.py

import tiktoken
from typing import Dict, List, Set, Tuple

class TokenGuard:
    """Token 级硬拦截 — 基于 Logit Bias 和 AC 自动机的双重防御"""
    
    # 绝对禁用词汇（中文需特殊处理）
    ABSOLUTE_FORBIDDEN_PHRASES = [
        # 微表情/微动作系列
        "一丝", "不易察觉", "嘴角上扬", "眼里闪过", "指尖泛白",
        # 生理性系列
        "生理性", "生理性泪水", "生理性水",
        # 声线描述系列
        "不容置疑", "不容置喙",
        # 小动物比喻
        "像小兔子", "像小鹿", "像小猫", "像小兽",
        # 经典 AI 比喻意象
        "投入心湖", "泛起涟漪", "荡起涟漪",
        # 语气前缀
        "带着不容置疑的语气", "声音比寒冰更冰冷",
    ]
    
    # 句式模式（需要 AC 自动机匹配）
    FORBIDDEN_PATTERNS = [
        # 不是…而是… 句式
        r"不是[^。，？！]{1,20}而是",
        r"不是[^。，？！]{1,20}只是",
        # 比喻句式
        r"[^，。]像[^，。]{1,10}一样",
        r"仿佛[^，。]{1,10}般",
        r"宛如[^，。]{1,10}般",
        r"如同[^，。]{1,10}一般",
        # 数字比喻
        r"[三四五六七八九]分[^，。]{1,6}[七八九]分",
    ]
    
    def __init__(self, model_name: str = "gpt-4"):
        self.model_name = model_name
        self._encoder = None
        self._logit_bias_cache: Dict[str, Dict[str, int]] = {}
        
    def _get_encoder(self):
        """延迟加载 tokenizer"""
        if self._encoder is None:
            try:
                self._encoder = tiktoken.encoding_for_model(self.model_name)
            except KeyError:
                self._encoder = tiktoken.get_encoding("cl100k_base")
        return self._encoder
    
    def build_logit_bias(self, bias_value: int = -100) -> Dict[str, int]:
        """构建 Logit Bias 映射
        
        Args:
            bias_value: 偏置值，-100 表示几乎完全禁止
            
        Returns:
            Dict[token_id_str, bias_value] 用于 API 调用
            
        Note:
            中文 token 化较复杂，一个词可能被拆分为多个 token。
            此处对每个词的所有可能 token 分片施加 bias。
        """
        encoder = self._get_encoder()
        bias_map = {}
        
        for phrase in self.ABSOLUTE_FORBIDDEN_PHRASES:
            try:
                token_ids = encoder.encode(phrase)
                for tid in token_ids:
                    bias_map[str(tid)] = bias_value
            except Exception:
                # 中文编码可能失败，记录后跳过
                continue
        
        return bias_map
    
    def get_api_params(self) -> Dict:
        """获取可注入 API 调用的参数"""
        return {
            "logit_bias": self.build_logit_bias(),
            "frequency_penalty": 0.3,  # 轻度惩罚重复
            "presence_penalty": 0.1,   # 鼓励多样性
        }
```

### 6.3 AC 自动机流式扫描

```python
# application/engine/services/stream_ac_scanner.py

from typing import List, Dict, Callable, Optional
from dataclasses import dataclass
import re
import ahocorasick  # pyahocorasick

@dataclass
class StreamViolation:
    """流式扫描违规记录"""
    pattern: str
    position: int      # 在完整文本中的位置
    severity: str      # "critical" | "warning"
    replacement_hint: str  # 替换建议

class StreamACScanner:
    """基于 AC 自动机的流式输出扫描器
    
    核心优势：O(n) 时间复杂度，支持实时扫描流式 Token。
    当检测到违禁模式时，立即触发回滚重生成。
    """
    
    def __init__(self):
        self._automaton = ahocorasick.Automaton()
        self._pattern_meta: Dict[str, dict] = {}
        self._build_automaton()
    
    def _build_automaton(self):
        """构建 AC 自动机"""
        # 词汇级精确匹配
        word_patterns = {
            # 微表情
            "一丝": {"severity": "warning", "hint": "用具体动作替代"},
            "嘴角上扬": {"severity": "critical", "hint": "写完整姿态变化或不写"},
            "指尖泛白": {"severity": "critical", "hint": "用行为传递紧张"},
            "眼里闪过": {"severity": "critical", "hint": "用对话或动作替代"},
            "不易察觉": {"severity": "warning", "hint": "要么可察觉，要么别写"},
            
            # 生理性
            "生理性": {"severity": "critical", "hint": "直接描述生理反应"},
            "生理性泪水": {"severity": "critical", "hint": "用哭泣的差异化写法"},
            
            # 声线
            "不容置疑": {"severity": "critical", "hint": "用对白本身的力度表现"},
            "不容置喙": {"severity": "critical", "hint": "用对白本身的力度表现"},
            
            # 小动物比喻
            "像小兔子": {"severity": "critical", "hint": "禁止动物比喻，用具体动作"},
            "像小鹿": {"severity": "critical", "hint": "禁止动物比喻，用具体动作"},
            "像小兽": {"severity": "critical", "hint": "禁止动物比喻，用具体动作"},
            
            # 经典意象
            "投入心湖": {"severity": "critical", "hint": "禁止心湖意象"},
            "泛起涟漪": {"severity": "critical", "hint": "禁止涟漪意象"},
            "精致人偶": {"severity": "critical", "hint": "用具体的外貌/姿态描写"},
            
            # 语气标签
            "带着": {"severity": "info", "hint": "检查是否为语气前缀"},
            "口吻": {"severity": "warning", "hint": "用对白本身表现语气"},
        }
        
        for word, meta in word_patterns.items():
            self._automaton.add_word(word, (word, meta))
            self._pattern_meta[word] = meta
        
        self._automaton.make_automaton()
        
        # 正则模式（用于二阶段验证）
        self._regex_patterns = [
            (re.compile(r"不是[^。，？！]{1,20}而是"), "不是…而是…句式", "critical"),
            (re.compile(r"仿佛[^。，]{1,8}般"), "仿佛…般比喻", "critical"),
            (re.compile(r"宛如[^。，]{1,8}般"), "宛如…般比喻", "critical"),
            (re.compile(r"如同[^。，]{1,8}一般"), "如同…一般比喻", "critical"),
            (re.compile(r"——"), "破折号", "warning"),
        ]
    
    def scan_chunk(self, chunk: str, position_offset: int = 0) -> List[StreamViolation]:
        """扫描一个流式 chunk
        
        Args:
            chunk: 流式输出的一小段文本
            position_offset: 在完整文本中的偏移量
            
        Returns:
            检测到的违规列表
        """
        violations = []
        
        # 第一阶段：AC 自动机精确匹配
        for end_pos, (word, meta) in self._automaton.iter(chunk):
            start_pos = end_pos - len(word) + 1
            violations.append(StreamViolation(
                pattern=word,
                position=start_pos + position_offset,
                severity=meta["severity"],
                replacement_hint=meta["hint"],
            ))
        
        # 第二阶段：正则模式匹配
        for pattern, name, severity in self._regex_patterns:
            for match in pattern.finditer(chunk):
                violations.append(StreamViolation(
                    pattern=f"{name}: {match.group()}",
                    position=match.start() + position_offset,
                    severity=severity,
                    replacement_hint="参见行为协议",
                ))
        
        return violations
    
    def should_rollback(self, violations: List[StreamViolation]) -> bool:
        """判断是否需要回滚重生成"""
        critical_count = sum(1 for v in violations if v.severity == "critical")
        return critical_count >= 1  # 任何 critical 违规立即回滚
```

### 6.4 Logit Bias 中文降级策略

> **⚠️ 架构评估结论**：鉴于中文 Token 化的不确定性，Logit Bias 在中文场景下存在高危的"词汇表坍塌"风险（详见 [18.1.3 架构隐患一](#1813-架构隐患一中文-token-碎片化误伤)）。本节提出降级方案，拦截核心全面转移至 AC 自动机和正则后处理。

#### 6.4.1 问题根因分析

中文在 `cl100k_base` 等分词器下，一个词通常被拆分为 2-5 个 Token。对某个子 Token 施加 -100 偏置时：

1. **连带误伤**：该子 Token 可能出现在多个合法词汇中
2. **偏置不可控**：无法精确控制"只禁止词 A 而不禁止包含相同子 Token 的词 B"
3. **后果不可逆**：生成时一旦某个子 Token 被抑制，整句的连贯性可能被破坏

```python
# 误伤实验示例（cl100k_base）
#
# "嘴角上扬" → [Token_嘴, Token_角, Token_上, Token_扬]
# "嘴角抽搐" → [Token_嘴, Token_角, Token_抽, Token_搐]
#
# 若对 Token_嘴 施加 -100 bias：
#   ❌ "嘴角上扬" 被阻止 ✅
#   ❌ "嘴角抽搐" 也被阻止 ❌ (这是合法词汇！)
#   ❌ "嘴硬" "嘴碎" "嘴巴" 都可能受影响 ❌
```

#### 6.4.2 降级方案：仅对安全 Token 施加 Logit Bias

```python
# application/engine/services/token_guard.py — 降级版

class SafeLogitBiasBuilder:
    """安全的 Logit Bias 构建器 — 仅对确认无误伤风险的 Token 施加偏置
    
    策略：
    1. 对短语/句式：完全放弃 Logit Bias，改用 AC 自动机
    2. 对单字/特定专有名词：确认无误伤风险后才施加 -100
    3. 对其他词汇：降级为 -5 ~ -10 的软偏置（降低概率但不禁止）
    """
    
    # ─── 安全集：单字/专有名词，确认无误伤 ───
    SAFE_BIAS_PHRASES = {
        # 这些词在中文中通常是独立的 Token，碎片化风险极低
        # 需要逐个在 tiktoken 中验证 encode() 结果长度为 1
        # 注意：以下列表需根据实际 tokenizer 输出动态校验
    }
    
    # ─── 软偏置集：降级偏置值 ───
    SOFT_BIAS_PHRASES = {
        # 这些词施加 -5 ~ -10 的软偏置，降低概率但不完全禁止
        # 配合 AC 自动机做二次拦截
        "一丝": -10,
        "不易察觉": -8,
        "生理性": -10,
    }
    
    # ─── 放弃集：完全依赖 AC 自动机 ───
    AC_ONLY_PHRASES = [
        # 短语和句式模式完全放弃 Logit Bias，由 AC 自动机 + 正则处理
        "嘴角上扬", "眼里闪过", "指尖泛白",  # 碎片化高危
        "不容置疑", "不容置喙",              # 碎片化高危
        "像小兔子", "像小鹿", "像小兽",      # 碎片化高危
    ]
    
    def build_safe_logit_bias(self) -> Dict[str, int]:
        """构建安全的 Logit Bias 映射
        
        Returns:
            Dict[token_id_str, bias_value] — 仅包含确认安全的偏置
        """
        encoder = self._get_encoder()
        bias_map = {}
        
        # 1. 安全集：施加 -100 硬偏置
        for phrase in self.SAFE_BIAS_PHRASES:
            token_ids = encoder.encode(phrase)
            if len(token_ids) == 1:
                # 单 Token 词，安全
                bias_map[str(token_ids[0])] = -100
            # 多 Token 词 → 跳过，交给 AC 自动机
        
        # 2. 软偏置集：施加 -5 ~ -10 的软偏置
        for phrase, bias_value in self.SOFT_BIAS_PHRASES.items():
            token_ids = encoder.encode(phrase)
            for tid in token_ids:
                existing = bias_map.get(str(tid), 0)
                # 取更严格的偏置值
                bias_map[str(tid)] = min(existing, bias_value)
        
        return bias_map
    
    def get_recommended_strategy(self) -> dict:
        """获取推荐的拦截策略配置"""
        return {
            "logit_bias": self.build_safe_logit_bias(),
            "primary_interception": "ac_automaton",  # 主拦截转至 AC 自动机
            "secondary_interception": "regex_post_process",  # 二次拦截
            "logit_bias_role": "supplementary",  # Logit Bias 降级为辅助角色
            "description": "Logit Bias 仅用于单 Token 安全词的硬偏置 + 软偏置降频，核心拦截由 AC 自动机承担"
        }
```

#### 6.4.3 拦截权重调整总结

| 拦截手段 | 原方案 | 降级后方案 | 覆盖范围 |
|---------|--------|-----------|---------|
| Logit Bias (-100) | 全部禁用词 | 仅单 Token 安全词 | ~5% 的禁用词 |
| Logit Bias (-5~-10) | 不使用 | 软偏置降频 | ~15% 的禁用词 |
| AC 自动机 | 辅助 | **主拦截** | 全部词汇级禁用词 |
| 正则后处理 | 辅助 | **二次拦截** | 全部句式模式 |
| 生成后 ClicheScanner | 最终兜底 | 最终兜底 | 全部模式 |

**核心转变**：拦截重心从"推理侧预防"转向"流式输出扫描"，这虽然增加了回滚频率，但消除了词汇表坍塌风险。配合 [7.3 缓冲队列分块验证策略](#73-缓冲队列分块验证策略chunked-buffer-strategy)，可控制回滚的算力损耗。

### 6.5 与现有管线集成

```python
# 在 auto_novel_generation_workflow.py 中的集成点

class AutoNovelGenerationWorkflow:
    
    def __init__(self, ...):
        # ... 现有初始化 ...
        self._token_guard = TokenGuard()
        self._stream_scanner = StreamACScanner()
    
    async def _stream_generate_with_guard(self, prompt, config):
        """带 Token 级防护的流式生成"""
        
        # 1. 注入 Logit Bias
        guard_params = self._token_guard.get_api_params()
        config.logit_bias = guard_params.get("logit_bias", {})
        config.frequency_penalty = guard_params.get("frequency_penalty", 0.3)
        config.presence_penalty = guard_params.get("presence_penalty", 0.1)
        
        # 2. 流式生成 + 实时扫描
        full_text = ""
        all_violations = []
        rollback_count = 0
        MAX_ROLLBACK = 2  # 最多回滚 2 次
        
        async for chunk in self.llm_service.stream_generate(prompt, config):
            full_text += chunk
            
            # 每 100 字扫描一次
            if len(full_text) % 100 < len(chunk):
                violations = self._stream_scanner.scan_chunk(
                    chunk, position_offset=len(full_text) - len(chunk)
                )
                all_violations.extend(violations)
                
                if self._stream_scanner.should_rollback(violations) and rollback_count < MAX_ROLLBACK:
                    # 回滚：截断到违规点之前，重新生成
                    rollback_point = min(v.position for v in violations if v.severity == "critical")
                    full_text = full_text[:rollback_point]
                    rollback_count += 1
                    
                    # 注入修正约束后重生成
                    violation_hints = "; ".join(set(
                        f"避免'{v.pattern}'" for v in violations if v.severity == "critical"
                    ))
                    # ... 触发重新生成 ...
        
        return full_text, all_violations
```

---

## 7. Layer 4: 生成后流式扫描与实时回滚

### 7.1 增强版 ClicheScanner

当前 `cliche_scanner.py` 只有 10 个模式，需要大幅扩充并与用户提供的禁用词库对齐。

```python
# application/audit/services/enhanced_cliche_scanner.py

import re
from dataclasses import dataclass, field
from typing import List, Tuple

@dataclass
class ClicheHit:
    """俗套句式命中结果（增强版）"""
    pattern: str
    text: str
    start: int
    end: int
    severity: str = "warning"  # "critical" | "warning" | "info"
    category: str = ""         # 新增：分类标签
    replacement_hint: str = "" # 新增：替换建议

class EnhancedClicheScanner:
    """增强版俗套扫描器 — 覆盖用户规则集中的全部禁用模式"""
    
    def __init__(self):
        self.patterns: List[Tuple[re.Pattern, str, str, str, str]] = []
        self._compile_patterns()
    
    def _compile_patterns(self):
        """编译全部检测模式
        
        格式：(compiled_regex, pattern_name, severity, category, hint)
        """
        raw_patterns = [
            # ═══ 微表情/微动作 ═══
            (r"嘴角(勾起|上扬|扬起|浮现|翘起)", "嘴角微表情", "critical", "微表情", "写完整姿态变化"),
            (r"眼里(闪过|显现出|漾起).{0,6}(光芒|光|星光|温柔)", "眼里闪过", "critical", "微表情", "用对话或动作替代"),
            (r"(指尖|指节)(泛白|发白)", "指尖泛白", "critical", "微表情", "用行为传递紧张感"),
            (r"(下意识|无意识地?)", "下意识/无意识", "warning", "微表情", "写完整的动作链"),
            (r"一丝.{0,4}(笑意|暖意|寒意|警惕|不易察觉)", "一丝系列", "warning", "微表情", "要么具体到可感知，要么别写"),
            (r"不易察觉", "不易察觉", "warning", "微表情", "如果不易察觉，读者怎么知道？"),
            
            # ═══ 声线/语气描述 ═══
            (r"带着.{1,8}(口吻|语气)", "带语气前缀", "critical", "声线", "用对白本身的标点和断句表现语气"),
            (r"(声音|语调).{0,5}(变得|比.{1,4}更).{0,5}(冰冷|低沉|凌厉)", "声线变化", "critical", "声线", "让对白内容自己说话"),
            (r"每一个字都带着", "字字带X", "critical", "声线", "删掉这句话，让对白自身有力度"),
            (r"不容(置疑|置喙)", "不容置疑", "critical", "声线", "用对白本身的力度表现权威"),
            
            # ═══ 比喻句式 ═══
            (r"(仿佛|宛如|犹如|恰似|酷似).{1,15}(般|一般|似的|一样)", "比喻句式", "critical", "比喻", "用感官细节替代比喻"),
            (r"如同.{1,12}(一般|一样)", "如同比喻", "critical", "比喻", "用感官细节替代比喻"),
            (r".{1,6}像.{1,4}投入.{1,6}(心湖|水面).{0,6}(泛起|荡起|漾起)涟漪", "心湖涟漪", "critical", "比喻", "禁止此意象，用具体动作"),
            (r".{1,6}(掠过|闪过|荡漾于).{1,6}", "掠过/闪过/荡漾", "warning", "比喻", "用具体动作替代"),
            
            # ═══ 生理性系列 ═══
            (r"生理性(泪水|水雾|液体|汽水|盐水)", "生理性液体", "critical", "生理", "直接描述哭泣的差异化写法"),
            (r"生理性", "生理性前缀", "critical", "生理", "删掉'生理性'，直接写反应"),
            
            # ═══ 情绪标签 ═══
            (r"(感到|觉得|心中|内心)(非常|极度|无比)?(愤怒|悲伤|恐惧|厌恶|惊讶|喜悦|痛苦)", "直接情绪标签", "warning", "情绪", "通过动作/环境暗示"),
            (r"(心中|内心)(泛起|涌起|掀起|燃起).{1,10}(波澜|怒火|暖流|感动)", "心中波澜系列", "critical", "情绪", "通过动作暗示"),
            
            # ═══ 句式 ═══
            (r"不是[^。，？！]{1,20}(而是|只是)", "不是而是句式", "warning", "句式", "转为直接叙述"),
            (r"——", "破折号", "warning", "句式", "正文用句号替代，对话中可保留"),
            
            # ═══ 小动物比喻 ═══
            (r"像(小兔子|小鹿|小猫|小兽|幼兽)", "小动物比喻", "critical", "比喻", "禁止动物比喻"),
            
            # ═══ 其他 AI 高频俗套 ═══
            (r"毫不夸张地说", "毫不夸张", "warning", "俗套", "删掉"),
            (r"(熊熊|滔滔不绝|如同实质般)", "经典俗套", "warning", "俗套", "用具体描写替代"),
            (r"眸色一沉|眼神暗了暗|眉头微皱|邪魅一笑|似笑非笑", "面部大忌", "critical", "俗套", "用动作或对白替代"),
            (r"呼吸一滞|倒吸一口凉气|喉结微滚|浑身一震|身子一僵", "身体大忌", "critical", "俗套", "用差异化反应替代"),
            (r"四肢百骸", "四肢百骸", "critical", "俗套", "用具体的身体部位描述"),
            (r"虔诚|膜拜", "虔诚/膜拜", "warning", "俗套", "用具体行为替代"),
        ]
        
        for pattern, name, severity, category, hint in raw_patterns:
            self.patterns.append((
                re.compile(pattern),
                name, severity, category, hint
            ))
    
    def scan(self, text: str) -> List[ClicheHit]:
        """扫描文本"""
        hits = []
        for compiled, name, severity, category, hint in self.patterns:
            for match in compiled.finditer(text):
                hits.append(ClicheHit(
                    pattern=name,
                    text=match.group(0),
                    start=match.start(),
                    end=match.end(),
                    severity=severity,
                    category=category,
                    replacement_hint=hint,
                ))
        hits.sort(key=lambda h: h.start)
        return hits
    
    def scan_by_category(self, text: str) -> dict:
        """按分类统计"""
        hits = self.scan(text)
        by_category = {}
        for h in hits:
            by_category.setdefault(h.category, []).append(h)
        return by_category
    
    def get_critical_count(self, text: str) -> int:
        """获取 critical 级别违规数"""
        return sum(1 for h in self.scan(text) if h.severity == "critical")
```

### 7.2 与 autopilot_daemon 的集成点

```python
# 在 autopilot_daemon.py 中的 post_process_generated_chapter 方法中集成

async def post_process_generated_chapter(self, novel_id, chapter_number, outline, content, scene_director=None):
    """章后处理（增强版）"""
    
    # 1. 增强版俗套扫描
    scanner = EnhancedClicheScanner()
    cliche_hits = scanner.scan(content)
    critical_hits = [h for h in cliche_hits if h.severity == "critical"]
    
    style_warnings = []
    for hit in cliche_hits:
        style_warnings.append({
            "type": "ai_flavor",
            "pattern": hit.pattern,
            "text": hit.text,
            "position": hit.start,
            "severity": hit.severity,
            "category": hit.category,
            "hint": hit.replacement_hint,
        })
    
    # 2. 如果 critical 违规过多，触发自动重写
    CRITICAL_THRESHOLD = 3  # 超过 3 个 critical 则自动重写
    if len(critical_hits) >= CRITICAL_THRESHOLD:
        # 构建定向修正提示
        violation_summary = "\n".join(
            f"- 第{h.start}字: '{h.text}' ({h.pattern}) → {h.replacement_hint}"
            for h in critical_hits[:10]  # 最多列 10 个
        )
        rewrite_prompt = self._build_targeted_rewrite_prompt(
            content, violation_summary
        )
        # ... 执行重写 ...
    
    return {
        "content": content,
        "style_warnings": style_warnings,
        "consistency_report": consistency_report,
        "ghost_annotations": ghost_annotations,
        "cliche_stats": {
            "total": len(cliche_hits),
            "critical": len(critical_hits),
            "by_category": {k: len(v) for k, v in scanner.scan_by_category(content).items()},
        }
    }
```

---

### 7.3 缓冲队列分块验证策略（Chunked Buffer Strategy）

> **⚠️ 架构评估结论**：原回滚机制在第 450 字检测到违规时截断整个请求重试，前序推理算力全部沉没。本节提出缓冲队列策略，将回滚粒度从"整个请求"降至"3 句话的验证块"（详见 [18.1.4 架构隐患二](#1814-架构隐患二回滚重生成的算力损耗)）。

#### 7.3.1 设计思路

与其截断整个请求重试，不如在内部建立缓冲队列。LLM 输出流先进入内部 Buffer（例如每 3 句话作为一个验证块），AC 自动机验证通过后再 flush 到存储或前端。一旦在此 Buffer 内发现违规，仅重发这 3 句话的生成请求（通过传递此时的上下文前缀），降低重试成本。

```
原方案（全量回滚）：

LLM → [1-450字] → AC扫描 → ✕违规 → 截断全部 → 重生成[1-N字]
                     ↑                          ↑
                   检测点                    沉没450字算力


新方案（分块验证）：

LLM → [块1: 1-3句] → Buffer → AC扫描 → ✅ → Flush → 存储/前端
    → [块2: 4-6句] → Buffer → AC扫描 → ✕ → 仅重试块2
    → [块2': 4-6句] → Buffer → AC扫描 → ✅ → Flush
    → [块3: 7-9句] → Buffer → AC扫描 → ✅ → Flush
    
沉没算力 = 仅3句话（约50-100字），而非整个前序生成
```

#### 7.3.2 实现

```python
# application/engine/services/chunked_buffer_scanner.py

import re
from typing import List, Optional, Callable, Awaitable
from dataclasses import dataclass, field

@dataclass
class VerificationChunk:
    """验证块 — 缓冲队列中的最小验证单元"""
    index: int                    # 块序号
    text: str                     # 块文本
    sentence_count: int           # 句子数
    char_count: int               # 字符数
    violations: List = field(default_factory=list)  # 违规列表
    status: str = "pending"       # pending | passed | failed | retried

class ChunkedBufferScanner:
    """缓冲队列分块验证策略
    
    核心思路：
    1. LLM 输出流先进入内部 Buffer
    2. 每积累 N 句话（默认3句）形成一个验证块
    3. AC 自动机验证通过后 flush 到存储/前端
    4. 违规时仅重试当前块，不丢弃前序已通过的块
    """
    
    def __init__(
        self,
        ac_scanner,               # StreamACScanner 实例
        sentences_per_chunk: int = 3,
        max_retry_per_chunk: int = 2,
        sentence_end_pattern: str = r"[。！？…]+",
    ):
        self.ac_scanner = ac_scanner
        self.sentences_per_chunk = sentences_per_chunk
        self.max_retry_per_chunk = max_retry_per_chunk
        self.sentence_end_re = re.compile(sentence_end_pattern)
        
        # 内部状态
        self._buffer: str = ""                    # 当前缓冲区
        self._completed_chunks: List[VerificationChunk] = []  # 已通过的块
        self._current_chunk_index: int = 0
    
    def feed_token(self, token_text: str) -> Optional[VerificationChunk]:
        """喂入一个流式 token
        
        Returns:
            如果当前块已完成验证且通过，返回该块；否则返回 None
        """
        self._buffer += token_text
        
        # 检查是否积累了足够的句子
        sentence_ends = self.sentence_end_re.findall(self._buffer)
        if len(sentence_ends) >= self.sentences_per_chunk:
            return self._try_form_chunk()
        
        return None
    
    def _try_form_chunk(self) -> Optional[VerificationChunk]:
        """尝试从缓冲区形成一个验证块"""
        # 找到第 N 个句子结束的位置
        count = 0
        cut_pos = len(self._buffer)
        for match in self.sentence_end_re.finditer(self._buffer):
            count += 1
            if count >= self.sentences_per_chunk:
                cut_pos = match.end()
                break
        
        chunk_text = self._buffer[:cut_pos]
        remaining = self._buffer[cut_pos:]
        
        # AC 自动机扫描
        violations = self.ac_scanner.scan_chunk(
            chunk_text, position_offset=sum(c.char_count for c in self._completed_chunks)
        )
        
        chunk = VerificationChunk(
            index=self._current_chunk_index,
            text=chunk_text,
            sentence_count=count,
            char_count=len(chunk_text),
            violations=violations,
        )
        
        critical_violations = [v for v in violations if v.severity == "critical"]
        
        if not critical_violations:
            # 验证通过 → flush
            chunk.status = "passed"
            self._completed_chunks.append(chunk)
            self._current_chunk_index += 1
            self._buffer = remaining  # 保留剩余文本
            return chunk
        else:
            # 验证失败 → 需要重试此块
            chunk.status = "failed"
            # 丢弃此块内容，保留 remaining
            self._buffer = remaining
            return None  # 调用方需要重试此块
    
    def get_retry_context(self) -> dict:
        """获取重试当前块所需的上下文信息
        
        返回已通过的所有块文本作为上下文前缀，
        以及当前块的违规信息用于构建修正约束
        """
        passed_text = "".join(c.text for c in self._completed_chunks)
        
        # 从当前缓冲区中提取违规信息（如果有）
        violations = self.ac_scanner.scan_chunk(self._buffer)
        critical_violations = [v for v in violations if v.severity == "critical"]
        
        violation_hints = "; ".join(set(
            f"避免'{v.pattern}'" for v in critical_violations
        )) if critical_violations else ""
        
        return {
            "context_prefix": passed_text,
            "violation_hints": violation_hints,
            "retry_chunk_index": self._current_chunk_index,
        }
    
    def flush_remaining(self) -> Optional[VerificationChunk]:
        """强制 flush 缓冲区中剩余的文本（用于生成结束时）"""
        if not self._buffer.strip():
            return None
        
        violations = self.ac_scanner.scan_chunk(
            self._buffer, position_offset=sum(c.char_count for c in self._completed_chunks)
        )
        
        chunk = VerificationChunk(
            index=self._current_chunk_index,
            text=self._buffer,
            sentence_count=len(self.sentence_end_re.findall(self._buffer)),
            char_count=len(self._buffer),
            violations=violations,
            status="passed" if not any(v.severity == "critical" for v in violations) else "failed",
        )
        
        if chunk.status == "passed":
            self._completed_chunks.append(chunk)
        
        self._buffer = ""
        return chunk
    
    def get_completed_text(self) -> str:
        """获取所有已通过验证块的合并文本"""
        return "".join(c.text for c in self._completed_chunks)
    
    def get_stats(self) -> dict:
        """获取缓冲队列统计信息"""
        return {
            "total_chunks": len(self._completed_chunks),
            "total_chars": sum(c.char_count for c in self._completed_chunks),
            "failed_chunks": sum(1 for c in self._completed_chunks if c.status == "failed"),
            "total_violations": sum(len(c.violations) for c in self._completed_chunks),
        }
```

#### 7.3.3 与流式生成管线的集成

```python
# 在 auto_novel_generation_workflow.py 中的集成 — 分块验证版

class AutoNovelGenerationWorkflow:
    
    def __init__(self, ...):
        # ... 现有初始化 ...
        self._ac_scanner = StreamACScanner()
        # Logit Bias 降级后，仅使用安全偏置
        self._safe_bias_builder = SafeLogitBiasBuilder()
    
    async def _stream_generate_with_chunked_buffer(self, prompt, config):
        """带分块缓冲验证的流式生成"""
        
        # 1. 注入安全 Logit Bias（降级版）
        safe_params = self._safe_bias_builder.get_recommended_strategy()
        config.logit_bias = safe_params["logit_bias"]
        config.frequency_penalty = 0.3
        config.presence_penalty = 0.1
        
        # 2. 初始化缓冲队列
        buffer_scanner = ChunkedBufferScanner(
            ac_scanner=self._ac_scanner,
            sentences_per_chunk=3,     # 每3句验证一次
            max_retry_per_chunk=2,     # 每块最多重试2次
        )
        
        total_retries = 0
        MAX_TOTAL_RETRIES = 4  # 整个请求最多重试4个块
        
        # 3. 流式生成
        async for token_text in self.llm_service.stream_generate(prompt, config):
            result_chunk = buffer_scanner.feed_token(token_text)
            
            if result_chunk is not None and result_chunk.status == "passed":
                # 块验证通过 → 输出到前端/存储
                yield result_chunk.text
            
            elif result_chunk is None and buffer_scanner._buffer == "":
                # 块验证失败 → 需要重试此块
                if total_retries < MAX_TOTAL_RETRIES:
                    retry_ctx = buffer_scanner.get_retry_context()
                    
                    # 构建修正约束
                    retry_prompt = self._build_chunk_retry_prompt(
                        context_prefix=retry_ctx["context_prefix"],
                        violation_hints=retry_ctx["violation_hints"],
                        original_prompt=prompt,
                    )
                    
                    # 重新生成当前块
                    async for token_text in self.llm_service.stream_generate(
                        retry_prompt, config
                    ):
                        result_chunk = buffer_scanner.feed_token(token_text)
                        if result_chunk is not None and result_chunk.status == "passed":
                            yield result_chunk.text
                    
                    total_retries += 1
        
        # 4. flush 剩余缓冲
        final_chunk = buffer_scanner.flush_remaining()
        if final_chunk and final_chunk.status == "passed":
            yield final_chunk.text
        
        # 5. 返回统计
        stats = buffer_scanner.get_stats()
        return stats
    
    def _build_chunk_retry_prompt(self, context_prefix: str, violation_hints: str, original_prompt) -> str:
        """构建块级重试的修正 Prompt"""
        retry_suffix = f"""
[修正约束] 上文生成中检测到以下问题，请避免：
{violation_hints}

上文已生成内容（续写自此）：
...{context_prefix[-500:]}

请续写，严格遵循行为协议。
"""
        return original_prompt + retry_suffix
```

#### 7.3.4 算力损耗对比

| 指标 | 原方案（全量回滚） | 新方案（分块验证） | 改善 |
|------|-------------------|-------------------|------|
| 单次回滚沉没算力 | 整个前序生成（~450字） | 1个验证块（~50-100字） | **降低 80%** |
| 回滚延迟（P95） | TTFT + 450字生成时间 | TTFT + 100字生成时间 | **降低 70%** |
| 最大重试次数 | 2次（全量） | 4次（分块，总算力仍更低） | 颗粒度更细 |
| 端到端延迟波动 | 大（回滚时不可预测） | 小（每次重试代价固定） | **显著改善** |
| 一次性通过率 | ~60% | ~85%（分块更易通过） | **提升 25%** |

---

## 8. Layer 5: 角色状态向量注入（State Management）

### 8.1 问题诊断

当前项目中 `verbal_tic`（口头禅）、`idle_behavior`（待机动作）、`mental_state`（心理状态）等锚点数据存储在 Bible 中，但在长上下文生成中极易发生**记忆漂移**。

根因：
1. 锚点数据仅作为上下文片段一次性注入，缺乏强制对齐机制
2. 模型在生成过程中逐渐"忘记"初始锚点
3. 缺乏对锚点使用情况的验证

### 8.2 角色状态向量设计

```python
# application/engine/services/character_state_vector.py

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum

class EmotionState(Enum):
    NORMAL = "平静"
    TENSE = "紧张"
    ANGRY = "愤怒"
    SAD = "悲伤"
    FEAR = "恐惧"
    EXCITED = "兴奋"

@dataclass
class CharacterStateVector:
    """角色状态向量 — 每次生成前强制注入的硬性前置条件
    
    设计原则：
    1. 所有字段必须有值（不能为空），空值用默认值填充
    2. 每次生成前从数据库读取最新状态
    3. 状态变化必须通过 API 显式更新
    """
    character_id: str
    name: str
    
    # ─── 核心锚点（不可为空）───
    nervous_habit: str = "搓手指"          # 紧张时的习惯动作
    anger_expression: str = "说话变慢变清楚" # 愤怒时的表达方式
    sadness_expression: str = "沉默，找事做" # 悲伤时的表达方式
    verbal_tic: str = ""                   # 口头禅
    idle_behavior: str = "摸耳垂"          # 待机动作
    
    # ─── 当前状态 ───
    current_emotion: EmotionState = EmotionState.NORMAL
    emotion_cause: str = ""               # 当前情绪的来源
    
    # ─── 物理状态 ───
    physical_condition: str = "正常"       # 疲惫/受伤/发热等
    energy_level: str = "正常"            # 精力水平
    
    # ─── 认知边界 ───
    knowledge_limit: str = ""             # 角色不知道什么
    professional_bias: str = ""           # 专业认知倾向
    
    # ─── 性格缝隙 ───
    exception_rule: str = ""              # "嘴硬的人在XX面前会笨拙"
    
    def to_prompt_block(self) -> str:
        """生成强制注入的 Prompt 片段"""
        lines = [f"[角色状态锁 · {self.name}]"]
        
        if self.current_emotion != EmotionState.NORMAL:
            lines.append(f"当前情绪：{self.current_emotion.value}（原因：{self.emotion_cause}）")
            lines.append(f"⚠ 此情绪必须延续，不能在本段突然消失")
        
        if self.physical_condition != "正常":
            lines.append(f"身体状态：{self.physical_condition}")
            lines.append(f"⚠ 动作要受此状态影响（变慢/变乱/撑不住）")
        
        lines.append(f"紧张时：{self.nervous_habit}")
        lines.append(f"愤怒时：{self.anger_expression}")
        lines.append(f"悲伤时：{self.sadness_expression}")
        
        if self.verbal_tic:
            lines.append(f"口头禅：{self.verbal_tic}")
        if self.idle_behavior:
            lines.append(f"待机动作：{self.idle_behavior}")
        if self.knowledge_limit:
            lines.append(f"认知盲区：{self.knowledge_limit}")
        if self.exception_rule:
            lines.append(f"性格缝隙：{self.exception_rule}")
        
        return "\n".join(lines)


class CharacterStateManager:
    """角色状态管理器"""
    
    def __init__(self, bible_repo, state_repo):
        self.bible_repo = bible_repo
        self.state_repo = state_repo
    
    def get_state_vector(self, novel_id: str, character_id: str) -> CharacterStateVector:
        """获取角色当前状态向量"""
        # 优先从状态仓储读取动态状态
        state = self.state_repo.get(novel_id, character_id)
        
        # 从 Bible 读取静态锚点
        bible = self.bible_repo.get_by_novel_id(NovelId(novel_id))
        char = next((c for c in bible.characters if c.id == character_id), None)
        
        if not char:
            raise EntityNotFoundError("Character", character_id)
        
        return CharacterStateVector(
            character_id=character_id,
            name=char.name,
            nervous_habit=getattr(char, 'idle_behavior', '') or self._infer_nervous_habit(char),
            anger_expression=state.anger_expression if state else "说话变慢",
            sadness_expression=state.sadness_expression if state else "沉默",
            verbal_tic=getattr(char, 'verbal_tic', '') or "",
            idle_behavior=getattr(char, 'idle_behavior', '') or "摸耳垂",
            current_emotion=EmotionState(state.emotion) if state else EmotionState.NORMAL,
            emotion_cause=state.emotion_cause if state else "",
            physical_condition=state.physical_condition if state else "正常",
            knowledge_limit=getattr(char, 'knowledge_limit', '') or "",
            exception_rule=getattr(char, 'exception_rule', '') or "",
        )
    
    def build_all_characters_block(self, novel_id: str, chapter_number: int) -> str:
        """为当前章节的所有在场角色构建状态锁"""
        # 获取本章涉及的角色列表
        characters = self._get_chapter_characters(novel_id, chapter_number)
        
        blocks = []
        for char_id in characters:
            vector = self.get_state_vector(novel_id, char_id)
            blocks.append(vector.to_prompt_block())
        
        return "\n\n".join(blocks)
    
    def _infer_nervous_habit(self, char) -> str:
        """根据角色设定推断紧张习惯"""
        # 简单规则映射（可后续用 LLM 增强）
        desc = (char.description or "").lower()
        if "学" in desc or "书" in desc:
            return "扶眼镜"
        if "武" in desc or "战" in desc:
            return "活动手腕"
        if "商" in desc or "市" in desc:
            return "摸袖口"
        return "搓手指"
```

### 8.3 状态向量的注入位置

在 `context_budget_allocator.py` 中，将角色状态向量注入 T0 层级：

```python
# 在 ContextBudgetAllocator.allocate() 中新增

def _allocate_character_state_vectors(self, novel_id, chapter_number, slots):
    """将角色状态向量注入 T0 层（最高优先级）"""
    manager = CharacterStateManager(self.bible_repo, self.state_repo)
    state_block = manager.build_all_characters_block(novel_id, chapter_number)
    
    slots["CHARACTER_STATE_VECTORS"] = ContextSlot(
        name="角色状态锁",
        tier=PriorityTier.T0_CRITICAL,
        content=state_block,
        priority=119,  # 介于 SCARS(118) 和 COMPLETED_BEATS(115) 之间
        max_tokens=1500,
    )
```

---

## 9. Layer 6: 文风指纹闭环（Voice Fingerprint）

### 9.1 现有架构评估

项目已有完整的文风指纹体系（参见 `docs/superpowers/specs/2026-04-05-intelligent-retrieval-context-management-design.md` 7.1-7.5 节）：

- ✅ 采血流程（AI原文 → 作者修改 → 差异捕获 → 存入金库）
- ✅ 指纹提取（词法基因、句法节奏、场景风格、叙事视角）
- ✅ 生成前约束（Prompt 注入）
- ✅ 生成后过滤（俗套扫描 + 文风匹配）
- ✅ 文风漂移监控

### 9.2 增强点：Anti-AI 指标注入

在现有指纹体系中新增"Anti-AI 指标"维度：

```python
# application/analyst/services/fingerprint_service.py 增强版

@dataclass
class AntiAIMetrics:
    """Anti-AI 文风指标 — 衡量文本的'人味'程度"""
    
    # 低 = 更像人
    metaphor_density: float = 0.0        # 比喻密度（次/千字）
    emotion_label_rate: float = 0.0      # 直接情绪标签率
    micro_expression_count: int = 0      # 微表情出现次数
    cliche_pattern_count: int = 0        # 俗套句式次数
    
    # 高 = 更像人
    action_based_emotion_ratio: float = 0.0  # 动作暗示情绪的比例
    dialogue_subtext_ratio: float = 0.0      # 潜台词对话比例
    sensory_detail_density: float = 0.0      # 感官细节密度
    character_differentiation: float = 0.0   # 角色反应差异化程度
    
    def human_score(self) -> float:
        """计算'人味'评分（0-100）"""
        # 低指标项（越低越好）
        low_score = max(0, 100 - (
            self.metaphor_density * 20 +
            self.emotion_label_rate * 30 +
            self.micro_expression_count * 5 +
            self.cliche_pattern_count * 8
        ))
        # 高指标项（越高越好）
        high_score = (
            self.action_based_emotion_ratio * 25 +
            self.dialogue_subtext_ratio * 25 +
            self.sensory_detail_density * 20 +
            self.character_differentiation * 30
        )
        return (low_score * 0.5 + high_score * 0.5)
    
    def to_prompt_constraint(self) -> str:
        """转化为可注入的约束"""
        parts = []
        if self.metaphor_density > 0.5:
            parts.append(f"比喻密度须低于{self.metaphor_density * 0.7:.1f}次/千字")
        if self.action_based_emotion_ratio < 0.6:
            parts.append("情绪表达须至少60%通过动作暗示")
        if self.sensory_detail_density < 2.0:
            parts.append(f"感官细节密度须达到{self.sensory_detail_density * 1.2:.1f}处/千字")
        return "；".join(parts) if parts else ""
```

### 9.3 采血差异的 Anti-AI 学习

```python
# application/analyst/services/anti_ai_learning.py

class AntiAILearning:
    """从作者修改差异中学习 Anti-AI 规则"""
    
    def analyze_diff(self, ai_original: str, author_refined: str) -> dict:
        """分析 AI → 作者的修改差异，提取 Anti-AI 规则"""
        
        # 使用 EnhancedClicheScanner 扫描两个版本
        scanner = EnhancedClicheScanner()
        ai_hits = scanner.scan(ai_original)
        author_hits = scanner.scan(author_refined)
        
        # 找出作者删掉的俗套
        removed_cliches = []
        for ah in ai_hits:
            # 检查作者的版本中同一位置是否还有俗套
            if not any(bh.start <= ah.start <= bh.end for bh in author_hits):
                removed_cliches.append({
                    "type": ah.category,
                    "pattern": ah.pattern,
                    "ai_text": ah.text,
                    "hint": ah.replacement_hint,
                })
        
        # 找出作者用什么替代了俗套
        # 简化版：使用 SequenceMatcher 找到修改区域
        from difflib import SequenceMatcher
        matcher = SequenceMatcher(None, ai_original, author_refined)
        
        replacements = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'replace':
                replacements.append({
                    "ai_version": ai_original[i1:i2],
                    "author_version": author_refined[j1:j2],
                })
        
        return {
            "removed_cliches": removed_cliches,
            "replacements": replacements,
            "lesson": self._extract_lessons(removed_cliches, replacements),
        }
    
    def _extract_lessons(self, removed, replacements) -> List[str]:
        """提取可复用的 Anti-AI 教训"""
        lessons = []
        
        # 常见模式学习
        for r in removed:
            if r["type"] == "微表情":
                lessons.append(f"微表情'{r['ai_text']}'应替换为完整动作或省略")
            elif r["type"] == "比喻":
                lessons.append(f"比喻'{r['ai_text']}'应替换为感官细节")
            elif r["type"] == "声线":
                lessons.append(f"声线描述'{r['ai_text']}'应通过对话本身表现")
        
        return lessons
```

---

## 10. Layer 7: 章后审计双刀（OOC + AI 味）

### 10.1 现有架构

项目已有 `review-character-consistency` 提示词（参见 `docs/audit-system-design.md` 10.2 节），实现了 OOC + AI 味双刀检测。

### 10.2 增强：Anti-AI 专项审计

```python
# application/audit/services/anti_ai_audit.py

from dataclasses import dataclass
from typing import List

@dataclass
class AntiAIAuditResult:
    """Anti-AI 专项审计结果"""
    total_issues: int
    critical_issues: int
    human_score: float         # 0-100
    category_breakdown: dict   # {category: count}
    top_violations: List[dict] # 最严重的违规
    rewrite_suggestions: List[dict]  # 改写建议

class AntiAIAuditor:
    """Anti-AI 专项审计服务"""
    
    def __init__(self, llm_service, scanner=None):
        self.llm_service = llm_service
        self.scanner = scanner or EnhancedClicheScanner()
    
    async def audit_chapter(self, content: str, characters: list) -> AntiAIAuditResult:
        """对章节进行 Anti-AI 专项审计"""
        
        # 1. 规则扫描（快速）
        hits = self.scanner.scan(content)
        critical_hits = [h for h in hits if h.severity == "critical"]
        by_category = {}
        for h in hits:
            by_category.setdefault(h.category, []).append(h)
        
        # 2. 角色差异化检查
        char_diff_score = self._check_character_differentiation(content, characters)
        
        # 3. 计算人味评分
        anti_ai_metrics = AntiAIMetrics(
            metaphor_density=self._calc_metaphor_density(content, hits),
            emotion_label_rate=self._calc_emotion_label_rate(content, hits),
            micro_expression_count=sum(1 for h in hits if h.category == "微表情"),
            cliche_pattern_count=len(hits),
            action_based_emotion_ratio=self._calc_action_emotion_ratio(content),
            character_differentiation=char_diff_score,
        )
        
        # 4. LLM 深度审计（仅对 critical 违规较多时触发）
        rewrite_suggestions = []
        if len(critical_hits) >= 3:
            rewrite_suggestions = await self._llm_deep_audit(content, critical_hits)
        
        return AntiAIAuditResult(
            total_issues=len(hits),
            critical_issues=len(critical_hits),
            human_score=anti_ai_metrics.human_score(),
            category_breakdown={k: len(v) for k, v in by_category.items()},
            top_violations=[
                {
                    "position": h.start,
                    "text": h.text,
                    "category": h.category,
                    "hint": h.replacement_hint,
                }
                for h in critical_hits[:5]
            ],
            rewrite_suggestions=rewrite_suggestions,
        )
    
    def _check_character_differentiation(self, content: str, characters: list) -> float:
        """检查角色反应差异化程度
        
        方法：统计不同角色在同一场景中的反应词汇重合度
        重合度越低，差异化越好
        """
        # 简化实现：提取每个角色名附近的动作/情绪词汇
        char_reactions = {}
        for char in characters:
            name = char.name
            # 找到角色名在文本中的位置
            reactions = []
            for i in range(len(content)):
                if content[i:i+len(name)] == name:
                    # 取角色名后 50 字的文本
                    context = content[i:i+50]
                    reactions.append(context)
            char_reactions[name] = reactions
        
        # 计算词汇重合度
        if len(char_reactions) < 2:
            return 1.0
        
        all_action_words = []
        for name, reactions in char_reactions.items():
            words = set()
            for r in reactions:
                # 提取动作词（简化版）
                for action in ["攥拳", "皱眉", "冷笑", "后退", "拔刀", "沉默", "转身", "低头"]:
                    if action in r:
                        words.add(action)
            all_action_words.append(words)
        
        # 计算平均重合度
        overlaps = []
        for i in range(len(all_action_words)):
            for j in range(i + 1, len(all_action_words)):
                if all_action_words[i] and all_action_words[j]:
                    overlap = len(all_action_words[i] & all_action_words[j])
                    total = len(all_action_words[i] | all_action_words[j])
                    overlaps.append(overlap / total if total > 0 else 0)
        
        avg_overlap = sum(overlaps) / len(overlaps) if overlaps else 0
        return 1.0 - avg_overlap  # 重合度越低，差异化越好
    
    def _calc_metaphor_density(self, content: str, hits: list) -> float:
        """比喻密度（次/千字）"""
        char_count = len(content)
        if char_count == 0:
            return 0.0
        metaphor_count = sum(1 for h in hits if h.category == "比喻")
        return metaphor_count / (char_count / 1000)
    
    def _calc_emotion_label_rate(self, content: str, hits: list) -> float:
        """直接情绪标签率"""
        char_count = len(content)
        if char_count == 0:
            return 0.0
        emotion_count = sum(1 for h in hits if h.category == "情绪")
        return emotion_count / (char_count / 1000)
    
    def _calc_action_emotion_ratio(self, content: str) -> float:
        """动作暗示情绪的比例"""
        # 简化实现：检查情绪词附近是否有动作描写
        emotion_patterns = re.compile(r"(感到|觉得|心中|内心)")
        action_patterns = re.compile(r"(手|脚|头|眼|嘴|肩|背|身|步|动作)")
        
        emotion_matches = list(emotion_patterns.finditer(content))
        if not emotion_matches:
            return 1.0  # 没有直接情绪词，说明都在用动作暗示
        
        action_near_emotion = 0
        for em in emotion_matches:
            # 检查情绪词前后 100 字是否有动作词
            context = content[max(0, em.start()-50):em.end()+50]
            if action_patterns.search(context):
                action_near_emotion += 1
        
        return action_near_emotion / len(emotion_matches)
    
    async def _llm_deep_audit(self, content: str, critical_hits: list) -> list:
        """LLM 深度审计 — 为 critical 违规生成改写建议"""
        # 构建审计 Prompt
        violation_list = "\n".join(
            f"- 位置{h.start}: '{h.text}' ({h.pattern}) → {h.replacement_hint}"
            for h in critical_hits[:8]
        )
        
        prompt = f"""你是小说文风审校编辑。以下文本中检测到 AI 生成俗套，请为每个问题提供改写建议。

检测结果：
{violation_list}

原文（相关段落）：
{content[:3000]}

请为每个问题提供：
1. 原文片段
2. 问题诊断
3. 改写建议（必须遵循 Show Don't Tell 原则）"""

        # 调用 LLM
        result = await self.llm_service.generate(prompt, GenerationConfig(max_tokens=2048, temperature=0.3))
        return self._parse_audit_result(result.content)
```

---

## 11. 提示词重构工程

### 11.1 当前 Prompt 结构问题

以 `chapter-generation-main` 为例，当前 system prompt 约 1500+ tokens，包含：
- 身份设定
- 写作秘诀（5 大条）
- 节拍衔接铁律（4 大条）

**问题**：规则散布在自然语言中，模型难以提取确定性的 condition→action 映射。

### 11.2 重构方案：协议化 Prompt

```python
# application/engine/prompts/chapter_generation_protocol.py

CHAPTER_GENERATION_PROTOCOL = """
你是长篇小说的创作者。你的核心协议如下：

【核心协议 · 不可违反】

P1. 信息密度法则
  每个段落必须推进以下至少一项：剧情事实、角色关系、悬念线索、信息差变化。
  写完一段后自查：这段删掉会影响读者理解吗？不会就删掉。

P2. 感官优先法则
  当你需要表达情绪或氛围时，执行顺序：
  感官细节（温度/光线/声音/触感/气味）→ 动作变化 → 对话内容
  禁止跳过前两步直接写情绪标签。

P3. 角色差异化法则
  不同角色面对同一事件的反应方式必须不同。
  反应方式 = 角色背景 × 当前身体状态 × 与事件的利益关系。
  每个角色有专属紧张习惯：{nervous_habits}

P4. 节奏法则
  节奏快 → 句子短，动词前移，主语可省。
  节奏慢 → 长短交替，感官细节穿插。
  禁止连续3句以上长度相近的句子。

P5. 衔接法则
  节拍间无断点。情绪有惯性。
  上一段在愤怒，这一段不能突然平静。
  禁止用时间词（后来/之后/转眼间）开头省略过渡。

【禁止模式 · 检测到必须修正】

B1. 禁止直接情绪标签（"他感到愤怒""她很悲伤"）
B2. 禁止微表情快照（嘴角上扬/眼里闪过/指尖泛白）
B3. 禁止比喻句式（仿佛/宛如/犹如/像…一样）
B4. 禁止声线标签（带着XX的语气/声音比寒冰更冰冷）
B5. 禁止"不是A而是B"句式
B6. 禁止破折号转折（正文用句号断句，对话可保留）
B7. 禁止动物比喻（像小兔子/小鹿/小兽）
B8. 禁止"生理性"前缀

⚠ 场景化豁免：部分规则在特定叙事场景（梦境/精神极端状态/超自然现象/文学性独白）下临时挂起，详见下方【场景化豁免】段。

【替换策略 · 检测到B类模式时执行】

R1. 情绪 → 找到角色此刻最可能做的小动作（手停住/话顿了一下/杯子端到嘴边又放下）
R2. 微表情 → 写完整姿态变化，或不写，让对白本身传递
R3. 比喻 → 写此刻的体温、光线角度、衣料触感
R4. 声线 → 用对白的标点和断句表现语气
R5. 不是而是 → 转为直接叙述（"他在等"而非"他不是害怕，而是在等"）
R6. 破折号 → 句号断开，让节奏自己制造停顿
R7. 动物比喻 → 删掉，用人的动作描写
R8. 生理性 → 直接写生理反应（眼睛酸了/鼻子红了/声音发闷）

{allowlist_block}
"""

def build_chapter_system_prompt(
    novel_title: str,
    nervous_habits: dict,  # {角色名: 紧张习惯}
    character_states: str,
    voice_block: str,
    allowlist_context: Optional[AllowlistContext] = None,  # 新增：白名单上下文
) -> str:
    """构建章节生成的 system prompt"""
    
    habits_str = "\n  ".join(f"{name}：{habit}" for name, habit in nervous_habits.items())
    
    # 构建白名单豁免块
    allowlist_block = ""
    if allowlist_context and allowlist_context.active_exceptions:
        allowlist_block = "【场景化豁免 · 当前激活】\n"
        for rule_id in sorted(allowlist_context.suspended_rules):
            allowlist_block += f"  规则 {rule_id} 在当前场景中临时挂起\n"
        for instruction in allowlist_context.extra_instructions:
            allowlist_block += f"\n{instruction}\n"
    
    protocol = CHAPTER_GENERATION_PROTOCOL.format(
        nervous_habits=habits_str,
        allowlist_block=allowlist_block,
    )
    
    return f"""{protocol}

{character_states}

{voice_block}
"""
```

### 11.3 节拍级 Prompt 重构

当前 `beat-focus-instructions` 的 user_template 约 800+ tokens，信息密集但缺乏优先级。

重构方案：将"禁止"和"必须"分开，"禁止"放最后（降低注意力权重，因为已有 AC 自动机兜底），"必须"放最前。

```python
BEAT_PROTOCOL_TEMPLATE = """
【本节拍任务】
目标字数：约 {target_words} 字
聚焦：{focus}
内容：{description}

【必须执行】
1. {instruction}
2. {anchor_line}
3. {obligation}
4. 本节拍第一句必须与上一节拍最后一句有连接（首个节拍除外）
5. 节拍内部有微弧线：起→承→收，不写流水账

【格式要求】
- 句号结束另起一行，每段最多5句
- 对话简短有力，双引号内通常只有一个句号
- 场景转换时空一行
- 适配手机阅读

【篇幅控制】
- 剧情完毕立即收束，不拖沓
- 禁止空洞感叹和重复对话凑字数
- 结尾必须完整，不允许截断

【最后提醒】
- 绝不在正文中输出【节拍 X/Y】标记
- 不写章节标题
- 不在节拍结尾总结全章
"""
```

---

## 12. 系统架构集成设计

### 12.1 全链路架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                     PlotPilot 防 AI 味全链路                        │
│                                                                     │
│  ┌─────────────┐    ┌─────────────┐    ┌──────────────────────┐   │
│  │ Layer 1      │    │ Layer 2      │    │ Layer 3              │   │
│  │ 正向行为映射  │───→│ 结构化规则    │───→│ Token 级硬拦截       │   │
│  │ (Prompt注入) │    │ (YAML协议)   │    │ (Logit Bias + AC)   │   │
│  └─────────────┘    └─────────────┘    └──────────────────────┘   │
│         │                   │                      │                │
│         ▼                   ▼                      ▼                │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │              上下文组装（ContextBudgetAllocator）          │      │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐  │      │
│  │  │ T0: 系统P │  │ T0: 角色  │  │ T0: 生命 │  │ T0: 行 │  │      │
│  │  │ rompt+   │  │ 状态锁   │  │ 周期准则 │  │ 为协议 │  │      │
│  │  │ 行为协议  │  │(新增强)  │  │(沙漏)   │  │(重构)  │  │      │
│  │  └──────────┘  └──────────┘  └──────────┘  └────────┘  │      │
│  └──────────────────────────────────────────────────────────┘      │
│                              │                                      │
│                              ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │              LLM 推理层（带 Logit Bias）                  │      │
│  │  ┌───────────────────────────────────────────────────┐   │      │
│  │  │          流式生成 + 实时 AC 自动机扫描              │   │      │
│  │  │  chunk → AC Scanner → 违规? → 回滚重生成           │   │      │
│  │  └───────────────────────────────────────────────────┘   │      │
│  └──────────────────────────────────────────────────────────┘      │
│                              │                                      │
│                              ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │              Layer 4: 生成后处理                           │      │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │      │
│  │  │ 俗套扫描     │  │ 文风指纹匹配  │  │ Anti-AI 审计  │   │      │
│  │  │ (Enhanced)   │  │ (Voice FP)   │  │ (新增强)     │   │      │
│  │  └──────────────┘  └──────────────┘  └──────────────┘   │      │
│  │         │                  │                  │           │      │
│  │         ▼                  ▼                  ▼           │      │
│  │  ┌──────────────────────────────────────────────────┐   │      │
│  │  │  定向修正循环（最多2轮）                            │   │      │
│  │  │  文风偏离 → 修文 → 复评分 → 通过/再修              │   │      │
│  │  └──────────────────────────────────────────────────┘   │      │
│  └──────────────────────────────────────────────────────────┘      │
│                              │                                      │
│                              ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐      │
│  │              Layer 5-7: 章后管线                          │      │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐              │      │
│  │  │ 角色状态  │  │ 文风指纹  │  │ 双刀审计  │              │      │
│  │  │ 更新     │  │ 更新     │  │ (OOC+AI) │              │      │
│  │  └──────────┘  └──────────┘  └──────────┘              │      │
│  │         │                                              │      │
│  │         ▼                                              │      │
│  │  ┌──────────────────────────────────────────────────┐   │      │
│  │  │  Feed-forward 反哺（注入下一章上下文）             │   │      │
│  │  └──────────────────────────────────────────────────┘   │      │
│  └──────────────────────────────────────────────────────────┘      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 12.2 数据流时序图

```
用户点击"生成章节"
        │
        ▼
┌─── autopilot_daemon ───┐
│                         │
│  1. 构建上下文           │
│  ├─ ContextBudgetAllocator.allocate()
│  │  ├─ T0: 系统Prompt + 行为协议(新)
│  │  ├─ T0: 角色状态锁(新)
│  │  ├─ T0: 生命周期沙漏
│  │  ├─ T0: FACT_LOCK + COMPLETED_BEATS
│  │  ├─ T1: 因果链 + 卷摘要
│  │  ├─ T2: 最近章节(章末2000字保留)
│  │  └─ T3: 向量召回(双路检索)
│  │
│  2. 注入 Logit Bias(新)  ← TokenGuard.get_api_params()
│     ├─ frequency_penalty: 0.3
│     ├─ presence_penalty: 0.1
│     └─ logit_bias: {forbidden_token_ids: -100}
│  │
│  3. 流式生成 + 实时扫描(新)
│     ├─ LLM.stream_generate(prompt, config)
│     │     │
│     │     ▼ 每100字
│     │  StreamACScanner.scan_chunk()
│     │     ├─ 无违规 → 继续流式输出
│     │     └─ critical违规 → 截断 + 回滚重生成(≤2次)
│  │
│  4. 生成后处理
│  ├─ EnhancedClicheScanner.scan(content) (新)
│  │  ├─ critical ≥ 3 → 触发定向修文
│  │  └─ critical < 3 → 继续
│  ├─ VoiceFingerprint.score() (已有)
│  │  ├─ similarity < 0.75 → 定向修文循环(≤2轮)
│  │  └─ similarity ≥ 0.75 → 继续
│  └─ AntiAIAuditor.audit_chapter() (新)
│     ├─ 计算 human_score
│     └─ 生成 rewrite_suggestions
│  │
│  5. 章后管线
│  ├─ ChapterAftermathPipeline.run()
│  │  ├─ 叙事同步(事件流+状态机更新)
│  │  ├─ 文风评分 → 指纹更新
│  │  ├─ KG推断
│  │  └─ 伏笔/三元组
│  ├─ TensionScoring
│  └─ Feed-forward → 下一章上下文
│
└─────────────────────────┘
```

### 12.3 与现有代码的集成点映射

| 新增/增强组件 | 现有代码文件 | 集成方式 | 影响范围 |
|-------------|------------|---------|---------|
| `positive_framing_rules.py` | `infrastructure/ai/prompts/prompts_defaults.json` | 替换 `chapter-generation-main` 的 system 字段 | 生成层 |
| `anti_ai_protocol.yaml` | 新文件 | 被 `rule_parser.py` 加载，注入 T0 槽位 | 上下文层 |
| `rule_parser.py` | 新文件 | 在 `context_budget_allocator.py.allocate()` 中调用 | 上下文层 |
| `token_guard.py` | 新文件 | 在 `auto_novel_generation_workflow.py._stream_generate()` 中注入 API 参数 | 推理层 |
| `stream_ac_scanner.py` | 新文件 | 在流式生成循环中每 100 字调用 | 推理层 |
| `enhanced_cliche_scanner.py` | `application/audit/services/cliche_scanner.py` | **替换**现有 10 模式版本 | 审计层 |
| `character_state_vector.py` | 新文件 | 在 `context_budget_allocator.py` 中新增 T0 槽位 `CHARACTER_STATE_VECTORS` | 上下文层 |
| `anti_ai_metrics.py` | `application/analyst/services/fingerprint_service.py` | 扩展 `FingerprintMetrics` dataclass | 分析层 |
| `anti_ai_learning.py` | `application/analyst/services/voice_sample_service.py` | 在 `append_sample()` 后触发差异学习 | 采血层 |
| `anti_ai_audit.py` | 新文件 | 在 `autopilot_daemon.py.post_process_generated_chapter()` 中调用 | 审计层 |
| `chapter_generation_protocol.py` | `infrastructure/ai/prompts/prompts_defaults.json` | 重构 system prompt 结构 | Prompt层 |
| `beat_protocol_template` | `prompts_defaults.json` 中 `beat-focus-instructions` | 重构 user_template | Prompt层 |

### 12.4 上下文配额分配调整

新增 Anti-AI 相关槽位后，T0 配额从 35% 提权至 40%：

```python
# context_budget_allocator.py 配额调整

# V9 Anti-AI 增强：T0 提权至 40%
T0_BUDGET_RATIO = 0.40   # 40% 给 T0（新增行为协议 + 角色状态锁）
T1_BUDGET_RATIO = 0.23   # 23% 给 T1（微降）
T2_BUDGET_RATIO = 0.28   # 28% 给 T2（微降）
T3_BUDGET_RATIO = 0.09   # 9% 给 T3（微降）

# T0 新增槽位
MAX_BEHAVIOR_PROTOCOL_TOKENS = 800    # 行为协议（P1-P5 + B1-B8 + R1-R8）
MAX_CHARACTER_STATE_TOKENS = 1500     # 角色状态锁（每角色约 200 字）
```

T0 槽位优先级重排：

| 优先级 | 槽位名 | 来源 | 最大 tokens | 变更 |
|--------|--------|------|------------|------|
| 135 | LIFECYCLE_DIRECTIVE | 沙漏阶段 | 600 | — |
| 132 | BEHAVIOR_PROTOCOL | **行为协议(新)** | 800 | 新增 |
| 130 | STORY_ANCHOR | 全书主线锚点 | 500 | — |
| 125 | FACT_LOCK | MemoryEngine | 2500 | — |
| 122 | CHARACTER_STATE_VECTORS | **角色状态锁(新)** | 1500 | 新增 |
| 120 | SCARS_AND_MOTIVATIONS | 人物状态机 | 1500 | — |
| 115 | COMPLETED_BEATS | MemoryEngine | 2000 | — |
| 112 | ACTIVE_ENTITY_MEMORY | 因果图谱 | 1000 | — |
| 110 | REVEALED_CLUES | MemoryEngine | 2000 | — |
| 108 | DEBT_DUE | 叙事债务 | 800 | — |

### 12.5 动态 T0 压缩策略（Dynamic State Summarization）

> **⚠️ 架构评估结论**：1500 Tokens 的角色状态锁过于庞大，T0 提权至 40% 会挤压 T1/T2 空间，长远可能引发剧情连贯性下降（详见 [18.1.5 架构隐患三](#1815-架构隐患三上下文配额挤压)）。本节引入状态机差分机制，将 T0 配额压制到 30% 以内。

#### 12.5.1 问题诊断

当前方案对所有在场角色无差别注入完整状态向量（每角色约 200 Tokens），导致：

1. **空间浪费**：边缘角色（仅路过/背景提及）占用了与核心 POV 角色相同的空间
2. **信息冗余**：角色情绪未变化时，每次生成仍注入完整状态
3. **配额挤压**：T0 占比 40% → T1+T2 合计仅 51%，剧情连贯性风险

```
当前注入策略（无差别）：

章节涉及角色: [主角A, 配角B, 路人C, 路人D]

T0 角色状态锁:
  [主角A: 完整200T] ──→ 核心POV，需要完整状态 ✅
  [配角B: 完整200T] ──→ 有对话，需要部分状态 ✅
  [路人C: 完整200T] ──→ 仅提了一次名字，不需要 ❌
  [路人D: 完整200T] ──→ 完全没出场，不需要 ❌
  
  浪费: ~400 Tokens（可释放给 T1/T2）
```

#### 12.5.2 差分注入策略

```python
# application/engine/services/dynamic_state_compressor.py

from enum import Enum
from typing import List, Optional
from dataclasses import dataclass

class CharacterRole(Enum):
    """角色在当前章节中的重要程度"""
    POV_CORE = "pov_core"         # 核心 POV 角色 → 完整注入
    ACTIVE = "active"             # 有对话/关键动作 → 部分注入
    PASSIVE = "passive"           # 仅被提及 → 精简注入
    BACKGROUND = "background"     # 背景存在 → 仅名字+标识

@dataclass
class CharacterRelevance:
    """角色在当前节拍中的相关度评估"""
    character_id: str
    role: CharacterRole
    has_dialogue: bool = False
    has_action: bool = False
    emotion_changed: bool = False   # 情绪是否发生改变
    is_pov: bool = False           # 是否是当前节拍的 POV 角色
    mention_count: int = 0         # 在大纲中被提及的次数

class DynamicStateCompressor:
    """动态 T0 压缩策略
    
    核心原则：
    1. 仅当角色状态发生变化，或该角色在当前节拍是核心 POV 时，才注入完整状态向量
    2. 边缘角色仅保留极其精简的名字与核心标识
    3. 将 T0 配额从 40% 压制到 30% 以内
    """
    
    # 各级别的 Token 预算
    BUDGET = {
        CharacterRole.POV_CORE: 200,    # 完整状态向量
        CharacterRole.ACTIVE: 80,       # 精简版：当前情绪+紧张习惯+口头禅
        CharacterRole.PASSIVE: 30,      # 极简版：名字+核心标识
        CharacterRole.BACKGROUND: 10,   # 仅名字
    }
    
    def classify_characters(
        self,
        novel_id: str,
        chapter_number: int,
        beat_description: str,
        previous_state_hashes: dict,
    ) -> List[CharacterRelevance]:
        """评估角色在当前节拍中的相关度
        
        Args:
            novel_id: 小说ID
            chapter_number: 章节号
            beat_description: 当前节拍描述
            previous_state_hashes: 上一节拍的角色状态哈希（用于差分检测）
        """
        characters = self._get_chapter_characters(novel_id, chapter_number)
        relevances = []
        
        for char in characters:
            relevance = CharacterRelevance(character_id=char.id)
            
            # 检查是否是 POV 角色
            relevance.is_pov = self._is_pov_character(char, beat_description)
            
            # 检查是否有对话/动作
            relevance.has_dialogue = self._has_dialogue_in_beat(char, beat_description)
            relevance.has_action = self._has_action_in_beat(char, beat_description)
            
            # 检查情绪是否变化（差分检测）
            current_hash = self._compute_state_hash(char)
            relevance.emotion_changed = (
                previous_state_hashes.get(char.id) != current_hash
            )
            
            # 统计提及次数
            relevance.mention_count = self._count_mentions(char, beat_description)
            
            # 分级
            if relevance.is_pov:
                relevance.role = CharacterRole.POV_CORE
            elif relevance.has_dialogue or relevance.has_action:
                relevance.role = CharacterRole.ACTIVE
            elif relevance.mention_count > 0:
                relevance.role = CharacterRole.PASSIVE
            else:
                relevance.role = CharacterRole.BACKGROUND
            
            relevances.append(relevance)
        
        return relevances
    
    def build_compressed_state_block(
        self,
        novel_id: str,
        chapter_number: int,
        beat_description: str,
        previous_state_hashes: dict,
    ) -> str:
        """构建压缩后的角色状态锁
        
        根据 CharacterRole 分级，为不同角色生成不同详细程度的注入文本
        """
        relevances = self.classify_characters(
            novel_id, chapter_number, beat_description, previous_state_hashes
        )
        
        parts = []
        total_tokens = 0
        
        for rel in relevances:
            char = self._get_character(novel_id, rel.character_id)
            vector = self._get_state_vector(novel_id, rel.character_id)
            
            if rel.role == CharacterRole.POV_CORE:
                # 完整注入
                block = vector.to_prompt_block()
                parts.append(block)
                total_tokens += self.BUDGET[CharacterRole.POV_CORE]
                
            elif rel.role == CharacterRole.ACTIVE:
                # 精简注入：当前情绪 + 紧张习惯 + 口头禅
                lines = [f"[{char.name} · 精简状态锁]"]
                if vector.current_emotion.value != "平静":
                    lines.append(f"当前：{vector.current_emotion.value}")
                lines.append(f"紧张时：{vector.nervous_habit}")
                if vector.verbal_tic:
                    lines.append(f"口头禅：{vector.verbal_tic}")
                parts.append("\n".join(lines))
                total_tokens += self.BUDGET[CharacterRole.ACTIVE]
                
            elif rel.role == CharacterRole.PASSIVE:
                # 极简注入：名字 + 核心标识
                line = f"[{char.name}"
                if vector.current_emotion.value != "平静":
                    line += f" · {vector.current_emotion.value}"
                line += "]"
                parts.append(line)
                total_tokens += self.BUDGET[CharacterRole.PASSIVE]
                
            else:
                # 仅名字
                parts.append(f"[在场: {char.name}]")
                total_tokens += self.BUDGET[CharacterRole.BACKGROUND]
        
        return "\n".join(parts)
    
    def _compute_state_hash(self, char) -> str:
        """计算角色状态的哈希值（用于差分检测）"""
        import hashlib
        state_str = f"{char.id}:{char.current_emotion.value}:{char.physical_condition}"
        return hashlib.md5(state_str.encode()).hexdigest()[:8]
    
    # ... 辅助方法省略（_is_pov_character, _has_dialogue_in_beat 等）
```

#### 12.5.3 压缩后的 T0 配额调整

采用动态压缩后，T0 配额可从 40% 回落至 30%：

```python
# context_budget_allocator.py 配额调整 — 动态压缩版

# V10 动态压缩：T0 降至 30%
T0_BUDGET_RATIO = 0.30   # 30% 给 T0（动态压缩后释放 10%）
T1_BUDGET_RATIO = 0.28   # 28% 给 T1（恢复 +5%）
T2_BUDGET_RATIO = 0.32   # 32% 给 T2（恢复 +4%）
T3_BUDGET_RATIO = 0.10   # 10% 给 T3（恢复 +1%）

# 角色状态锁 Token 预算调整
MAX_CHARACTER_STATE_TOKENS = 800     # 原 1500 → 800（动态压缩）
MAX_BEHAVIOR_PROTOCOL_TOKENS = 600   # 原 800 → 600（精简行为协议表述）
```

T0 槽位优先级重排（压缩版）：

| 优先级 | 槽位名 | 最大 tokens | 变更 | 说明 |
|--------|--------|------------|------|------|
| 135 | LIFECYCLE_DIRECTIVE | 600 | — | — |
| 132 | BEHAVIOR_PROTOCOL | 600 | ↓200 | 精简表述，去除冗余示例 |
| 130 | STORY_ANCHOR | 500 | — | — |
| 125 | FACT_LOCK | 2500 | — | — |
| 122 | CHARACTER_STATE_VECTORS | 800 | ↓700 | 动态压缩（核心完整+边缘精简） |
| 120 | SCARS_AND_MOTIVATIONS | 1500 | — | — |
| 115 | COMPLETED_BEATS | 2000 | — | — |

#### 12.5.4 配额释放收益

| 指标 | V9 (40% T0) | V10 (30% T0) | 改善 |
|------|------------|-------------|------|
| T0 占比 | 40% | 30% | ↓10% |
| T1 可用空间 | 23% | 28% | ↑5% |
| T2 可用空间 | 28% | 32% | ↑4% |
| 角色状态锁 Token | 1500 | 800 (核心~200×2+边缘~50×8) | ↓47% |
| 因果链可用空间 | ~5700T | ~7000T | ↑23% |
| 最近章节可用空间 | ~7000T | ~8000T | ↑14% |
| 剧情连贯性风险 | 中 | 低 | ↓ |

### 12.6 前端展示集成

```typescript
// frontend/src/types/anti-ai.ts

export interface ClicheHit {
  pattern: string
  text: string
  start: number
  end: number
  severity: 'critical' | 'warning' | 'info'
  category: string
  replacementHint: string
}

export interface AntiAIAuditResult {
  totalIssues: number
  criticalIssues: number
  humanScore: number       // 0-100
  categoryBreakdown: Record<string, number>
  topViolations: Array<{
    position: number
    text: string
    category: string
    hint: string
  }>
  rewriteSuggestions: Array<{
    original: string
    suggestion: string
    category: string
  }>
}

export interface AntiAIMetrics {
  metaphorDensity: number
  emotionLabelRate: number
  microExpressionCount: number
  clichePatternCount: number
  actionBasedEmotionRatio: number
  dialogueSubtextRatio: number
  sensoryDetailDensity: number
  characterDifferentiation: number
}
```

```typescript
// frontend/src/api/anti-ai.ts

import { apiClient } from '@/utils/api'
import type { AntiAIAuditResult, AntiAIMetrics } from '@/types/anti-ai'

export const antiAiApi = {
  /** 获取章节 Anti-AI 审计结果 */
  getAuditResult(novelId: string, chapterNumber: number): Promise<AntiAIAuditResult> {
    return apiClient.get(
      `/novels/${novelId}/chapters/${chapterNumber}/anti-ai-audit`
    ) as unknown as Promise<AntiAIAuditResult>
  },

  /** 获取 Anti-AI 指标 */
  getMetrics(novelId: string, chapterNumber: number): Promise<AntiAIMetrics> {
    return apiClient.get(
      `/novels/${novelId}/chapters/${chapterNumber}/anti-ai-metrics`
    ) as unknown as Promise<AntiAIMetrics>
  },

  /** 触发定向修文 */
  requestRewrite(novelId: string, chapterNumber: number, violations: string[]): Promise<{ content: string }> {
    return apiClient.post(
      `/novels/${novelId}/chapters/${chapterNumber}/anti-ai-rewrite`,
      { violation_ids: violations }
    ) as unknown as Promise<{ content: string }>
  },
}
```

### 12.6 API 端点设计

```python
# interfaces/api/v1/anti_ai.py

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter(prefix="/novels/{novel_id}/chapters/{chapter_number}", tags=["anti-ai"])


class ClicheHitResponse(BaseModel):
    pattern: str
    text: str
    start: int
    end: int
    severity: str
    category: str
    replacement_hint: str


class AntiAIAuditResponse(BaseModel):
    total_issues: int
    critical_issues: int
    human_score: float
    category_breakdown: dict
    top_violations: List[dict]
    rewrite_suggestions: List[dict]


class AntiAIRewriteRequest(BaseModel):
    violation_ids: List[str] = []


class AntiAIRewriteResponse(BaseModel):
    content: str


@router.get("/anti-ai-audit", response_model=AntiAIAuditResponse)
async def get_anti_ai_audit(novel_id: str, chapter_number: int):
    """获取章节 Anti-AI 审计结果"""
    # 调用 AntiAIAuditor.audit_chapter()
    ...


@router.get("/anti-ai-metrics")
async def get_anti_ai_metrics(novel_id: str, chapter_number: int):
    """获取 Anti-AI 文风指标"""
    ...


@router.post("/anti-ai-rewrite", response_model=AntiAIRewriteResponse)
async def request_anti_ai_rewrite(
    novel_id: str,
    chapter_number: int,
    request: AntiAIRewriteRequest,
):
    """触发 Anti-AI 定向修文"""
    ...
```

---

## 13. 附录：禁用词库与规则清单

### 13.1 绝对禁用词汇（Logit Bias -100）

| 词汇 | 类别 | 严重性 | 替换策略 |
|------|------|--------|---------|
| 一丝 | 微表情 | warning | 用具体动作替代 |
| 不易察觉 | 微表情 | warning | 要么可察觉，要么别写 |
| 嘴角上扬 | 微表情 | critical | 写完整姿态变化 |
| 嘴角勾起 | 微表情 | critical | 写完整姿态变化 |
| 眼里闪过 | 微表情 | critical | 用对话或动作替代 |
| 指尖泛白 | 微表情 | critical | 用行为传递紧张 |
| 指节泛白 | 微表情 | critical | 用行为传递紧张 |
| 下意识 | 微表情 | warning | 写完整的动作链 |
| 无意识 | 微表情 | warning | 写完整的动作链 |
| 生理性 | 生理 | critical | 直接写生理反应 |
| 生理性泪水 | 生理 | critical | 用差异化哭泣写法 |
| 不容置疑 | 声线 | critical | 用对白力度表现 |
| 不容置喙 | 声线 | critical | 用对白力度表现 |
| 投入心湖 | 比喻意象 | critical | 禁止心湖意象 |
| 泛起涟漪 | 比喻意象 | critical | 禁止涟漪意象 |
| 荡起涟漪 | 比喻意象 | critical | 禁止涟漪意象 |
| 精致人偶 | 比喻意象 | critical | 用具体外貌/姿态描写 |
| 像小兔子 | 动物比喻 | critical | 禁止动物比喻 |
| 像小鹿 | 动物比喻 | critical | 禁止动物比喻 |
| 像小猫 | 动物比喻 | critical | 禁止动物比喻 |
| 像小兽 | 动物比喻 | critical | 禁止动物比喻 |
| 幼兽 | 动物比喻 | critical | 禁止动物比喻 |
| 四肢百骸 | 俗套 | critical | 用具体身体部位 |
| 共犯 | 严禁词 | critical | 删除或换词 |
| 该死 | 严禁词 | warning | 删除或换词 |
| 见鬼 | 严禁词 | warning | 删除或换词 |
| 极其 | 严禁词 | warning | 删除或减少程度词 |
| 虔诚 | 俗套 | warning | 用具体行为替代 |
| 膜拜 | 俗套 | warning | 用具体行为替代 |
| 死死 | 严禁词 | critical | 删除或换词 |

### 13.2 禁用短语

| 短语 | 类别 | 替换策略 |
|------|------|---------|
| 精密仪器 | 比喻 | 用具体的精确描述 |
| 磨人的小妖精 | 俗套 | 删除 |
| 要我的命 | 夸张 | 用具体感受替代 |
| 仿佛一折就断 | 比喻 | 写具体的脆弱表现 |
| 轻描淡写 | 俗套 | 写具体的无所谓的动作 |
| 角落上扬露出一丝微笑 | 微表情 | 写完整姿态或不写 |
| 眼里显现出光芒 | 微表情 | 用对话或动作替代 |
| 带着XXX的口吻 | 声线 | 用对白标点和断句 |
| 用XXX的语气 | 声线 | 用对白标点和断句 |
| 充满了XXX的味道 | 声线 | 用对白本身表现 |
| 声音比寒冰更冰冷 | 声线 | 删掉，让对白自身有力度 |
| 每一个字都带着XXX | 声线 | 删掉，让对白自身有力度 |
| 话语充满书卷气 | 声线 | 用具体用词表现 |

### 13.3 禁用句式模式

| 模式 | 正则 | 替换策略 |
|------|------|---------|
| 不是…而是… | `不是[^。，？！]{1,20}而是` | 转为直接叙述 |
| 不是…只是… | `不是[^。，？！]{1,20}只是` | 转为直接叙述 |
| 仿佛…般 | `仿佛[^。，]{1,8}般` | 用感官细节替代 |
| 宛如…般 | `宛如[^。，]{1,8}般` | 用感官细节替代 |
| 犹如…般 | `犹如[^。，]{1,8}般` | 用感官细节替代 |
| 如同…一般 | `如同[^。，]{1,8}一般` | 用感官细节替代 |
| 像…一样 | `[^，。]像[^，。]{1,10}一样` | 用感官细节替代 |
| X分…Y分 | `[三四五六七八九]分[^，。]{1,6}[七八九]分` | 删除数字量化 |
| 破折号（正文） | `——` | 用句号断句替代 |

### 13.4 禁用比喻意象清单

| 意象 | 禁用理由 |
|------|---------|
| 心湖 | AI 高频俗套 |
| 涟漪 | AI 高频俗套 |
| 藤蔓 | AI 高频俗套 |
| 石子 | AI 高频俗套 |
| 针 | AI 高频俗套 |
| 蛇 | AI 高频俗套 |
| 淬毒 | AI 高频俗套 |
| 小兔子/小鹿/天使/恶魔 | 小动物/拟人比喻 |
| 冰山/火焰/暴风雨 | 自然意象俗套 |
| 海洋/深渊 | 自然意象俗套 |
| 阳光/月光/星光 | 光线意象俗套 |
| 花朵/蔷薇 | 植物意象俗套 |
| 野兽/猛兽 | 动物比喻俗套 |

### 13.5 面部大忌词汇

| 禁用 | 替代思路 |
|------|---------|
| 眼神冰冷 | 写对话时的具体反应 |
| 深邃 | 删除或用具体描述 |
| 暗了暗 | 写具体的视线方向/停留时间 |
| 眸色一沉 | 写完整姿态变化 |
| 眉头微皱 | 写手部动作替代 |
| 邪魅一笑 | 删除，用对话内容本身 |
| 似笑非笑 | 写具体的嘴角以外部位的变化 |

### 13.6 身体大忌词汇

| 禁用 | 替代思路 |
|------|---------|
| 青筋暴起 | 写紧握的物体变形/碎裂 |
| 呼吸一滞 | 写说话时的停顿 |
| 倒吸一口凉气 | 删除，用沉默替代 |
| 喉结微滚 | 写喝水/清嗓子等具体动作 |
| 浑身一震 | 写手中的东西掉了/脚步停了 |
| 身子一僵 | 写某动作中断 |

### 13.7 情绪表达替换速查表

| 情绪 | ❌ AI 套路 | ✅ 人味写法（示例） |
|------|----------|------------------|
| 愤怒 | 眼神变冷，周身气压降低 | 说话变慢变清楚；笑了但眼睛没动；开始收拾东西 |
| 悲伤 | 泪水模糊了视线 | 鼻子先红声音发闷；没哭出来但嘴在抖；低头时水滴落手背愣了一下 |
| 紧张 | 指尖泛白攥紧拳头 | 脚趾蜷缩；咬嘴唇内侧；开始说废话；后背出汗 |
| 恐惧 | 呼吸一滞浑身一僵 | 往后退了半步；手摸向腰间；声音突然变轻 |
| 喜悦 | 嘴角上扬眼里闪过光芒 | 步子变快了；把手里的事放下了；说了句不着边际的话 |
| 尴尬 | 脸色微红不自然地笑 | 开始找东西；话说到一半岔开；擦了一个不存在的污渍 |
| 嫉妒 | 眸色暗了暗 | 说话变酸了；突然提到另一个人的名字；手上的动作变重了 |

---

## 14. 工程落地优先级与实施路线图

### 14.1 优先级矩阵

```
影响 ↑
     │  ┌───────────────┐  ┌────────────────┐
     │  │ P0: Enhanced   │  │ P0: Positive   │
     │  │ ClicheScanner  │  │ Framing 重构   │
     │  │ (替换现有10模式)│  │ (Prompt核心)   │
     │  └───────────────┘  └────────────────┘
     │  ┌───────────────┐  ┌────────────────┐
     │  │ P1: Anti-AI    │  │ P1: Character  │
     │  │ Audit 集成     │  │ State Vector   │
     │  │ (章后管线)     │  │ (T0注入)       │
     │  └───────────────┘  └────────────────┘
     │  ┌───────────────┐  ┌────────────────┐
     │  │ P2: Stream AC  │  │ P2: Logit Bias │
     │  │ Scanner        │  │ Token Guard    │
     │  │ (实时拦截)     │  │ (推理侧拦截)   │
     │  └───────────────┘  └────────────────┘
     │  ┌───────────────┐  ┌────────────────┐
     │  │ P3: Anti-AI    │  │ P3: YAML       │
     │  │ Learning       │  │ Protocol       │
     │  │ (采血学习)     │  │ (规则引擎)     │
     │  └───────────────┘  └────────────────┘
     └──────────────────────────────────────────→ 实施难度
```

### 14.2 分阶段实施计划

#### Phase 1：即时生效（1-2 天）

| 任务 | 改动文件 | 预期效果 |
|------|---------|---------|
| EnhancedClicheScanner 替换 | `application/audit/services/cliche_scanner.py` | 检测模式从 10 → 35+，覆盖全部禁用词 |
| Prompt 正向行为映射重构 | `infrastructure/ai/prompts/prompts_defaults.json` | 将"禁令清单"转为"行为协议"，预期遵循率提升 15-25% |
| chapter-generation-main 协议化 | `prompts_defaults.json` system 字段 | 结构化 P1-P5 + B1-B8 + R1-R8 |

**核心改动示例**：

```python
# 将现有 cliche_scanner.py 的 AI_CLICHE_PATTERNS 替换为增强版
# 直接在现有文件中扩展即可，无需新建文件

AI_CLICHE_PATTERNS = [
    # ═══ 原有 10 模式保留 ═══
    (r"熊熊(烈火|怒火|火焰|燃烧)", "熊熊系列"),
    (r"(眼中|眸中|目光中)闪过一丝", "眼神闪过系列"),
    # ... 保留原有 ...

    # ═══ 新增：微表情/微动作 ═══
    (r"嘴角(勾起|上扬|扬起|浮现|翘起)", "嘴角微表情"),
    (r"(指尖|指节)(泛白|发白)", "指尖泛白"),
    (r"不易察觉", "不易察觉"),
    
    # ═══ 新增：声线描述 ═══
    (r"带着.{1,8}(口吻|语气)", "带语气前缀"),
    (r"不容(置疑|置喙)", "不容置疑"),
    
    # ═══ 新增：比喻句式 ═══
    (r"(仿佛|宛如|犹如|恰似|酷似).{1,15}(般|一般|似的|一样)", "比喻句式"),
    (r"投入.{0,6}(心湖|水面).{0,6}(泛起|荡起|漾起)涟漪", "心湖涟漪"),
    
    # ═══ 新增：生理性系列 ═══
    (r"生理性(泪水|水雾|液体|汽水|盐水)", "生理性液体"),
    (r"生理性", "生理性前缀"),
    
    # ═══ 新增：情绪标签 ═══
    (r"(心中|内心)(泛起|涌起|掀起|燃起).{1,10}(波澜|怒火|暖流|感动)", "心中波澜系列"),
    
    # ═══ 新增：句式 ═══
    (r"不是[^。，？！]{1,20}(而是|只是)", "不是而是句式"),
    
    # ═══ 新增：小动物比喻 ═══
    (r"像(小兔子|小鹿|小猫|小兽|幼兽)", "小动物比喻"),
    
    # ═══ 新增：面部/身体大忌 ═══
    (r"眸色一沉|眼神暗了暗|眉头微皱|邪魅一笑|似笑非笑", "面部大忌"),
    (r"呼吸一滞|倒吸一口凉气|喉结微滚|浑身一震|身子一僵", "身体大忌"),
    (r"四肢百骸", "四肢百骸"),
]
```

#### Phase 2：短期增强（3-7 天）

| 任务 | 新增文件 | 依赖 |
|------|---------|------|
| 角色状态向量注入 | `character_state_vector.py` | Bible 仓储 + 新 state_repo |
| T0 槽位扩展 | `context_budget_allocator.py` 修改 | Phase 1 完成 |
| Anti-AI 审计集成 | `anti_ai_audit.py` | EnhancedClicheScanner |
| 章后管线集成 | `autopilot_daemon.py` 修改 | Anti-AI Audit |

#### Phase 3：中期架构（1-3 周）

| 任务 | 新增文件 | 依赖 |
|------|---------|------|
| StreamACScanner 实时拦截 | `stream_ac_scanner.py` | pyahocorasick 依赖 |
| TokenGuard Logit Bias | `token_guard.py` | tiktoken 依赖 |
| 流式生成管线改造 | `auto_novel_generation_workflow.py` | Phase 2 + 3 |
| API 端点 + 前端展示 | `interfaces/api/v1/anti_ai.py` + Vue 组件 | Phase 2 |

#### Phase 4：长期优化（持续）

| 任务 | 描述 |
|------|------|
| Anti-AI Learning | 从采血差异中自动学习新规则 |
| YAML Protocol 规则引擎 | 动态加载/热更新规则 |
| 跨模型适配 | 不同模型（GPT/Claude/国产）的 Logit Bias 差异化 |
| 人味评分仪表盘 | 前端可视化 human_score 趋势 |
| 规则 A/B 测试 | 不同规则集对生成质量的对比实验 |

### 14.3 风险与缓解

| 风险 | 概率 | 影响 | 缓解策略 |
|------|------|------|---------|
| Logit Bias 中文 Token 碎片化 | 高 | 中 | 优先依赖 AC 自动机而非 Logit Bias |
| 正向行为映射增加 Prompt 长度 | 高 | 中 | 严格控制 ≤ 800 tokens，示例每条1行 |
| 流式回滚导致生成延迟 | 中 | 高 | 限制回滚 ≤ 2 次，超限放行 |
| 过度过滤导致文本干瘪 | 中 | 高 | 区分 critical/warning/info，warning 仅标记不拦截 |
| 角色状态向量与 Bible 冗余 | 低 | 低 | 状态向量侧重动态状态，Bible 侧重静态设定 |
| 规则集膨胀难以维护 | 中 | 中 | YAML Protocol 分级管理 + 版本控制 |

### 14.4 效果度量指标

| 指标 | 基线（当前） | 目标（3个月后） | 测量方法 |
|------|------------|---------------|---------|
| 比喻密度 | ~3.2次/千字 | < 1.0次/千字 | EnhancedClicheScanner |
| 直接情绪标签率 | ~2.8次/千字 | < 0.5次/千字 | 正则扫描 |
| 微表情出现率 | ~1.5次/千字 | < 0.2次/千字 | AC 自动机 |
| 角色反应差异化 | ~0.3（高重合） | > 0.7（低重合） | 词汇重合度算法 |
| 人味评分(human_score) | ~45/100 | > 75/100 | AntiAIMetrics 综合 |
| 文风指纹匹配度 | ~0.68 | > 0.82 | VoiceFingerprint |
| 章后修文触发率 | ~40% | < 15% | autopilot_daemon 日志 |

---

## 15. 进阶专题：长上下文生成中的指令穿透专项治理

### 15.1 问题的本质

PlotPilot 的章节生成通常在 3000-8000 字范围，节拍级生成每次 500-1500 字。在多节拍连续生成时，上下文窗口中的规则集逐渐被"推出"注意力核心区域。

```
多节拍生成时的注意力衰减：

节拍1  节拍2  节拍3  节拍4  节拍5
 │      │      │      │      │
 ▼      ▼      ▼      ▼      ▼
[规则]  [规则]  [规则]  [规则]  [规则]
[大纲]  [大纲]  [大纲]  [大纲]  [大纲]
[节拍1] [节拍1] [节拍1] [节拍1] [节拍1]
        [节拍2] [节拍2] [节拍2] [节拍2]
                [节拍3] [节拍3] [节拍3]
                        [节拍4] [节拍4]
                                [节拍5]

规则注意力权重:  0.85 → 0.72 → 0.58 → 0.41 → 0.28
穿透概率:         8%  → 18% → 32% → 48% → 62%
```

### 15.2 中段刷新策略（Mid-generation Refresh）

在多节拍生成中，每隔 N 个节拍插入一条"规则刷新"消息：

```python
# application/engine/services/mid_generation_refresh.py

REFRESH_TEMPLATE = """[系统校验] 规则遵循性检查：
- 情绪必须通过动作/环境暗示，禁止直接标签
- 禁止微表情（嘴角上扬/眼里闪过/指尖泛白）
- 禁止比喻（仿佛/宛如/犹如）
- 禁止"不是…而是…"句式
- 每个角色的反应方式必须不同
以上规则你是否遵守？如果是，继续生成。"""

class MidGenerationRefresh:
    """多节拍生成中的规则刷新"""
    
    def __init__(self, refresh_interval: int = 3):
        """
        Args:
            refresh_interval: 每隔几个节拍刷新一次
        """
        self.refresh_interval = refresh_interval
    
    def should_refresh(self, beat_index: int) -> bool:
        """判断是否需要在本节拍前刷新规则"""
        return beat_index > 0 and beat_index % self.refresh_interval == 0
    
    def get_refresh_message(self, beat_index: int, total_beats: int) -> str:
        """获取刷新消息"""
        progress = f"({beat_index + 1}/{total_beats})"
        return f"{REFRESH_TEMPLATE}\n当前进度：{progress}"
```

### 15.3 尾段增强策略（Tail Reinforcement）

当生成进度超过 70% 时，在 Prompt 尾部追加强化约束：

```python
def build_tail_reinforcement(beat_index: int, total_beats: int) -> str:
    """当生成进度超过70%时，追加强化约束"""
    if (beat_index + 1) / total_beats < 0.7:
        return ""
    
    return """
[尾段强化] 即将完成本章。注意：
1. 收束阶段最容易放松警惕，此时最需严格执行行为协议
2. 结尾段落禁止用比喻收束（如"仿佛一切都在…"）
3. 最后一句必须是具体的画面、动作或对话，禁止抽象总结
"""
```

### 15.4 生成后验证的分层策略

```python
class PostGenerationValidator:
    """生成后验证的分层策略"""
    
    def validate(self, content: str, beat_index: int, total_beats: int) -> dict:
        """分层验证生成结果"""
        
        progress = (beat_index + 1) / total_beats
        scanner = EnhancedClicheScanner()
        hits = scanner.scan(content)
        
        # 根据生成位置调整阈值
        if progress > 0.7:
            # 尾段：更严格
            critical_threshold = 1  # 1个critical就标记
            warning_threshold = 3
        else:
            # 前段：稍宽松
            critical_threshold = 2
            warning_threshold = 5
        
        critical_count = sum(1 for h in hits if h.severity == "critical")
        warning_count = sum(1 for h in hits if h.severity == "warning")
        
        return {
            "needs_rewrite": critical_count >= critical_threshold,
            "needs_flag": warning_count >= warning_threshold,
            "critical_count": critical_count,
            "warning_count": warning_count,
            "progress": progress,
            "hits": hits,
        }
```

---

## 16. 跨模型适配指南

### 16.1 不同模型的 Logit Bias 差异

| 模型 | Tokenizer | 中文支持 | Logit Bias 效果 | 推荐替代方案 |
|------|-----------|---------|----------------|------------|
| GPT-4o | cl100k_base | 中文多 token 碎片 | 中等 | AC 自动机优先 |
| GPT-4 | cl100k_base | 中文多 token 碎片 | 中等 | AC 自动机优先 |
| Claude | 自有 tokenizer | 中文处理更好 | 不支持 Logit Bias | 纯 Prompt + AC 自动机 |
| 国产模型(通义/文心) | 各自不同 | 原生中文支持较好 | 部分支持 | Prompt 为主 + 生成后过滤 |
| DeepSeek | 自有 tokenizer | 中文原生 | 部分支持 | Prompt + AC 自动机 |

### 16.2 适配层设计

```python
# application/engine/services/model_adapter.py

from abc import ABC, abstractmethod
from typing import Dict, Optional

class ModelAdapter(ABC):
    """模型适配器 — 不同模型的 Anti-AI 策略差异化"""
    
    @abstractmethod
    def get_logit_bias(self, forbidden_phrases: list) -> Optional[Dict[str, int]]:
        """获取 Logit Bias（不支持则返回 None）"""
        pass
    
    @abstractmethod
    def get_prompt_strategy(self) -> str:
        """获取 Prompt 策略类型"""
        pass
    
    @abstractmethod
    def get_recommended_frequency_penalty(self) -> float:
        pass
    
    @abstractmethod
    def get_recommended_presence_penalty(self) -> float:
        pass


class GPTAdapter(ModelAdapter):
    def get_logit_bias(self, forbidden_phrases: list) -> Optional[Dict[str, int]]:
        guard = TokenGuard()
        return guard.build_logit_bias()
    
    def get_prompt_strategy(self) -> str:
        return "protocol"  # 协议化 Prompt
    
    def get_recommended_frequency_penalty(self) -> float:
        return 0.3
    
    def get_recommended_presence_penalty(self) -> float:
        return 0.1


class ClaudeAdapter(ModelAdapter):
    def get_logit_bias(self, forbidden_phrases: list) -> Optional[Dict[str, int]]:
        return None  # Claude 不支持 Logit Bias
    
    def get_prompt_strategy(self) -> str:
        return "xml_protocol"  # 使用 XML 标签结构化（Claude 对 XML 遵循率更高）
    
    def get_recommended_frequency_penalty(self) -> float:
        return 0.0  # Claude 不支持此参数
    
    def get_recommended_presence_penalty(self) -> float:
        return 0.0


class DomesticModelAdapter(ModelAdapter):
    """国产模型适配（通义/文心/DeepSeek 等）"""
    
    def get_logit_bias(self, forbidden_phrases: list) -> Optional[Dict[str, int]]:
        # 国产模型对中文 Logit Bias 支持不一，保守返回 None
        return None
    
    def get_prompt_strategy(self) -> str:
        return "numbered_rules"  # 编号式规则（国产模型对编号遵循率较高）
    
    def get_recommended_frequency_penalty(self) -> float:
        return 0.2
    
    def get_recommended_presence_penalty(self) -> float:
        return 0.05


def get_adapter(model_name: str) -> ModelAdapter:
    """工厂方法"""
    if "gpt" in model_name.lower():
        return GPTAdapter()
    elif "claude" in model_name.lower():
        return ClaudeAdapter()
    else:
        return DomesticModelAdapter()
```

### 16.3 Claude 专用 XML Prompt 模板

Claude 对 XML 标签的遵循率显著高于普通文本，针对 Claude 的 Anti-AI 协议应使用 XML 结构：

```python
CLAUDE_ANTI_AI_PROTOCOL = """
<anti_ai_protocol>
  <core_rules>
    <rule id="P1" priority="highest">
      <condition>Writing any paragraph</condition>
      <action>Every paragraph must advance at least one of: plot facts, character relationships, suspense threads, information gap changes</action>
    </rule>
    <rule id="P2" priority="highest">
      <condition>Expressing emotion or atmosphere</condition>
      <action>Execute in order: sensory detail → action change → dialogue content. NEVER skip to emotion labels directly</action>
    </rule>
    <rule id="P3" priority="high">
      <condition>Multiple characters present</condition>
      <action>At least 2 characters must react differently. Reaction = background × physical state × stake in event</action>
    </rule>
  </core_rules>
  
  <forbidden_patterns>
    <pattern id="B1">Direct emotion labels ("他感到愤怒" "她很悲伤")</pattern>
    <pattern id="B2">Micro-expression snapshots (嘴角上扬/眼里闪过/指尖泛白)</pattern>
    <pattern id="B3">Simile structures (仿佛/宛如/犹如/像…一样)</pattern>
    <pattern id="B4">Voice/tone labels (带着XX的语气/声音比寒冰更冰冷)</pattern>
    <pattern id="B5">"不是A而是B" sentence structure</pattern>
    <pattern id="B6">Em-dashes in narrative text (——)</pattern>
    <pattern id="B7">Animal similes (像小兔子/小鹿/小兽)</pattern>
    <pattern id="B8">"生理性" prefix for any bodily reaction</pattern>
  </forbidden_patterns>
  
  <replacement_strategies>
    <strategy for="B1">Find the character's most likely micro-action at this moment</strategy>
    <strategy for="B2">Write full posture change, or let dialogue itself convey emotion</strategy>
    <strategy for="B3">Write current body temperature, light angle, fabric texture</strategy>
    <strategy for="B4">Use dialogue punctuation and rhythm to convey tone</strategy>
    <strategy for="B5">Convert to direct statement</strategy>
    <strategy for="B6">Use periods to create rhythm pauses</strategy>
    <strategy for="B7">Delete, use human action description</strategy>
    <strategy for="B8">Describe the physiological reaction directly</strategy>
  </replacement_strategies>
</anti_ai_protocol>
"""
```

---

## 17. 总结与核心洞察

### 17.1 诊断总结

| 维度 | 核心问题 | 根因 | 首选方案 |
|------|---------|------|---------|
| Prompt 层 | 否定指令激活禁用 Token | Transformer Self-Attention 预热 | 正向行为映射 |
| 规则层 | 抽象约束无法精确执行 | 模型需要 condition→action 映射 | YAML Protocol 结构化 |
| 推理层 | 长上下文规则遵循率骤降 | 注意力稀释 + 位置衰减 | Logit Bias + AC 自动机 |
| 上下文层 | 角色锚点在长生成中遗忘 | 一次性注入无强制对齐 | 角色状态向量 T0 注入 |
| 审计层 | 检测模式覆盖不足 | 现有仅 10 个模式 | EnhancedClicheScanner 35+ |
| 反馈层 | 采血差异未反哺生成 | 缺乏自动学习闭环 | Anti-AI Learning |

### 17.2 三条核心原则

1. **正向映射优于否定禁止**：告诉模型"遇到X时做Y"，而非"不要做X"
2. **推理侧拦截优于 Prompt 约束**：Logit Bias 和 AC 自动机的遵循率远高于 Prompt 指令
3. **闭环学习优于静态规则**：从作者的修改差异中持续学习，让规则随创作演化

### 17.3 预期收益

按照 Phase 1-4 逐步实施后，预期在 3 个月内实现：

- **AI 味指标下降 70%**：比喻密度从 3.2 降至 < 1.0 次/千字
- **人味评分提升 65%**：human_score 从 45 提升至 > 75
- **章后修文率下降 60%**：从 40% 降至 < 15%
- **角色差异化提升 130%**：差异化评分从 0.3 提升至 > 0.7
- **指令穿透率下降 80%**：长上下文尾段穿透率从 62% 降至 < 12%

---

> **文档维护说明**：本文档应与 `prompts_defaults.json` 和 `anti_ai_protocol.yaml` 保持同步。当禁用词库或规则发生变更时，需同步更新本文档第 13 章附录。建议每月 review 一次效果度量指标，根据实际数据调整规则优先级和阈值。

---

## 18. 架构综合评估与优化策略

> **评审日期**: 2026-05-09  
> **评审维度**: 系统工程与计算复杂性 × 文本质感降维计算 × 落地可行性  
> **评审结论**: 七层纵深防御架构逻辑严密，但在中文 Token 碎片化误伤、回滚算力损耗、上下文配额挤压、过度去修辞化四个方面存在可优化的结构性隐患。本章给出针对性的工程修正方案。

### 18.1 架构师视角：系统工程与计算复杂性诊断

#### 18.1.1 防御前置与流式干预——架构最优解确认

核心亮点在于 Layer 3 和 Layer 4。大模型长文本生成的指令遗忘是注意力机制的数学必然，仅靠 Layer 1/2 的 Prompt 优化无法根除。引入 AC 自动机进行 $O(n)$ 复杂度的流式扫描，并在推理侧（Inference）进行硬拦截，是解决指令穿透的唯一绝对路径。

```
防御有效性与成本象限：

效果 ↑
     │                    ┌──────────────────┐
     │                    │ ★ AC 自动机流式扫描 │  ← 最优解
     │                    │   O(n), 确定性拦截  │
     │   ┌──────────────┐└──────────────────┘
     │   │ Logit Bias   │
     │   │ (中文高危)    │
     │   ├──────────────┤
     │   │ 正向行为映射  │
     │   │ (成本最低)    │
     │   └──────────────┘
     └──────────────────────────────────────────→ 实施成本
```

#### 18.1.2 状态向量化管理（State Injection）确认

Layer 5 采用 CharacterStateVector 并在上下文组装时提权至 T0 层级，有效解决了长线生成中角色设定的记忆漂移。强制所有字段非空（赋默认值）的设计，保证了 Prompt 结构的稳定性，降低了模型解析的随机性。

#### 18.1.3 架构隐患一：中文 Token 碎片化误伤

**问题**：Layer 3 的 Logit Bias 方案在中文场景下存在高危风险。如 `cl100k_base` 分词器会将一个中文字词拆分成多个 Token。对某个切片 Token 施加 -100 的偏置，极易导致其他包含该子 Token 的合法词汇生成崩溃（即"词汇表坍塌"）。

```
中文 Token 碎片化示例：

"嘴角" → Token[1234] + Token[5678]
"嘴角上扬" → Token[1234] + Token[5678] + Token[9012]

若对 Token[1234] 施加 -100 bias：
  ✅ 阻止了 "嘴角上扬" 的生成
  ❌ 同时阻止了 "嘴角抽搐" 等合法词汇的生成
  ❌ 可能影响包含相同子 Token 的完全无关词汇
```

**优化方案**：详见 [6.5 Logit Bias 中文降级策略](#65-logit-bias-中文降级策略)。

#### 18.1.4 架构隐患二：回滚重生成的算力损耗

**问题**：流式扫描触发的回滚机制（Rollback）虽然能保证绝对的安全，但成本极高。若在第 450 字检测到违规并截断重生成，前序的推理算力将全部沉没，且会显著增加端到端的延迟（TTFT 和 TPOT 波动）。

```
算力沉没示意：

Token 生成流: ───[1-450]───✕ 违规检测 ───→ 截断
                                │
                                ▼
              沉没算力 = 450 tokens × 推理成本/token
              重试成本 = 上下文前缀 + 重新生成
              延迟增加 = 沉没时间 + 重试时间
```

**优化方案**：详见 [7.3 缓冲队列分块验证策略](#73-缓冲队列分块验证策略chunked-buffer-strategy)。

#### 18.1.5 架构隐患三：上下文配额挤压

**问题**：T0 提权至 40%（包含 1500 Tokens 的角色状态和 800 Tokens 的行为协议）会导致留给 T1（因果链/剧情图谱）和 T2（最近章节）的物理空间受限。长远看，可能引发短期剧情连贯性下降。

```
配额挤压示意：

V8 (原)                    V9 Anti-AI 增强
┌──────────┐ 35%          ┌──────────┐ 40%
│   T0     │              │   T0     │ ← +5% (行为协议+状态锁)
├──────────┤ 25%          ├──────────┤ 23% ← -2%
│   T1     │              │   T1     │
├──────────┤ 30%          ├──────────┤ 28% ← -2%
│   T2     │              │   T2     │
├──────────┤ 10%          ├──────────┤  9% ← -1%
│   T3     │              │   T3     │
└──────────┘              └──────────┘
                              ⚠ T1+T2 合计减少 4%
                              ⚠ 长线剧情连贯性风险
```

**优化方案**：详见 [12.7 动态 T0 压缩策略](#127-动态-t0-压缩策略dynamic-state-summarization)。

### 18.2 专业小说家视角：文本质感的降维计算

#### 18.2.1 正向行为映射（Positive Framing）的价值确认

彻底摒弃了无效的"禁止写 X"逻辑，转为"遇到 X 必须执行 Y（感官/动作）"。这在文学上等同于强迫模型执行"冰山理论"，将情绪标签降维为物理交互，极大提升了文本的潜台词密度和"人味"。

```
文学降维示意：

情绪标签（AI味）           物理交互（人味）
┌──────────┐              ┌──────────────────────┐
│ "他感到愤怒" │ ──降维──→ │ "他说话变得很慢，      │
│              │          │  每个字都咬得很清楚。"  │
└──────────┘              └──────────────────────┘
   告诉读者                   让读者自己感受到
   信息密度: 1               信息密度: 3+ (语速+咬字+克制)
```

#### 18.2.2 反同质化协议确认

P3 规则（角色差异化 = 背景 × 身体状态 × 利益关系）和专有紧张习惯的设定，切断了 AI 使用单一模板应对所有冲突的捷径，赋予了角色独立的行事逻辑。

#### 18.2.3 指标量化（Anti-AIMetrics）确认

将"文风"这种不可名状的概念，拆解为比喻密度、情绪标签率、潜台词比例等硬性指标。这使得系统具备了可测试性和可迭代性。

#### 18.2.4 文学死角：过度去修辞化风险

**问题**：极其严格的比喻禁令和破折号禁令，可能会导致文本走向另一个极端——干瘪的说明文风格。部分高级的通感比喻是文学张力的重要来源，一刀切的硬拦截可能会扼杀文本的灵气。

```
过度去修辞化的风险谱：

AI味浓 ←────────────────────────────────→ 干瘪说明文
  │                                              │
  │  ┌──────────────────┐                        │
  │  │ 当前系统目标区间  │                        │
  │  │ (去除俗套比喻)   │                        │
  │  └──────────────────┘                        │
  │                    ┌──────────────────┐       │
  │                    │ 理想目标区间      │       │
  │                    │ (保留高级通感比喻) │       │
  │                    └──────────────────┘       │
  │                                                 │
  系统若不设白名单 → 容易滑向右侧极端
```

**典型场景**：

| 场景 | ❌ 俗套比喻（应拦截） | ✅ 高级通感比喻（应保留） | 判定依据 |
|------|----------------------|--------------------------|---------|
| 表达记忆 | "记忆如潮水般涌来" | "那个夏天装在一块冰的碎裂声里" | 是否使用了陈旧意象 |
| 表达恐惧 | "心跳像鼓点一样" | "恐惧是舌尖上的铁锈味" | 是否构成通感且有新意 |
| 表达距离 | "仿佛隔了一个世界" | "她的声音从很远的地方来，像穿过了一整面墙的棉花" | 是否有物理交互质感 |
| 梦境/幻觉 | — | 应完全允许比喻 | 叙事层特殊性 |
| 精神极端状态 | — | 应允许风格扩张 | 人物主观体验 |

**优化方案**：详见 [5.4 场景化白名单机制](#54-场景化白名单机制allowlist-exception)。

### 18.3 优化策略汇总与实施优先级

#### 18.3.1 四项优化策略优先级矩阵

```
收益 ↑
     │  ┌────────────────────┐
     │  │ ★ P0: 缓冲队列分块  │
     │  │   验证策略(Chunked   │
     │  │   Buffer Strategy)  │
     │  │   → 降低回滚算力损耗│
     │  └────────────────────┘
     │  ┌─────────────────┐  ┌─────────────────────┐
     │  │ P1: 动态 T0 压缩 │  │ P1: Logit Bias 中文  │
     │  │ → 释放上下文空间 │  │   降级策略           │
     │  │                  │  │ → 消除词汇表坍塌风险 │
     │  └─────────────────┘  └─────────────────────┘
     │  ┌────────────────────┐
     │  │ P2: 场景化白名单    │
     │  │ → 避免过度去修辞化  │
     │  └────────────────────┘
     └────────────────────────────────────────────→ 实施难度
```

#### 18.3.2 优化策略与原文章节映射

| 优化策略 | 回写章节 | 实施阶段 | 依赖 | 预期收益 |
|---------|---------|---------|------|---------|
| Logit Bias 中文降级 | 6.5 新增 | Phase 2 | tiktoken 分析工具 | 消除词汇表坍塌风险，拦截核心转至 AC 自动机 |
| 缓冲队列分块验证 | 7.3 新增 | Phase 3 | StreamACScanner | 回滚算力损耗降低 60-80% |
| 动态 T0 压缩 | 12.7 新增 | Phase 2 | CharacterStateManager | T0 配额从 40% 压制到 30%，释放 T1/T2 空间 |
| 场景化白名单 | 5.4 新增 | Phase 2 | anti_ai_protocol.yaml | 保留高级通感比喻，避免干瘪说明文风格 |

#### 18.3.3 优化后的预期收益修正

原第17.3节的预期收益保持不变，但以下指标需修正测量方法：

| 指标 | 原目标 | 修正后目标 | 修正理由 |
|------|--------|-----------|---------|
| 比喻密度 | < 1.0次/千字 | < 1.5次/千字（但高级通感比喻不计入） | 白名单豁免后，低俗比喻减少但保留高级比喻 |
| 人味评分 | > 75/100 | > 80/100 | T0 压缩后 T1/T2 空间增加，剧情连贯性提升 |
| 章后修文率 | < 15% | < 12% | 分块验证减少大段回滚，一次性通过率更高 |
| 生成延迟（P95） | 未设定 | 增长 < 15% | 缓冲队列将回滚延迟从 O(full) 降至 O(chunk) |

---

> **文档维护说明**：本文档应与 `prompts_defaults.json` 和 `anti_ai_protocol.yaml` 保持同步。当禁用词库或规则发生变更时，需同步更新本文档第 13 章附录。建议每月 review 一次效果度量指标，根据实际数据调整规则优先级和阈值。当架构评估结论发生变更时，需同步更新第 18 章评估结论及对应回写章节的标注。
