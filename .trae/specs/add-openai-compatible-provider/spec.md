# 兼容 OpenAI 的大模型提供商支持 Spec

## Why
目前系统默认强绑定 Anthropic (Claude) 作为大语言模型提供商，在 `interfaces/api/dependencies.py` 等多处硬编码了 `AnthropicProvider`。为了让系统兼容更多的大模型（如 GPT-4, DeepSeek, 豆包等），我们需要引入兼容 OpenAI API 标准的 `OpenAIProvider`，并通过环境变量支持在不同模型提供商之间切换。

## What Changes
- **新增** `OpenAIProvider`：在 `infrastructure/ai/providers/openai_provider.py` 中实现，继承 `BaseProvider`，并使用 `openai` SDK 或 `httpx` 实现 `generate` 和 `stream_generate` 方法。
- **修改** 依赖注入 `interfaces/api/dependencies.py`：引入 `LLM_PROVIDER` 环境变量（可选值为 `openai` 或 `anthropic`），并根据配置动态返回对应的 Provider。
- **修改** 获取环境配置的逻辑：新增获取 `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL` 的相关函数。
- **兼容性**：确保原有的 `AnthropicProvider` 功能不受影响，并在没有配置时依然可以降级为 `MockProvider`。

## Impact
- Affected specs: 系统的核心 AI 调用链路、各业务模块的依赖注入流程。
- Affected code: 
  - `infrastructure/ai/providers/openai_provider.py` (新增)
  - `interfaces/api/dependencies.py`

## ADDED Requirements
### Requirement: 兼容 OpenAI API 的 LLM 服务
系统应当能够通过配置使用符合 OpenAI 接口标准的大模型服务。

#### Scenario: Success case
- **WHEN** 用户在环境变量中设置 `LLM_PROVIDER=openai`, 并且配置了 `OPENAI_API_KEY`（以及可选的 `OPENAI_BASE_URL`）
- **THEN** 系统在获取 LLM 服务时应返回 `OpenAIProvider` 实例，所有大模型调用（文本生成、流式生成）将路由至对应的 OpenAI 兼容接口。

## MODIFIED Requirements
### Requirement: 动态模型提供商选择
原系统只检测 Anthropic 的 API Key，现在应根据 `LLM_PROVIDER` 选择对应的初始化逻辑，并在指定服务未配置时优雅降级为 `MockProvider`。