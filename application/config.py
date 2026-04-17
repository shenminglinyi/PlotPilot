"""PlotPilot 中央配置

所有业务层常量集中在此处定义，避免在各模块中散落硬编码值。

使用方式：
    from application.config import AppConfig

    words = AppConfig.DEFAULT_WORDS_PER_CHAPTER
    port  = AppConfig.DEFAULT_PORT

扩展指南：
    - 新增常量直接在对应分组下添加类属性即可
    - 运行时可覆盖的值（端口、路径等）优先读取环境变量，
      AppConfig 提供 classmethod 作为统一入口
    - 不要在此处放 API Key / 密码等敏感信息（使用 .env）
"""

from __future__ import annotations

import os


class AppConfig:
    # ──────────────────────────────────────────────
    # 服务端口
    # ──────────────────────────────────────────────
    DEFAULT_PORT: int = int(os.getenv("PLOTPILOT_PORT", "8005"))

    # ──────────────────────────────────────────────
    # 小说 / 章节默认值
    # ──────────────────────────────────────────────
    DEFAULT_WORDS_PER_CHAPTER: int = int(
        os.getenv("DEFAULT_WORDS_PER_CHAPTER", "3500")
    )
    # 节拍（Beat）拆分时各类型的目标字数
    BEAT_TARGET_WORDS_SENSORY: int = 500
    BEAT_TARGET_WORDS_DIALOGUE: int = 800
    BEAT_TARGET_WORDS_ACTION: int = 600
    BEAT_TARGET_WORDS_EMOTION: int = 500
    BEAT_TARGET_WORDS_DEFAULT: int = 700

    # ──────────────────────────────────────────────
    # LLM 上下文预算（token）
    # ──────────────────────────────────────────────
    CONTEXT_MAX_TOKENS: int = int(os.getenv("CONTEXT_MAX_TOKENS", "35000"))

    # ──────────────────────────────────────────────
    # 向量存储
    # ──────────────────────────────────────────────
    VECTOR_STORE_PATH: str = os.getenv("VECTOR_STORE_PATH", "./data/chromadb")

    # ──────────────────────────────────────────────
    # 数据目录（与 application/paths.py 保持同步）
    # ──────────────────────────────────────────────
    DATA_DIR: str = os.getenv("PLOTPILOT_DATA_DIR", "./data")

    # ──────────────────────────────────────────────
    # 导出格式白名单
    # ──────────────────────────────────────────────
    SUPPORTED_EXPORT_FORMATS: tuple[str, ...] = ("epub", "pdf", "docx", "markdown")

    # ──────────────────────────────────────────────
    # 题材（Genre）枚举
    # 前后端共用，避免字符串散落各处
    # ──────────────────────────────────────────────
    GENRES: dict[str, str] = {
        "xuanhuan": "玄幻",
        "dushi": "都市",
        "scifi": "科幻",
        "history": "历史",
        "wuxia": "武侠",
        "xianxia": "仙侠",
        "fantasy": "奇幻",
        "game": "游戏",
        "suspense": "悬疑",
        "romance": "言情",
        "other": "其他",
    }

    @classmethod
    def genre_label(cls, key: str) -> str:
        """返回题材中文标签，未知 key 原样返回。"""
        return cls.GENRES.get(key, key)
