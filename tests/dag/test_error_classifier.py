"""节点错误分类器测试"""
import asyncio
import sqlite3
import pytest
from application.engine.dag.error_classifier import (
    ErrorClassification,
    ErrorLevel,
    NodeErrorClassifier,
    RetryStrategy,
)


class TestNodeErrorClassifier:
    """节点错误分类器测试"""

    def test_api_timeout_is_retryable(self):
        error = type("APITimeoutError", (Exception,), {})("请求超时")
        result = NodeErrorClassifier.classify(error)
        assert result.level == ErrorLevel.RETRYABLE
        assert result.strategy == RetryStrategy.EXPONENTIAL_BACKOFF
        assert result.max_retries == 3

    def test_rate_limit_is_retryable(self):
        error = type("RateLimitError", (Exception,), {})("请求频率超限")
        result = NodeErrorClassifier.classify(error)
        assert result.level == ErrorLevel.RETRYABLE
        assert result.max_retries == 3

    def test_connection_error_is_retryable(self):
        error = type("APIConnectionError", (Exception,), {})("连接失败")
        result = NodeErrorClassifier.classify(error)
        assert result.level == ErrorLevel.RETRYABLE
        assert result.strategy == RetryStrategy.LINEAR_BACKOFF
        assert result.max_retries == 5

    def test_bad_request_is_fatal(self):
        error = type("BadRequestError", (Exception,), {})("请求格式错误")
        result = NodeErrorClassifier.classify(error)
        assert result.level == ErrorLevel.FATAL
        assert result.node_impact == "block"

    def test_db_locked_is_retryable(self):
        error = sqlite3.OperationalError("database is locked")
        result = NodeErrorClassifier.classify(error)
        assert result.level == ErrorLevel.RETRYABLE
        assert result.max_retries == 10

    def test_db_other_error_is_recoverable(self):
        error = sqlite3.OperationalError("disk I/O error")
        result = NodeErrorClassifier.classify(error)
        assert result.level == ErrorLevel.RECOVERABLE
        assert result.strategy == RetryStrategy.CHECKPOINT_ROLLBACK

    def test_chromadb_error_is_degradable(self):
        error = Exception("chromadb connection failed")
        result = NodeErrorClassifier.classify(error)
        assert result.level == ErrorLevel.DEGRADABLE
        assert result.strategy == RetryStrategy.SKIP_WITH_DEFAULT

    def test_timeout_error_is_retryable(self):
        error = asyncio.TimeoutError()
        result = NodeErrorClassifier.classify(error)
        assert result.level == ErrorLevel.RETRYABLE
        assert result.strategy == RetryStrategy.SINGLE_RETRY

    def test_unknown_error_is_fatal(self):
        error = RuntimeError("未知运行时错误")
        result = NodeErrorClassifier.classify(error)
        assert result.level == ErrorLevel.FATAL
        assert "未知错误" in result.message

    def test_classify_with_node_type(self):
        error = Exception("chromadb error")
        result = NodeErrorClassifier.classify(error, node_type="val_kg_infer")
        assert result.level == ErrorLevel.DEGRADABLE
