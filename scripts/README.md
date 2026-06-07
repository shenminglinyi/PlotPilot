# PlotPilot（墨枢）— 脚本目录

运维与工具脚本按子目录划分，与主应用测试（`tests/`）分开。


| 目录            | 说明                        |
| ------------- | ------------------------- |
| `install/`    | 图形安装器 / PyInstaller 相关入口  |
| `setup/`      | 环境自检、数据库初始化               |
| `evaluation/` | 离线评估与跑分                   |
| `migrations/` | 一次性数据迁移                   |
| `utils/`      | 模型下载、本地数据清理等              |
| `prototypes/` | 可选实验原型（模拟/真实 API），非 CI 依赖 |


## backup_novel.py

复制小说引导状态（世界观、结构、大纲、人物等）到新 ID，清空正文内容，重置为 planning 阶段。

```bash
# 自动生成新 ID
python scripts/backup_novel.py novel-1779868467739

# 指定目标 ID
python scripts/backup_novel.py novel-1779868467739 novel-1799999999999
```

**复制内容**：小说记录、章节结构（清空正文）、故事节点、Bible（角色/地点/时间线/风格）、故事线、情节弧、伏笔、快照、知识图谱等。
**不会复制**：章节正文（已清空）、自动驾驶运行状态（已停止）。


## export_ai_traces.py

导出 AI 调用链路追踪（Trace）为 Markdown 文件，包含每次 LLM 调用的完整 prompt、response、耗时、token 用量等。

```bash
# 导出指定小说的所有 trace
python scripts/export_ai_traces.py <novel_id>

# 导出全部 trace
python scripts/export_ai_traces.py --all

# 导出最新一次 trace
python scripts/export_ai_traces.py --latest
```

输出目录：`data/trace_exports/<novel_id>/`，包含 `index.md`（索引）和每个 trace 的 `{trace_id}.md`（完整 timeline）。

**前置条件**：环境变量 `AI_TRACE_ENABLED=true`（默认开启），每次 AI 调用会自动记录到 `ai_trace_spans` 表。关闭后不再记录。

迁移说明见 `scripts/MIGRATION_GUIDE.md`。贡献者文档索引见 [docs/README.md](../docs/README.md)。其余见仓库根目录 [README.md](../README.md)。