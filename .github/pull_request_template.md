## 变更说明
- 将章节张力评分从单一 `tension_score` 重构为多维张力分析（情节张力 / 情绪张力 / 节奏张力）
- 新增 `TensionDimensions` 值对象，自动计算加权综合分（plot 40%, emotional 30%, pacing 30%）
- 新增 `TensionScoringService`，使用独立 LLM prompt 对章节正文进行三维张力评分
- 新增通用结构化 JSON 管线 `structured_json_pipeline`（清洗 → json_repair → Pydantic 校验 → 重试）
- 张力评分从 `llm_chapter_extract_bundle()` 多任务 JSON 中拆出，改为独立调用，提升准确度
- `GenerationConfig` 新增 `response_format` 字段，Anthropic provider 透传以强制 JSON 输出
- DB 迁移：`chapters` 表新增 `plot_tension`、`emotional_tension`、`pacing_tension` 三列
- 新增 `json-repair` 依赖

## 测试
- [x] 本地已跑核心用例（`pytest tests/unit/domain/ tests/unit/application/ai/` — 345 passed）
- [x] 新增模块导入验证通过：`TensionDimensions`、`TensionScoringService`、`structured_json_pipeline`、`tension_scoring_contract`
- [ ] 关键路径手测通过（启动后端/前端、主要功能点）

## 风险与回滚
- 风险：`TensionScoringService` 每次 `sync_chapter_narrative_after_save` 会额外调用一次 LLM，增加 token 消耗和保存延迟；若评分失败会 fallback 到 neutral(50.0)，不影响主流程
- 回滚方式：`git revert` 本 PR；DB 迁移为纯 ADD COLUMN（带默认值），不影响已有数据
