"""FastAPI 主应用

提供 RESTful API 接口。
"""
# 必须在任何 HuggingFace/Transformers 导入前设置离线模式
import os
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_DATASETS_OFFLINE'] = '1'
if os.getenv('DISABLE_SSL_VERIFY', 'false').lower() == 'true':
    os.environ['CURL_CA_BUNDLE'] = ''
    os.environ['REQUESTS_CA_BUNDLE'] = ''

from pathlib import Path
import sys
import time
import logging
from datetime import datetime
from typing import Any, Dict, Optional

# 必须在其他 aitext 模块导入前执行：将仓库根目录 `.env` 写入 os.environ
_AITEXT_ROOT = Path(__file__).resolve().parents[1]
if str(_AITEXT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AITEXT_ROOT))
try:
    from load_env import load_env

    load_env()
except Exception:
    # 无 .env 或非标准启动方式时忽略
    pass

# 配置日志（必须在导入其他模块前）
from interfaces.api.middleware.logging_config import setup_logging

log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
log_file = os.getenv("LOG_FILE", "logs/aitext.log")
setup_logging(level=log_level, log_file=log_file)

logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, JSONResponse
from starlette.requests import Request
import threading
import multiprocessing
import signal

# Core module
from interfaces.api.v1.core import novels, chapters, scene_generation_routes, settings as llm_settings, export

# World module
from interfaces.api.v1.world import bible, cast, knowledge, knowledge_graph_routes, worldbuilding_routes

# Blueprint module
from interfaces.api.v1.blueprint import continuous_planning_routes, beat_sheet_routes, story_structure

# Engine module routes
from interfaces.api.v1.engine import (
    generation,
    context_intelligence,
    autopilot_routes,
    chronicles,
    snapshot_routes,
    workbench_context_routes,
    character_scheduler_routes,  # 角色调度API（正式功能）
    checkpoint_routes,  # Checkpoint + QualityGuardrail + StoryPhase
)

# Audit module
from interfaces.api.v1.audit import chapter_review_routes, macro_refactor, chapter_element_routes

# Analyst module
from interfaces.api.v1.analyst import voice, narrative_state, foreshadow_ledger

# System module (internal tooling)
from interfaces.api.v1 import system as system_routes

# Reader Simulation module
from interfaces.api.v1 import reader as reader_module

# Workbench module
from interfaces.api.v1.workbench import sandbox, writer_block, monitor, llm_control
from interfaces.api.stats.routers.stats import create_stats_router
from interfaces.api.stats.services.stats_service import StatsService
from interfaces.api.stats.repositories.sqlite_stats_repository_adapter import SqliteStatsRepositoryAdapter
from infrastructure.persistence.database.connection import get_database

# 产品发布版本（与前端 / 安装包一致）
APP_RELEASE_VERSION = "1.0.2"
# 构建标识（与安装包/发布说明一致，便于对账）
BACKEND_BUILD_ID = "build-20260209-1200-c4d2"
STARTUP_TIME = time.time()

logger.info("=" * 80)
logger.info(
    "🚀 BACKEND STARTING - Release %s (build %s)",
    APP_RELEASE_VERSION,
    BACKEND_BUILD_ID,
)
logger.info(f"   Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
logger.info(f"   Log Level: {logging.getLevelName(log_level)}")
logger.info(f"   Log File: {log_file}")
logger.info(f"   Python: {sys.version.split()[0]}")
logger.info(f"   Working Dir: {Path.cwd()}")
logger.info("=" * 80)

# 创建 FastAPI 应用
app = FastAPI(
    title="PlotPilot API",
    version="1.0.2",
    description="PlotPilot（墨枢）AI 小说创作平台 API",
    redirect_slashes=True,  # 自动将 /api/v1/novels 重定向到 /api/v1/novels/
)

# ── 前端静态文件托管 ──
_FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend" / "dist"
if _FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIR / "assets")), name="frontend-assets")
    # favicon 等根级静态资源
    _favicon = _FRONTEND_DIR / "favicon.svg"
    if _favicon.exists():
        app.get("/favicon.svg", include_in_schema=False, response_class=FileResponse)(
            lambda: FileResponse(str(_favicon), media_type="image/svg+xml")
        )
    # SPA fallback: 所有非 API 路径都返回 index.html
    _INDEX_HTML = _FRONTEND_DIR / "index.html"

