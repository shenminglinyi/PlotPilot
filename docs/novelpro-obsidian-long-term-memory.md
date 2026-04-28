# NovelPro Obsidian 长期记忆

## 定位

Obsidian 不是第二套知识库。PlotPilot 的 SQLite Knowledge 仍然是权威数据源；Obsidian 只是章后管线自动导出的 Markdown 镜像，方便长期阅读、检索和双链整理。

## 自动同步时机

- 章节正文保存后，`ChapterAftermathPipeline` 会先执行现有叙事同步、向量、三元组、伏笔、文风和 KG 推断。
- 候选稿采纳仍复用章节保存后的同一管线，因此也会自动同步 Obsidian。
- 后台 `EXTRACT_BUNDLE` 任务完成叙事同步后，也会尝试同步 Obsidian。
- Obsidian 同步失败只记录 warning，不阻断正文保存和候选稿采纳。

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
  04_Timelines/
    Timeline.md
```

## 数据来源

- `00_Index.md`：从当前 Knowledge 章节摘要生成入口索引。
- `01_Fact_Locks.md`：从 `premise_lock` 和知识三元组生成长期事实锁。
- `02_Chapters/Chapter_XXXX.md`：从分章摘要、关键事件、未解问题、连续性说明和节拍生成章节记忆。
- `04_Timelines/Timeline.md`：从分章关键事件和未解问题生成章节时间线。

## 使用原则

- 在 PP 里写作、生成、采纳和维护结构化知识。
- 在 Obsidian 里阅读、复盘、做人工链接或补充个人笔记。
- 如果 Obsidian 里的人工笔记需要回流，应再进入 PP 的知识库/章节/设定界面维护，避免双源冲突。
