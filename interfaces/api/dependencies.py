"""依赖注入配置

提供 FastAPI 依赖注入函数，用于创建服务和仓储实例。
"""
import logging
import os
from pathlib import Path
from functools import lru_cache
from typing import TYPE_CHECKING, Optional

from domain.ai.services.llm_service import LLMService

if TYPE_CHECKING:
    from application.engine.services.scene_director_service import SceneDirectorService

from application.paths import DATA_DIR
from infrastructure.persistence.storage.file_storage import FileStorage
from infrastructure.persistence.database.connection import get_database
from infrastructure.persistence.database.sqlite_novel_repository import SqliteNovelRepository
from infrastructure.persistence.database.sqlite_chapter_repository import SqliteChapterRepository
from infrastructure.persistence.database.sqlite_knowledge_repository import SqliteKnowledgeRepository
from infrastructure.persistence.database.sqlite_bible_repository import SqliteBibleRepository
from infrastructure.persistence.database.sqlite_storyline_repository import SqliteStorylineRepository
from infrastructure.persistence.database.sqlite_plot_arc_repository import SqlitePlotArcRepository
from infrastructure.persistence.database.sqlite_voice_vault_repository import SqliteVoiceVaultRepository
from infrastructure.persistence.database.sqlite_voice_fingerprint_repository import SQLiteVoiceFingerprintRepository
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
from infrastructure.persistence.database.sqlite_cast_repository import SqliteCastRepository
from infrastructure.persistence.database.sqlite_foreshadowing_repository import SqliteForeshadowingRepository
from infrastructure.persistence.database.sqlite_timeline_repository import SqliteTimelineRepository
from infrastructure.ai.config.settings import Settings
from infrastructure.ai.provider_factory import DynamicLLMService, LLMProviderFactory
from application.ai.llm_control_service import LLMControlService

from application.core.services.novel_service import NovelService
from application.core.services.chapter_service import ChapterService
from application.world.services.bible_service import BibleService
from application.world.services.cast_service import CastService
from application.world.services.knowledge_service import KnowledgeService
from application.analyst.services.voice_sample_service import VoiceSampleService
from application.analyst.services.voice_fingerprint_service import VoiceFingerprintService
from application.analyst.services.voice_drift_service import VoiceDriftService
from application.engine.services.context_builder import ContextBuilder
from application.world.services.auto_bible_generator import AutoBibleGenerator
from application.world.services.auto_knowledge_generator import AutoKnowledgeGenerator
from application.analyst.services.state_extractor import StateExtractor
from application.analyst.services.state_updater import StateUpdater
from application.workflows.auto_novel_generation_workflow import AutoNovelGenerationWorkflow
from application.engine.services.hosted_write_service import HostedWriteService
from domain.novel.services.consistency_checker import ConsistencyChecker
from domain.novel.services.storyline_manager import StorylineManager
from domain.bible.services.relationship_engine import RelationshipEngine
from domain.ai.services.vector_store import VectorStore

if TYPE_CHECKING:
    from application.analyst.services.narrative_entity_state_service import NarrativeEntityStateService


logger = logging.getLogger(__name__)

# 全局存储实例
_storage = None


def _anthropic_api_key() -> Optional[str]:
    """优先 ANTHROPIC_API_KEY，否则 ANTHROPIC_AUTH_TOKEN（与部分代理/IDE 配置命名一致）。"""
    raw = os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")
    if raw is None:
        return None
    key = raw.strip()
    return key or None


def _anthropic_base_url() -> Optional[str]:
    u = os.getenv("ANTHROPIC_BASE_URL")
    return u.strip() if u and u.strip() else None


def _anthropic_settings(require_key: bool = True) -> Optional[Settings]:
    """构建 Anthropic Settings；require_key=False 时无密钥返回 None。"""
    key = _anthropic_api_key()
    if not key:
        if require_key:
            raise ValueError(
                "Set ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN (optional: ANTHROPIC_BASE_URL)"
            )
        return None
    return Settings(
        api_key=key,
        base_url=_anthropic_base_url(),
        default_model=os.getenv("WRITING_MODEL", ""),
    )


def _openai_api_key() -> Optional[str]:
    raw = os.getenv("OPENAI_API_KEY")
    if raw is None:
        return None
    key = raw.strip()
    return key or None


def _openai_base_url() -> Optional[str]:
    u = os.getenv("OPENAI_BASE_URL")
    return u.strip() if u and u.strip() else None


