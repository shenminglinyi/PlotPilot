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
)

# Audit module
from interfaces.api.v1.audit import chapter_review_routes, macro_refactor, chapter_element_routes

# Analyst module
from interfaces.api.v1.analyst import voice, narrative_state, foreshadow_ledger

# System module (internal tooling)
from interfaces.api.v1 import system as system_routes

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

    # 重启时将所有运行中的小说设置为停止状态
    _stop_all_running_novels()
    
    # 启动自动驾驶守护进程（后台线程）
    _start_autopilot_daemon_thread()

def _checkpoint_sqlite_wal_safe() -> None:
    """桌面端优雅退出时尽量将 WAL 落盘，降低异常断电时的损坏概率。"""
    try:
        import sqlite3

        from application.paths import get_db_path

        dbp = get_db_path()
        conn = sqlite3.connect(dbp, timeout=15.0)
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            conn.close()
    except Exception as e:
        logger.warning("WAL checkpoint 失败（可忽略）: %s", e)


def _run_backend_shutdown_hooks() -> None:
    """与 shutdown 生命周期钩子共用：守护进程停止 + WAL + 日志。"""
    _stop_autopilot_daemon_thread()
    _checkpoint_sqlite_wal_safe()

    uptime = time.time() - STARTUP_TIME
    logger.info("=" * 80)
    logger.info("🛑 BACKEND SHUTTING DOWN")
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
    time.sleep(0.15)
    if os.name == "nt":
        _run_backend_shutdown_hooks()
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

# HTTP 访问日志由 uvicorn.access 输出（与 uvicorn 默认格式一致：IP + 请求行 + 状态码）

# Core module routes
app.include_router(novels.router, prefix="/api/v1")
app.include_router(chapters.router, prefix="/api/v1/novels")
app.include_router(scene_generation_routes.router)
app.include_router(llm_settings.router, prefix="/api/v1")
app.include_router(llm_settings.embedding_router, prefix="/api/v1")
app.include_router(export.router, prefix="/api/v1")

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

# System module routes (internal tooling)
app.include_router(system_routes.router, prefix="/api/v1")

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
