"""Application composition root helpers.

The public functions in ``interfaces.api.dependencies`` remain the FastAPI
dependency surface. This container gives those functions a single place to
delegate long-lived infrastructure wiring.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from application.ai.llm_control_service import LLMControlService
from application.paths import DATA_DIR
from domain.ai.services.vector_store import VectorStore
from infrastructure.ai.provider_factory import DynamicLLMService, LLMProviderFactory
from infrastructure.persistence.storage.file_storage import FileStorage
from interfaces.api.settings import BackendSettings, get_backend_settings

logger = logging.getLogger(__name__)


@dataclass
class AppContainer:
    settings: BackendSettings = field(default_factory=get_backend_settings)
    _storage: FileStorage | None = None
    _llm_control_service: LLMControlService | None = None
    _llm_provider_factory: LLMProviderFactory | None = None
    _llm_service: DynamicLLMService | None = None
    _vector_store: Optional[VectorStore] = None
    _vector_store_init_failed: bool = False

    def reload_settings(self) -> None:
        self.settings = get_backend_settings()

    def get_storage(self) -> FileStorage:
        if self._storage is None:
            self._storage = FileStorage(DATA_DIR)
        return self._storage

    def get_llm_control_service(self) -> LLMControlService:
        if self._llm_control_service is None:
            self._llm_control_service = LLMControlService()
        return self._llm_control_service

    def get_llm_provider_factory(self) -> LLMProviderFactory:
        if self._llm_provider_factory is None:
            self._llm_provider_factory = LLMProviderFactory(
                self.get_llm_control_service()
            )
        return self._llm_provider_factory

    def get_llm_service(self) -> DynamicLLMService:
        if self._llm_service is None:
            self._llm_service = DynamicLLMService(self.get_llm_provider_factory())
        return self._llm_service

    def get_vector_store(self) -> Optional[VectorStore]:
        if self._vector_store is not None:
            return self._vector_store
        if self._vector_store_init_failed:
            return None
        vector_settings = self.settings.vector_store
        if not vector_settings.enabled:
            return None

        try:
            if vector_settings.use_qdrant:
                from infrastructure.ai.qdrant_vector_store import QdrantVectorStore

                host = vector_settings.qdrant_host
                port = int(vector_settings.qdrant_port)
                self._vector_store = QdrantVectorStore(
                    host=host,
                    port=port,
                    api_key=vector_settings.qdrant_api_key,
                )
                logger.info("Qdrant 向量存储初始化成功: %s:%s", host, port)
                return self._vector_store

            from infrastructure.ai.chromadb_vector_store import ChromaDBVectorStore

            self._vector_store = ChromaDBVectorStore(
                persist_directory=vector_settings.persist_directory
            )
            logger.info("本地向量存储初始化成功: %s", vector_settings.persist_directory)
            return self._vector_store
        except Exception as exc:
            self._vector_store_init_failed = True
            logger.warning(
                "向量存储初始化失败，已降级禁用。"
                "如需使用向量功能，请安装依赖: pip install -r requirements-local.txt"
                " 或设置 VECTOR_STORE_TYPE=qdrant。错误: %s",
                exc,
            )
            return None

    def reset_vector_store(self) -> None:
        self._vector_store = None
        self._vector_store_init_failed = False


_container = AppContainer()


def get_container() -> AppContainer:
    return _container


def reset_container() -> AppContainer:
    global _container
    _container = AppContainer()
    return _container
