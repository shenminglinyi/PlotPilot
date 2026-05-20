# PlotPilot 世界观生成逻辑全景

> 版本：v1.0 · 生成日期：2026-05-19  
> 涵盖范围：世界观5维度框架、分阶段生成流程、SSE流式生成、双存储架构、前端交互

---

## 1. 总体架构概览

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                        世界观生成全景流水线                                    │
│                                                                                │
│  ┌────────────┐    ┌──────────────────────────────┐    ┌──────────────────┐   │
│  │  故事梗概   │───▶│  AutoBibleGenerator          │───▶│  双存储持久化     │   │
│  │  (premise) │    │  ┌──────────────────────┐    │    │  ┌────────────┐  │   │
│  └────────────┘    │  │ 文风公约 (style)      │    │    │  │ Worldbuilding│  │   │
│       │            │  ├──────────────────────┤    │    │  │ 表(ORM 15槽) │  │   │
│       ▼            │  │ 1.核心法则 core_rules │    │    │  └────────────┘  │   │
│  ┌────────────┐    │  │ 2.地理生态 geography  │    │    │  ┌────────────┐  │   │
│  │ 目标章节数  │    │  │ 3.社会结构 society    │    │    │  │Bible.world_ │  │   │
│  │ (chapters) │    │  │ 4.历史文化 culture    │    │    │  │settings(扩展)│  │   │
│  └────────────┘    │  │ 5.沉浸细节 daily_life │    │    │  └────────────┘  │   │
│                    │  └──────────────────────┘    │    └──────────────────┘   │
│                    │           │                   │            │              │
│                    │           ▼                   │            ▼              │
│                    │  ┌──────────────────────┐    │    ┌──────────────────┐   │
│                    │  │ 人物生成(characters)  │    │    │  合并读取API      │   │
│                    │  └──────────────────────┘    │    │  merge_worldbuild │   │
│                    │  ┌──────────────────────┐    │    │  ing_table_and_   │   │
│                    │  │ 地点生成(locations)   │    │    │  bible_slices     │   │
│                    │  └──────────────────────┘    │    └──────────────────┘   │
│                    └──────────────────────────────┘                            │
└────────────────────────────────────────────────────────────────────────────────┘
```

**核心数据流**：`故事梗概(premise) → 文风公约 + 5维度世界观 → 人物(基于世界观) → 地点(基于世界观+人物) → 知识库`

---

## 2. 领域模型：5维度框架

### 2.1 Worldbuilding 实体

文件：`domain/worldbuilding/worldbuilding.py`

```python
@dataclass
class Worldbuilding:
    """世界观构建实体 - 基于专业小说家的5维度框架"""
    id: str
    novel_id: str

    # 1. 核心法则与底层逻辑 (The Rules)
    power_system: str = ""      # 力量体系/科技树
    physics_rules: str = ""     # 物理规律
    magic_tech: str = ""        # 魔法/科技机制

    # 2. 地理与生态环境 (Geography & Ecology)
    terrain: str = ""           # 地形
    climate: str = ""           # 气候
    resources: str = ""         # 资源分布
    ecology: str = ""           # 生态链

    # 3. 社会结构与权力分配 (Society & Power)
    politics: str = ""          # 政治体制
    economy: str = ""           # 经济模式
    class_system: str = ""      # 阶级系统

    # 4. 历史、信仰与文化 (History & Culture)
    history: str = ""           # 关键历史事件
    religion: str = ""          # 宗教信仰
    taboos: str = ""            # 文化禁忌

    # 5. 沉浸感细节 (Daily Life)
    food_clothing: str = ""     # 衣食住行
    language_slang: str = ""    # 俚语口音
    entertainment: str = ""     # 娱乐方式
