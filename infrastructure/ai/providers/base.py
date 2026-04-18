"""LLM 提供商基类"""
from abc import ABC
from domain.ai.services.llm_service import LLMService
from infrastructure.ai.config.settings import Settings


class BaseProvider(LLMService, ABC):
    """LLM 提供商基类

    所有 LLM 提供商的抽象基类，继承自 LLMService 接口。
    自动为子类的 generate 和 stream_generate 方法添加 Token 监控装饰器。
    
    Provider 名称自动从类名推断：
    - AnthropicProvider -> 'anthropic'
    - OpenAIProvider -> 'openai'
    - GeminiProvider -> 'gemini'
    """

    def __init__(self, settings: Settings):
        """初始化提供商

        Args:
            settings: AI 配置设置
        """
        self.settings = settings

    def __init_subclass__(cls, **kwargs):
        """子类创建时自动添加 Token 监控装饰器"""
        super().__init_subclass__(**kwargs)
        
        # 从类名推断 provider 名称：AnthropicProvider -> anthropic
        class_name = cls.__name__
        if class_name.endswith('Provider'):
            provider_name = class_name[:-8].lower()
        else:
            return
        
        from infrastructure.monitoring import watch_tokens, watch_stream_tokens
        
        # 检查 generate 方法
        generate_method = getattr(cls, 'generate', None)
        if generate_method and not getattr(generate_method, '_watched', False):
            # 跳过抽象方法
            if not getattr(generate_method, '__isabstractmethod__', False):
                wrapped = watch_tokens(provider_name)(generate_method)
                wrapped._watched = True
                cls.generate = wrapped
        
        # 检查 stream_generate 方法
        stream_method = getattr(cls, 'stream_generate', None)
        if stream_method and not getattr(stream_method, '_watched', False):
            # 跳过抽象方法
            if not getattr(stream_method, '__isabstractmethod__', False):
                wrapped = watch_stream_tokens(provider_name)(stream_method)
                wrapped._watched = True
                cls.stream_generate = wrapped
