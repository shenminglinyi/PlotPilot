# 选题立项池（设计）

**日期**：2026-04-29  
**状态**：设计已定稿，待实现计划（writing-plans）  
**定位**：一期按轻量选题池交付；数据、接口与页面命名按最终「创作立项系统」预留。

## 1. 目标

- **降低开书返工**：在正式建档前，先比较多个选题，减少一时兴起创建无效书目的情况。
- **保持低侵入**：选题数据独立于小说、Bible、章节、知识图谱和故事线；只有用户明确「采用为新书」时才进入现有小说链路。
- **最终可扩展**：第一期只做生成、保存、归档、采用；但字段与接口保留市场标签、风险、长线潜力、评分等立项评估维度。
- **复用现有建档流程**：采用后调用现有 `NovelService.create_novel`，后续仍走新书设置向导生成世界观、人物、地图和主线。

## 2. 范围

### 一期交付

- 首页增加「选题池 / 立项池」入口。
- 用户输入题材偏好、关键词、爽点、避雷点、目标篇幅。
- AI 一次生成 3-5 个候选选题。
- 候选选题保存到 SQLite。
- 支持列表查看、归档、恢复、采用为新书。
- 采用后创建小说并进入现有新书设置向导。

### 暂不交付

- 不做竞品库、平台榜单抓取、真实市场数据分析。
- 不做复杂多维打分模型，只保存 AI 给出的推荐指数与理由。
- 不直接生成 Bible、章节、大纲或知识图谱。
- 不修改现有主线候选 Step 4；该步骤仍保留为建档后的主线选择。

## 3. 用户流程

1. 用户在首页打开「选题池」。
2. 输入创作偏好：
   - 赛道 / 类型
   - 世界观基调
   - 关键词
   - 目标爽点
   - 想避开的套路
   - 目标篇幅档
3. 点击「生成选题」。
4. 后端调用 LLM，返回并落库 3-5 个候选。
5. 用户浏览候选卡片：
   - 书名候选
   - 一句话卖点
   - 核心冲突
   - 主角钩子
   - 开篇事件
   - 长线升级空间
   - 商业看点
   - 风险提示
   - 推荐指数
6. 用户选择：
   - 归档：不删除，只隐藏在默认列表外。
   - 恢复：从归档回到草稿。
   - 采用为新书：创建 Novel，标记该选题为 adopted，并记录 `adopted_novel_id`。

## 4. 数据模型

新增表：`topic_ideas`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | 选题 ID，服务端生成 UUID 或稳定短 ID |
| title | TEXT | 书名候选 |
| genre | TEXT | 赛道 / 类型 |
| world_preset | TEXT | 世界观基调 |
| length_tier | TEXT | `short` / `standard` / `epic` |
| logline | TEXT | 一句话卖点 |
| premise | TEXT | 可直接用于建档的梗概 |
| protagonist_hook | TEXT | 主角钩子 |
| core_conflict | TEXT | 核心冲突 |
| opening_hook | TEXT | 开篇事件 |
| selling_points_json | TEXT | 商业看点数组 |
| long_term_potential | TEXT | 长线升级空间 |
| risk_notes_json | TEXT | 风险提示数组 |
| market_tags_json | TEXT | 市场标签数组，为二期立项评估预留 |
| score | INTEGER | 推荐指数，建议 0-100 |
| status | TEXT | `draft` / `adopted` / `archived` |
| adopted_novel_id | TEXT | 采用后关联的小说 ID |
| source_brief_json | TEXT | 本次生成输入，便于复盘与再生成 |
| created_at | TEXT | 创建时间 |
| updated_at | TEXT | 更新时间 |

JSON 字段只用于候选内部的弱结构化展示；正式小说、Bible、章节等主数据不依赖这些 JSON 字段。

## 5. 后端设计

### 模块

```text
domain/topic/
application/topic/services/topic_idea_service.py
infrastructure/persistence/database/sqlite_topic_idea_repository.py
interfaces/api/v1/topic/topic_ideas.py
```

### 服务职责

`TopicIdeaService`

- 构建选题生成 prompt。
- 调用现有动态 LLM 服务。
- 解析模型 JSON，失败时返回本地兜底候选。
- 落库生成结果。
- 查询选题池。
- 更新状态。
- 采用选题并调用 `NovelService.create_novel`。

`SqliteTopicIdeaRepository`

- 负责 `topic_ideas` 的 CRUD。
- 负责 JSON 字段序列化与反序列化。
- 保证 `adopt` 幂等：同一选题如果已采用，重复调用返回已关联小说，不重复建书。

## 6. API 设计