# 修复反向代理场景下 trailing slash 重定向使用后端本地地址的 bug
# 当 FastAPI 的 trailing slash 重定向指向 127.0.0.1 时，
# 从 X-Forwarded-Host / Host / Referer 获取真实地址并改写 Location header
@app.middleware("http")
async def fix_redirect_host(request, call_next):
    response = await call_next(request)
    if response.status_code in (301, 307, 308):
        location = response.headers.get("location", "")
        if location and ("127.0.0.1" in location or "localhost" in location):
            from urllib.parse import urlparse, urlunparse
            parsed = urlparse(location)
            original_host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
            if not original_host or "127.0.0.1" in original_host or "localhost" in original_host:
                referer = request.headers.get("referer", "")
                if referer:
                    from urllib.parse import urlparse as _urlparse
                    ref_host = _urlparse(referer).netloc
                    if ref_host and "127.0.0.1" not in ref_host and "localhost" not in ref_host:
                        original_host = ref_host
            if original_host and "127.0.0.1" not in original_host and "localhost" not in original_host:
                scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
                new_location = urlunparse((scheme, original_host, parsed.path, parsed.params, parsed.query, parsed.fragment))
                response.headers["location"] = new_location
    return response


@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("📦 Loading modules and routes...")
    logger.info("✅ FastAPI application started successfully")
    logger.info(f"📊 Registered {len(app.routes)} routes")

    # Windows: 启动前清理上次可能残留的进程
    if os.name == "nt":
        logger.info("🧹 Windows 启动前检查残留进程...")
        _cleanup_orphan_python_processes()

    # 重启时将所有运行中的小说设置为停止状态
    _stop_all_running_novels()

    # AOF 崩溃恢复：扫描残留的 .draft 文件，恢复到 DB
    _recover_drafts_on_startup()

    # 启动自动驾驶守护进程（后台线程）
    _start_autopilot_daemon_thread()

    # 初始化 DAG 节点注册表（加载所有 V1 节点实现）
    _init_dag_node_registry()

def _checkpoint_sqlite_wal_safe() -> None:
    """桌面端优雅退出时尽量将 WAL 落盘，降低异常断电时的损坏概率。"""
    try:
        import sqlite3

        from application.paths import get_db_path

        dbp = get_db_path()
        conn = sqlite3.connect(dbp, timeout=2.0)  # 减少超时
        try:
            conn.execute("PRAGMA journal_mode=WAL")       # 确保与主连接一致
            conn.execute("PRAGMA busy_timeout=2000")      # 最多等 2 秒拿锁
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            conn.close()
    except Exception as e:
        logger.warning("WAL checkpoint 失败（可忽略）: %s", e)


