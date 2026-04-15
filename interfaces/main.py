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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import threading
import multiprocessing

# Core module
from interfaces.api.v1.core import novels, chapters, scene_generation_routes, settings as llm_settings

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
)

# Audit module
from interfaces.api.v1.audit import chapter_review_routes, macro_refactor, chapter_element_routes

# Analyst module
from interfaces.api.v1.analyst import voice, narrative_state, foreshadow_ledger

# Workbench module
from interfaces.api.v1.workbench import sandbox, writer_block, monitor, llm_control
from interfaces.api.stats.routers.stats import create_stats_router
from interfaces.api.stats.services.stats_service import StatsService
from interfaces.api.stats.repositories.sqlite_stats_repository_adapter import SqliteStatsRepositoryAdapter
from infrastructure.persistence.database.connection import get_database
from application.paths import DATA_DIR

# 后端版本号（每次重启递增）
BACKEND_VERSION = datetime.now().strftime("%Y%m%d-%H%M%S")
STARTUP_TIME = time.time()

logger.info("=" * 80)
logger.info(f"🚀 BACKEND STARTING - Version: {BACKEND_VERSION}")
logger.info(f"   Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
logger.info(f"   Log Level: {logging.getLevelName(log_level)}")
logger.info(f"   Log File: {log_file}")
logger.info(f"   Python: {sys.version.split()[0]}")
logger.info(f"   Working Dir: {Path.cwd()}")
logger.info("=" * 80)

# 创建 FastAPI 应用
app = FastAPI(
    title="aitext API",
    version="2.0.0",
    description="AI 小说创作平台 API"
)

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
    
    # 从 JSON 文件恢复上次激活的 LLM 配置
    try:
        from application.settings.llm_config_manager import LLMConfigManager
        LLMConfigManager(DATA_DIR / "llm_configs.json").apply_active_on_startup()
    except Exception as exc:
        logger.warning("LLM config restore skipped: %s", exc)

    # 重启时将所有运行中的小说设置为停止状态
    _stop_all_running_novels()
    
    # 启动自动驾驶守护进程（后台线程）
    _start_autopilot_daemon_thread()

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    # 停止守护进程线程
    _stop_autopilot_daemon_thread()
    
    uptime = time.time() - STARTUP_TIME
    logger.info("=" * 80)
    logger.info(f"🛑 BACKEND SHUTTING DOWN")
    logger.info(f"   Total uptime: {uptime:.2f} seconds ({uptime/3600:.2f} hours)")
    logger.info("=" * 80)

# 守护进程进程管理（使用独立进程避免阻塞主事件循环）
_daemon_process = None
_daemon_stop_event = None


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
    """重启时将所有运行中的小说设置为停止状态"""
    try:
        from application.paths import get_db_path
        import sqlite3
        from pathlib import Path
        
        db_path = get_db_path()
        db_path_obj = Path(db_path) if isinstance(db_path, str) else db_path
        
        if not db_path_obj.exists():
            logger.warning(f"⚠️  数据库文件不存在: {db_path}")
            return
        
        conn = sqlite3.connect(str(db_path_obj), timeout=10.0)
        try:
            # 检查有多少运行中的小说
            cursor = conn.execute(
                "SELECT COUNT(*) FROM novels WHERE autopilot_status = 'running'"
            )
            running_count = cursor.fetchone()[0]
            
            if running_count > 0:
                # 将所有运行中的小说设置为停止状态
                conn.execute(
                    "UPDATE novels SET autopilot_status = 'stopped', updated_at = CURRENT_TIMESTAMP WHERE autopilot_status = 'running'"
                )
                conn.commit()
                logger.info(f"🔒 已将 {running_count} 本运行中的小说设置为停止状态（服务重启）")
            else:
                logger.info("✅ 没有运行中的小说需要停止")
                
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"❌ 停止运行中小说失败: {e}", exc_info=True)


def _run_daemon_in_process(
    stop_event: threading.Event, 
    log_level: int, 
    log_file: str,
    stream_queue=None
):
    """在独立进程中运行守护进程（完全隔离，不阻塞主进程）
    
    Args:
        stop_event: 停止信号
        log_level: 日志级别
        log_file: 日志文件路径
        stream_queue: StreamingBus 的队列对象（从主进程传入）
    """
    # 重新配置日志（子进程需要独立配置）
    from interfaces.api.middleware.logging_config import setup_logging
    setup_logging(level=log_level, log_file=log_file)
    
    # 注入流式队列（必须在导入任何使用 streaming_bus 的模块前设置）
    if stream_queue is not None:
        from application.engine.services.streaming_bus import inject_stream_queue
        inject_stream_queue(stream_queue)
        logger.info("✅ 守护进程：流式队列已注入")
    
    try:
        from scripts.start_daemon import build_daemon
        daemon = build_daemon()
        logger.info("🚀 守护进程已启动（独立进程），开始轮询...")
        
        while not stop_event.is_set():
            try:
                # 执行守护进程的一个轮询周期
                active_novels = daemon._get_active_novels()
                
                if active_novels:
                    import asyncio
                    for novel in active_novels:
                        if stop_event.is_set():
                            break
                        # 使用独立事件循环处理每个小说
                        asyncio.run(daemon._process_novel(novel))
                
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
    # 使用普通 Queue（可以 pickle 序列化传递给子进程）
    from application.engine.services.streaming_bus import init_streaming_bus
    stream_queue = init_streaming_bus()
    
    _daemon_stop_event = multiprocessing.Event()
    
    # 使用独立进程运行守护进程，完全隔离于主进程的事件循环
    # 将队列传递给守护进程，实现跨进程通信
    _daemon_process = multiprocessing.Process(
        target=_run_daemon_in_process,
        args=(_daemon_stop_event, log_level, log_file, stream_queue),
        name="AutopilotDaemon",
        daemon=True,
    )
    _daemon_process.start()
    logger.info("✅ 守护进程已创建并启动（独立进程模式，流式队列已传递）")