def _openai_settings(require_key: bool = True) -> Optional[Settings]:
    """构建 OpenAI Settings；require_key=False 时无密钥返回 None。"""
    key = _openai_api_key()
    if not key:
        if require_key:
            raise ValueError(
                "Set OPENAI_API_KEY (optional: OPENAI_BASE_URL)"
            )
        return None
    return Settings(
        api_key=key,
        base_url=_openai_base_url(),
        default_model=os.getenv("WRITING_MODEL") or os.getenv("ARK_MODEL", ""),
    )


@lru_cache
def get_llm_control_service() -> LLMControlService:
    return LLMControlService()


@lru_cache
def get_llm_provider_factory() -> LLMProviderFactory:
    return LLMProviderFactory(get_llm_control_service())


def llm_runtime_is_mock(llm_service: Optional[LLMService] = None) -> bool:
    runtime = get_llm_control_service().get_runtime_summary()
    return runtime.using_mock


def get_storage() -> FileStorage:
    """获取存储后端实例

    Returns:
        FileStorage 实例
    """
    global _storage
    if _storage is None:
        _storage = FileStorage(DATA_DIR)
    return _storage


# Repository 依赖
def get_novel_repository() -> SqliteNovelRepository:
    """获取 Novel 仓储（SQLite）

    Returns:
        SqliteNovelRepository 实例
    """
    return SqliteNovelRepository(get_database())


def get_chapter_repository() -> SqliteChapterRepository:
    """获取 Chapter 仓储（SQLite）

    Returns:
        SqliteChapterRepository 实例
    """
    return SqliteChapterRepository(get_database())


def get_chapter_element_repository():
    """获取章节元素仓储

    Returns:
        ChapterElementRepository 实例
    """
    from infrastructure.persistence.database.chapter_element_repository import ChapterElementRepository
    from application.paths import get_db_path
    return ChapterElementRepository(get_db_path())


def get_bible_repository() -> SqliteBibleRepository:
    """获取 Bible 仓储（SQLite 唯一数据源）。"""
    return SqliteBibleRepository(get_database())


def get_cast_repository() -> SqliteCastRepository:
    """获取 Cast 仓储（SQLite JSON Blob）

    Returns:
        SqliteCastRepository 实例
    """
    return SqliteCastRepository(get_database())


def get_knowledge_repository() -> SqliteKnowledgeRepository:
    """获取 Knowledge 仓储（SQLite）

    Returns:
        SqliteKnowledgeRepository 实例
    """
    return SqliteKnowledgeRepository(get_database())


def get_storyline_repository() -> SqliteStorylineRepository:
    """获取 Storyline 仓储（SQLite）。"""
    return SqliteStorylineRepository(get_database())


def get_plot_arc_repository() -> SqlitePlotArcRepository:
    """获取 PlotArc 仓储（SQLite）。"""
    return SqlitePlotArcRepository(get_database())


def get_foreshadowing_repository() -> SqliteForeshadowingRepository:
    """伏笔与潜台词账本仓储（SQLite，与 novels 同库；不再使用 foreshadowings/*.json）。"""
    return SqliteForeshadowingRepository(get_database())


def get_snapshot_service():
    """语义快照服务（novel_snapshots；用于编年史 BFF 与回滚）。"""
    from application.snapshot.services.snapshot_service import SnapshotService

    return SnapshotService(
        get_database(),
        get_chapter_repository(),
        get_foreshadowing_repository(),
    )


def get_timeline_repository() -> SqliteTimelineRepository:
    """获取时间线仓储"""
    return SqliteTimelineRepository(get_database())


def get_beat_sheet_repository():
    """获取节拍表仓储"""
    from infrastructure.persistence.database.sqlite_beat_sheet_repository import SqliteBeatSheetRepository
    return SqliteBeatSheetRepository(get_database())


def get_story_node_repository() -> StoryNodeRepository:
    """获取 StoryNode 仓储

    Returns:
        StoryNodeRepository 实例（复用 DatabaseConnection 线程本地连接）
    """
    return StoryNodeRepository(get_database())


# Service 依赖
def get_novel_service() -> NovelService:
    """获取 Novel 服务

    Returns:
        NovelService 实例
    """
    return NovelService(
        get_novel_repository(),
        get_chapter_repository(),
        get_story_node_repository()
    )


def get_chapter_renumber_coordinator():
    """删章后章号侧车数据（伏笔 JSON、快照内嵌 JSON、向量元数据）重排编排。"""
    from application.novel.chapter_renumber.coordinator import (
        build_default_chapter_renumber_coordinator,
    )

    return build_default_chapter_renumber_coordinator(
        db=get_database(),
        foreshadowing_repository=get_foreshadowing_repository(),
        vector_store=get_vector_store(),
    )