```

### 2.2 ORM 15槽位 vs LLM 扩展字段

**核心矛盾**：Worldbuilding ORM 实体只有 15 个字符串槽位（3+4+3+3+3），但 LLM 在 SSE 流式生成时会产出**扩展字段**（超出 15 个的字段）。

| 维度 | ORM 经典字段（3-4个） | LLM 扩展字段（3-4个额外） |
|------|----------------------|--------------------------|
| `core_rules` | power_system, physics_rules, magic_tech | cost_and_limitation, resource_scarcity |
| `geography` | terrain, climate, resources, ecology | forbidden_zones, urban_core, hidden_realms |
| `society` | politics, economy, class_system | power_structure, oppression_mechanism, class_division |
| `culture` | history, religion, taboos | worship, oaths_and_curses |
| `daily_life` | food_clothing, language_slang, entertainment | survival_tactics, market_reality, food_and_drink, slang_and_profanity |

### 2.3 维度定义（_DIMENSION_DEFS）

文件：`application/world/services/auto_bible_generator.py`

这是 LLM 生成时使用的完整字段定义，共 **30 个字段**（15 经典 + 15 扩展）：

```python
_DIMENSION_DEFS = {
    "core_rules": {
        "label": "核心法则",
        "fields": {
            "power_system": "力量体系/科技树的描述",
            "physics_rules": "物理规律的特殊之处",
            "magic_tech": "魔法或科技的运作机制",
            "cost_and_limitation": "力量使用的代价与限制",
            "resource_scarcity": "稀缺资源及其分配",
        },
    },
    "geography": {
        "label": "地理生态",
        "fields": {
            "terrain": "主要地形特征",
            "climate": "气候特点与环境",
            "resources": "自然资源分布",
            "ecology": "生态系统与生物链",
            "forbidden_zones": "禁区/危险区域",
            "urban_core": "核心城市/聚居地",
            "hidden_realms": "秘境/隐藏空间",
        },
    },
    "society": {
        "label": "社会结构",
        "fields": {
            "politics": "政治体制与权力架构",
            "economy": "经济模式与贸易",
            "class_system": "阶级/等级系统",
            "power_structure": "明暗权力结构",
            "oppression_mechanism": "压迫/控制机制",
            "class_division": "阶层划分与流动壁垒",
        },
    },
    "culture": {
        "label": "历史文化",
        "fields": {
            "history": "关键历史事件与时代背景",
            "religion": "宗教信仰体系",
            "taboos": "文化禁忌与违逆后果",
            "worship": "崇拜对象与祭祀仪式",
            "oaths_and_curses": "誓言体系与诅咒",
        },
    },
    "daily_life": {
        "label": "沉浸感细节",
        "fields": {
            "food_clothing": "衣食住行的日常细节",
            "language_slang": "俚语、口音与方言",
            "entertainment": "娱乐方式与消遣",
            "survival_tactics": "底层/弱者的生存策略",
            "market_reality": "市场/交易的真实状况",
            "food_and_drink": "饮食文化与特色食物",
            "slang_and_profanity": "粗话、黑话与市井语言",
        },
    },
}
```

---

## 3. 双存储架构

### 3.1 为什么需要双存储

| 存储 | 表 | 容量 | 用途 |
|------|---|------|------|
| **Worldbuilding 表** | `worldbuilding` | 15 个经典字段 | ORM 可直接读写，用于后续人物/地点生成的上下文读取 |
| **Bible.world_settings** | `bible` 内嵌 | 无限制（name=`维度.字段`） | 前端显示、扩展字段存储、SSE 流式写入 |

### 3.2 双写流程

```
LLM 生成维度数据
       │
       ▼
_save_worldbuilding(novel_id, worldbuilding_data)
       │
       ├─▶ 1. WorldbuildingService.update_worldbuilding()
       │      → 只写入 ORM 15 个经典字段（子集）
       │
       └─▶ 2. BibleService.add_world_setting()
              → 将所有字段（含扩展）写为 world_setting 条目
              → name 格式："{dimension_name}.{key}"
              → setting_type 统一为 "rule"
              → 例：name="society.power_structure", description="..."
```

### 3.3 合并读取流程

文件：`application/world/worldbuilding_merge.py`

```
GET /novels/{slug}/worldbuilding
       │
       ▼
1. 从 Bible 读取 world_settings → bible_dto_world_settings_to_slices()
   (含所有字段，包括扩展字段)
       │
       ▼
2. 从 Worldbuilding 表读取 → worldbuilding_entity_to_slices()
   (只有 15 个经典字段，但用户在面板修改过的值优先)
       │
       ▼
3. 合并 → merge_worldbuilding_table_and_bible_slices()
   规则：以 Bible 为基底，Worldbuilding 表中非空字段覆盖同名键
       │
       ▼
