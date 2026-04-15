# Multi-Agent v0.1 Audit Checklist

## 1) 配置与模型列表

- 打开“核心引擎配置 (Model Matrix)”弹窗
- 为以下角色分别配置 Provider / API Key / Base URL，并保存：
  - default_model
  - research_model
  - fact_review_model / genre_review_model / reader_review_model
- 关闭弹窗后再次打开
- 点击各角色的“获取模型列表”
  - 预期：无需重输 API Key 也能拿到 models（走后端代取 `/api/v1/system/llm/models`）

## 2) Worldbuilding 闭环

- 创建新小说并触发 worldbuilding 生成
- 后端日志预期出现：
  - `Starting background research for premise...`（仅首次或 research 被返工时出现）
  - `Research keywords: [...]`
  - `Executing web search...` / `Web search done...`
  - Reviewer 失败时应记录：`Fact reviewer failed:` 等
- 数据落库预期（bibles.extensions）：
  - `research` 存在且包含 `facts/sources`
  - `worldbuilding_draft` 存在
  - `review.worldbuilding` 存在且包含 `reviews/final_verdict`

## 3) 红线与返工

- 调整 reviewer 模型为一个“严格”模型（或人为在 research 里注入相互冲突事实）
- 预期：
  - 任一 reviewer 触发 `redlines_triggered` 后，聚合器 `redline_veto=true`
  - `final_verdict` 变为 `rework`
- 若 reviewer 返回 `needs_research_rework=true`
  - 预期：research 工件被置空并重新生成，最终 `extensions.research.version/created_at` 更新

## 4) 冒烟命令

```bash
python -m py_compile interfaces/api/v1/system/llm.py application/world/services/auto_bible_generator.py
pytest -q tests/unit/application/services/test_research_report_artifact.py tests/unit/application/services/test_worldbuilding_review_committee.py
cd frontend && npx vue-tsc -p tsconfig.json --noEmit
```