def get_chapter_service() -> ChapterService:
    """获取 Chapter 服务

    Returns:
        ChapterService 实例
    """
    from infrastructure.persistence.database.sqlite_chapter_review_repository import SqliteChapterReviewRepository
    
    review_repo = SqliteChapterReviewRepository(get_database())
    return ChapterService(
        get_chapter_repository(), 
        get_novel_repository(),
        review_repo,
        chapter_renumber_coordinator=get_chapter_renumber_coordinator(),
    )


@lru_cache
def get_background_task_service():
    """单例后台任务队列（API 进程内）：文风；章末 bundle（叙事+三元组+伏笔+故事线+张力+对话+剧情点）与管线同源单次 LLM。"""
    from application.engine.services.background_task_service import BackgroundTaskService
    from infrastructure.persistence.database.triple_repository import TripleRepository
    from infrastructure.persistence.database.sqlite_storyline_repository import SqliteStorylineRepository
    from infrastructure.persistence.database.sqlite_narrative_event_repository import SqliteNarrativeEventRepository
    from infrastructure.persistence.database.connection import get_database

    db = get_database()
    return BackgroundTaskService(
        voice_drift_service=get_voice_drift_service(),
        llm_service=get_llm_service(),
        foreshadowing_repo=get_foreshadowing_repository(),
        triple_repository=TripleRepository(db),
        knowledge_service=get_knowledge_service(),
        chapter_indexing_service=get_chapter_indexing_service(),
        storyline_repository=SqliteStorylineRepository(db),
        chapter_repository=get_chapter_repository(),
        plot_arc_repository=get_plot_arc_repository(),
        narrative_event_repository=SqliteNarrativeEventRepository(db),
    )


@lru_cache
def get_chapter_aftermath_pipeline():
    """章节保存后统一管线（单例缓存，避免每次 PUT 请求重建 Pipeline + 8 个 Repository）。
    
    叙事/向量、文风、KG 推断；三元组与伏笔、故事线、张力、对话、剧情点、因果边、人物状态、债务在叙事同步中一次 LLM 落库。
    """
    from application.engine.services.chapter_aftermath_pipeline import ChapterAftermathPipeline
    from infrastructure.persistence.database.triple_repository import TripleRepository
    from infrastructure.persistence.database.sqlite_storyline_repository import SqliteStorylineRepository
    from infrastructure.persistence.database.sqlite_narrative_event_repository import SqliteNarrativeEventRepository
    from infrastructure.persistence.database.sqlite_causal_edge_repository import SqliteCausalEdgeRepository
    from infrastructure.persistence.database.sqlite_character_state_repository import SqliteCharacterStateRepository
    from infrastructure.persistence.database.sqlite_narrative_debt_repository import SqliteNarrativeDebtRepository
    from infrastructure.persistence.database.connection import get_database

    db = get_database()

    # ★ V8 Feed-forward: 因果边 / 人物状态 / 叙事债务 仓储
    causal_edge_repo = None
    character_state_repo = None
    debt_repo = None
    bible_repo = None

    try:
        causal_edge_repo = SqliteCausalEdgeRepository(db)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("CausalEdgeRepository 初始化失败: %s", e)

    try:
        character_state_repo = SqliteCharacterStateRepository(db)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("CharacterStateRepository 初始化失败: %s", e)

    try:
        debt_repo = SqliteNarrativeDebtRepository(db)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("NarrativeDebtRepository 初始化失败: %s", e)

    try:
        bible_repo = get_bible_repository()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("BibleRepository 初始化失败: %s", e)

    return ChapterAftermathPipeline(
        knowledge_service=get_knowledge_service(),
        chapter_indexing_service=get_chapter_indexing_service(),
        llm_service=get_llm_service(),
        voice_drift_service=get_voice_drift_service(),
        triple_repository=TripleRepository(db),
        foreshadowing_repository=get_foreshadowing_repository(),
        storyline_repository=SqliteStorylineRepository(db),
        chapter_repository=get_chapter_repository(),
        plot_arc_repository=get_plot_arc_repository(),
        narrative_event_repository=SqliteNarrativeEventRepository(db),
        causal_edge_repository=causal_edge_repo,
        character_state_repository=character_state_repo,
        debt_repository=debt_repo,
        bible_repository=bible_repo,
        unified_checkpoint_service=get_unified_checkpoint_service(),
    )