4. 投影 → project_slices_to_legacy_api_shape()
   将扩展字段合并到每个维度的"最后一个经典字段"中
   例：society.power_structure → 追加到 society.class_system 末尾
```

**合并规则**：
- Bible 侧是完整基底（含 SSE 写入的扩展字段）
- Worldbuilding 表中非空的字段覆盖同名键（用户在面板改过的优先）
- 扩展字段投影时合并到经典字段的最后一个，格式：`【字段key】字段值`

---

## 4. 生成模式

### 4.1 三种生成模式对比

| 模式 | 入口 API | 生成策略 | 适用场景 |
|------|---------|---------|---------|
| **一次性全量** | `POST /bible/novels/{id}/generate?stage=all` | 单次 LLM 调用生成所有内容 | 向后兼容、快速生成 |
| **分阶段异步** | 同上，`stage=worldbuilding/characters/locations` | 每阶段一次 LLM 调用 | 轮询检查状态 |
| **SSE 流式** | `POST /bible/novels/{id}/generate-stream` | 逐维度逐 token 流式推送 | 前端实时渲染 |

### 4.2 分阶段生成的依赖关系

```
worldbuilding ──▶ characters ──▶ locations ──▶ knowledge
   (世界观)        (人物)        (地点)       (知识库)
    │                │              │
    │                │              │
    │                └─ 依赖已有世界观 ─┘
    │                                  │
    └──── 依赖已有世界观 + 人物 ────────┘
```

**阶段参数**：
- `stage=all`：一次性生成世界观+人物+地点
- `stage=worldbuilding`：只生成世界观5维度+文风公约
- `stage=characters`：基于已有世界观生成人物
- `stage=locations`：基于已有世界观+人物生成地点

---

## 5. 一次性全量生成模式

### 5.1 流程

```
AutoBibleGenerator.generate_and_save(novel_id, premise, target_chapters, stage="all")
       │
       ▼
1. 创建空 Bible（如不存在）
       │
       ▼
2. _generate_bible_data(premise, target_chapters)
   → 单次 LLM 调用，输出完整 JSON：
     { characters: [...], locations: [...], style: "...", worldbuilding: {...} }
   → CPMS 节点: BIBLE_ALL
   → 回退常量: _FALLBACK_BIBLE_ALL_SYSTEM
       │
       ▼
3. _save_to_bible(novel_id, bible_data)
   → 保存人物、地点、风格笔记到 Bible
       │
       ▼
4. _save_worldbuilding(novel_id, bible_data["worldbuilding"])
   → 双写：Worldbuilding 表 + Bible.world_settings
```

### 5.2 LLM 输出 JSON 格式

```json
{
  "characters": [
    { "name": "人物名", "role": "主角/配角/对手/导师", "description": "性格、背景、目标" }
  ],
  "locations": [
    { "id": "loc-continent-1", "name": "地点名", "type": "城市/建筑/区域",
      "description": "地点描述", "parent_id": null }
  ],
  "style": "第三人称有限视角，以XX视角为主。基调XX，节奏XX。避免XX。营造XX氛围。",
  "worldbuilding": {
    "core_rules": { "power_system": "...", "physics_rules": "...", "magic_tech": "..." },
    "geography":   { "terrain": "...", "climate": "...", "resources": "...", "ecology": "..." },
    "society":     { "politics": "...", "economy": "...", "class_system": "..." },
    "culture":     { "history": "...", "religion": "...", "taboos": "..." },
    "daily_life":  { "food_clothing": "...", "language_slang": "...", "entertainment": "..." }
  }
}
```

---

## 6. SSE 流式生成模式（核心）

### 6.1 完整流程

```
POST /bible/novels/{novel_id}/generate-stream?stage=worldbuilding
       │
       ▼
_sse_bible_generator(novel_id, stage, bible_generator, knowledge_generator)
       │
       ▼
