"""Token 监控装饰器 - 低侵入性方案"""
import functools
import logging
import time
from typing import Callable, TypeVar, ParamSpec, AsyncIterator, Any

from infrastructure.monitoring import get_token_watcher

logger = logging.getLogger(__name__)

P = ParamSpec('P')
T = TypeVar('T')


def _extract_model(args: tuple, kwargs: dict) -> str:
    """从方法参数中提取模型名称"""
    # 优先从 kwargs 获取
    model = kwargs.get('model') or kwargs.get('config')
    if model and isinstance(model, str):
        return model
    if hasattr(model, 'model') and model.model:
        return model.model

    # 从位置参数提取：self, prompt, config
    if len(args) >= 3:
        config = args[2]
        if hasattr(config, 'model') and config.model:
            return config.model

    # 从 self.settings 回退
    self_arg = args[0] if args else None
    if self_arg and hasattr(self_arg, 'settings'):
        settings = self_arg.settings
        if hasattr(settings, 'default_model') and settings.default_model:
            return settings.default_model

    return 'unknown'


def _build_request_data(args: tuple, kwargs: dict) -> dict | None:
    """构建请求数据摘要"""
    data = {}

    prompt = kwargs.get('prompt')
    if not prompt and len(args) >= 2:
        prompt = args[1]

    if prompt is not None:
        if hasattr(prompt, '__dict__'):
            data['prompt'] = {k: v for k, v in vars(prompt).items() if not k.startswith('_')}
        else:
            data['prompt'] = str(prompt)

    config = kwargs.get('config')
    if not config and len(args) >= 3:
        config = args[2]

    if config and hasattr(config, '__dict__'):
        data['config'] = {k: v for k, v in vars(config).items() if not k.startswith('_')}

    return data if data else None


def _build_response_data(result: Any) -> dict | None:
    """构建响应数据摘要"""
    if not result:
        return None
    try:
        if hasattr(result, '__dict__'):
            return {k: v for k, v in vars(result).items() if not k.startswith('_')}
        if isinstance(result, str):
            return {'output': result}
        if hasattr(result, 'text'):
            return {'text': result.text}
        if hasattr(result, 'content'):
            return {'content': result.content}
        return {'result': str(result)}
    except Exception as e:
        return {'error': f'Failed to serialize: {e}'}


def _record_call(
    watcher,
    provider_name: str,
    model: str,
    args: tuple,
    kwargs: dict,
    start_time: float,
    success: bool,
    error_msg: str | None,
    input_tokens: int,
    output_tokens: int,
    result: Any = None,
    response_data: dict | None = None,
):
    """公共记录逻辑，async/sync 共用

    request_data / response_data 仅在详情记录开启时构建，避免无效计算
    """
    latency_ms = int((time.perf_counter() - start_time) * 1000)

    request_data = None
    resp_data = response_data
    if not watcher.config.usage_only:
        request_data = _build_request_data(args, kwargs)
        if resp_data is None:
            resp_data = _build_response_data(result)

    try:
        watcher.record_call(
            model=model,
            provider=provider_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            success=success,
            error_message=error_msg,
            request_data=request_data,
            response_data=resp_data,
        )
    except Exception as e:
        logger.warning(f'TokenWatcher record_call failed: {e}')


def watch_tokens(
    provider_name: str,
):
    """Token 监控装饰器

    自动记录 LLM 调用的 token 使用情况，对业务代码零侵入。

    用法:
        @watch_tokens('anthropic')
        async def generate(self, prompt, config) -> GenerationResult:
            ...

    装饰器会自动从 GenerationResult.token_usage 中提取 token 信息。
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            watcher = get_token_watcher()

            if not watcher.enabled:
                return await func(*args, **kwargs)

            model = _extract_model(args, kwargs)

            start_time = time.perf_counter()
            success = True
            error_msg = None
            input_tokens = 0
            output_tokens = 0
            result = None

            try:
                result = await func(*args, **kwargs)

                if hasattr(result, 'token_usage') and result.token_usage:
                    input_tokens = result.token_usage.input_tokens
                    output_tokens = result.token_usage.output_tokens

                return result
            except Exception as e:
                success = False
                error_msg = str(e)
                raise
            finally:
                _record_call(
                    watcher, provider_name, model,
                    args, kwargs, start_time, success, error_msg,
                    input_tokens, output_tokens, result,
                )

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            watcher = get_token_watcher()

            if not watcher.enabled:
                return func(*args, **kwargs)

            model = _extract_model(args, kwargs)

            start_time = time.perf_counter()
            success = True
            error_msg = None
            input_tokens = 0
            output_tokens = 0
            result = None

            try:
                result = func(*args, **kwargs)

                if hasattr(result, 'token_usage') and result.token_usage:
                    input_tokens = result.token_usage.input_tokens
                    output_tokens = result.token_usage.output_tokens

                return result
            except Exception as e:
                success = False
                error_msg = str(e)
                raise
            finally:
                _record_call(
                    watcher, provider_name, model,
                    args, kwargs, start_time, success, error_msg,
                    input_tokens, output_tokens, result,
                )

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def watch_stream_tokens(
    provider_name: str,
):
    """流式生成 Token 监控装饰器

    专门用于 stream_generate 方法，包装 AsyncIterator 并收集 token 信息。

    用法:
        @watch_stream_tokens('anthropic')
        async def stream_generate(self, prompt, config) -> AsyncIterator[str]:
            ...
    """
    def decorator(func: Callable[P, AsyncIterator[str]]) -> Callable[P, AsyncIterator[str]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> AsyncIterator[str]:
            watcher = get_token_watcher()

            if not watcher.enabled:
                async for chunk in func(*args, **kwargs):
                    yield chunk
                return

            model = _extract_model(args, kwargs)

            start_time = time.perf_counter()
            success = True
            error_msg = None
            input_tokens = 0
            output_tokens = 0
            chunk_count = 0
            response_chunks = []

            try:
                stream = func(*args, **kwargs)
                async for chunk in stream:
                    chunk_count += 1

                    if hasattr(chunk, '__dict__'):
                        usage = getattr(chunk, 'usage', None)
                        if usage:
                            input_tokens = getattr(usage, 'prompt_tokens', 0) or 0
                            output_tokens = getattr(usage, 'completion_tokens', 0) or 0

                    if len(response_chunks) < 10:
                        try:
                            if isinstance(chunk, str):
                                response_chunks.append(chunk)
                            elif hasattr(chunk, '__dict__'):
                                response_chunks.append({k: v for k, v in vars(chunk).items() if not k.startswith('_')})
                        except Exception:
                            pass

                    yield chunk
            except Exception as e:
                success = False
                error_msg = str(e)
                raise
            finally:
                if input_tokens == 0 and output_tokens == 0:
                    output_tokens = chunk_count * 4

                _record_call(
                    watcher, provider_name, model,
                    args, kwargs, start_time, success, error_msg,
                    input_tokens, output_tokens,
                    response_data={
                        'chunk_count': chunk_count,
                        'preview_chunks': response_chunks[:10],
                    },
                )

        return wrapper

    return decorator