基础路径：`/api/v1/topics`

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/generate` | 根据输入生成并保存一组选题 |
| GET | `/` | 查询选题列表，支持 `status` 过滤 |
| GET | `/{topic_id}` | 查询单个选题 |
| PATCH | `/{topic_id}` | 更新状态或人工修订内容 |
| POST | `/{topic_id}/adopt` | 采用为新书 |

### `POST /generate` 请求

```json
{
  "genre": "玄幻升级",
  "world_preset": "修仙风",
  "keywords": ["废柴", "宗门", "旧神"],
  "desired_selling_points": ["升级爽", "反转", "群像"],
  "avoid_patterns": ["无脑退婚", "机械系统"],
  "length_tier": "standard",
  "count": 3
}
```

### `POST /{topic_id}/adopt` 行为

- 若选题为 `draft` 或 `archived`：创建小说，更新选题为 `adopted`。
- 若选题已 `adopted` 且 `adopted_novel_id` 存在：返回已有小说，不重复创建。
- 建档字段映射：
  - `title` → `Novel.title`
  - `premise` → `Novel.premise`
  - `genre` → `CreateNovelRequest.genre`
  - `world_preset` → `CreateNovelRequest.world_preset`
  - `length_tier` → `CreateNovelRequest.length_tier`

## 7. 前端设计

### 新增文件

```text
frontend/src/api/topic.ts
frontend/src/components/topic/TopicIdeaPanel.vue
```

### 首页接入

- 在 `Home.vue` 的「新建书目」区域增加「打开选题池」按钮。
- 选题池以弹窗或同页折叠面板呈现；一期推荐弹窗，减少首页布局扰动。
- 采用后复用现有 `setupWizard` 状态，进入新书设置向导。

### 候选卡片

每张卡片展示：

- 标题、赛道、世界观、推荐指数。
- 一句话卖点。
- 核心冲突、主角钩子、开篇事件。
- 商业看点标签。
- 风险提示。
- 操作：采用、归档、恢复。

一期不显示复杂雷达图，不做竞品横向对比。

## 8. LLM 契约

模型必须输出可解析 JSON：

```json
{
  "topic_ideas": [
    {
      "title": "书名候选",
      "genre": "玄幻升级",
      "world_preset": "修仙风",
      "length_tier": "standard",
      "logline": "一句话卖点",
      "premise": "可直接用于建档的 300-800 字梗概",
      "protagonist_hook": "主角钩子",
      "core_conflict": "核心冲突",
      "opening_hook": "开篇事件",
      "selling_points": ["爽点1", "爽点2"],
      "long_term_potential": "长线升级空间",
      "risk_notes": ["风险1", "风险2"],
      "market_tags": ["标签1", "标签2"],
      "score": 85
    }
  ]
}
```

解析失败或不足数量时，服务端用本地模板补足，保证页面有可操作结果。

## 9. 错误处理

- LLM 超时：返回明确错误；不写入空候选。
- JSON 解析失败：记录日志，使用兜底候选。
- 采用失败：选题状态不变。
- 重复采用：返回已有 `adopted_novel_id`，不创建重复 Novel。
- 缺失必要字段：服务端做 trim 与默认值补齐；无法补齐的候选丢弃。

## 10. 测试要点

- 生成接口在 mock LLM 下返回并保存 3 条候选。
- 解析失败时使用兜底候选。
- 列表接口按 `draft` / `archived` / `adopted` 过滤。
- 归档和恢复只更新状态，不删除数据。
- 采用选题会创建 Novel，并写回 `adopted_novel_id`。
- 对同一选题重复调用 adopt 不重复创建 Novel。
- 前端采用后能进入现有新书向导。

## 11. 分期

### 第一期：轻量立项池

- 表结构、仓储、服务、API。
- 首页弹窗式选题池。
- 生成、保存、归档、恢复、采用为新书。

### 第二期：单条深化

- `POST /topics/{topic_id}/deepen`
- 将候选扩写成完整立项案：人设、金手指、反派、前三章钩子、第一卷目标。

### 第三期：立项评估

- `POST /topics/{topic_id}/evaluate`
- 增加同质化风险、开篇强度、主角动机、长线升级空间、商业清晰度等维度。

### 第四期：选题对比

- `POST /topics/compare`
- 多选题横向比较，输出推荐写哪一本、为什么、最大失败风险是什么。

---

本设计确认：一期以方案 B 的低复杂度实现，但命名、字段、接口和页面方向服务于最终方案 C。选题池是正式小说数据之前的「立项缓冲区」，只有采用动作才进入现有小说创作链路。