┌─────────────────────────────────────────────────┐
│ Phase: init          → "正在准备生成环境..."     │
├─────────────────────────────────────────────────┤
│ Phase: worldbuilding → "AI 正在构建世界观..."    │
│                                                   │
│  ┌─ Phase: worldbuilding_style                    │
│  │   → _generate_style(premise, chapters)         │
│  │   → SSE: data {type:"style", content:"..."}    │
│  │   → 即时保存到 Bible.style_notes               │
│  │                                                │
│  ├─ Phase: worldbuilding_core_rules               │
│  │   → _stream_single_dimension(...)              │
│  │   → SSE: data {type:"worldbuilding_dim_chunk"} │
│  │   → 解析JSON → 逐字段推送                      │
│  │   → SSE: data {type:"worldbuilding_field",     │
│  │                  dimension, field, value}       │
│  │   → 即时保存到 Worldbuilding表 + Bible          │
│  │                                                │
│  ├─ Phase: worldbuilding_geography                │
│  │   → (同上，传入已生成的core_rules作为上下文)    │
│  │                                                │
│  ├─ Phase: worldbuilding_society                  │
│  │   → (同上，传入已生成的前3个维度作为上下文)     │
│  │                                                │
│  ├─ Phase: worldbuilding_culture                  │
│  │   → (同上)                                     │
│  │                                                │
│  └─ Phase: worldbuilding_daily_life               │
│      → (同上)                                     │
│                                                   │
│ Phase: worldbuilding_done → "世界观生成完成！"    │
├─────────────────────────────────────────────────┤
│ Phase: characters → "AI 正在生成主要角色..."      │
│  → _stream_generate_characters(...)               │
│  → 逐角色推送 SSE: data {type:"character"}        │
│  → 即时落库到 Bible.characters                    │
│  → 生成人物关系三元组                              │
│ Phase: characters_done                            │
├─────────────────────────────────────────────────┤
│ Phase: locations → "AI 正在生成地图系统..."       │
│  → _stream_generate_locations(...)                │
│  → 逐地点推送 SSE: data {type:"location"}         │
│  → 即时落库到 Bible.locations                     │
│  → 生成地点关系三元组                              │
│ Phase: locations_done                             │
├─────────────────────────────────────────────────┤
│ Phase: knowledge → "正在构建知识库..."            │
│  → knowledge_generator.generate_and_save(...)     │
├─────────────────────────────────────────────────┤
│ Done: "全部生成完成！"                             │
└─────────────────────────────────────────────────┘
```

### 6.2 SSE 事件类型

| 事件 | 数据结构 | 说明 |
|------|---------|------|
| `phase` | `{phase, message}` | 阶段变更通知 |
| `data` (style) | `{type:"style", content:"..."}` | 文风公约文本 |
| `data` (dim_chunk) | `{type:"worldbuilding_dim_chunk", dimension, chunk}` | 维度 JSON 的逐 token 片段 |
| `data` (field) | `{type:"worldbuilding_field", dimension, field, value}` | 解析后的完整字段值 |
| `data` (character) | `{type:"character", index, content}` | 单个人物数据 |
| `data` (character_chunk) | `{type:"character_chunk", chunk}` | 人物 LLM 原始 token |
| `data` (location) | `{type:"location", index, content}` | 单个地点数据 |
| `data` (location_chunk) | `{type:"location_chunk", chunk}` | 地点 LLM 原始 token |
| `done` | `{message, novel_id}` | 全部完成 |
| `error` | `{message}` | 错误 |

### 6.3 逐维度流式生成细节

**`_stream_single_dimension()`** 方法：

```
输入：premise, target_chapters, dim_key, existing_worldbuilding
      │
      ▼
1. 构建字段说明 (fields_desc)
   → 从 _DIMENSION_DEFS[dim_key] 读取字段定义
      │
      ▼
2. 构建上下文块 (context_block)
   → 已生成维度的摘要（帮助 LLM 保持一致性）
   → 格式："已生成的其他维度（请保持一致性）：\n- core_rules: power_system: ..."
      │
      ▼
3. CPMS 渲染提示词
   → 节点: BIBLE_WORLDBUILDING_DIMENSION
   → 变量: dim_label, premise, target_chapters, context_block, fields_desc
   → 降级: 回退到硬编码 system_prompt + user_prompt
      │
      ▼
4. LLM 流式生成
   → stream_generate(prompt, GenerationConfig(max_tokens=4096, temperature=0.7))
   → 逐 token yield
```

**LLM 输出要求**：
- 必须严格按照指定的字段名输出，不要自创字段名
- 每个字段至少 50 字
- 字段值是纯文本字符串，不要嵌套对象
- 只输出 JSON

### 6.4 逐字段流式生成

**`_stream_single_field()`** 方法：

```
输入：premise, target_chapters, dim_key, field_key, existing_worldbuilding, existing_dim_fields
      │
      ▼
