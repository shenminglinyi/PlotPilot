# 提示词目录说明

- `**rules_seed.json**`：旧版 `PromptRuntimeService` 使用的 **规则** 列表（`rule.`*），与 CPMS 节点种子无关。
- **CPMS 内置节点种子**：已迁至 `../prompt_packages/`（`package.yaml` + `system.md` + `user.md` + 可选 `extras.json`）。勿在此目录恢复巨型 `prompts_*.json`；若需从 JSON 重建包，将归档 JSON 临时放回本目录后运行：
  `python -m infrastructure.ai.prompt_seed.export_legacy`

