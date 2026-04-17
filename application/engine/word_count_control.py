"""章节生成字数控制引擎适配层。

对外暴露 async 闭环函数；底层规则仍由 ``WordControlService`` 提供。
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, Optional
import inspect

from application.engine.services.word_control_service import WordControlService
from domain.ai.services.llm_service import GenerationConfig
from domain.ai.value_objects.prompt import Prompt


_word_control_service = WordControlService()


def _coerce_content(result: Any) -> str:
    if isinstance(result, str):
        return result
    return str(getattr(result, "content", "") or "")


async def _invoke_llm_caller(
    llm_caller: Callable[..., Awaitable[Any]],
    prompt: Prompt,
    config: Optional[GenerationConfig],
) -> Any:
    """兼容 `llm_caller(prompt)` 与 `llm_caller(prompt, config)` 两种签名。"""
    try:
        signature = inspect.signature(llm_caller)
    except (TypeError, ValueError):
        signature = None

    if signature is not None:
        positional = [
            parameter
            for parameter in signature.parameters.values()
            if parameter.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]
        has_varargs = any(
            parameter.kind == inspect.Parameter.VAR_POSITIONAL
            for parameter in signature.parameters.values()
        )
        if has_varargs or len(positional) >= 2:
            return await llm_caller(prompt, config or GenerationConfig())

    return await llm_caller(prompt)


async def check_word_count(text: str, target: int, tolerance: float = 0.15) -> Dict[str, Any]:
    """检测正文是否落在目标字数容忍区间内。"""
    result = _word_control_service.check_word_count(text, target, tolerance=tolerance)
    return {
        "actual_word_count": result.actual,
        "target_word_count": result.target,
        "delta": result.delta,
        "status": result.status,
        "within_tolerance": result.within_tolerance,
        "min_allowed": result.min_allowed,
        "max_allowed": result.max_allowed,
        "tolerance": result.tolerance,
    }


async def trim_to_target(text: str, target: int) -> str:
    """将超长正文裁剪到目标附近，优先保留完整句边界。"""
    return _word_control_service.trim_to_target(text, target)


async def generate_with_word_control(
    prompt: Prompt,
    target_words: int,
    llm_caller: Callable[..., Awaitable[Any]],
    *,
    initial_content: Optional[str] = None,
    emit_event: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    generation_config: Optional[GenerationConfig] = None,
) -> Dict[str, Any]:
    """执行生成 -> 检测 -> 补写/裁剪闭环。"""
    if initial_content is None:
        initial_result = await _invoke_llm_caller(llm_caller, prompt, generation_config)
        content = _coerce_content(initial_result).strip()
    else:
        content = (initial_content or "").strip()
    best_content = content
    best_check = _word_control_service.check_word_count(best_content, target_words)
    expansion_attempts = 0
    trim_applied = False
    fallback_used = False

    if best_check.status == "too_short":
        for attempt in range(1, _word_control_service.max_expansion_attempts + 1):
            expansion_attempts = attempt
            if emit_event is not None:
                await emit_event(
                    {
                        "type": "phase",
                        "phase": "post",
                        "status_text": f"自动补写第 {attempt} 轮",
                        "word_control_step": "expanding",
                        "word_control_attempt": attempt,
                    }
                )
            expansion_prompt = _word_control_service.build_expansion_prompt(
                existing_text=best_content,
                outline=prompt.user,
                target=target_words,
                current=best_check.actual,
                attempt=attempt,
                max_attempts=_word_control_service.max_expansion_attempts,
            )
            addition_result = await _invoke_llm_caller(llm_caller, expansion_prompt, generation_config)
            addition = _coerce_content(addition_result).strip()
            if addition:
                best_content = f"{best_content.rstrip()}\n\n{addition}".strip()
            current_check = _word_control_service.check_word_count(best_content, target_words)
            if abs(current_check.delta) <= abs(best_check.delta):
                best_check = current_check
            if current_check.within_tolerance:
                best_check = current_check
                break

        if not best_check.within_tolerance:
            fallback_used = expansion_attempts >= _word_control_service.max_expansion_attempts

    final_check = _word_control_service.check_word_count(best_content, target_words)
    if abs(final_check.delta) <= abs(best_check.delta):
        best_check = final_check

    if best_check.status == "too_long":
        if emit_event is not None:
            await emit_event(
                {
                    "type": "phase",
                    "phase": "post",
                    "status_text": "正文超长，正在智能裁剪",
                    "word_control_step": "trimming",
                }
            )
        trimmed_content = await trim_to_target(best_content, target_words)
        trimmed_check = _word_control_service.check_word_count(trimmed_content, target_words)
        if abs(trimmed_check.delta) <= abs(best_check.delta):
            best_content = trimmed_content
            best_check = trimmed_check
        trim_applied = trimmed_content != content

    action = "none"
    if trim_applied:
        action = "trimmed"
    elif expansion_attempts > 0:
        action = "expanded"

    return {
        "content": best_content,
        "actual_word_count": best_check.actual,
        "target_word_count": best_check.target,
        "delta": best_check.delta,
        "status": best_check.status,
        "within_tolerance": best_check.within_tolerance,
        "expansion_attempts": expansion_attempts,
        "trim_applied": trim_applied,
        "fallback_used": fallback_used,
        "action": action,
        "min_allowed": best_check.min_allowed,
        "max_allowed": best_check.max_allowed,
        "tolerance": best_check.tolerance,
    }