1. 构建维度内同字段上下文 (sibling_block)
   → "同维度「核心法则」已生成的字段（请保持内容不重复、风格一致）："
      │
      ▼
2. CPMS 渲染提示词
   → 节点: BIBLE_WORLDBUILDING_FIELD
   → 变量: dim_label, field_label_cn, premise, target_chapters, field_desc, context_block, sibling_block
      │
      ▼
3. LLM 流式生成
   → GenerationConfig(max_tokens=1024, temperature=0.7)
   → 直接输出纯文本（不输出JSON）
```

---

## 7. 世界观 → 人物 → 地点的级联生成

### 7.1 人物生成（基于世界观）

```
_generate_characters(premise, target_chapters, existing_worldbuilding)
       │
       ▼
1. 读取已有世界观 (_load_worldbuilding)
   → 合并 Worldbuilding 表 + Bible.world_settings
       │
       ▼
2. 构建提示词
   → CPMS 节点: BIBLE_CHARACTERS
   → 将世界观5维度摘要注入 system prompt
   → 人物要求：3-5个主要角色，有冲突和互动
   → 姓名约束：禁用俗套大姓，从姓氏卡池随机选用
       │
       ▼
3. LLM 生成
   → 输出: [{name, role, description, relationships}]
       │
       ▼
4. 保存到 Bible.characters
   → 自动生成人物关系三元组 (Triple)
```

### 7.2 地点生成（基于世界观+人物）

```
_generate_locations(premise, target_chapters, existing_worldbuilding, existing_characters)
       │
       ▼
1. 读取已有世界观 + 人物
       │
       ▼
2. 构建提示词
   → CPMS 节点: BIBLE_LOCATIONS
   → 将世界观和人物信息注入
   → 地点要求：5-10个重要地点，含层级(parent_id)
       │
       ▼
3. LLM 生成
   → 输出: [{id, name, type, description, parent_id}]
       │
       ▼
4. 规范化地点数据
   → _prepare_locations_for_save()
   → 确保父节点优先、缺失父节点降级为根节点
   → 拓扑排序：先保存父地点，再保存子地点
       │
       ▼
5. 保存到 Bible.locations
   → 自动生成地点关系三元组 (Triple)
```

### 7.3 _load_worldbuilding：世界观读取合并

```
_load_worldbuilding(novel_id)
       │
       ├─▶ Worldbuilding 表 → worldbuilding_entity_to_slices(wb)
       │   → 只有 15 个经典字段
       │
       ├─▶ Bible.world_settings → bible_dto_world_settings_to_slices(bible)
       │   → 含所有字段（含扩展字段）
       │
       └─▶ merge_worldbuilding_table_and_bible_slices(table, bible)
           → Bible 为基底，表非空字段覆盖同名键
           → 确保下游（人物/地点生成）拿到最完整的世界观数据
```

---

## 8. CPMS 提示词节点体系

### 8.1 世界观相关 CPMS 节点

| CPMS Key | 名称 | 类别 | 变量 | 输出格式 |
|---------|------|------|------|---------|
| `bible-all` | Bible 全量生成 | world | premise, target_chapters | JSON |
| `bible-worldbuilding` | 世界观+文风 | world | premise, target_chapters | JSON |
| `bible-worldbuilding-dimension` | 单维度生成 | world | dim_label, premise, target_chapters, context_block, fields_desc | JSON |
| `bible-worldbuilding-field` | 单字段生成 | world | dim_label, field_label_cn, premise, target_chapters, field_desc, context_block, sibling_block | 纯文本 |
| `bible-characters` | 人物生成 | world | premise, target_chapters, worldbuilding_block | JSON |
| `bible-locations` | 地点生成 | world | premise, target_chapters, worldbuilding_block, characters_block | JSON |
| `bible-style-convention` | 文风公约 | world | premise, target_chapters | 纯文本 |

### 8.2 三级降级策略

```
1. CPMS 节点渲染 → PromptRegistry.render_to_prompt(key, variables)
       │ 失败
       ▼
2. get_prompt_system(key) → 从配置文件读取 system prompt
       │ 失败
       ▼
