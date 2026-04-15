"""启动自动驾驶守护进程

使用方法：
    python scripts/start_daemon.py

功能：
1. 初始化所有依赖服务
2. 启动守护进程死循环
3. 轮询数据库，处理所有 autopilot_status=RUNNING 的小说
"""
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 添加项目根目录到路径（start_daemon 位于 scripts/setup/）
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from infrastructure.ai.llm_client import LLMClient
from application.engine.services.autopilot_daemon import AutopilotDaemon
from application.engine.services.context_builder import ContextBuilder
from application.engine.services.background_task_service import BackgroundTaskService
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_novel_repository import SqliteNovelRepository
from infrastructure.persistence.database.sqlite_chapter_repository import SqliteChapterRepository
from interfaces.api.middleware.logging_config import SafeUnicodeStreamHandler

# 配置日志（文件 UTF-8；控制台在 Windows GBK 下安全写入）
_DAEMON_LOG = _PROJECT_ROOT / "data" / "logs" / "autopilot_daemon.log"
_DAEMON_LOG.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(_DAEMON_LOG, encoding="utf-8"),
        SafeUnicodeStreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info("启动自动驾驶守护进程")
    logger.info("=" * 80)

    # 初始化数据库连接
    db_path = _PROJECT_ROOT / "data" / "novels.db"
    db = DatabaseConnection(str(db_path))
    novel_repository = SqliteNovelRepository(db)
    chapter_repository = SqliteChapterRepository(db)

    # 初始化 LLM 客户端
    llm_client = LLMClient()

    # 初始化上下文构建器（简化版，后续接入完整依赖）
    context_builder = ContextBuilder(
        bible_service=None,
        storyline_manager=None,
        relationship_engine=None,
        vector_store=None,
        novel_repository=novel_repository,
        chapter_repository=chapter_repository,
    )

    # 初始化后台任务服务
    background_task_service = BackgroundTaskService()

    # 初始化守护进程
    daemon = AutopilotDaemon(
        novel_repository=novel_repository,
        llm_service=llm_client,
        context_builder=context_builder,
        background_task_service=background_task_service,
        poll_interval=5,  # 5 秒轮询一次
    )

    # 启动守护进程
    try:
        daemon.run_forever()
    except KeyboardInterrupt:
        logger.info("收到中断信号，停止守护进程")
    except Exception as e:
        logger.error(f"守护进程异常退出: {e}", exc_info=True)


if __name__ == "__main__":
    main()
