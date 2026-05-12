"""启动自动驾驶守护进程（v2，全依赖注入 + 护城河）

日志：默认与 API 共用 ``logs/aitext.log``（环境变量 LOG_FILE），便于在「主日志」里查看
规划/写作/节拍；另可设 LOG_FILE 仅写文件。
"""
import os
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_DATASETS_OFFLINE'] = '1'
if os.getenv('DISABLE_SSL_VERIFY', 'false').lower() == 'true':
    os.environ['CURL_CA_BUNDLE'] = ''
    os.environ['REQUESTS_CA_BUNDLE'] = ''

import sys
import logging
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent))

from application.paths import AITEXT_ROOT, get_db_path, DATA_DIR
from infrastructure.persistence.database.connection import get_database
from infrastructure.persistence.database.sqlite_novel_repository import SqliteNovelRepository
from infrastructure.persistence.database.sqlite_chapter_repository import SqliteChapterRepository
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
from infrastructure.persistence.database.chapter_element_repository import ChapterElementRepository
from infrastructure.persistence.database.sqlite_foreshadowing_repository import SqliteForeshadowingRepository
from infrastructure.persistence.database.sqlite_storyline_repository import SqliteStorylineRepository
from infrastructure.persistence.database.sqlite_plot_arc_repository import SqlitePlotArcRepository
from infrastructure.persistence.database.sqlite_narrative_event_repository import SqliteNarrativeEventRepository

from application.engine.services.autopilot_daemon import AutopilotDaemon
from application.engine.services.background_task_service import BackgroundTaskService
from application.engine.services.chapter_aftermath_pipeline import ChapterAftermathPipeline
from application.engine.services.circuit_breaker import CircuitBreaker
from application.blueprint.services.continuous_planning_service import ContinuousPlanningService

# 复用 API 层的工厂函数，保证与 FastAPI 层使用同一套配置
from interfaces.api.dependencies import (
    get_llm_service,
    build_auto_workflow,
    get_context_builder,
    get_bible_service,
    get_foreshadowing_repository,
    get_novel_repository,
    get_chapter_repository,
    get_voice_drift_service,
    get_knowledge_service,
    get_chapter_indexing_service,
)
from interfaces.api.middleware.logging_config import setup_logging

(DATA_DIR / "logs").mkdir(parents=True, exist_ok=True)
_log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
_default_log = str(AITEXT_ROOT / "logs" / "aitext.log")
_log_file = os.getenv("LOG_FILE", _default_log)
setup_logging(level=_log_level, log_file=_log_file)

logger = logging.getLogger(__name__)


