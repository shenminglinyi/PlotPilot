# 提示词广场系统 (Prompt Plaza) — 设计规格

> **状态**: ✅ 已实现  
> **版本**: v2.0 (数据库驱动 + 版本管理)  
> **更新日期**: 2026-04-16

---

## 1. 系统概述

提示词广场是 PlotPilot 的 AI 提示词统一管理中心。它将分散在代码各处的 26+ 个内置提示词集中到 SQLite 数据库中，提供：

- **分类浏览** — 按功能分为 6 大类（内容生成、信息提取、审稿质检、规划设计、世界设定、创意辅助）
- **版本管理** — 每个「节点」（单个提示词）拥有完整的 Git-like 版本历史，支持回滚
- **模板包概念** — 提示词按「模板包」组织，可组合成工作流
- **变量渲染** — 支持 `{variable}` 占位符的安全替换
- **自定义扩展** — 用户可创建自己的提示词节点和模板包

### 架构关系

```
prompt_templates (模板包) ──1:N──> prompt_nodes (节点)
                                          │
                                          └──1:N──> prompt_versions (版本历史)
```

### 与旧版对比

| 维度 | 旧版 (JSON 文件) | 新版 (DB 驱动) |
|------|------------------|----------------|
| 存储 | `prompts_defaults.json` | SQLite 三表 |
| 版本管理 | ❌ 无 | ✅ 完整时间线 |
| 回滚 | 覆盖/删除 | 一键回滚任意版本 |
| 自定义 | JSON override 文件 | DB 独立记录 |
| 对比 | ❌ | ✅ 双版本 diff |
| 模板组合 | ❌ | ✅ template → node |

---

## 2. 数据库设计

### 2.1 表结构

#### `prompt_templates` — 模板包

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | UUID |
| name | TEXT NOT NULL | 名称 |
| description | TEXT | 描述 |
| category | TEXT DEFAULT 'user' | builtin / user / workflow |
| version | TEXT DEFAULT '1.0.0' | 语义化版本号 |
| author | TEXT | 作者 |
| icon | TEXT DEFAULT '📦' | 图标 emoji |
| color | TEXT DEFAULT '#6b7280' | 主题色 |
| is_builtin | INTEGER NOT NULL DEFAULT 0 | 是否内置 |
| metadata | TEXT DEFAULT '{}' | JSON 扩展字段 |
| created_at / updated_at | TIMESTAMP | 时间戳 |

#### `prompt_nodes` — 提示词节点

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | UUID |
| template_id | TEXT FK → templates | 所属模板包 |
| node_key | TEXT UNIQUE | 唯一标识，如 `chapter-generation-main` |
| name / description | TEXT | 名称/描述 |
| category | TEXT | generation/extraction/review/planning/world/creative |
| source | TEXT | 来源代码位置 |
| output_format | TEXT | text / json |
| contract_module / contract_model | TEXT | Pydantic 合约引用 |
| tags | TEXT JSON | 标签数组 |
| variables | TEXT JSON | 变量定义数组 |
| system_file | TEXT | 引用的 .txt 系统文件名 |
| is_builtin | INTEGER | 是否内置 |
| sort_order | INTEGER | 排序权重 |
| active_version_id | TEXT FK → versions | 当前激活版本 ID |

#### `prompt_versions` — 版本历史

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | UUID |
| node_id | TEXT FK → nodes | 所属节点 |
| version_number | INTEGER | 版本号 (自增) |
| system_prompt | TEXT | System 角色提示词 |
| user_template | TEXT | User 模板 |
| change_summary | TEXT | 变更说明 |
| created_by | TEXT | system / user |
| created_at | TIMESTAMP | 创建时间 |

**约束**: `(node_id, version_number)` 唯一

### 2.2 迁移

表定义在 `infrastructure/persistence/database/schema.sql` 中。由于使用 `CREATE TABLE IF NOT EXISTS`，新库自动建表；旧库通过 schema 脚本幂等追加。