def get_hosted_write_service() -> HostedWriteService:
    """托管连写：自动大纲 + 多章流式生成 + 可选落库。"""
    return HostedWriteService(
        get_auto_workflow(),
        get_chapter_service(),
        get_novel_service(),
        chapter_aftermath_pipeline=get_chapter_aftermath_pipeline(),
    )


@lru_cache
def get_llm_service():
    """获取动态 LLM 服务实例。

    返回长生命周期包装器：每次 generate/stream_generate 时重新读取当前激活配置，
    因此前台控制面板修改后无需重启 API / 守护进程即可生效。
    """
    return DynamicLLMService(get_llm_provider_factory())


def get_setup_main_plot_suggestion_service():
    """向导 Step 4：主线候选推演服务。"""
    from application.blueprint.services.setup_main_plot_suggestion_service import (
        SetupMainPlotSuggestionService,
    )

    return SetupMainPlotSuggestionService(
        llm_service=get_llm_service(),
        bible_service=get_bible_service(),
        novel_service=get_novel_service(),
    )


def get_bible_service() -> BibleService:
    """获取 Bible 服务

    Returns:
        BibleService 实例
    """
    from application.paths import get_db_path
    from application.world.services.bible_location_triple_sync import BibleLocationTripleSyncService
    from infrastructure.persistence.database.triple_repository import TripleRepository

    sync = BibleLocationTripleSyncService(TripleRepository())
    return BibleService(
        get_bible_repository(),
        novel_repository=get_novel_repository(),
        chapter_repository=get_chapter_repository(),
        location_triple_sync=sync,
    )


def get_cast_service() -> CastService:
    """获取 Cast 服务

    Returns:
        CastService 实例
    """
    storage = get_storage()
    storage_root = storage.base_path
    return CastService(storage_root, knowledge_repository=get_knowledge_repository())


def get_knowledge_service() -> KnowledgeService:
    """获取 Knowledge 服务

    Returns:
        KnowledgeService 实例
    """
    return KnowledgeService(get_knowledge_repository())


def get_storyline_manager() -> StorylineManager:
    """获取 Storyline 管理器

    Returns:
        StorylineManager 实例
    """
    return StorylineManager(get_storyline_repository())


def get_consistency_checker() -> ConsistencyChecker:
    """获取一致性检查器

    Returns:
        ConsistencyChecker 实例
    """
    return ConsistencyChecker()


def get_embedding_service():
    """获取 Embedding 服务（优先从数据库读取配置，环境变量作为 fallback）。

    配置优先级：
    1. 数据库 embedding_config 表中的 mode / api_key / base_url / model / model_path / use_gpu
    2. 环境变量 EMBEDDING_SERVICE / EMBEDDING_MODEL_PATH 等
    3. 环境变量 EMBEDDING_MODEL / EMBEDDING_MODEL_PATH（无代码内写死的模型名）

    如果 VECTOR_STORE_ENABLED=false，返回 None。
    """
    if os.getenv("VECTOR_STORE_ENABLED", "true").lower() != "true":
        return None

    # 尝试从数据库读取配置
    _mode = "local"
    _api_key = ""
    _base_url = ""
    _model = ""
    _model_path = ""
    _use_gpu = True

    try:
        from application.ai.embedding_config_service import get_embedding_config_service
        cfg_svc = get_embedding_config_service()
        cfg = cfg_svc.get_config()
        _mode = cfg.mode
        _api_key = cfg.api_key
        _base_url = cfg.base_url
        _model = (cfg.model or "").strip()
        _model_path = (cfg.model_path or "").strip()
        _use_gpu = cfg.use_gpu
        logger.info(
            "Embedding 配置来源: 数据库 | mode=%s, model=%s, path=%s",
            _mode, _model, _model_path,
        )
    except Exception as exc:
        # 数据库不可用时回退到环境变量
        _mode = os.getenv("EMBEDDING_SERVICE", "local").lower()
        _api_key = os.getenv("EMBEDDING_API_KEY") or ""
        _base_url = os.getenv("EMBEDDING_BASE_URL") or ""
        _model = (os.getenv("EMBEDDING_MODEL") or "").strip()
        _model_path = (os.getenv("EMBEDDING_MODEL_PATH") or "").strip()
        _use_gpu = os.getenv("EMBEDDING_USE_GPU", "true").lower() == "true"
        logger.warning("读取嵌入配置失败，回退到环境变量: %s", exc)

    try:
        if _mode == "openai":
            key = _api_key or os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
            if not key:
                logger.warning("embedding mode=openai 但未配置 API Key，向量检索已禁用")
                return None
            if not (_model or "").strip():
                logger.warning("embedding mode=openai 但未配置模型 ID（model / EMBEDDING_MODEL），向量检索已禁用")
                return None
            from infrastructure.ai.openai_embedding_service import OpenAIEmbeddingService
            logger.info("使用 OpenAI 嵌入服务 (DB配置): base_url=%s, model=%s", _base_url, _model)
            return OpenAIEmbeddingService(
                api_key=key,
                base_url=_base_url or None,
                model=_model,
            )
        else:
            # 默认 local 模式
            if not (_model_path or "").strip():
                logger.warning("embedding mode=local 但未配置 model_path，向量检索已禁用")
                return None
            from infrastructure.ai.local_embedding_service import LocalEmbeddingService
            logger.info("使用本地嵌入服务 (DB配置): path=%s, gpu=%s", _model_path, _use_gpu)
            return LocalEmbeddingService(model_name=_model_path, use_gpu=_use_gpu)
    except Exception as e:
        logger.warning("EmbeddingService 初始化失败: %s", e)
        return None


