"""测试依赖注入配置"""
import os
import pytest
from unittest.mock import patch, MagicMock
import interfaces.api.dependencies as dependencies
from infrastructure.ai.provider_factory import DynamicLLMService


def test_topic_idea_service_uses_analysis_llm_route():
    """选题/市场判断属于分析决策任务，应固定走 DS 分析模型路由。"""
    analysis_llm = MagicMock(name="analysis-llm")
    writing_llm = MagicMock(name="writing-llm")
    repository = MagicMock(name="topic-repository")
    novel_service = MagicMock(name="novel-service")

    with patch.object(dependencies, "get_analysis_llm_service", return_value=analysis_llm) as analysis_mock:
        with patch.object(dependencies, "get_writing_llm_service", return_value=writing_llm) as writing_mock:
            with patch.object(dependencies, "get_topic_idea_repository", return_value=repository):
                with patch.object(dependencies, "get_novel_service", return_value=novel_service):
                    service = dependencies.get_topic_idea_service()

    assert service._llm is analysis_llm
    analysis_mock.assert_called_once_with()
    writing_mock.assert_not_called()


def test_auto_bible_generator_uses_analysis_llm_route():
    """新书向导 Bible 是结构化规划/记忆种子，应走 DS 分析模型路由，避免 GPT 写作模型长思考超时。"""
    analysis_llm = MagicMock(name="analysis-llm")
    writing_llm = MagicMock(name="writing-llm")
    bible_service = MagicMock(name="bible-service")

    with patch.object(dependencies, "get_analysis_llm_service", return_value=analysis_llm) as analysis_mock:
        with patch.object(dependencies, "get_writing_llm_service", return_value=writing_llm) as writing_mock:
            with patch.object(dependencies, "get_bible_service", return_value=bible_service):
                generator = dependencies.get_auto_bible_generator()

    assert generator.llm_service is analysis_llm
    analysis_mock.assert_called_once_with()
    writing_mock.assert_not_called()


def test_setup_main_plot_suggestion_service_uses_analysis_llm_route():
    """向导主线候选推演也是结构化规划任务，应走 DS 分析模型路由。"""
    analysis_llm = MagicMock(name="analysis-llm")
    writing_llm = MagicMock(name="writing-llm")
    bible_service = MagicMock(name="bible-service")
    novel_service = MagicMock(name="novel-service")

    with patch.object(dependencies, "get_analysis_llm_service", return_value=analysis_llm) as analysis_mock:
        with patch.object(dependencies, "get_writing_llm_service", return_value=writing_llm) as writing_mock:
            with patch.object(dependencies, "get_bible_service", return_value=bible_service):
                with patch.object(dependencies, "get_novel_service", return_value=novel_service):
                    service = dependencies.get_setup_main_plot_suggestion_service()

    assert service._llm is analysis_llm
    analysis_mock.assert_called_once_with()
    writing_mock.assert_not_called()


def test_get_writing_llm_service_uses_dynamic_profile_runtime():
    """写作路由应跟随后台激活配置，不再固定 profile_id。"""
    dependencies.get_writing_llm_service.cache_clear()
    factory = MagicMock(name="factory")
    with patch.object(dependencies, "get_llm_provider_factory", return_value=factory):
        service = dependencies.get_writing_llm_service()
    assert isinstance(service, DynamicLLMService)
    assert service.factory is factory
    dependencies.get_writing_llm_service.cache_clear()


class TestGetVectorStore:
    """测试 get_vector_store 依赖注入函数"""

    def setup_method(self):
        dependencies._vector_store_singleton = None
        dependencies._vector_store_init_failed = False

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