---

## 3. 后端服务

### 3.1 PromptManager (`infrastructure/ai/prompt_manager.py`)

核心服务类，职责：

```
ensure_seeded()     → 从 prompts_defaults.json 初始化内置种子（幂等）
list_nodes()        → 查询节点列表（支持分类/模板过滤）
get_node()          → 单个节点详情（含激活版本）
search_nodes()      → 全文搜索
create_node()       → 创建自定义节点（自动 v1）
update_node()       → 编辑内容 → 自动创建新版本
rollback_node()     → 回滚到指定历史版本（创建回滚快照）
get_node_versions() → 版本时间线
compare_versions()   → 双版本对比
render()            → {variable} 模板渲染
get_stats()         → 统计信息
get_categories_info() → 分类定义（含计数）
```

**关键设计决策**:
- **回滚不删除历史**: 回滚时创建一个新版本（标记为"回滚到 vN"），保留完整时间线
- **SafeDict 渲染**: 未提供的变量保留 `{varname}` 原样输出，不会抛异常
- **延迟注入 DB**: 通过 `_get_db()` 延迟获取连接，避免循环导入

### 3.2 API 接口 (`interfaces/api/v1/workbench/llm_control.py`)

基础路径: `/api/v1/llm-control/prompts`

#### 统计 & 分类

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/stats` | 库统计（总节点数/版本数/各分类计数） |
| GET | `/categories-info` | 分类定义列表（含节点计数） |

#### 模板包 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/templates` | 模板包列表 |
| POST | `/templates` | 创建自定义模板包 |

#### 节点 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/prompts?category=&search=` | 节点列表（支持过滤） |
| GET | `/prompts/by-category` | 按分类分组 |
| GET | `/prompts/{node_key}` | 节点详情（含完整 system/user） |
| POST | `/prompts/nodes` | 创建自定义节点 |
| DELETE | `/prompts/nodes/{id}` | 删除自定义节点（内置不可删） |

#### 版本管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/prompts/{key}/versions` | 版本时间线 |
| GET | `/prompts/versions/{ver_id}` | 版本详情（含完整内容） |
| PUT | `/prompts/{key}` | 更新（自动创建新版本） |
| POST | `/prompts/{key}/rollback/{ver_id}` | 回滚到指定版本 |
| GET | `/prompts/compare/{v1}/{v2}` | 对比两个版本差异 |

#### 渲染

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/prompts/{key}/render` | 渲染（传入 variables） |

---

## 4. 前端架构

### 4.1 文件结构

```
frontend/src/
├── api/
│   └── llmControl.ts              # promptPlazaApi + 所有 TypeScript 类型
├── components/
│   ├── global/
│   │   └── PromptPlazaFAB.vue      # 浮动入口按钮 + Drawer（独立于 LLM 控制台）
│   └── workbench/
│       ├── PromptPlaza.vue        # 主组件：搜索/分类Tab/卡片网格/创建弹窗
│       └── promptPlaza/
│           ├── NodeCard.vue       # 提示词卡片（名称/变量/版本/来源）
│           └── PromptDetailPanel.vue  # 详情面板：3 Tab（详情/编辑器/版本时间线）
└── views/
    └── Home.vue                   # 集成：header 按钮 + FAB teleport
```

### 4.2 入口方式

提示词广场有 **两个入口**:

1. **首页 Header 按钮** — 右上角 🏪 图标按钮（在齿轮设置按钮左边），点击打开 Drawer
2. **右下角 FAB 浮动按钮** — 紫色渐变圆形按钮（在 AI 控制台 FAB 左边），带角标显示提示词数量

两个入口共享同一个 `PromptPlazaFAB.vue` 组件实例。

### 4.3 TypeScript 类型

```typescript
// 核心类型（定义在 api/llmControl.ts）
interface PromptCategoryInfo    // 分类信息
interface PromptTemplate        // 模板包
interface PromptVariable        // 变量定义 { name, desc, type, required }
interface PromptNode             // 节点（列表项，含预览）
interface PromptNodeDetail       // 节点详情（含完整内容）
interface PromptVersion          // 版本信息（列表项）
interface PromptVersionDetail    // 版本详情（含完整内容）
interface VersionCompareResult   // 版本对比结果
interface PromptStats            // 统计信息
interface RenderResult           // 渲染结果 { system, user }
```

### 4.4 组件交互流

```
用户点击入口按钮
    ↓