def _run_backend_shutdown_hooks() -> None:
    """与 shutdown 生命周期钩子共用：守护进程停止 + DB 连接关闭 + WAL + 日志。"""
    _start_force_exit_watchdog()  # 启动看门狗，防止关闭流程卡死
    _stop_autopilot_daemon_thread()
    # 关闭所有数据库连接（跳过 WAL checkpoint，避免锁等待卡死）
    try:
        from infrastructure.persistence.database.connection import get_database
        db = get_database()
        db.close_all(skip_checkpoint=True)
    except Exception as e:
        logger.warning("关闭数据库连接失败: %s", e)
    _checkpoint_sqlite_wal_safe()

    # 关闭 LLM Provider HTTP 连接池
    try:
        import asyncio
        from interfaces.api.dependencies import get_llm_service
        svc = get_llm_service()
        if hasattr(svc, 'aclose'):
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(svc.aclose())
                else:
                    loop.run_until_complete(svc.aclose())
            except RuntimeError:
                pass
    except Exception:
        pass

    uptime = time.time() - STARTUP_TIME
    logger.info("=" * 80)
    logger.info("\U0001f6d1 BACKEND SHUTTING DOWN")
    logger.info("   Total uptime: %.2f seconds (%.2f hours)", uptime, uptime / 3600)
    logger.info("=" * 80)


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件（uvicorn 优雅退出时触发；Windows 桌面专用路径见 /internal/shutdown）。"""
    _run_backend_shutdown_hooks()


def _assert_internal_shutdown_localhost(request: Request) -> None:
    if not request.client:
        raise HTTPException(status_code=403, detail="forbidden")
    host = request.client.host or ""
    if host not in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
        raise HTTPException(status_code=403, detail="forbidden")


def _internal_shutdown_after_response() -> None:
    """HTTP 响应已发出后再触发进程级退出，避免截断响应体。"""
    time.sleep(0.15)  # 让 HTTP 响应先发出去
    if os.name == "nt":
        # Windows: 必须在 os._exit 之前确保守护子进程被终止
        # os._exit(0) 不会触发 Python 的正常清理流程，
        # multiprocessing.Process 的 daemon 子进程可能变成孤儿
        _stop_autopilot_daemon_thread()
        # 关闭数据库连接（跳过 checkpoint，避免锁等待卡死）
        try:
            from infrastructure.persistence.database.connection import get_database
            db = get_database()
            db.close_all(skip_checkpoint=True)
        except Exception as e:
            logger.warning("关闭数据库连接失败: %s", e)
        _checkpoint_sqlite_wal_safe()

        uptime = time.time() - STARTUP_TIME
        logger.info("=" * 80)
        logger.info("\U0001f6d1 BACKEND SHUTTING DOWN (Windows forced exit)")
        logger.info("   Total uptime: %.2f seconds (%.2f hours)", uptime, uptime / 3600)
        logger.info("=" * 80)
        logging.shutdown()
        os._exit(0)
    os.kill(os.getpid(), signal.SIGINT)


@app.post("/internal/shutdown", include_in_schema=False)
async def internal_shutdown(request: Request):
    """仅本机：供 Tauri 在关闭窗口前触发优雅停机（Unix 走 SIGINT→uvicorn；Windows 走钩子+_exit）。"""
    _assert_internal_shutdown_localhost(request)
    threading.Thread(target=_internal_shutdown_after_response, daemon=True).start()
    return {"ok": True, "message": "shutting down"}

# 守护进程进程管理（使用独立进程避免阻塞主事件循环）
_daemon_process = None
_daemon_stop_event = None

# ── 跨进程共享状态字典（核心架构：状态走内存，数据走磁盘）──
# 在启动守护进程前初始化，供 API 进程零 DB IO 读取实时状态
_mp_manager: multiprocessing.Manager | None = None
_shared_state: dict | None = None


def _get_shared_state() -> dict:
    """获取跨进程共享状态字典（惰性初始化）。

    架构原则：
    - 守护进程写入：stage、audit_progress、last_chapter_tension 等高频状态字段
    - API 进程读取：/status 和 SSE 直接读内存，零 DB IO，纳秒级响应
    - DB 只负责：核心业务数据固化（低频、可延迟）
    """
    global _mp_manager, _shared_state
    if _shared_state is not None:
        return _shared_state
    _mp_manager = multiprocessing.Manager()
    _shared_state = _mp_manager.dict()
    logger.info("✅ 跨进程共享状态字典已初始化 (multiprocessing.Manager)")
    return _shared_state


def update_shared_novel_state(novel_id: str, **fields) -> None:
    """守护进程调用：更新指定小说的实时状态到共享内存。

    Args:
        novel_id: 小说 ID
        **fields: 状态字段，如 stage="auditing", audit_progress="voice_check"
    """
    state = _get_shared_state()
    key = f"novel:{novel_id}"
    # Manager.dict 中的值需要是可序列化的，用普通 dict
    current = dict(state.get(key, {}))
    # 🔥 确保 novel_id 始终在数据中
    fields["novel_id"] = novel_id
    current.update(fields)
    current["_updated_at"] = time.time()
    state[key] = current


def get_shared_novel_state(novel_id: str) -> Dict[str, Any]:
    """API 进程调用：从共享内存读取小说实时状态（零 DB IO）。

    Returns:
        状态字典，如果不存在返回空 dict
    """
    state = _get_shared_state()
    key = f"novel:{novel_id}"
    return dict(state.get(key, {}))


def _is_expected_daemon_shutdown_exception(exc: BaseException) -> bool:
    """热重载/停止时的中断视为正常退出，避免子进程打印长栈。"""
    import asyncio

    current = exc
    visited = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, (KeyboardInterrupt, asyncio.CancelledError)):
            return True
        current = current.__cause__ or current.__context__
    return False


def _stop_all_running_novels():
    """重启时将所有运行中的小说设置为停止状态

    修复：
    - 使用与 DatabaseConnection 一致的 PRAGMA 配置（WAL + busy_timeout + synchronous=NORMAL），
      避免裸连接因 journal_mode 不匹配导致 disk I/O error。
    - 增加 WAL 残留文件清理：若上次异常退出遗留 -wal/-shm 文件且 DB 无活跃连接，
      SQLite 会自动恢复；但若残留文件损坏则主动清理后重试。
    - 增加重试机制：应对启动阶段磁盘 I/O 短暂不可用（如 PyInstaller DLL 尚未完全释放）。
    """
    import sqlite3
    import time
    from pathlib import Path
    from application.paths import get_db_path

    db_path = get_db_path()
    db_path_obj = Path(db_path) if isinstance(db_path, str) else db_path

    if not db_path_obj.exists():
        logger.warning(f"⚠️  数据库文件不存在: {db_path}")
        return

    # 与 DatabaseConnection.get_connection() 保持一致的 PRAGMA 配置
    def _open_with_pragma(path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")
        return conn

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            conn = _open_with_pragma(str(db_path_obj))
            try:
                cur = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='novels' LIMIT 1"
                )
                if cur.fetchone() is None:
                    logger.info("ℹ️  新库尚无 novels 表，跳过运行中小说复位")
                    return

                cursor = conn.execute(
                    "SELECT COUNT(*) FROM novels WHERE autopilot_status = 'running'"
                )
                running_count = cursor.fetchone()[0]

                if running_count > 0:
                    conn.execute(
                        "UPDATE novels SET autopilot_status = 'stopped', updated_at = CURRENT_TIMESTAMP WHERE autopilot_status = 'running'"
                    )
                    conn.commit()
                    logger.info(f"🔒 已将 {running_count} 本运行中的小说设置为停止状态（服务重启）")
                else:
                    logger.info("✅ 没有运行中的小说需要停止")
                return  # 成功，退出重试循环

            finally:
                try:
                    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except Exception:
                    pass
                conn.close()

        except sqlite3.OperationalError as e:
            if "disk I/O error" in str(e) and attempt < max_retries:
                logger.warning(
                    f"⚠️  停止运行中小说遇到 disk I/O error（第 {attempt}/{max_retries} 次），"
                    f"尝试清理 WAL 残留后重试..."
                )
                # 清理可能损坏的 WAL 残留文件
                for suffix in ("-wal", "-shm"):
                    wal_file = db_path_obj.parent / (db_path_obj.name + suffix)
                    if wal_file.exists():
                        try:
                            wal_file.unlink()
                            logger.info(f"🧹 已清理残留 WAL 文件: {wal_file}")
                        except OSError as unlink_err:
                            logger.warning(f"清理 WAL 文件失败: {wal_file} — {unlink_err}")
                time.sleep(1.0 * attempt)  # 递增等待
            else:
                logger.error(
                    "❌ 停止运行中小说失败: db=%s err=%s",
                    db_path_obj,
                    e,
                    exc_info=True,
                )
                return
        except Exception as e:
            logger.error(
                "❌ 停止运行中小说失败: db=%s err=%s",
                db_path_obj,
                e,
                exc_info=True,
            )
            return


def _recover_drafts_on_startup():
    """AOF 崩溃恢复：扫描残留的 .draft 文件，恢复到 DB"""
    try:
        from application.engine.services.draft_aof import recover_all_drafts
        recovered = recover_all_drafts()
        if recovered > 0:
            logger.info(f"🔧 AOF 崩溃恢复：已恢复 {recovered} 个章节的草稿数据")
        else:
            logger.info("✅ AOF 检查：无残留草稿需要恢复")
    except Exception as e:
        logger.warning(f"⚠️ AOF 崩溃恢复失败（可忽略）: {e}")


def _run_daemon_in_process(
    stop_event: threading.Event,
    log_level: int,
    log_file: str,
    stream_queue=None,
    shared_state=None,
    persistence_queue=None,
):
    """在独立进程中运行守护进程（完全隔离，不阻塞主进程）

    Args:
        stop_event: 停止信号
        log_level: 日志级别
        log_file: 日志文件路径
        stream_queue: StreamingBus 的队列对象（从主进程传入）
        shared_state: multiprocessing.Manager().dict() 共享状态字典
        persistence_queue: 持久化队列（CQRS 单一写入者模式）
    """
    # 重新配置日志（子进程需要独立配置）
    from interfaces.api.middleware.logging_config import setup_logging
    setup_logging(level=log_level, log_file=log_file)

    # 注入流式队列（必须在导入任何使用 streaming_bus 的模块前设置）
    if stream_queue is not None:
        from application.engine.services.streaming_bus import inject_stream_queue
        inject_stream_queue(stream_queue)
        logger.info("✅ 守护进程：流式队列已注入")

    # 注入共享状态字典（供守护进程写入实时状态）
    if shared_state is not None:
        try:
            # 将共享状态注入到全局，供 daemon 使用
            import sys
            sys.modules["__shared_state"] = shared_state

            # 🔥 初始化共享状态仓库（守护进程端）
            from application.engine.services.shared_state_repository import (
                inject_shared_dict,
                get_shared_state_repository,
            )
            inject_shared_dict(shared_state)
            logger.info("✅ 守护进程：共享状态字典已注入")

            # 🔥 初始化状态发布器（守护进程的唯一写入入口）
            from application.engine.services.state_publisher import get_state_publisher
            get_state_publisher()  # 会自动获取共享状态仓库和持久化队列
            logger.info("✅ 守护进程：状态发布器已初始化")

        except Exception as e:
            logger.warning("共享状态注入失败（可忽略）: %s", e)

    # 🔥 注入持久化队列（守护进程通过此队列发送 DB 写命令）
    if persistence_queue is not None:
        try:
            from application.engine.services.persistence_queue import inject_persistence_queue
            inject_persistence_queue(persistence_queue)
            logger.info("✅ 守护进程：持久化队列已注入")
        except Exception as e:
            logger.warning("持久化队列注入失败（可忽略）: %s", e)

    # 初始化小说停止信号模块（Queue 驱动，无需额外注入）
    try:
        from application.engine.services.novel_stop_signal import inject_novel_stop_events
        inject_novel_stop_events()
    except Exception as e:
        logger.debug("小说停止信号模块初始化失败（可忽略）: %s", e)

    try:
        from scripts.start_daemon import build_daemon
        daemon = build_daemon()
        logger.info("🚀 守护进程已启动（独立进程），开始轮询...")

        # 创建持久化事件循环（避免每个小说都 asyncio.run() 创建/销毁循环）
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        logger.info("✅ 守护进程：持久化事件循环已创建")

        while not stop_event.is_set():
            try:
                # 消费 mp.Queue 中的停止信号消息（设置本地 threading.Event）
                try:
                    from application.engine.services.streaming_bus import streaming_bus
                    streaming_bus.consume_stop_signals()
                except Exception:
                    pass

                # 执行守护进程的一个轮询周期
                active_novels = daemon._get_active_novels()

                if active_novels:
                    for novel in active_novels:
                        if stop_event.is_set():
                            break
                        # 使用持久化事件循环处理每个小说
                        loop.run_until_complete(daemon._process_novel(novel))

                # 轮询间隔（使用 wait 而非 sleep，以便快速响应停止信号）
                stop_event.wait(timeout=daemon.poll_interval)

            except BaseException as e:
                if stop_event.is_set() or _is_expected_daemon_shutdown_exception(e):
                    logger.info("ℹ️ 守护进程在停止/热重载期间中断，正常退出")
                    break
                logger.error(f"❌ 守护进程异常: {e}", exc_info=True)
                stop_event.wait(timeout=10)  # 异常后等待10秒

    except BaseException as e:
        if stop_event.is_set() or _is_expected_daemon_shutdown_exception(e):
            logger.info("ℹ️ 守护进程收到停止信号，正常退出")
        else:
            logger.error(f"❌ 守护进程初始化失败: {e}", exc_info=True)
    finally:
        logger.info("🛑 守护进程已停止")


def _init_dag_node_registry():
    """初始化 DAG 节点注册表 — 加载所有 V1 节点实现"""
    try:
        # 导入所有节点模块，触发 @NodeRegistry.register 装饰器
        from application.engine.dag.nodes import context_nodes, execution_nodes, validation_nodes, gateway_nodes  # noqa: F401
        from application.engine.dag.registry import NodeRegistry
        logger.info(f"✅ DAG 节点注册表已初始化: {sorted(NodeRegistry.all_types())}")
    except Exception as e:
        logger.warning(f"⚠️ DAG 节点注册表初始化失败（DAG 引擎将不可用）: {e}")


def _start_autopilot_daemon_thread():
    """启动自动驾驶守护进程（独立进程，不阻塞主事件循环）"""
    global _daemon_process, _daemon_stop_event

    if _daemon_process is not None and _daemon_process.is_alive():
        logger.warning("⚠️  守护进程已在运行，跳过重复启动")
        return

    # 检查环境变量是否禁用自动启动守护进程
    if os.getenv("DISABLE_AUTO_DAEMON", "").lower() in ("1", "true", "yes"):
        logger.info("🔒 守护进程自动启动已禁用（DISABLE_AUTO_DAEMON=1）")
        return

    # 重要：在启动守护进程前初始化 StreamingBus 的队列
    # 使用 mp.Queue（可 pickle 序列化传递给子进程）
    from application.engine.services.streaming_bus import init_streaming_bus
    stream_queue = init_streaming_bus()

    # 初始化跨进程共享状态字典（必须在启动子进程前完成）
    shared_state = _get_shared_state()

    # 🔥 初始化共享状态仓库（内存优先读取的核心组件）
    from application.engine.services.shared_state_repository import (
        init_shared_state_repository,
    )
    shared_state_repo = init_shared_state_repository(shared_state)
    logger.info("✅ 共享状态仓库已初始化")

    # 🔥 启动时从 DB 加载所有数据到共享内存
    from application.engine.services.state_bootstrap import bootstrap_state
    bootstrap_stats = bootstrap_state()
    logger.info(f"✅ 状态已从 DB 加载到共享内存: {bootstrap_stats}")

    # 🔥 初始化查询服务（API 层的唯一查询入口）
    from application.engine.services.query_service import init_query_service
    init_query_service(shared_state_repo)
    logger.info("✅ 查询服务已初始化")

    # 🔥 初始化持久化队列（CQRS 单一写入者模式）
    from application.engine.services.persistence_queue import (
        initialize_persistence_queue, get_persistence_queue,
        register_persistence_handlers
    )
    persistence_queue = initialize_persistence_queue()

    # 注册持久化处理器（在主进程执行 DB 写入）
    register_persistence_handlers()

    # 启动消费者线程（唯一的 DB 写入者）
    get_persistence_queue().start_consumer()
    logger.info("✅ 持久化消费者线程已启动（单一写入者模式）")

    _daemon_stop_event = multiprocessing.Event()

    # 使用独立进程运行守护进程，完全隔离于主进程的事件循环
    _daemon_process = multiprocessing.Process(
        target=_run_daemon_in_process,
        args=(_daemon_stop_event, log_level, log_file, stream_queue, shared_state, persistence_queue),
        name="AutopilotDaemon",
        daemon=True,
    )
    _daemon_process.start()
    logger.info("✅ 守护进程已创建并启动（独立进程模式，流式队列 + 共享状态 + 持久化队列已传递）")


def _cleanup_orphan_python_processes():
    """Windows: 清理可能残留的 plotpilot-backend 相关进程。

    注意：只清理命令行中包含 'plotpilot' 或 'autopilot' 的 Python 进程，
    避免误杀其他无关的 Python 进程。
    """
    import subprocess

    try:
        # 获取当前进程 PID
        current_pid = os.getpid()
        logger.info(f"🔍 检查残留进程（当前 PID={current_pid}）...")

        # 使用 wmic 查找 Python 进程
        result = subprocess.run(
            ['wmic', 'process', 'where', "name='python.exe' or name='python3.exe' or name='plotpilot-backend.exe'",
             'get', 'processid,commandline'],
            capture_output=True,
            text=True,
            timeout=5
        )

        lines = result.stdout.strip().split('\n')
        killed_count = 0

        for line in lines:
            line = line.strip()
            if not line or 'CommandLine' in line:
                continue

            # 检查是否是相关进程
            if any(keyword in line.lower() for keyword in ['plotpilot', 'autopilot', 'uvicorn', 'interfaces.main']):
                # 提取 PID（最后一个数字）
                parts = line.split()
                for part in reversed(parts):
                    if part.isdigit():
                        pid = int(part)
                        # 不要杀死当前进程
                        if pid != current_pid:
                            try:
                                logger.info(f"🧹 清理残留进程 PID={pid}: {line[:80]}...")
                                subprocess.run(['taskkill', '/F', '/PID', str(pid)],
                                             capture_output=True, timeout=5)
                                killed_count += 1
                            except Exception as e:
                                logger.warning(f"清理进程 {pid} 失败: {e}")
                        break

        if killed_count > 0:
            logger.info(f"✅ 已清理 {killed_count} 个残留进程")
        else:
            logger.info("✅ 未发现残留进程")

    except subprocess.TimeoutExpired:
        logger.warning("⚠️ 进程清理超时")
    except Exception as e:
        logger.warning(f"⚠️ 进程清理失败: {e}")


def _stop_autopilot_daemon_thread():
    """停止守护进程

    关键修复：确保 multiprocessing.Process 子进程在 os._exit 之前被彻底终止。
    Windows 上 os._exit(0) 不会触发 Python 的正常清理流程，
    daemon=True 的子进程可能变成孤儿进程，导致应用无法关闭。
    """
    global _daemon_process, _daemon_stop_event

    daemon_pid = _daemon_process.pid if _daemon_process else None

    # 🔥 停止持久化消费者线程（先停止消费，再停止守护进程）
    try:
        from application.engine.services.persistence_queue import get_persistence_queue
        get_persistence_queue().stop_consumer()
    except Exception as e:
        logger.debug(f"停止持久化消费者失败（可忽略）: {e}")

    # 通过 StreamingBus 发布全局停止信号（确保守护进程内正在运行的小说也能立即感知）
    try:
        from application.engine.services.streaming_bus import streaming_bus
        streaming_bus.publish_stop_signal("__all__")  # 特殊 ID，通知守护进程所有小说
    except Exception as e:
        logger.debug("发布全局停止信号失败（可忽略）: %s", e)

    if _daemon_stop_event:
        logger.info("🛑 正在停止守护进程...")
        _daemon_stop_event.set()

    if _daemon_process and _daemon_process.is_alive():
        _daemon_process.join(timeout=2)  # 给守护进程 2 秒完成当前轮询
        if _daemon_process.is_alive():
            logger.warning("⚠️  守护进程未在超时时间内停止，强制终止")
            _daemon_process.terminate()
            _daemon_process.join(timeout=1)
            # 如果还是活着，强制kill
            if _daemon_process.is_alive():
                logger.warning("⚠️  守护进程仍未停止，使用 SIGKILL")
                try:
                    os.kill(_daemon_process.pid, signal.SIGKILL)
                    _daemon_process.join(timeout=1)
                except Exception as e:
                    logger.error(f"强制终止守护进程失败: {e}")
        else:
            logger.info("✅ 守护进程已成功停止")

    # Windows: 使用 taskkill 强制杀死已知 PID 的子进程（双保险）
    # multiprocessing 在 Windows 上使用 spawn 方式，子进程可能不在同一进程树
    if os.name == "nt" and daemon_pid:
        try:
            import subprocess
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(daemon_pid)],
                capture_output=True, timeout=3
            )
            logger.info(f"🛑 Windows: 已通过 taskkill 终止守护进程 PID={daemon_pid}")
        except Exception as e:
            logger.debug(f"taskkill 终止守护进程失败（可能已退出）: {e}")

    _daemon_process = None
    _daemon_stop_event = None

    # Windows: 额外清理可能残留的 Python 子进程
    if os.name == "nt":
        _cleanup_orphan_python_processes()


def restart_autopilot_daemon():
    """重启守护进程以拾取新的 LLM / 嵌入配置（跨进程 env 不可共享，必须重启）。"""
    _stop_autopilot_daemon_thread()
    _start_autopilot_daemon_thread()
    logger.info("🔄 守护进程已因配置变更重启")


# 配置 CORS
# 前后端同端口部署：前端是同源请求，默认允许所有源。
# 开发环境可通过 CORS_ORIGINS 环境变量限制。
_cors_origins_env = os.getenv("CORS_ORIGINS", "")
if _cors_origins_env:
    _allowed_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
else:
    _allowed_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册统一错误处理器（捕获未处理异常并记录日志）
from interfaces.api.middleware.error_handler import add_error_handlers
add_error_handlers(app)

# HTTP 访问日志由 uvicorn.access 输出（与 uvicorn 默认格式一致：IP + 请求行 + 状态码）

# ════════════════════════════════════════════════════════════════════════════
# 路由注册
#
# 约定：
#   1. 所有 API 路由统一使用 /api/v1 前缀，在 include_router 处一次性注入
#   2. 各 router 模块内部只声明语义路径（如 /novels、/bible），不得硬编码 /api/v1
#   3. 前端 apiClient.baseURL = '/api/v1'，调用时使用相对路径（如 /novels/{id}）
# ════════════════════════════════════════════════════════════════════════════

_V1 = "/api/v1"

# ── Core：小说 / 章节 / 导出 / 设置 ──
app.include_router(novels.router,                   prefix=_V1)
app.include_router(chapters.router,                 prefix="/api/v1/novels")  # chapters 路由无自身 prefix，挂在 /novels 下
app.include_router(export.router,                   prefix=_V1)
app.include_router(llm_settings.router,             prefix=_V1)
app.include_router(llm_settings.embedding_router,   prefix=_V1)
app.include_router(scene_generation_routes.router,  prefix=_V1)  # /scenes

# ── World：世界观 / 人物谱 / 知识库 / 知识图谱 ──
app.include_router(bible.router,                    prefix=_V1)  # /bible
app.include_router(cast.router,                     prefix=_V1)  # 无 prefix，路由自身含 /novels/{id}/cast
app.include_router(knowledge.router,                prefix=_V1)  # /novels/{id}/knowledge
app.include_router(knowledge_graph_routes.router,   prefix=_V1)  # /knowledge-graph
app.include_router(worldbuilding_routes.router,     prefix=_V1)  # /novels/{id}/worldbuilding

# ── Blueprint：规划 / 节拍表 / 故事结构 ──
app.include_router(continuous_planning_routes.router, prefix=_V1)  # /planning
app.include_router(beat_sheet_routes.router,          prefix=_V1)  # /beat-sheets
app.include_router(story_structure.router,             prefix=_V1)  # 无 prefix，路由自身含 /novels/{id}/structure

# ── Engine：生成 / 上下文 / 编年史 / 快照 / 自动驾驶 / 工作台 / 角色调度 / 检查点 ──
app.include_router(generation.router,                     prefix=_V1)
app.include_router(context_intelligence.router,           prefix=_V1)
app.include_router(chronicles.router,                     prefix=_V1)
app.include_router(snapshot_routes.router,                prefix=_V1)
app.include_router(autopilot_routes.router,               prefix=_V1)  # /autopilot
app.include_router(workbench_context_routes.router,       prefix=_V1)
app.include_router(character_scheduler_routes.router,     prefix=_V1)  # /character-scheduler
app.include_router(checkpoint_routes.router,              prefix=_V1)  # Checkpoint + QualityGuardrail + StoryPhase + CharacterPsyche

# ── Engine：溯源 / DAG 工作流 ──
from interfaces.api.v1.engine.trace_routes import router as trace_router
app.include_router(trace_router,                          prefix=_V1)

from interfaces.api.v1.engine.dag.dag_routes import router as dag_router
app.include_router(dag_router,                            prefix=_V1)  # /dag

# ── Audit：审稿 / 宏观重构 / 章节元素 ──
app.include_router(chapter_review_routes.router,          prefix=_V1)  # /chapter-reviews
app.include_router(macro_refactor.router,                 prefix=_V1)
app.include_router(chapter_element_routes.router,         prefix=_V1)  # /chapters (元素关联)

# ── Analyst：文风 / 叙事状态 / 伏笔 ──
app.include_router(voice.router,                          prefix=_V1)
app.include_router(narrative_state.router,                prefix=_V1)
app.include_router(foreshadow_ledger.router,              prefix=_V1)

# ── System：内部工具（不暴露到 OpenAPI 文档）──
app.include_router(system_routes.router,                  prefix=_V1)

# ── Reader Simulation：读者模拟 ──
app.include_router(reader_module.router,                  prefix=_V1)  # /reader

# ── Workbench：写作工具 ──
app.include_router(writer_block.router,                   prefix=_V1)
app.include_router(sandbox.router,                        prefix=_V1)
app.include_router(monitor.router,                        prefix=_V1)
app.include_router(llm_control.router,                    prefix=_V1)  # /llm-control

# ── Anti-AI：防御系统 ──
from interfaces.api.v1 import anti_ai as anti_ai_routes
app.include_router(anti_ai_routes.router,                 prefix=_V1)  # /anti-ai

# ── Stats：统计（独立前缀 /api/stats，不走 /api/v1）──
stats_repository = SqliteStatsRepositoryAdapter(get_database())
stats_service = StatsService(stats_repository)
stats_router = create_stats_router(stats_service)
app.include_router(stats_router, prefix="/api/stats", tags=["statistics"])


@app.get("/")
async def root():
    """根路径 — 返回前端页面（SPA）或 API 欢迎消息"""
    if _FRONTEND_DIR.exists() and _INDEX_HTML.exists():
        return FileResponse(str(_INDEX_HTML), media_type="text/html")
    return {"message": "PlotPilot API", "release": APP_RELEASE_VERSION}


@app.get("/health")
async def health_check():
    """健康检查

    Returns:
        健康状态
    """
    uptime = time.time() - STARTUP_TIME
    daemon_alive = _daemon_process is not None and _daemon_process.is_alive()
    return {
        "status": "healthy",
        "version": APP_RELEASE_VERSION,
        "build_id": BACKEND_BUILD_ID,
        "uptime_seconds": round(uptime, 2),
        "daemon_process": {
            "running": daemon_alive,
            "pid": _daemon_process.pid if _daemon_process else None
        }
    }


# ── SPA fallback：前端路由兜底（必须在 API 路由之后注册）──
if _FRONTEND_DIR.exists() and _INDEX_HTML.exists():
    @app.get("/{full_path:path}", include_in_schema=False)
    @app.post("/{full_path:path}", include_in_schema=False)
    @app.put("/{full_path:path}", include_in_schema=False)
    @app.patch("/{full_path:path}", include_in_schema=False)
    @app.delete("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str, req: Request):
        """SPA fallback — 所有未匹配的路径返回 index.html"""
        # 排除 API 路径、统计路由和静态资源
        if (full_path.startswith("api/") or full_path.startswith("stats/")
                or full_path.startswith("assets/") or full_path.startswith("_")):
            # 对无尾部斜杠的 API 路径做 307 重定向到带斜杠版本
            if not full_path.endswith('/'):
                redirect_url = req.url.path + '/'
                if req.url.query:
                    redirect_url += '?' + req.url.query
                return RedirectResponse(url=redirect_url, status_code=307)
            return JSONResponse({"error": "Not Found"}, status_code=404)
        return FileResponse(str(_INDEX_HTML), media_type="text/html")


# ── Windows CTRL+C 防卡死：看门狗线程 + atexit 双保险 ──
_shutdown_deadline: float | None = None


def _force_exit_watchdog() -> None:
    """看门狗线程：监控关闭流程，超时后强制 os._exit(0)。

    问题背景：
    - uvicorn 收到 SIGINT 后走优雅关闭（shutdown event → close_all → WAL checkpoint）
    - 但 Windows 下守护进程可能持有 DB 写锁，close_all 的 checkpoint 会无限等待
    - Intel Fortran runtime 也会拦截 CTRL+C（forrtl: error 200）
    - multiprocessing 子进程可能在 uvicorn join 时卡住

    解决方案：
    - 在 shutdown event 触发时启动看门狗，给优雅关闭 8 秒时间
    - 超时后直接 os._exit(0)，确保进程能退出
    """
    global _shutdown_deadline
    if _shutdown_deadline is None:
        return
    # 等待优雅关闭完成或超时
    while time.time() < _shutdown_deadline:
        time.sleep(0.5)
    # 超时，强制退出
    logger.warning("看门狗：优雅关闭超时（8s），强制退出")
    logging.shutdown()
    os._exit(0)


def _start_force_exit_watchdog() -> None:
    """在关闭流程开始时启动看门狗线程。"""
    global _shutdown_deadline
    _shutdown_deadline = time.time() + 8.0
    t = threading.Thread(target=_force_exit_watchdog, daemon=True)
    t.start()


# atexit 钩子：确保无论哪种退出路径都能清理
import atexit as _atexit


def _atexit_shutdown_guard() -> None:
    """atexit 钩子：在 Python 正常退出时确保进程能终止。

    如果 uvicorn 的 shutdown event 已经处理了清理，这里什么也不做。
    如果是 os._exit 之外的退出路径（如 sys.exit），看门狗确保不会卡住。
    """
    _start_force_exit_watchdog()


_atexit.register(_atexit_shutdown_guard)


if os.name == "nt":
    # Windows: 注册 SIGBREAK 处理器（CTRL+BREAK 比 CTRL+C 更不容易被拦截）
    try:
        def _sigbreak_handler(signum, frame):
            logger.info("收到 SIGBREAK 信号，强制退出")
            _stop_autopilot_daemon_thread()
            logging.shutdown()
            os._exit(0)

        signal.signal(signal.SIGBREAK, _sigbreak_handler)
    except (OSError, ValueError, AttributeError):
        pass  # SIGBREAK 仅 Windows，非主线程也无法注册


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
