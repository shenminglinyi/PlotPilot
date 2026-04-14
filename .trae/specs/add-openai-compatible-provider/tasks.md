# Tasks
- [x] Task 1: 实现 `OpenAIProvider` 核心逻辑
  - [x] SubTask 1.1: 在 `infrastructure/ai/providers/openai_provider.py` 中创建 `OpenAIProvider`，继承 `BaseProvider`。
  - [x] SubTask 1.2: 使用 `openai.AsyncOpenAI` 或 `httpx` 实现异步 `generate` 方法，接收 `Prompt` 和 `GenerationConfig`，返回 `GenerationResult`，并处理 token usage。
  - [x] SubTask 1.3: 实现异步流式 `stream_generate` 方法，处理 SSE 流返回文本数据。
- [x] Task 2: 修改依赖注入配置 `interfaces/api/dependencies.py`
  - [x] SubTask 2.1: 增加对 `OPENAI_API_KEY`、`OPENAI_BASE_URL` 和 `OPENAI_MODEL` 的环境变量读取和验证逻辑 (`_openai_settings`)。
  - [x] SubTask 2.2: 根据 `LLM_PROVIDER`（默认 `openai` 或 `anthropic`）动态返回对应的 `Provider` 实例（在 `get_llm_service`, `get_auto_workflow`, `get_auto_bible_generator` 等相关所有直接使用 `AnthropicProvider` 的地方进行替换或抽象）。

# Task Dependencies
- [Task 2] depends on [Task 1]