PromptPlazaFAB.vue 打开 NDrawer
    ↓
PromptPlaza.vue 加载数据
    ├─ getStats() + getCategoriesInfo() + listNodesByCategory()
    ├─ 显示: 搜索栏 + 分类标签栏 + 分类卡片网格
    │
    ├─ [点击卡片] → 打开 PromptDetailPanel 抽屉
    │                ├─ Tab "📋 详情": 变量表 / System / User / 标签 / 合约
    │                ├─ Tab "✏️ 编辑": 编辑 System + User → 保存为新版本
    │                └─ Tab "📜 版本历史": 时间线 → 查看 / 回滚
    │
    └─ [点击"新建"] → 弹窗创建自定义节点
```

---

## 5. 内置种子

### 5.1 种子文件

`infrastructure/ai/prompts/prompts_defaults.json`

首次启动时由 `PromptManager.ensure_seeded()` 自动导入。已存在则跳过。

### 5.2 内置分类

| Key | 名称 | 图标 | 说明 |
|-----|------|------|------|
| generation | 内容生成 | ✍️ | 章节正文、场景、对白等创作 |
| extraction | 信息提取 | 🔎 | 结构化信息分析 |
| review | 审稿质检 | 🔬 | 一致性检查、质量评估 |
| planning | 规划设计 | 📋 | 大纲拆解、摘要、宏观规划 |
| world | 世界设定 | 🏰 | Bible 人物、地点、文风 |
| creative | 创意辅助 | 💡 | 对白润色、重构提案、卡文诊断 |

### 5.3 种子数据格式

```json
{
  "_meta": {
    "name": "PlotPilot 内置",
    "version": "1.0.0",
    "author": "PlotPilot Team"
  },
  "prompts": [
    {
      "id": "chapter-generation-main",
      "name": "章节正文生成",
      "description": "根据大纲和上下文生成章节正文",
      "category": "generation",
      "source": "application/engine/chapter_generation_service.py",
      "output_format": "text",
      "system": "你是一个专业小说作家...",
      "user_template": "请根据以下信息生成第 {chapter_number} 章...",
      "variables": [
        { "name": "chapter_number", "desc": "章节数", "type": "integer", "required": true },
        { "name": "chapter_outline", "desc": "本章大纲", "type": "string" }
      ],
      "tags": ["核心", "生成"],
      "contract_module": null,
      "contract_model": null
    }
  ]
}
```

---

## 6. 版本管理机制

### 6.1 工作流程

```
初始状态:  v1 (系统种子)
              ↓ 用户第一次编辑
          v2 (用户修改, change_summary="优化了角色描写")
              ↓ 用户第二次编辑
          v3 (用户修改, change_summary="调整了节奏")
              ↓ 用户觉得 v2 更好, 点击回滚
          v4 (回滚快照, change_summary="回滚到 v2")
              ↓ ...
