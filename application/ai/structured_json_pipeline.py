"""通用结构化 JSON 输出管线。

完整流程：LLM 原始输出 -> 清洗 -> json_repair 修复 -> Pydantic schema 校验 -> 可选重试。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import List, Optional, Tuple, Type, TypeVar

from json_repair import repair_json
from pydantic import BaseModel, ValidationError

from application.ai.llm_output_sanitize import strip_reasoning_artifacts
from application.ai.llm_retry_policy import LLM_MAX_TOTAL_ATTEMPTS
from application.ai.trace_context import content_hash, preview_value
from domain.ai.services.llm_service import GenerationConfig, LLMService
from domain.ai.value_objects.prompt import Prompt
from infrastructure.ai.trace_recorder import get_trace_recorder

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# 校验或解析失败后的额外重试轮数；总次数 = 1 + 该值，且不超过全局上限。
DEFAULT_MAX_RETRIES = LLM_MAX_TOTAL_ATTEMPTS - 1


def _is_retryable_llm_error(exc: Exception) -> bool:
    """识别上游临时故障，避免 429/5xx/超时直接短路。"""
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


def sanitize_llm_output(raw: str) -> str:
    """对 LLM 原始输出进行清洗，去除干扰字符。"""
    from application.ai.llm_json_extract import strip_json_fences

    return strip_json_fences(strip_reasoning_artifacts(raw))


def parse_and_repair_json(cleaned: str) -> Tuple[Optional[dict], List[str]]:
    """尝试解析 JSON；失败则使用 json_repair 和外层花括号提取兜底。"""
    errors: List[str] = []

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data, []
        errors.append(f"根节点不是 JSON 对象，而是 {type(data).__name__}")
    except json.JSONDecodeError as exc:
        errors.append(f"标准 JSON 解析失败: {exc}")

    try:
        repaired = repair_json(cleaned)
        data = json.loads(repaired)
        if isinstance(data, dict):
            logger.debug("json_repair 修复成功")
            return data, []
        errors.append(f"json_repair 后根节点不是 JSON 对象，而是 {type(data).__name__}")
    except Exception as exc:
        errors.append(f"json_repair 修复失败: {exc}")

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        fragment = cleaned[start : end + 1]
        try:
            data = json.loads(fragment)
            if isinstance(data, dict):
                logger.debug("外层花括号提取解析成功")
                return data, []
        except json.JSONDecodeError:
            pass
        try:
            repaired = repair_json(fragment)
            data = json.loads(repaired)
            if isinstance(data, dict):
                logger.debug("外层花括号提取 + json_repair 修复成功")
                return data, []
        except Exception:
            pass

    return None, errors


def validate_json_schema(
    data: dict,
    model_cls: Type[T],
) -> Tuple[Optional[T], List[str]]:
    """使用 Pydantic 模型校验 dict。"""
    try:
        instance = model_cls.model_validate(data)
        return instance, []
    except ValidationError as exc:
        err_list = exc.errors()
        msgs = [
            f"{'/'.join(str(x) for x in err.get('loc', ()))}: {err.get('msg', '')}"
            for err in err_list[:12]
        ]
        return None, msgs or [str(exc)]


async def structured_json_generate(
    llm: LLMService,
    prompt: Prompt,
    config: GenerationConfig,
    schema_model: Type[T],
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> Optional[T]:
    """调用 LLM 获取结构化 JSON 输出，并经过清洗、修复、校验管线。"""
    current_prompt = prompt
    last_errors: List[str] = []
    total_attempts = min(1 + max(0, max_retries), LLM_MAX_TOTAL_ATTEMPTS)
    recorder = get_trace_recorder()

    for attempt in range(total_attempts):
        try:
            result = await llm.generate(current_prompt, config)
            raw = result.content if hasattr(result, "content") else str(result)
        except Exception as exc:
            logger.warning("结构化 JSON 管线 LLM 调用失败 (attempt=%d): %s", attempt, exc)
            last_errors = [str(exc)]
            recorder.record_span(
                phase="error",
                node_type="parser",
                error=str(exc),
                metadata={
                    "schema_model": schema_model.__name__,
                    "attempt": attempt + 1,
                    "stage": "llm_generate",
                },
            )
            if attempt < total_attempts - 1 and _is_retryable_llm_error(exc):
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

        cleaned = sanitize_llm_output(raw)
        data, parse_errors = parse_and_repair_json(cleaned)
        recorder.record_span(
            phase="output_parsed",
            node_type="parser",
            response_hash=content_hash(raw),
            response_preview=preview_value(raw),
            response_full=raw,
            error="; ".join(parse_errors[:8]) if parse_errors else None,
            metadata={
                "schema_model": schema_model.__name__,
                "attempt": attempt + 1,
                "parse_success": data is not None,
                "cleaned_hash": content_hash(cleaned),
            },
        )

        if data is not None:
            instance, schema_errors = validate_json_schema(data, schema_model)
            if instance is not None:
                recorder.record_span(
                    phase="schema_validated",
                    node_type="parser",
                    response_hash=content_hash(data),
                    response_preview=preview_value(data),
                    response_full=data,
                    metadata={
                        "schema_model": schema_model.__name__,
                        "attempt": attempt + 1,
                        "valid": True,
                    },
                )
                if attempt > 0:
                    logger.info("结构化 JSON 管线重试成功 (attempt=%d)", attempt)
                return instance
            last_errors = parse_errors + schema_errors
            recorder.record_span(
                phase="schema_validated",
                node_type="parser",
                response_hash=content_hash(data),
                response_preview=preview_value(data),
                response_full=data,
                error="; ".join(schema_errors[:8]),
                metadata={
                    "schema_model": schema_model.__name__,
                    "attempt": attempt + 1,
                    "valid": False,
                },
            )
        else:
            last_errors = parse_errors

        logger.warning(
            "结构化 JSON 管线校验失败 (第 %d/%d 次): %s",
            attempt + 1,
            total_attempts,
            last_errors,
        )

        if attempt < total_attempts - 1:
            recorder.record_span(
                phase="fallback_used",
                node_type="parser",
                error="; ".join(last_errors[:8]),
                metadata={
                    "schema_model": schema_model.__name__,
                    "reason": "parse_or_schema_failed",
                    "next_attempt": attempt + 2,
                },
            )
            error_feedback = "\n".join(f"- {err}" for err in last_errors[:8])
            retry_note = (
                "\n\n【系统反馈】你上一次的输出格式有误，请修正后重新输出：\n"
                f"{error_feedback}\n"
                "请只输出符合要求的 JSON 对象，不要包含其他文字。"
            )
            current_prompt = Prompt(
                system=prompt.system,
                user=prompt.user + retry_note,
            )

    logger.error(
        "结构化 JSON 管线全部重试耗尽 (total_attempts=%d): %s",
        total_attempts,
        last_errors,
    )
    recorder.record_span(
        phase="error",
        node_type="parser",
        error="; ".join(last_errors[:8]),
        metadata={
            "schema_model": schema_model.__name__,
            "stage": "exhausted",
            "total_attempts": total_attempts,
        },
    )
    return None
