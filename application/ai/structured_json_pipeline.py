"""通用结构化 JSON 输出管线。

完整流程：LLM 原始输出 → 清洗 → json_repair 修复 → Pydantic schema 校验 → 重试。

设计要点：
- 所有需要 LLM 返回结构化 JSON 的服务均可复用此管线
- 调用方只需提供 LLMService、Prompt、GenerationConfig、Pydantic 模型
- 管线自动处理清洗/修复/校验/重试，返回 Pydantic 模型实例或 None
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Generic, List, Optional, Tuple, Type, TypeVar

from pydantic import BaseModel, ValidationError
from json_repair import repair_json

from domain.ai.services.llm_service import GenerationConfig, LLMService
from domain.ai.value_objects.prompt import Prompt
from application.ai.llm_output_sanitize import strip_reasoning_artifacts
from application.ai.llm_retry_policy import LLM_MAX_TOTAL_ATTEMPTS

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# 校验/解析失败后的额外重试轮数（总次数 = 1 + 该值，且不超过 LLM_MAX_TOTAL_ATTEMPTS）
DEFAULT_MAX_RETRIES = LLM_MAX_TOTAL_ATTEMPTS - 1


def _is_retryable_llm_error(exc: Exception) -> bool:
    """识别上游临时性故障，避免 529/429/5xx 直接短路。"""
    message = str(exc).lower()
    retryable_markers = (
        "overloaded_error",
        "rate limit",
        "timeout",
        "temporar",
        "connection reset",
        "service unavailable",
    )
    retryable_statuses = (" 429", " 500", " 502", " 503", " 504", " 529")
    return any(marker in message for marker in retryable_markers) or any(
        status in message for status in retryable_statuses
    )


def _retry_delay_seconds(attempt: int) -> float:
    """简单指数退避，保持总等待可控。"""
    return min(1.5 * (2 ** attempt), 8.0)


# ---------------------------------------------------------------------------
# 第一步：正则清洗
# ---------------------------------------------------------------------------


def sanitize_llm_output(raw: str) -> str:
    """对 LLM 原始输出进行清洗，去除干扰字符。

    处理内容：
    1. BOM 头 (\\ufeff)
    2. 思维链 / reasoning 块（见 strip_reasoning_artifacts）
    3. Markdown 代码块围栏 (```json ... ```)
    4. 前后空白 / 零宽字符
    """
    s = raw

    # 1. 去 BOM
    if s and s[0] == "\ufeff":
        s = s[1:]

    # 2. 去思维链与厂商 reasoning 围栏
    s = strip_reasoning_artifacts(s)

    # 3. 去 markdown 围栏
    #    匹配 ```json ... ``` 或 ``` ... ```
    fence_pattern = re.compile(
        r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL
    )
    fence_match = fence_pattern.search(s)
    if fence_match:
        s = fence_match.group(1)

    # 4. 去零宽字符
    s = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", s)

    # 5. strip
    s = s.strip()

    return s


# ---------------------------------------------------------------------------
# 第二步：JSON 解析 + json_repair 修复
# ---------------------------------------------------------------------------


def parse_and_repair_json(cleaned: str) -> Tuple[Optional[dict], List[str]]:
    """尝试解析 JSON；失败则用 json_repair 修复后重试。

    Returns:
        (dict, [])  成功
        (None, [错误信息])  完全无法解析
    """
    errors: List[str] = []

    # 第一次尝试：标准 json.loads
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data, []
        errors.append(f"根节点不是 JSON 对象，而是 {type(data).__name__}")
    except json.JSONDecodeError as e:
        errors.append(f"标准 JSON 解析失败: {e}")

    # 第二次尝试：json_repair
    try:
        repaired = repair_json(cleaned)
        data = json.loads(repaired)
        if isinstance(data, dict):
            logger.debug("json_repair 修复成功")
            return data, []
        errors.append(f"json_repair 后根节点不是 JSON 对象，而是 {type(data).__name__}")
    except Exception as e:
        errors.append(f"json_repair 修复失败: {e}")

    # 第三次尝试：提取最外层 { }
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        fragment = cleaned[start : end + 1]
        try:
            data = json.loads(fragment)
            if isinstance(data, dict):
                logger.debug("最外层花括号提取解析成功")
                return data, []
        except json.JSONDecodeError:
            pass
        # 对提取片段再走一次 json_repair
        try:
            repaired = repair_json(fragment)
            data = json.loads(repaired)
            if isinstance(data, dict):
                logger.debug("最外层花括号提取 + json_repair 修复成功")
                return data, []
        except Exception:
            pass

    return None, errors


# ---------------------------------------------------------------------------
# 第三步：Pydantic schema 校验
# ---------------------------------------------------------------------------


def validate_json_schema(
    data: dict,
    model_cls: Type[T],
) -> Tuple[Optional[T], List[str]]:
    """用 Pydantic 模型校验 dict，extra='forbid' 拒绝多余字段。

    Returns:
        (model_instance, [])  校验通过
        (None, [错误信息])  校验失败
    """
    try:
        instance = model_cls.model_validate(data)
        return instance, []
    except ValidationError as e:
        err_list = e.errors()
        msgs = [
            f"{'/'.join(str(x) for x in err.get('loc', ()))}: {err.get('msg', '')}"
            for err in err_list[:12]
        ]
        return None, msgs or [str(e)]


# ---------------------------------------------------------------------------
# 完整管线：清洗 → 修复 → 校验 → 可选重试
# ---------------------------------------------------------------------------


async def structured_json_generate(
    llm: LLMService,
    prompt: Prompt,
    config: GenerationConfig,
    schema_model: Type[T],
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> Optional[T]:
    """调用 LLM 获取结构化 JSON 输出，经过完整清洗/修复/校验管线。

    如果校验失败，会将错误信息追加到 prompt 中让 LLM 重新生成。
    总调用次数（含首次）不超过 LLM_MAX_TOTAL_ATTEMPTS（默认 3），全部失败返回 None。

    Args:
        llm: LLM 服务实例
        prompt: 原始 prompt
        config: 生成配置（可含 response_format 强制 JSON）
        schema_model: Pydantic 模型类，用于 schema 校验
        max_retries: 期望的「额外重试轮数」，会被压缩到总次数上限内

    Returns:
        校验通过的 Pydantic 模型实例，或 None（全部失败）

    Usage::

        payload = await structured_json_generate(
            llm=self._llm,
            prompt=prompt,
            config=GenerationConfig(max_tokens=512, temperature=0.3,
                                    response_format=tension_scoring_response_format()),
            schema_model=TensionScoringLlmPayload,
        )
        if payload is None:
            return TensionDimensions.neutral()
        return tension_scoring_payload_to_domain(payload)
    """
    current_prompt = prompt
    last_errors: List[str] = []
    total_attempts = min(1 + max(0, max_retries), LLM_MAX_TOTAL_ATTEMPTS)

    for attempt in range(total_attempts):
        # --- 调用 LLM ---
        try:
            result = await llm.generate(current_prompt, config)
            raw = result.content if hasattr(result, "content") else str(result)
        except Exception as e:
            logger.warning("结构化 JSON 管线 LLM 调用失败 (attempt=%d): %s", attempt, e)
            last_errors = [str(e)]
            if attempt < total_attempts - 1 and _is_retryable_llm_error(e):
                delay = _retry_delay_seconds(attempt)
                logger.info(
                    "结构化 JSON 管线遇到可重试错误，%.1f 秒后重试 (attempt=%d/%d)",
                    delay,
                    attempt + 1,
                    total_attempts,
                )
                await asyncio.sleep(delay)
                continue
            return None

        # --- 清洗 → 修复 → 校验 ---
        cleaned = sanitize_llm_output(raw)
        data, parse_errors = parse_and_repair_json(cleaned)

        if data is not None:
            instance, schema_errors = validate_json_schema(data, schema_model)
            if instance is not None:
                if attempt > 0:
                    logger.info("结构化 JSON 管线重试成功 (attempt=%d)", attempt)
                return instance
            last_errors = parse_errors + schema_errors
        else:
            last_errors = parse_errors

        logger.warning(
            "结构化 JSON 管线校验失败 (第 %d/%d 次): %s",
            attempt + 1,
            total_attempts,
            last_errors,
        )

        # --- 构建重试 prompt：把错误反馈给 LLM ---
        if attempt < total_attempts - 1:
            error_feedback = "\n".join(f"- {e}" for e in last_errors[:8])
            retry_note = (
                f"\n\n【系统反馈】你上一次的输出格式有误，请修正后重新输出：\n"
                f"{error_feedback}\n"
                f"请只输出符合要求的 JSON 对象，不要包含其他文字。"
            )
            # 在 user message 末尾追加错误反馈
            current_prompt = Prompt(
                system=prompt.system,
                user=prompt.user + retry_note,
            )

    logger.error(
        "结构化 JSON 管线全部重试耗尽 (total_attempts=%d): %s",
        total_attempts, last_errors,
    )
    return None