def get_chapter_indexing_service():
    """获取章节索引服务（依赖 VectorStore + Embedding，任一不可用则返回 None）。"""
    vs = get_vector_store()
    es = get_embedding_service()
    if vs is None or es is None:
        return None
    from application.analyst.services.chapter_indexing_service import ChapterIndexingService
    return ChapterIndexingService(vs, es)


def get_triple_indexing_service():
    """获取三元组索引服务（依赖 VectorStore + Embedding，任一不可用则返回 None）。
    
    用于将三元组向量化并支持语义检索。
    """
    vs = get_vector_store()
    es = get_embedding_service()
    if vs is None or es is None:
        return None
    from application.analyst.services.triple_indexing_service import TripleIndexingService
    return TripleIndexingService(vs, es)


_vector_store_singleton: Optional[VectorStore] = None
_vector_store_init_failed: bool = False


def get_vector_store() -> Optional[VectorStore]:
    """获取向量存储（单例，整个进程共享同一实例）

    使用本地 FAISS 向量存储（ChromaDBVectorStore），无需外部服务。

    环境变量配置：
    - VECTOR_STORE_ENABLED: 是否启用（"true" 启用，默认 "true"）
    - VECTOR_STORE_PATH: 本地存储路径（默认 "./data/chromadb"）

    Returns:
        VectorStore 实例或 None
    """
    global _vector_store_singleton, _vector_store_init_failed

    # 如果已经初始化过（成功或失败），直接返回结果
    if _vector_store_singleton is not None:
        return _vector_store_singleton
    if _vector_store_init_failed:
        return None

    enabled = os.getenv("VECTOR_STORE_ENABLED", "true").lower() == "true"
    if not enabled:
        _vector_store_init_failed = True
        return None

    try:
        from infrastructure.ai.chromadb_vector_store import ChromaDBVectorStore
        persist_dir = os.getenv("VECTOR_STORE_PATH", "./data/chromadb")
        _vector_store_singleton = ChromaDBVectorStore(persist_directory=persist_dir)
        logger.info("向量存储初始化成功: %s", persist_dir)
        return _vector_store_singleton
    except Exception as e:
        _vector_store_init_failed = True
        logger.warning(
            "向量存储初始化失败，已降级禁用。"
            "如需使用向量功能，请安装依赖: pip install -r requirements-local.txt"
            " 或设置 VECTOR_STORE_TYPE=qdrant。错误: %s",
            e,
        )
        return None


def get_relationship_engine() -> RelationshipEngine:
    """获取关系引擎

    Returns:
        RelationshipEngine 实例
    """
    from domain.bible.value_objects.relationship_graph import RelationshipGraph
    return RelationshipEngine(RelationshipGraph())


def get_context_builder() -> ContextBuilder:
    """获取上下文构建器

    Returns:
        ContextBuilder 实例
    """
    from infrastructure.persistence.database.triple_repository import TripleRepository
    return ContextBuilder(
        bible_service=get_bible_service(),
        storyline_manager=get_storyline_manager(),
        relationship_engine=get_relationship_engine(),
        vector_store=get_vector_store(),
        novel_repository=get_novel_repository(),
        chapter_repository=get_chapter_repository(),
        plot_arc_repository=get_plot_arc_repository(),
        embedding_service=get_embedding_service(),
        foreshadowing_repository=get_foreshadowing_repository(),
        chapter_element_repository=get_chapter_element_repository(),
        triple_repository=TripleRepository(),
    )