def build_daemon() -> AutopilotDaemon:
    db_path = get_db_path()
    db = get_database(db_path)

    novel_repo = SqliteNovelRepository(db)
    chapter_repo = SqliteChapterRepository(db)
    story_node_repo = StoryNodeRepository(db_path)
    chapter_element_repo = ChapterElementRepository(db_path)
    foreshadow_repo = SqliteForeshadowingRepository(db)

    llm_service = get_llm_service()
    chapter_workflow = build_auto_workflow(llm_service)
    context_builder = get_context_builder()

    planning_service = ContinuousPlanningService(
        story_node_repo=story_node_repo,
        chapter_element_repo=chapter_element_repo,
        llm_service=llm_service,
        bible_service=get_bible_service(),
        chapter_repository=chapter_repo,
    )

    # VoiceDriftService：与 FastAPI get_voice_drift_service() 同源（chapter_style_scores.upsert，勿用 VoiceVault）
    voice_drift_service = None
    try:
        voice_drift_service = get_voice_drift_service()
        logger.info("VoiceDriftService 已启用（与 API 同源注入）")
    except Exception as e:
        logger.warning(f"VoiceDriftService 初始化失败，文风检测已禁用：{e}")

    # TripleRepository（可选）
    triple_repo = None
    try:
        from infrastructure.persistence.database.triple_repository import TripleRepository
        triple_repo = TripleRepository(db)
        logger.info("TripleRepository 已启用")
    except Exception as e:
        logger.warning(f"TripleRepository 不可用，图谱提取已禁用：{e}")

    bg_service = BackgroundTaskService(
        voice_drift_service=voice_drift_service,
        llm_service=llm_service,
        foreshadowing_repo=foreshadow_repo,
        triple_repository=triple_repo,
        knowledge_service=get_knowledge_service(),
        chapter_indexing_service=get_chapter_indexing_service(),
        storyline_repository=SqliteStorylineRepository(get_database()),
        chapter_repository=get_chapter_repository(),
        plot_arc_repository=SqlitePlotArcRepository(get_database()),
        narrative_event_repository=SqliteNarrativeEventRepository(get_database()),
    )

    aftermath_pipeline = None
    try:
        # ★ V8 Feed-forward: 因果边 / 人物状态 / 叙事债务 仓储
        causal_edge_repo = None
        character_state_repo = None
        debt_repo = None
        bible_repo = None

        try:
            from infrastructure.persistence.database.sqlite_causal_edge_repository import SqliteCausalEdgeRepository
            causal_edge_repo = SqliteCausalEdgeRepository(get_database())
        except Exception as e:
            logger.warning(f"CausalEdgeRepository 初始化失败: {e}")

        try:
            from infrastructure.persistence.database.sqlite_character_state_repository import SqliteCharacterStateRepository
            character_state_repo = SqliteCharacterStateRepository(get_database())
        except Exception as e:
            logger.warning(f"CharacterStateRepository 初始化失败: {e}")

        try:
            from infrastructure.persistence.database.sqlite_narrative_debt_repository import SqliteNarrativeDebtRepository
            debt_repo = SqliteNarrativeDebtRepository(get_database())
        except Exception as e:
            logger.warning(f"NarrativeDebtRepository 初始化失败: {e}")

        try:
            from interfaces.api.dependencies import get_bible_repository
            bible_repo = get_bible_repository()
        except Exception as e:
            logger.warning(f"BibleRepository 初始化失败: {e}")

        unified_checkpoint_svc = None
        try:
            from interfaces.api.dependencies import get_unified_checkpoint_service
            unified_checkpoint_svc = get_unified_checkpoint_service()
        except Exception as e:
            logger.warning(f"UnifiedCheckpointService 初始化失败: {e}")

        aftermath_pipeline = ChapterAftermathPipeline(
            knowledge_service=get_knowledge_service(),
            chapter_indexing_service=get_chapter_indexing_service(),
            llm_service=llm_service,
            voice_drift_service=voice_drift_service,
            triple_repository=triple_repo,
            foreshadowing_repository=foreshadow_repo,
            storyline_repository=SqliteStorylineRepository(get_database()),
            chapter_repository=get_chapter_repository(),
            plot_arc_repository=SqlitePlotArcRepository(get_database()),
            narrative_event_repository=SqliteNarrativeEventRepository(get_database()),
            causal_edge_repository=causal_edge_repo,
            character_state_repository=character_state_repo,
            debt_repository=debt_repo,
            bible_repository=bible_repo,
            unified_checkpoint_service=unified_checkpoint_svc,
        )
        logger.info("ChapterAftermathPipeline 已注入（叙事/向量/文风/KG；三元组/伏笔/故事线/张力/对话/因果边/人物状态/债务 单次 LLM）")
    except Exception as e:
        logger.warning("ChapterAftermathPipeline 初始化失败，审计将降级：%s", e)

    # 熔断器配置：适应 API 限流
    # - failure_threshold: 允许连续失败的次数（增大以容忍临时限流）
    # - reset_timeout: 熔断后等待恢复的时间（秒）
    circuit_breaker = CircuitBreaker(
        failure_threshold=10,  # 从 5 增加到 10，更宽容临时限流
        reset_timeout=180,     # 从 120 增加到 180 秒，给 API 更多恢复时间
    )

    return AutopilotDaemon(
        novel_repository=novel_repo,
        llm_service=llm_service,
        context_builder=context_builder,
        background_task_service=bg_service,
        planning_service=planning_service,
        story_node_repo=story_node_repo,
        chapter_repository=chapter_repo,
        poll_interval=10,  # 从 5 秒增加到 10 秒，降低轮询频率以减少 API 压力
        voice_drift_service=voice_drift_service,
        circuit_breaker=circuit_breaker,
        chapter_workflow=chapter_workflow,
        aftermath_pipeline=aftermath_pipeline,
        knowledge_service=get_knowledge_service(),
    )


if __name__ == "__main__":
    logger.info("=" * 80)
    logger.info("🚀 Autopilot Daemon v2 Starting（日志写入 %s）", _log_file)
    logger.info("=" * 80)

    daemon = build_daemon()
    try:
        daemon.run_forever()
    except KeyboardInterrupt:
        logger.info("守护进程已停止（KeyboardInterrupt）")
    except Exception as e:
        logger.error(f"守护进程异常退出：{e}", exc_info=True)
        raise