3. 硬编码回退常量 → _FALLBACK_BIBLE_*_SYSTEM
```

---

## 9. JSON 解析与修复管线

### 9.1 LLM 输出后处理链

```
LLM 原始输出
     │
     ▼
_sanitize_llm_json_output(raw)
   → 去除 ANSI 转义码
   → 去除 <think>...</think> 思考链
   → 提取 ```json ... ``` 代码块
     │
     ▼
_normalize_quotes_in_json(text)
   → 替换中文引号 "" → ASCII ""
   → 替换全角引号 ＂ → ASCII "
   → 只在字符串值内部替换，不误伤 JSON 结构
     │
     ▼
_repair_json_string(text)
   → 阶段0：直接 json.loads()（最快路径）
   → 阶段1：标准化引号后重试
   → 阶段2：补全未关闭的花括号/方括号
   → 阶段3：递归删除末尾逗号后重试（最多15次）
     │
     ▼
_extract_outer_json_object(text)
   → 提取最外层 { ... } 对象
     │
     ▼
json.loads() 成功 ✓
```

### 9.2 SSE 维度 JSON 解析

`_parse_dimension_json(raw_text, dim_key)` 特殊处理：

```
1. 尝试直接解析
2. LLM 可能多包一层 → 检查 {"worldbuilding": {dim_key: {...}}}
3. LLM 可能单键包裹 → 检查 {dim_key: {...}}
4. 标准化：只保留字符串字段，list/dict 转 str()
```

---

## 10. API 接口汇总

### 10.1 世界观 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/novels/{slug}/worldbuilding` | 获取世界观（合并读取） |
| `POST` | `/novels/{slug}/worldbuilding` | 创建空白世界观 |
| `PUT` | `/novels/{slug}/worldbuilding` | 更新世界观（部分更新） |

### 10.2 Bible 生成

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/bible/novels/{id}/generate?stage=all` | 异步全量生成 |
| `POST` | `/bible/novels/{id}/generate?stage=worldbuilding` | 异步只生成世界观 |
| `POST` | `/bible/novels/{id}/generate?stage=characters` | 异步只生成人物 |
| `POST` | `/bible/novels/{id}/generate?stage=locations` | 异步只生成地点 |
| `POST` | `/bible/novels/{id}/generate-stream?stage=worldbuilding` | SSE 流式生成 |
| `GET` | `/bible/novels/{id}/bible/status` | 检查生成状态 |
| `GET` | `/bible/novels/{id}/bible/generation-feedback` | 获取最近一次失败原因 |

### 10.3 Bible CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/bible/novels/{id}/bible` | 获取 Bible（不存在时自动创建空 Bible） |
| `PUT` | `/bible/novels/{id}/bible` | 批量更新 Bible |
| `POST` | `/bible/novels/{id}/bible/characters` | 添加人物 |
| `POST` | `/bible/novels/{id}/bible/world-settings` | 添加世界设定 |
| `POST` | `/bible/novels/{id}/bible/locations` | 添加地点 |
| `POST` | `/bible/novels/{id}/bible/style-notes` | 添加风格笔记 |

---

## 11. 前端交互

### 11.1 NovelSetupGuide 向导

文件：`frontend/src/components/onboarding/NovelSetupGuide.vue`

前端维护与后端 `_DIMENSION_DEFS` 一致的维度标签映射：

```typescript
const WB_DIMS = ['core_rules', 'geography', 'society', 'culture', 'daily_life'] as const

const dimKeyLabels: Record<string, string> = {
  power_system: '力量体系', physics_rules: '物理规律', magic_tech: '魔法/科技',
  cost_and_limitation: '代价与限制', resource_scarcity: '稀缺资源',
  terrain: '地形', climate: '气候', resources: '资源', ecology: '生态',
  forbidden_zones: '禁区', urban_core: '核心城市', hidden_realms: '秘境',
  politics: '政治', economy: '经济', class_system: '阶级',
  power_structure: '权力结构', oppression_mechanism: '压迫机制', class_division: '阶层划分',
  history: '历史', religion: '宗教', taboos: '禁忌',
  worship: '崇拜与祭祀', oaths_and_curses: '誓言与诅咒',
  food_clothing: '衣食住行', language_slang: '俚语口音', entertainment: '娱乐方式',
  survival_tactics: '生存策略', market_reality: '市场真相',
  food_and_drink: '饮食文化', slang_and_profanity: '黑话粗话',
}
```