def build_auto_workflow(llm_service: LLMService) -> AutoNovelGenerationWorkflow:
    """用指定 LLM 实例构造章节工作流（与守护进程、API 共用同一 provider 时注入同一实例）。"""
    from application.audit.services.conflict_detection_service import ConflictDetectionService
    from application.audit.services.cliche_scanner import ClicheScanner

    return AutoNovelGenerationWorkflow(
        context_builder=get_context_builder(),
        consistency_checker=get_consistency_checker(),
        storyline_manager=get_storyline_manager(),
        plot_arc_repository=get_plot_arc_repository(),
        llm_service=llm_service,
        state_extractor=get_state_extractor(),
        state_updater=get_state_updater(),
        bible_repository=get_bible_repository(),
        foreshadowing_repository=get_foreshadowing_repository(),
        voice_fingerprint_service=get_voice_fingerprint_service(),
        conflict_detection_service=ConflictDetectionService(),
        cliche_scanner=ClicheScanner(),
    )


def get_auto_workflow() -> AutoNovelGenerationWorkflow:
    """获取自动小说生成工作流

    Returns:
        AutoNovelGenerationWorkflow 实例
    """
    llm_service = get_llm_service()
    if llm_runtime_is_mock(llm_service):
        logger.warning("No API key found, using MockProvider for workflow")
    else:
        logger.info(f"Using {llm_service.__class__.__name__} for workflow")

    return build_auto_workflow(llm_service)


def get_auto_bible_generator() -> AutoBibleGenerator:
    """获取自动 Bible 生成器

    Returns:
        AutoBibleGenerator 实例
    """
    llm_service = get_llm_service()
    if llm_runtime_is_mock(llm_service):
        logger.warning("No API key found, using MockProvider for Bible generation")
    else:
        logger.info(f"Using {llm_service.__class__.__name__} for Bible generation")

    # 导入 WorldbuildingService 和 TripleRepository
    from application.world.services.worldbuilding_service import WorldbuildingService
    from infrastructure.persistence.database.worldbuilding_repository import WorldbuildingRepository
    from infrastructure.persistence.database.triple_repository import TripleRepository
    from application.paths import get_db_path

    db_path = get_db_path()
    worldbuilding_repo = WorldbuildingRepository(db_path)
    worldbuilding_service = WorldbuildingService(worldbuilding_repo)
    triple_repo = TripleRepository()

    return AutoBibleGenerator(
        llm_service=llm_service,
        bible_service=get_bible_service(),
        worldbuilding_service=worldbuilding_service,
        triple_repository=triple_repo
    )


def get_state_extractor() -> StateExtractor:
    """获取状态提取器

    Returns:
        StateExtractor 实例
    """
    return StateExtractor(llm_service=get_llm_service())


def get_auto_knowledge_generator() -> AutoKnowledgeGenerator:
    """获取自动 Knowledge 生成器

    Returns:
        AutoKnowledgeGenerator 实例
    """
    return AutoKnowledgeGenerator(
        llm_service=get_llm_service(),
        knowledge_service=get_knowledge_service()
    )


def get_state_updater() -> StateUpdater:
    """获取状态更新器

    Returns:
        StateUpdater 实例
    """
    return StateUpdater(
        bible_repository=get_bible_repository(),
        foreshadowing_repository=get_foreshadowing_repository(),
        timeline_repository=get_timeline_repository(),
        storyline_repository=get_storyline_repository(),
        knowledge_service=get_knowledge_service()
    )


def get_beat_sheet_service():
    """获取节拍表生成服务

    Returns:
        BeatSheetService 实例
    """
    from application.blueprint.services.beat_sheet_service import BeatSheetService

    llm_service = get_llm_service()
    if llm_runtime_is_mock(llm_service):
        logger.warning("No API key found, using MockProvider for beat sheet generation")
    else:
        logger.info(f"Using {llm_service.__class__.__name__} for beat sheet generation")

    return BeatSheetService(
        beat_sheet_repo=get_beat_sheet_repository(),
        chapter_repo=get_chapter_repository(),
        storyline_repo=get_storyline_repository(),
        llm_service=llm_service,
        vector_store=get_vector_store(),
        bible_service=get_bible_service()
    )


def get_scene_generation_service():
    """获取场景生成服务

    Returns:
        SceneGenerationService 实例
    """
    from application.core.services.scene_generation_service import SceneGenerationService

    llm_service = get_llm_service()
    if llm_runtime_is_mock(llm_service):
        logger.warning("No API key found, using MockProvider for scene generation")
    else:
        logger.info(f"Using {llm_service.__class__.__name__} for scene generation")

    return SceneGenerationService(
        llm_service=llm_service,
        scene_director=get_scene_director_service(),
        vector_store=get_vector_store(),
        embedding_service=get_embedding_service()
    )


