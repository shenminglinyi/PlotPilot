"""Qwen3.5 / OpenAI 兼容网关：实机验证「关思考」后响应不含思考围栏。

运行前将仓库根目录 ``.env.example`` 复制为 ``.env`` 并按其中「Qwen3.5实机」一节填写
（与示例保持一致，便于他人复现）。

本测试**不会**默认执行：须显式 ``RUN_QWEN_NO_THINK_LIVE=1``，并满足``OPENAI_BASE_URL``、``OPENAI_API_KEY``、``OPENAI_MODEL``、``LLM_DISABLE_REASONING=true``。
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

pytest.importorskip("dotenv")
from dotenv import load_dotenv

from domain.ai.services.llm_service import GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from infrastructure.ai.config.settings import Settings
from infrastructure.ai.llm_runtime_flags import is_llm_reasoning_disabled
from infrastructure.ai.model_resolution import resolve_openai_chat_model
from infrastructure.ai.providers.openai_provider import (
    OpenAIProvider,
    _build_chat_messages,
    _openai_no_think_request_options,
)
from infrastructure.ai.think_leak_detection import (
    message_dump_has_think_leak,
    reasoning_channel_should_be_empty_when_disabled,
)


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in [p, *p.parents]:
        if (parent / "pytest.ini").is_file():
            return parent
    return p.parents[4]


@pytest.fixture(scope="module")
def _load_project_dotenv():
    env_path = _repo_root() / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=False)
    else:
        pytest.skip(f"未找到 {env_path}，请从 .env.example 复制并填写")


def _truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes")


@pytest.mark.integration
def test_live_qwen_openai_compat_no_think_markers_in_raw_response(
    _load_project_dotenv,
):
    """直连 OpenAI 兼容 API：在 LLM_DISABLE_REASONING 下，原始 message 不得含 think 围栏。"""
    if not _truthy("RUN_QWEN_NO_THINK_LIVE"):
        pytest.skip("设置 RUN_QWEN_NO_THINK_LIVE=1 以对本机 .env 中的网关做实机校验")

    base_url = (os.getenv("OPENAI_BASE_URL") or "").strip()
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not base_url or not api_key:
        pytest.skip("需要 OPENAI_BASE_URL 与 OPENAI_API_KEY（见 .env.example）")

    if (os.getenv("LLM_PROVIDER") or "anthropic").strip().lower() != "openai":
        pytest.skip("本实机用例针对 LLM_PROVIDER=openai")

    if not is_llm_reasoning_disabled():
        pytest.fail(
            "请在 .env 中设置 LLM_DISABLE_REASONING=true，以校验「关思考」行为；"
            "并与 .env.example 中 Qwen3.5 推荐项保持一致。"
        )

    model = resolve_openai_chat_model(os.getenv("OPENAI_MODEL"))
    if not _truthy("RUN_QWEN_NO_THINK_LIVE_SKIP_MODEL_CHECK"):
        if "qwen" not in model.lower():
            pytest.skip(
                f"OPENAI_MODEL={model!r} 不含 qwen；测其它模型请设 RUN_QWEN_NO_THINK_LIVE_SKIP_MODEL_CHECK=1"
            )

    settings = Settings(api_key=api_key, base_url=base_url)

    async def _call_provider():
        provider = OpenAIProvider(settings)
        prompt = Prompt(
            system="你只输出 JSON，不要其它文字。",
            user='只输出一个 JSON对象：{"ping":true}，不要 markdown。',
        )
        messages = _build_chat_messages(prompt, settings.base_url)
        extras = _openai_no_think_request_options(settings.base_url)

        resp = await provider.async_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
            max_tokens=256,
            **extras,
        )
        assert resp.choices, "API 未返回 choices"
        msg = resp.choices[0].message

        assert not message_dump_has_think_leak(
            msg
        ), "原始响应仍含 think/redacted 标记，关思考可能未生效（检查模型版本、模板与 extra_body）"
        
        # 部分 Qwen 部署仍会把摘要写入 reasoning_content，与 content 并存；默认不强制该字段为空。
        if _truthy("RUN_QWEN_REQUIRE_EMPTY_REASONING_CHANNEL"):
            leak_reason = reasoning_channel_should_be_empty_when_disabled(msg)
            assert (
                leak_reason is None
            ), f"{leak_reason}；原始片段: content={getattr(msg, 'content', None)!r}"

        result = await provider.generate(
            prompt, GenerationConfig(max_tokens=256, temperature=0.2, model=model)
        )
        assert result.content.strip().startswith(
            "{"
        ), f"期望 JSON 开头，实际: {result.content[:200]!r}"

    asyncio.run(_call_provider())
