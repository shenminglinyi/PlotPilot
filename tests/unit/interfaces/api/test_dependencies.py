"""测试依赖注入配置"""
import os
import pytest
from unittest.mock import patch, MagicMock
from interfaces.api.dependencies import get_vector_store


class TestGetVectorStore:
    """测试 get_vector_store 依赖注入函数"""

    _qdrant_env = {
        "VECTOR_STORE_ENABLED": "true",
        "VECTOR_STORE_TYPE": "qdrant",
    }

    def test_get_vector_store_returns_chromadb_by_default(self):
        """默认类型为 chromadb（仅启用向量存储时）"""
        with patch.dict(os.environ, {"VECTOR_STORE_ENABLED": "true"}, clear=True):
            with patch(
                "infrastructure.ai.chromadb_vector_store.ChromaDBVectorStore"
            ) as mock_chroma:
                mock_instance = MagicMock()
                mock_chroma.return_value = mock_instance
                result = get_vector_store()
                assert result is mock_instance
                mock_chroma.assert_called_once()

    def test_get_vector_store_returns_none_when_disabled(self):
        """VECTOR_STORE_ENABLED=false 时返回 None"""
        with patch.dict(os.environ, {"VECTOR_STORE_ENABLED": "false"}, clear=True):
            result = get_vector_store()
            assert result is None

    def test_get_vector_store_returns_qdrant_when_type_set(self):
        """VECTOR_STORE_TYPE=qdrant 时构造 QdrantVectorStore"""
        with patch.dict(
            os.environ,
            {**self._qdrant_env, "QDRANT_HOST": "localhost", "QDRANT_PORT": "6333"},
            clear=True,
        ):
            with patch(
                "infrastructure.ai.qdrant_vector_store.QdrantVectorStore"
            ) as mock_qdrant:
                mock_instance = MagicMock()
                mock_qdrant.return_value = mock_instance

                result = get_vector_store()

                # 验证返回了实例
                assert result is mock_instance
                # 验证使用正确的参数初始化
                mock_qdrant.assert_called_once_with(
                    host="localhost",
                    port=6333,
                    api_key=None,
                    url=None,
                    timeout=None,
                    https=None,
                )

    def test_get_vector_store_qdrant_custom_host_port(self):
        """Qdrant 自定义 host / port"""
        with patch.dict(
            os.environ,
            {
                **self._qdrant_env,
                "QDRANT_HOST": "qdrant.example.com",
                "QDRANT_PORT": "6334",
            },
            clear=True,
        ):
            with patch(
                "infrastructure.ai.qdrant_vector_store.QdrantVectorStore"
            ) as mock_qdrant:
                mock_instance = MagicMock()
                mock_qdrant.return_value = mock_instance

                result = get_vector_store()

                mock_qdrant.assert_called_once_with(
                    host="qdrant.example.com",
                    port=6334,
                    api_key=None,
                    url=None,
                    timeout=None,
                    https=None,
                )

    def test_get_vector_store_qdrant_with_api_key(self):
        """Qdrant API Key"""
        with patch.dict(
            os.environ,
            {
                **self._qdrant_env,
                "QDRANT_HOST": "localhost",
                "QDRANT_PORT": "6333",
                "QDRANT_API_KEY": "test-api-key",
            },
            clear=True,
        ):
            with patch(
                "infrastructure.ai.qdrant_vector_store.QdrantVectorStore"
            ) as mock_qdrant:
                mock_instance = MagicMock()
                mock_qdrant.return_value = mock_instance

                result = get_vector_store()

                mock_qdrant.assert_called_once_with(
                    host="localhost",
                    port=6333,
                    api_key="test-api-key",
                    url=None,
                    timeout=None,
                    https=None,
                )

    def test_get_vector_store_qdrant_url_and_options(self):
        """QDRANT_URL 与超时、HTTPS"""
        with patch.dict(
            os.environ,
            {
                **self._qdrant_env,
                "QDRANT_URL": "https://cluster.example.cloud.qdrant.io:6333",
                "QDRANT_TIMEOUT": "30",
                "QDRANT_HTTPS": "true",
                "QDRANT_API_KEY": "secret",
            },
            clear=True,
        ):
            with patch(
                "infrastructure.ai.qdrant_vector_store.QdrantVectorStore"
            ) as mock_qdrant:
                mock_instance = MagicMock()
                mock_qdrant.return_value = mock_instance

                get_vector_store()

                # 验证使用默认值
                mock_qdrant.assert_called_once_with(
                    host="localhost",
                    port=6333,
                    api_key="secret",
                    url="https://cluster.example.cloud.qdrant.io:6333",
                    timeout=30.0,
                    https=True,
                )