def get_scene_director_service() -> "SceneDirectorService":
    """获取场景导演服务

    Returns:
        SceneDirectorService 实例
    """
    from application.engine.services.scene_director_service import SceneDirectorService

    llm_service = get_llm_service()
    if llm_runtime_is_mock(llm_service):
        logger.warning("No API key found, using MockProvider for scene director")
    else:
        logger.info(f"Using {llm_service.__class__.__name__} for scene director")
        
    return SceneDirectorService(llm_service=llm_service)


def get_narrative_entity_state_service() -> "NarrativeEntityStateService":
    """获取叙事实体状态服务

    Returns:
        NarrativeEntityStateService 实例
    """
    from application.analyst.services.narrative_entity_state_service import NarrativeEntityStateService
    from infrastructure.persistence.database.sqlite_entity_base_repository import SqliteEntityBaseRepository
    from infrastructure.persistence.database.sqlite_narrative_event_repository import SqliteNarrativeEventRepository

    entity_base_repo = SqliteEntityBaseRepository(get_database())
    narrative_event_repo = SqliteNarrativeEventRepository(get_database())

    return NarrativeEntityStateService(entity_base_repo, narrative_event_repo)


def get_voice_vault_repository() -> SqliteVoiceVaultRepository:
    """获取 Voice Vault 仓储（SQLite）

    Returns:
        SqliteVoiceVaultRepository 实例
    """
    return SqliteVoiceVaultRepository(get_database())


def get_voice_fingerprint_repository() -> SQLiteVoiceFingerprintRepository:
    """获取 Voice Fingerprint 仓储（SQLite）

    Returns:
        SQLiteVoiceFingerprintRepository 实例
    """
    return SQLiteVoiceFingerprintRepository(get_database())


def get_voice_sample_service() -> VoiceSampleService:
    """获取文风样本服务

    Returns:
        VoiceSampleService 实例
    """
    return VoiceSampleService(
        get_voice_vault_repository(),
        fingerprint_service=get_voice_fingerprint_service()
    )


def get_voice_fingerprint_service() -> VoiceFingerprintService:
    """获取文风指纹服务

    Returns:
        VoiceFingerprintService 实例
    """
    return VoiceFingerprintService(
        get_voice_fingerprint_repository(),
        get_voice_vault_repository()
    )


def get_voice_drift_service() -> VoiceDriftService:
    """获取文风漂移监控服务"""
    from infrastructure.persistence.database.sqlite_chapter_style_score_repository import (
        SqliteChapterStyleScoreRepository,
    )
    score_repo = SqliteChapterStyleScoreRepository(get_database())
    return VoiceDriftService(score_repo, get_voice_fingerprint_repository())


def get_macro_refactor_scanner():
    """获取宏观重构扫描器

    Returns:
        MacroRefactorScanner 实例
    """
    from application.audit.services.macro_refactor_scanner import MacroRefactorScanner
    from infrastructure.persistence.database.sqlite_narrative_event_repository import SqliteNarrativeEventRepository

    narrative_event_repo = SqliteNarrativeEventRepository(get_database())
    return MacroRefactorScanner(narrative_event_repo)


def get_macro_refactor_proposal_service():
    """获取宏观重构提案服务

    Returns:
        MacroRefactorProposalService 实例
    """
    from application.audit.services.macro_refactor_proposal_service import MacroRefactorProposalService

    llm_service = get_llm_service()
    if llm_runtime_is_mock(llm_service):
        logger.warning("No API key found, using MockProvider for macro refactor proposals")
    else:
        logger.info(f"Using {llm_service.__class__.__name__} for macro refactor proposals")

    return MacroRefactorProposalService(llm_service)


def get_mutation_applier():
    """获取 Mutation 应用器

    Returns:
        MutationApplier 实例
    """
    from application.audit.services.mutation_applier import MutationApplier
    from infrastructure.persistence.database.sqlite_narrative_event_repository import SqliteNarrativeEventRepository

    narrative_event_repo = SqliteNarrativeEventRepository(get_database())
    return MutationApplier(narrative_event_repo)


def get_macro_diagnosis_service():
    """获取宏观诊断服务

    Returns:
        MacroDiagnosisService 实例
    """
    from application.audit.services.macro_diagnosis_service import MacroDiagnosisService
    from application.audit.services.macro_refactor_scanner import MacroRefactorScanner
    from infrastructure.persistence.database.sqlite_narrative_event_repository import SqliteNarrativeEventRepository

    db = get_database()
    narrative_event_repo = SqliteNarrativeEventRepository(db)
    scanner = MacroRefactorScanner(narrative_event_repo)
    return MacroDiagnosisService(db, scanner)


