"""Infrastructure AI module.

避免包导入时强制拉起可选第三方 SDK（anthropic/openai 等）。
"""

from .config import Settings

__all__ = ["Settings"]
