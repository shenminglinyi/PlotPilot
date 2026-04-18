"""Token 监控装饰器 - 低侵入性方案"""
import functools
import time
from typing import Callable, TypeVar, ParamSpec, AsyncIterator, Any

from infrastructure.monitoring import get_token_watcher

P = ParamSpec('P')
T = TypeVar('T')


def watch_tokens(
    provider_name: str,
    operation_type: str = 'generate',
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
            
            self_arg = args[0] if args else None
            model = 'unknown'
            
            if len(args) >= 3:
                config = args[2]
                if hasattr(config, 'model') and config.model:
                    model = config.model
                elif self_arg and hasattr(self_arg, 'settings'):
                    settings = self_arg.settings
                    if hasattr(settings, 'default_model') and settings.default_model:
                        model = settings.default_model
            
            start_time = time.perf_counter()
            success = True
            error_msg = None
            input_tokens = 0
            output_tokens = 0
            result = None
            
            request_data = None
            if len(args) >= 2:
                prompt = args[1]
                if hasattr(prompt, '__dict__'):
                    request_data = {'prompt': {k: v for k, v in vars(prompt).items() if not k.startswith('_')}}
                else:
                    request_data = {'prompt': str(prompt)}
                
                if len(args) >= 3:
                    config = args[2]
                    if hasattr(config, '__dict__'):
                        request_data['config'] = {k: v for k, v in vars(config).items() if not k.startswith('_')}
            
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
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                
                response_data = None
                if result:
                    try:
                        if hasattr(result, '__dict__'):
                            response_data = {k: v for k, v in vars(result).items() if not k.startswith('_')}
                        elif isinstance(result, str):
                            response_data = {'output': result}
                        elif hasattr(result, 'text'):
                            response_data = {'text': result.text}
                        elif hasattr(result, 'content'):
                            response_data = {'content': result.content}
                        else:
                            response_data = {'result': str(result)}
                    except Exception as e:
                        response_data = {'error': f'Failed to serialize: {e}'}
                
                try:
                    watcher.record_call(
                        model=model,
                        provider=provider_name,
                        operation_type=operation_type,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        latency_ms=latency_ms,
                        success=success,
                        error_message=error_msg,
                        request_data=request_data,
                        response_data=response_data,
                    )
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f'TokenWatcher record_call failed: {e}')
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            watcher = get_token_watcher()
            
            if not watcher.enabled:
                return func(*args, **kwargs)
            
            self_arg = args[0] if args else None
            model = 'unknown'
            
            if len(args) >= 3:
                config = args[2]
                if hasattr(config, 'model') and config.model:
                    model = config.model
                elif self_arg and hasattr(self_arg, 'settings'):
                    settings = self_arg.settings
                    if hasattr(settings, 'default_model') and settings.default_model:
                        model = settings.default_model
            
            start_time = time.perf_counter()
            success = True
            error_msg = None
            input_tokens = 0
            output_tokens = 0
            result = None
            
            request_data = None
            if len(args) >= 2:
                prompt = args[1]
                if hasattr(prompt, '__dict__'):
                    request_data = {'prompt': {k: v for k, v in vars(prompt).items() if not k.startswith('_')}}
                else:
                    request_data = {'prompt': str(prompt)}
                
                if len(args) >= 3:
                    config = args[2]
                    if hasattr(config, '__dict__'):
                        request_data['config'] = {k: v for k, v in vars(config).items() if not k.startswith('_')}
            
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
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                
                response_data = None
                if result:
                    try:
                        if hasattr(result, '__dict__'):
                            response_data = {k: v for k, v in vars(result).items() if not k.startswith('_')}
                        elif isinstance(result, str):
                            response_data = {'output': result}
                        elif hasattr(result, 'text'):
                            response_data = {'text': result.text}
                        elif hasattr(result, 'content'):
                            response_data = {'content': result.content}
                        else:
                            response_data = {'result': str(result)}
                    except Exception as e:
                        response_data = {'error': f'Failed to serialize: {e}'}
                
                try:
                    watcher.record_call(
                        model=model,
                        provider=provider_name,
                        operation_type=operation_type,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        latency_ms=latency_ms,
                        success=success,
                        error_message=error_msg,
                        request_data=request_data,
                        response_data=response_data,
                    )
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f'TokenWatcher record_call failed: {e}')
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def watch_stream_tokens(
    provider_name: str,
    operation_type: str = 'stream_generate',
):
    """流式生成 Token 监控装饰器
    
    专门用于 stream_generate 方法，包装 AsyncIterator 并收集 token 信息。
    
    用法:
        @watch_stream_tokens('anthropic')
        async def stream_generate(self, prompt, config) -> AsyncIterator[str]:
            ...
    
    装饰器会自动：
    1. 包装整个流
    2. 从流中提取 token 信息（如果可用）
    3. 记录监控数据
    """
    def decorator(func: Callable[P, AsyncIterator[str]]) -> Callable[P, AsyncIterator[str]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> AsyncIterator[str]:
            watcher = get_token_watcher()
            
            if not watcher.enabled:
                async for chunk in func(*args, **kwargs):
                    yield chunk
                return
            
            self_arg = args[0] if args else None
            model = 'unknown'
            
            if len(args) >= 3:
                config = args[2]
                if hasattr(config, 'model') and config.model:
                    model = config.model
                elif self_arg and hasattr(self_arg, 'settings'):
                    settings = self_arg.settings
                    if hasattr(settings, 'default_model') and settings.default_model:
                        model = settings.default_model
            
            start_time = time.perf_counter()
            success = True
            error_msg = None
            input_tokens = 0
            output_tokens = 0
            chunk_count = 0
            
            request_data = None
            if len(args) >= 2:
                prompt = args[1]
                if hasattr(prompt, '__dict__'):
                    request_data = {'prompt': {k: v for k, v in vars(prompt).items() if not k.startswith('_')}}
                else:
                    request_data = {'prompt': str(prompt)}
                
                if len(args) >= 3:
                    config = args[2]
                    if hasattr(config, '__dict__'):
                        request_data['config'] = {k: v for k, v in vars(config).items() if not k.startswith('_')}
            
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
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                
                if input_tokens == 0 and output_tokens == 0:
                    output_tokens = chunk_count * 4
                
                response_data = {
                    'chunk_count': chunk_count,
                    'preview_chunks': response_chunks[:10]
                }
                
                try:
                    watcher.record_call(
                        model=model,
                        provider=provider_name,
                        operation_type=operation_type,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        latency_ms=latency_ms,
                        success=success,
                        error_message=error_msg,
                        request_data=request_data,
                        response_data=response_data,
                    )
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f'TokenWatcher record_call failed: {e}')
        
        return wrapper
    
    return decorator