### 11.2 Bible.world_settings → 世界观5维映射

前端解析 Bible 的 `world_settings` 数组，通过 `name` 中的 `.` 分隔符还原为5维度结构：

```typescript
function worldbuildingFromWorldSettings(settings) {
  const out = emptyWorldbuildingShape()
  for (const s of settings || []) {
    const dot = s.name.indexOf('.')
    const dim = s.name.slice(0, dot)   // 如 "society"
    const key = s.name.slice(dot + 1)  // 如 "power_structure"
    out[dim][key] = s.description
  }
  return out
}
```

---

## 12. 数据库表结构

### 12.1 worldbuilding 表

```sql
CREATE TABLE worldbuilding (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL UNIQUE,

    -- 1. 核心法则
    power_system TEXT DEFAULT '',
    physics_rules TEXT DEFAULT '',
    magic_tech TEXT DEFAULT '',

    -- 2. 地理生态
    terrain TEXT DEFAULT '',
    climate TEXT DEFAULT '',
    resources TEXT DEFAULT '',
    ecology TEXT DEFAULT '',

    -- 3. 社会结构
    politics TEXT DEFAULT '',
    economy TEXT DEFAULT '',
    class_system TEXT DEFAULT '',

    -- 4. 历史文化
    history TEXT DEFAULT '',
    religion TEXT DEFAULT '',
    taboos TEXT DEFAULT '',

    -- 5. 沉浸细节
    food_clothing TEXT DEFAULT '',
    language_slang TEXT DEFAULT '',
    entertainment TEXT DEFAULT '',

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);
```

---

## 13. 关键设计决策

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| 存储方式 | A.单表 B.双存储 | **B.双存储** | ORM 15槽位固定但可类型安全读写；Bible.world_settings 灵活存扩展字段 |
| 生成粒度 | A.全量 B.逐维度 C.逐字段 | **B.逐维度为主，C可选** | 逐维度保证字段间一致性；逐字段为编辑/重生成场景预留 |
| 上下文传递 | A.无上下文 B.全量 C.摘要 | **C.摘要** | 已生成维度的字段值摘要注入 prompt，保持跨维度一致性 |
| 扩展字段处理 | A.丢弃 B.单独存储 C.合并到经典字段 | **C.合并到经典字段** | 投影到经典字段末尾（`【key】value`），API 兼容且不丢内容 |
| JSON修复 | A.简单try B.多级修复 | **B.多级修复** | LLM输出不稳定（中文引号/截断/多余逗号），需健壮修复管线 |
| 流式生成 | A.后端缓冲 B.逐token推送 | **B.逐token推送** | 前端打字机效果，同时每维度完成后推送解析后的完整字段值 |

---

## 14. 核心文件索引

| 层次 | 文件 | 核心类/函数 |
|------|------|------------|
| 领域模型 | `domain/worldbuilding/worldbuilding.py` | `Worldbuilding` 实体 |
| 世界观服务 | `application/world/services/worldbuilding_service.py` | `WorldbuildingService` |
| Bible 服务 | `application/world/services/bible_service.py` | `BibleService` |
| 自动生成器 | `application/world/services/auto_bible_generator.py` | `AutoBibleGenerator` |
| 数据合并 | `application/world/worldbuilding_merge.py` | `merge_worldbuilding_table_and_bible_slices()` |
| 仓储 | `infrastructure/persistence/database/worldbuilding_repository.py` | `WorldbuildingRepository` |
| 迁移 | `infrastructure/persistence/database/migrations/add_worldbuilding.sql` | 建表 SQL |
| CPMS维度节点 | `infrastructure/ai/prompt_packages/nodes/bible-worldbuilding-dimension/` | 维度级提示词 |
| CPMS字段节点 | `infrastructure/ai/prompt_packages/nodes/bible-worldbuilding-field/` | 字段级提示词 |
| API路由 | `interfaces/api/v1/world/worldbuilding_routes.py` | 世界观 CRUD |
| API路由 | `interfaces/api/v1/world/bible.py` | Bible 生成 + SSE 流 |
| 前端向导 | `frontend/src/components/onboarding/NovelSetupGuide.vue` | 新书设置向导 |
