# 提示词包（CPMS 内置种子）

v4 起，内置提示词从 **目录化包** 加载，由 `PromptManager.ensure_seeded()` 导入 SQLite；提示词广场仍读写数据库，与此目录为 **发行源 ↔ 运行时** 关系。

## 布局

| 路径 | 说明 |
|------|------|
| `bundle_meta.yaml` | 模板包元数据；`version` 变更会触发对用户库 **增量同步**（系统版本） |
| `nodes/<node_key>/package.yaml` | 节点元数据：`id`、`name`、`category`、`tags`、`variables` 等 |
| `nodes/<node_key>/system.md` | System 模板正文 |
| `nodes/<node_key>/user.md` | User 模板正文 |
| `nodes/<node_key>/extras.json` | 可选；顶层 `_directives`、`_focus_instructions` 等扩展字段 |
| `fragments/` | 预留：可复用片段（后续可用 Jinja `include` 组装） |

## 维护流程

1. 编辑某节点下 `package.yaml` / `*.md` / `extras.json`。
2. 提升 `bundle_meta.yaml` 或 `bundle_meta.yaml` 内与导出脚本一致的 **version**（与 `export_legacy` 写入的 `bundle_meta.yaml` 同源）。
3. 启动应用或触发种子逻辑；内置模板包版本与 DB 不一致时会 **增量更新**（用户改过 `created_by=user` 的版本会跳过正文覆盖）。

从旧版 **monolithic JSON** 重新导出：

```bash
python -m infrastructure.ai.prompt_seed.export_legacy --version 4.x.y-your-tag
```

（需在仍存在 `infrastructure/ai/prompts/prompts_*.json` 的归档副本上运行；当前仓库已以本目录为 SSOT。）

## 依赖

解析 `package.yaml` 需要 **PyYAML**（见根目录 `requirements.txt`）。