def _stop_autopilot_daemon_thread():
    """停止守护进程"""
    global _daemon_process, _daemon_stop_event

    if _daemon_stop_event:
        logger.info("🛑 正在停止守护进程...")
        _daemon_stop_event.set()

    if _daemon_process and _daemon_process.is_alive():
        _daemon_process.join(timeout=5)  # 等待最多5秒
        if _daemon_process.is_alive():
            logger.warning("⚠️  守护进程未在超时时间内停止，强制终止")
            _daemon_process.terminate()
            _daemon_process.join(timeout=2)
        else:
            logger.info("✅ 守护进程已成功停止")

    _daemon_process = None
    _daemon_stop_event = None


def restart_autopilot_daemon():
    """重启守护进程以拾取新的 LLM / 嵌入配置（跨进程 env 不可共享，必须重启）。"""
    _stop_autopilot_daemon_thread()
    _start_autopilot_daemon_thread()
    logger.info("🔄 守护进程已因配置变更重启")


# 配置 CORS
# 生产环境请将 CORS_ORIGINS 环境变量设置为允许的域名列表，逗号分隔
# 例如：CORS_ORIGINS=https://yourapp.com,https://www.yourapp.com
# 未设置时默认仅允许 localhost（开发模式）
_cors_origins_env = os.getenv("CORS_ORIGINS", "")
if _cors_origins_env:
    _allowed_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
else:
    _allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000",
                        "http://localhost:5173", "http://127.0.0.1:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# HTTP 访问日志由 uvicorn.access 输出（与 uvicorn 默认格式一致：IP + 请求行 + 状态码）

# Core module routes
app.include_router(novels.router, prefix="/api/v1")
app.include_router(chapters.router, prefix="/api/v1/novels")
app.include_router(scene_generation_routes.router)
app.include_router(llm_settings.router, prefix="/api/v1")
app.include_router(llm_settings.embedding_router, prefix="/api/v1")

# World module routes
app.include_router(bible.router, prefix="/api/v1")
app.include_router(cast.router, prefix="/api/v1")
app.include_router(knowledge.router, prefix="/api/v1")
app.include_router(knowledge_graph_routes.router)
app.include_router(worldbuilding_routes.router)

# Blueprint module routes
app.include_router(continuous_planning_routes.router)
app.include_router(beat_sheet_routes.router)
app.include_router(story_structure.router, prefix="/api/v1")

# Engine module routes
app.include_router(generation.router, prefix="/api/v1")
app.include_router(context_intelligence.router, prefix="/api/v1")
app.include_router(chronicles.router, prefix="/api/v1")
app.include_router(snapshot_routes.router, prefix="/api/v1")
app.include_router(autopilot_routes.router, prefix="/api/v1")
app.include_router(workbench_context_routes.router, prefix="/api/v1")
app.include_router(character_scheduler_routes.router, prefix="/api/v1")  # 角色调度服务

# Audit module routes
app.include_router(chapter_review_routes.router)
app.include_router(macro_refactor.router, prefix="/api/v1")
app.include_router(chapter_element_routes.router)

# Analyst module routes
app.include_router(voice.router, prefix="/api/v1")
app.include_router(narrative_state.router, prefix="/api/v1")
app.include_router(foreshadow_ledger.router, prefix="/api/v1")

# Workbench module routes
app.include_router(writer_block.router, prefix="/api/v1")
app.include_router(sandbox.router, prefix="/api/v1")
app.include_router(monitor.router, prefix="/api/v1")
app.include_router(llm_control.router, prefix="/api/v1")

# 注册统计路由（使用 SQLite 适配器）
stats_repository = SqliteStatsRepositoryAdapter(get_database())
stats_service = StatsService(stats_repository)
stats_router = create_stats_router(stats_service)
app.include_router(stats_router, prefix="/api/stats", tags=["statistics"])


@app.get("/")
async def root():
    """根路径

    Returns:
        欢迎消息
    """
    return {"message": "aitext API v2.0"}


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
        "version": BACKEND_VERSION,
        "uptime_seconds": round(uptime, 2),
        "daemon_process": {
            "running": daemon_alive,
            "pid": _daemon_process.pid if _daemon_process else None
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
