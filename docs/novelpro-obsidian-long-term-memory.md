# NovelPro Obsidian 长期记忆

## 定位

Obsidian 是 NovelPro 的长期主记忆层。PlotPilot 写作、生成和采纳仍然走原有章节与 Knowledge 管线；章后管线会把 PP 缓存自动导出到 Obsidian，后续读取 Knowledge 时会优先回读 Obsidian，再同步回 PP SQLite 缓存。

这样只有一条写作链路：作者仍然在 PP 内写作，AI 仍使用 PP 当前激活配置；Obsidian 负责长期记忆、人工复盘、双链整理和关系图展示。

## 自动同步时机

- 章节正文保存后，`ChapterAftermathPipeline` 会先执行现有叙事同步、向量、三元组、伏笔、文风和 KG 推断。
- 候选稿采纳仍复用章节保存后的同一管线，因此也会自动同步 Obsidian。
- 后台 `EXTRACT_BUNDLE` 任务完成叙事同步后，也会尝试同步 Obsidian。
- Obsidian 同步失败只记录 warning，不阻断正文保存和候选稿采纳。
- Obsidian 导出会读取 PP SQLite 缓存，不会在写后导出时反向读取旧 Markdown，避免刚保存的章节记忆被旧 Obsidian 内容遮挡。

## Vault 路径

默认导出到：

```text
data/obsidian-vault/<novel_id>/
```

如需接入已有 Obsidian vault，可设置环境变量：

```bash
export PLOTPILOT_OBSIDIAN_VAULT="/你的/Obsidian/Vault/路径"
```

## 目录结构

每本书会生成独立目录：

```text
<novel_id>/
  00_Index.md
  01_Fact_Locks.md
  02_Chapters/
    Chapter_0001.md
    Chapter_0002.md
  03_Entities/
    Character_Relationships.md
  04_Timelines/
    Timeline.md
```

## 数据来源

- `00_Index.md`：从当前 Knowledge 章节摘要生成入口索引。
- `01_Fact_Locks.md`：从 `premise_lock` 和知识三元组生成长期事实锁。
- `02_Chapters/Chapter_XXXX.md`：从分章摘要、关键事件、未解问题、连续性说明和节拍生成章节记忆。
- `03_Entities/Character_Relationships.md`：从知识三元组生成 Mermaid 关系图，展示角色关系、故事关系和势力关联。
- `04_Timelines/Timeline.md`：从分章关键事件和未解问题生成章节时间线。

## 使用原则

- 在 PP 里写作、生成、采纳和维护章节正文，避免复制粘贴到外部模型形成双线。
- 在 Obsidian 里阅读、复盘、补充长期记忆和人工链接；`01_Fact_Locks.md` 与章节笔记可作为回读来源。
- 若人工编辑 Obsidian，建议保持现有 Markdown 表格和章节模板结构，否则 PP 回读可能无法识别。

## 自动监控

右侧 `NovelPro 测试区 -> 监控中心` 会聚合：

- Obsidian 主记忆是否可回读。
- 长期事实、章节摘要和关系图数量。
- 连续性巡检里的角色掉线、关系沉默、文风漂移、时间线冲突和大纲偏离。
- 战力系统里的跳级过快、无代价越级和高战力缺限制等提醒。

## AI 填表建议

NovelPro 的手动表单已接入 `AI 生成建议`：

- 口吻锁定：生成角色心理状态、口头禅、小动作和 OOC 禁忌。
- 对话沙盒：生成角色语气锚点和试写场景。
- 连续性巡检：生成关系事件和大纲节点状态。
- 战力系统：生成战力规则、角色战力档案、战斗/升级事件。
- 精细改稿：生成改稿目标、重点片段和作者要求。

这些建议只会填入表单，不会自动保存或自动采纳；作者仍保留最后确认权。
