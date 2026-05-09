"""节点错误分类器 -- 根据异常类型决定处理策略"""
from __future__ import annotations

import asyncio
import sqlite3
from enum import Enum
from dataclasses import dataclass
from typing import Optional


class ErrorLevel(str, Enum):
    IGNORABLE = "ignorable"
    RETRYABLE = "retryable"
    DEGRADABLE = "degradable"
    RECOVERABLE = "recoverable"
    FATAL = "fatal"


class RetryStrategy(str, Enum):
    NONE = "none"
    SINGLE_RETRY = "single_retry"
    LINEAR_BACKOFF = "linear_backoff"
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    SKIP_WITH_DEFAULT = "skip_with_default"
    CHECKPOINT_ROLLBACK = "checkpoint_rollback"


@dataclass
class ErrorClassification:
    level: ErrorLevel
    strategy: RetryStrategy
    max_retries: int = 0
    node_impact: str = "none"  # none / delay / degrade / block / rollback
    message: str = ""
    default_value: Optional[dict] = None


class NodeErrorClassifier:
    """节点错误分类器"""

    @classmethod
    def classify(cls, error: Exception, node_type: str = "") -> ErrorClassification:
        # LLM API 错误
        error_name = type(error).__name__
        error_msg = str(error)

        if error_name in ("APITimeoutError", "RateLimitError"):
            return ErrorClassification(
                level=ErrorLevel.RETRYABLE,
                strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
                max_retries=3,
                node_impact="delay",
            )

        if error_name == "APIConnectionError":
            return ErrorClassification(
                level=ErrorLevel.RETRYABLE,
                strategy=RetryStrategy.LINEAR_BACKOFF,
                max_retries=5,
                node_impact="delay",
            )

        if error_name == "BadRequestError":
            return ErrorClassification(
                level=ErrorLevel.FATAL,
                strategy=RetryStrategy.NONE,
                node_impact="block",
                message="LLM 请求格式错误，请检查 Prompt 模板",
            )

        # 数据库错误
        if isinstance(error, sqlite3.OperationalError):
            if "locked" in error_msg:
                return ErrorClassification(
                    level=ErrorLevel.RETRYABLE,
                    strategy=RetryStrategy.LINEAR_BACKOFF,
                    max_retries=10,
                    node_impact="delay",
                )
            return ErrorClassification(
                level=ErrorLevel.RECOVERABLE,
                strategy=RetryStrategy.CHECKPOINT_ROLLBACK,
                node_impact="rollback",
            )

        # 向量库错误
        if "chromadb" in error_msg.lower() or "chroma" in error_name.lower():
            return ErrorClassification(
                level=ErrorLevel.DEGRADABLE,
                strategy=RetryStrategy.SKIP_WITH_DEFAULT,
                node_impact="degrade",
                default_value={"vector_stored": False},
            )

        # 超时
        if isinstance(error, asyncio.TimeoutError) or "timeout" in error_msg.lower():
            return ErrorClassification(
                level=ErrorLevel.RETRYABLE,
                strategy=RetryStrategy.SINGLE_RETRY,
                max_retries=1,
                node_impact="delay",
            )

        # 未知错误
        return ErrorClassification(
            level=ErrorLevel.FATAL,
            strategy=RetryStrategy.NONE,
            node_impact="block",
            message=f"未知错误: {error_name}: {error_msg}",
        )