```

### 6.2 回滚策略

采用 **"回滚快照"模式** 而非直接切换指针：
- 不删除任何历史版本
- 回滚本身也是一个新版本（vN+1），内容复制自目标版本
- 可以无限次来回回滚
- 时间线始终完整可追溯

### 6.3 版本对比

`GET /prompts/compare/{v1_id}/{v2_id}` 返回:
```json
{
  "v1": { /* v1 完整内容 */ },
  "v2": { /* v2 完整内容 */ },
  "diff": {
    "system_changed": true,
    "user_changed": false
  }
}
```

---

## 7. 渲染引擎

### 7.1 变量语法

使用 Python `str.format_map()` 兼容的 `{variable}` 语法：

```
System: 你是一个{genre}小说家...
User:   请生成第{chapter_number}章，标题《{title}》...
```

### 7.2 安全特性

- **SafeDict**: 缺失变量保留原样 `{undefined_var}` 而非抛异常
- **不执行代码**: 纯字符串替换，无 eval / exec
- **类型安全**: 变量定义中标注 type 和 required

### 7.3 调用示例

```python
# 后端
result = mgr.render("chapter-generation-main", {
    "chapter_number": 42,
    "title": "暗夜重逢",
    "genre": "玄幻"
})
# => {"system": "你是一个玄幻小说家...", "user": "请生成第42章..."}

# 前端
const res = await promptPlazaApi.renderPrompt("chapter-generation-main", {
  chapter_number: 42,
  title: "暗夜重逢"
})
```

---

## 8. UI 设计规范

### 8.1 配色方案

| 元素 | 颜色 | 用途 |
|------|------|------|
| 主色调 | `#4f46e5` (Indigo) | 内置节点边框、FAB 按钮 |
| 辅助色 | `#8b5cf6` (Purple) | FAB 渐变 |
| 编辑标记 | `#f59e0b` (Amber) | 已修改节点、用户版本 |
| 成功 | `#10b981` (Emerald) | JSON 输出标签 |
| 错误 | `#ef4444` (Red) | 必填标记、角标 |

### 8.2 FAB 按钮

- 位置：右下角（AI 控制台左侧 56px）
- 尺寸：52×52px，圆角 16px
- 样式：紫蓝渐变 + 发光动画 + 角标（提示词数量）
- hover：上浮 2px + 放大 1.05x + 光晕增强

### 8.3 卡片网格

- 布局：CSS Grid `repeat(auto-fill, minmax(300px, 1fr))`
- 内置节点：左侧 3px 彩色边框标识
- 已修改节点：左侧 3px 琥珀色边框
- hover：上浮 2px + 边框高亮 + 阴影

### 8.4 详情抽屉

- 宽度：680px
- 三个 Tab 页：
  - **详情**：变量表格 + System/User 代码块（Catppuccin Mocha 暗色主题）
  - **编辑**：双文本域 + 变更摘要 + 保存按钮
  - **版本历史**：垂直时间线（圆点 + 连线），当前版本高亮

---

## 9. 扩展指南

### 9.1 添加新的内置提示词

1. 编辑 `infrastructure/ai/prompts/prompts_defaults.json`
2. 在 `prompts` 数组中添加新条目
3. 如果需要独立的 System 文件，创建 `.txt` 放在同目录并设置 `system_file`
4. **不需要迁移** — 删除数据库后重启即可重新 seed

### 9.2 创建自定义工作流模板包

```bash
POST /api/v1/llm-control/prompts/templates
{"name": "我的悬疑写作流程", "description": "...", "category": "workflow"}
# → 返回 template_id

# 在该模板下创建多个节点
POST /api/v1/llm-control/prompts/nodes
{"template_id": "...", "name": "步骤1-悬念铺设", ...}
POST /api/v1/llm-control/prompts/nodes
{"template_id": "...", "name": "步骤2-线索埋设", ...}
```

### 9.3 在业务代码中使用提示词

```python
from infrastructure.ai.prompt_manager import get_prompt_manager

mgr = get_prompt_manager()
mgr.ensure_seeded()

# 渲染提示词
result = mgr.render("chapter-generation-main", {
    "chapter_number": 10,
    "title": "命运转折",
})

# 传给 LLM
messages = [
    {"role": "system", "content": result["system"]},
    {"role": "user", "content": result["user"]},
]
response = await llm_client.chat(messages)
```
