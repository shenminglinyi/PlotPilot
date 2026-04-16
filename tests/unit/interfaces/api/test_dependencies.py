"""测试依赖注入配置"""
import os
import pytest
from unittest.mock import patch, MagicMock
import interfaces.api.dependencies as dependencies


class TestGetVectorStore:
    """测试 get_vector_store 依赖注入函数"""

    def setup_method(self):
        dependencies._vector_store_singleton = None

    def test_get_vector_store_returns_none_when_no_env(self):
        """未设置环境变量时默认返回 ChromaDB 实例。"""
        with patch.dict(os.environ, {}, clear=True):
            with patch("infrastructure.ai.chromadb_vector_store.ChromaDBVectorStore") as mock_chromadb:
                mock_instance = MagicMock()
                mock_chromadb.return_value = mock_instance

                result = dependencies.get_vector_store()

                assert result is mock_instance
                mock_chromadb.assert_called_once_with(persist_directory="./data/chromadb")

    def test_get_vector_store_returns_none_when_disabled(self):
        """VECTOR_STORE_ENABLED 为 false 时返回 None。"""
        with patch.dict(os.environ, {"VECTOR_STORE_ENABLED": "false"}, clear=True):
            result = dependencies.get_vector_store()
            assert result is None

    def test_get_vector_store_returns_qdrant_when_legacy_env_set(self):
        """兼容旧版 QDRANT_ENABLED=true 配置。"""
        with patch.dict(os.environ, {
            "QDRANT_ENABLED": "true",
            "QDRANT_HOST": "localhost",
            "QDRANT_PORT": "6333"
        }, clear=True):
            # Mock QdrantVectorStore to avoid actual connection
            with patch("infrastructure.ai.qdrant_vector_store.QdrantVectorStore") as mock_qdrant:
                mock_instance = MagicMock()
                mock_qdrant.return_value = mock_instance

                result = dependencies.get_vector_store()

                # 验证返回了实例
                assert result is mock_instance
                # 验证使用正确的参数初始化
                mock_qdrant.assert_called_once_with(
                    host="localhost",
                    port=6333,
                    api_key=None
                )

    def test_get_vector_store_returns_qdrant_when_store_type_set(self):
        """显式设置 VECTOR_STORE_TYPE=qdrant 时返回 QdrantVectorStore 实例。"""
        with patch.dict(os.environ, {
            "VECTOR_STORE_TYPE": "qdrant",
            "QDRANT_HOST": "localhost",
            "QDRANT_PORT": "6333"
        }, clear=True):
            with patch("infrastructure.ai.qdrant_vector_store.QdrantVectorStore") as mock_qdrant:
                mock_instance = MagicMock()
                mock_qdrant.return_value = mock_instance

                result = dependencies.get_vector_store()

                assert result is mock_instance
                mock_qdrant.assert_called_once_with(
                    host="localhost",
                    port=6333,
                    api_key=None
                )

    def test_get_vector_store_with_custom_host_port(self):
        """使用自定义 host 和 port"""
        with patch.dict(os.environ, {
            "VECTOR_STORE_TYPE": "qdrant",
            "QDRANT_HOST": "qdrant.example.com",
            "QDRANT_PORT": "6334"
        }, clear=True):
            with patch("infrastructure.ai.qdrant_vector_store.QdrantVectorStore") as mock_qdrant:
                mock_instance = MagicMock()
                mock_qdrant.return_value = mock_instance

                result = dependencies.get_vector_store()

                mock_qdrant.assert_called_once_with(
                    host="qdrant.example.com",
                    port=6334,
                    api_key=None
                )

    def test_get_vector_store_with_api_key(self):
        """使用 API key"""
        with patch.dict(os.environ, {
            "VECTOR_STORE_TYPE": "qdrant",
            "QDRANT_HOST": "localhost",
            "QDRANT_PORT": "6333",
            "QDRANT_API_KEY": "test-api-key"
        }, clear=True):
            with patch("infrastructure.ai.qdrant_vector_store.QdrantVectorStore") as mock_qdrant:
                mock_instance = MagicMock()
                mock_qdrant.return_value = mock_instance

                result = dependencies.get_vector_store()

                mock_qdrant.assert_called_once_with(
                    host="localhost",
                    port=6333,
                    api_key="test-api-key"
                )

    def test_get_vector_store_uses_qdrant_default_values(self):
        """只设置 qdrant 类型时使用默认 host/port。"""
        with patch.dict(os.environ, {
            "VECTOR_STORE_TYPE": "qdrant"
        }, clear=True):
            with patch("infrastructure.ai.qdrant_vector_store.QdrantVectorStore") as mock_qdrant:
                mock_instance = MagicMock()
                mock_qdrant.return_value = mock_instance

                result = dependencies.get_vector_store()

                # 验证使用默认值
                mock_qdrant.assert_called_once_with(
                    host="localhost",
                    port=6333,
                    api_key=None
                )

    def test_get_vector_store_returns_chromadb_by_default(self):
        """未指定类型时默认使用 ChromaDB。"""
        with patch.dict(os.environ, {}, clear=True):
            with patch("infrastructure.ai.chromadb_vector_store.ChromaDBVectorStore") as mock_chromadb:
                mock_instance = MagicMock()
                mock_chromadb.return_value = mock_instance

                result = dependencies.get_vector_store()

                assert result is mock_instance
                mock_chromadb.assert_called_once_with(persist_directory="./data/chromadb")