def get_tension_analyzer():
    """获取张力分析器

    Returns:
        TensionAnalyzer 实例
    """
    from application.analyst.services.tension_analyzer import TensionAnalyzer
    from infrastructure.persistence.database.sqlite_narrative_event_repository import SqliteNarrativeEventRepository
    from infrastructure.ai.llm_client import LLMClient

    llm_provider = get_llm_service()
    if llm_runtime_is_mock(llm_provider):
        logger.warning("No API key found, using MockProvider for tension analyzer")
    else:
        logger.info(f"Using {llm_provider.__class__.__name__} for tension analyzer")

    llm_client = LLMClient(provider=llm_provider)
    narrative_event_repo = SqliteNarrativeEventRepository(get_database())
    return TensionAnalyzer(
        narrative_event_repo,
        llm_client,
        chapter_repository=get_chapter_repository(),
        plot_arc_repository=get_plot_arc_repository(),
    )


def get_sandbox_dialogue_service():
    """获取沙盘对白服务

    Returns:
        SandboxDialogueService 实例
    """
    from application.workbench.services.sandbox_dialogue_service import SandboxDialogueService
    from infrastructure.persistence.database.sqlite_narrative_event_repository import SqliteNarrativeEventRepository

    narrative_event_repo = SqliteNarrativeEventRepository(get_database())
    return SandboxDialogueService(narrative_event_repo)


def get_chapter_review_service():
    """获取章节审稿服务

    Returns:
        ChapterReviewService 实例
    """
    from application.audit.services.chapter_review_service import ChapterReviewService
    from infrastructure.persistence.database.sqlite_chapter_repository import SqliteChapterRepository
    from infrastructure.persistence.database.sqlite_cast_repository import SqliteCastRepository
    from infrastructure.persistence.database.sqlite_timeline_repository import SqliteTimelineRepository
    from infrastructure.persistence.database.sqlite_storyline_repository import SqliteStorylineRepository
    from infrastructure.persistence.database.sqlite_foreshadowing_repository import SqliteForeshadowingRepository

    db = get_database()
    chapter_repo = SqliteChapterRepository(db)
    cast_repo = SqliteCastRepository(db)
    timeline_repo = SqliteTimelineRepository(db)
    storyline_repo = SqliteStorylineRepository(db)
    foreshadowing_repo = SqliteForeshadowingRepository(db)
    vector_store = get_vector_store()
    llm_service = get_llm_service()

    return ChapterReviewService(
        chapter_repo=chapter_repo,
        cast_repo=cast_repo,
        timeline_repo=timeline_repo,
        storyline_repo=storyline_repo,
        foreshadowing_repo=foreshadowing_repo,
        vector_store=vector_store,
        llm_service=llm_service
    )


def get_foreshadow_ledger_service():
    """获取伏笔台账服务

    Returns:
        伏笔台账服务实例
    """
    from application.analyst.services.foreshadow_ledger_service import ForeshadowLedgerService
    return ForeshadowLedgerService(get_foreshadowing_repository())


def get_checkpoint_store():
    """获取 Checkpoint 持久化存储（SQLite）

    Returns:
        CheckpointStore 实例
    """
    from engine.infrastructure.persistence.checkpoint_store import CheckpointStore
    return CheckpointStore(get_database())


def get_checkpoint_manager():
    """获取 Checkpoint 管理器

    Returns:
        CheckpointManager 实例
    """
    from engine.runtime.checkpoint_manager.manager import CheckpointManager
    return CheckpointManager(get_checkpoint_store())


def get_quality_guardrail():
    """获取质量护栏总控

    Returns:
        QualityGuardrail 实例
    """
    from engine.runtime.quality_guardrails.quality_guardrail import QualityGuardrail
    return QualityGuardrail()


def get_narrative_engine_read_facade():
    """叙事引擎只读门面（小说家工作流聚合）。"""
    from application.narrative_engine.read_facade import NarrativeEngineReadFacade

    return NarrativeEngineReadFacade()


def get_unified_checkpoint_service():
    """统一 Checkpoint 服务（世界线管理）。"""
    from application.checkpoint.services.unified_checkpoint_service import UnifiedCheckpointService

    return UnifiedCheckpointService(
        db=get_database(),
        chapter_repository=get_chapter_repository(),
        foreshadowing_repo=get_foreshadowing_repository(),
    )

