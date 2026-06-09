"""FastAPI 主应用

提供 RESTful API 接口。
"""
import os
from interfaces.api.settings import (
    BackendSettings,
    configure_process_environment,
    get_backend_settings,
)

# 必须在任何 HuggingFace/Transformers 导入前设置离线模式
configure_process_environment()

from pathlib import Path
import sys
import time
import logging
from contextlib import asynccontextmanager
from datetime import datetime

# 必须在其他应用模块导入前执行：将仓库根目录 `.env` 写入 os.environ
_PLOTPILOT_ROOT = Path(__file__).resolve().parents[1]
if str(_PLOTPILOT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLOTPILOT_ROOT))
try:
    from load_env import load_env

    load_env()
except Exception:
    # 无 .env 或非标准启动方式时忽略
    pass

# 配置日志（必须在导入其他模块前）
from interfaces.api.middleware.logging_config import (
    log_startup_banner,
    parse_log_level,
    setup_logging,
)

settings = get_backend_settings()
log_level = parse_log_level(settings.log_level)
log_file = settings.log_file
setup_logging(level=log_level, log_file=log_file)

logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from starlette.requests import Request
import threading
import signal

from interfaces.api.routes import register_api_routes
from interfaces.daemon_manager import AutopilotDaemonManager
from interfaces.runtime import BackendLifecycle, get_backend_lifecycle_settings
from interfaces.runtime_state import (
    _get_shared_state,
    get_shared_novel_state,
    update_shared_novel_state,
)

APP_RELEASE_VERSION = settings.release_version
BACKEND_BUILD_ID = settings.build_id
STARTUP_TIME = time.time()

log_level = parse_log_level(settings.log_level)
log_file = settings.log_file
log_startup_banner(
    logger,
    title="PlotPilot service is starting",
    fields={
        "Release": APP_RELEASE_VERSION,
        "Build": BACKEND_BUILD_ID,
        "Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Log level": logging.getLevelName(log_level),
        "Log file": log_file,
        "Python": sys.version.split()[0],
        "Workdir": Path.cwd(),
    },
)

_FRONTEND_DIR = settings.frontend_dir
_FRONTEND_ASSETS_DIR = _FRONTEND_DIR / "assets"
_INDEX_HTML = _FRONTEND_DIR / "index.html"
_FAVICON = _FRONTEND_DIR / "favicon.svg"
_lifecycle: BackendLifecycle | None = None
_daemon_manager: AutopilotDaemonManager | None = None


def _get_lifecycle() -> BackendLifecycle:
    global _lifecycle
    if _lifecycle is None:
        _lifecycle = BackendLifecycle(
            logger=logger,
            startup_time=STARTUP_TIME,
            start_daemon=_start_autopilot_daemon_thread,
            stop_daemon=_stop_autopilot_daemon_thread,
            cleanup_orphans=_cleanup_orphan_python_processes,
            stop_async_bridge=_stop_async_bridge,
            stop_background_tasks=_stop_background_task_service,
            stop_persistence_consumer=_stop_persistence_consumer,
            stop_managed_resources=_stop_managed_resources,
            start_force_exit_watchdog=_start_force_exit_watchdog,
        )
    return _lifecycle


def _stop_background_task_service() -> None:
    from interfaces.api.dependencies import shutdown_background_task_service_if_initialized

    shutdown_background_task_service_if_initialized()


def _stop_async_bridge() -> None:
    from application.core.async_bridge import shutdown_async_bridge_executor_if_initialized

    shutdown_async_bridge_executor_if_initialized()


def _stop_persistence_consumer() -> None:
    from application.engine.services.persistence_queue import shutdown_persistence_queue_if_initialized

    shutdown_persistence_queue_if_initialized()


def _stop_managed_resources() -> None:
    from application.engine.services.resource_manager import shutdown_resource_manager_if_initialized

    shutdown_resource_manager_if_initialized()


def _get_daemon_manager() -> AutopilotDaemonManager:
    global _daemon_manager
    if _daemon_manager is None:
        _daemon_manager = AutopilotDaemonManager(
            logger=logger,
            log_level=log_level,
            log_file=log_file,
            shared_state_provider=_get_shared_state,
        )
    return _daemon_manager


def _sync_daemon_compat_state() -> None:
    global _daemon_process, _daemon_stop_event
    manager = _get_daemon_manager()
    _daemon_process = manager.process
    _daemon_stop_event = manager.stop_event


def _register_spa_fallback(created: FastAPI) -> None:
    @created.get("/{full_path:path}", include_in_schema=False)
    @created.post("/{full_path:path}", include_in_schema=False)
    @created.put("/{full_path:path}", include_in_schema=False)
    @created.patch("/{full_path:path}", include_in_schema=False)
    @created.delete("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str, req: Request):
        """SPA fallback — 所有未匹配的路径返回 index.html"""
        if (full_path.startswith("api/") or full_path.startswith("stats/")
                or full_path.startswith("assets/") or full_path.startswith("_")):
            if not full_path.endswith('/'):
                redirect_url = req.url.path + '/'
                if req.url.query:
                    redirect_url += '?' + req.url.query
                return RedirectResponse(url=redirect_url, status_code=307)
            return JSONResponse({"error": "Not Found"}, status_code=404)
        index_html = globals().get("_INDEX_HTML", _FRONTEND_DIR / "index.html")
        return FileResponse(str(index_html), media_type="text/html")


def create_app(app_settings: BackendSettings | None = None) -> FastAPI:
    """Create the FastAPI application while preserving the legacy module entry."""
    app_settings = app_settings or get_backend_settings()

    @asynccontextmanager
    async def lifespan(lifespan_app: FastAPI):
        _get_lifecycle().startup(len(lifespan_app.routes))
        try:
            yield
        finally:
            _get_lifecycle().shutdown()

    created = FastAPI(
        title="PlotPilot API",
        version=app_settings.release_version,
        description="PlotPilot（墨枢）AI 小说创作平台 API",
        redirect_slashes=True,
        lifespan=lifespan,
    )
    created.state.backend_settings = app_settings

    frontend_dir = app_settings.frontend_dir
    frontend_assets_dir = frontend_dir / "assets"
    favicon = frontend_dir / "favicon.svg"
    if frontend_assets_dir.exists():
        created.mount(
            "/assets",
            StaticFiles(directory=str(frontend_assets_dir)),
            name="frontend-assets",
        )
    if favicon.exists():
        created.get(
            "/favicon.svg",
            include_in_schema=False,
            response_class=FileResponse,
        )(lambda: FileResponse(str(favicon), media_type="image/svg+xml"))

    created.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.cors_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from interfaces.api.middleware.error_handler import add_error_handlers

    add_error_handlers(created)
    register_api_routes(created)

    @created.middleware("http")
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
                    response.headers["location"] = urlunparse(
                        (scheme, original_host, parsed.path, parsed.params, parsed.query, parsed.fragment)
                    )
        return response

    @created.post("/internal/shutdown", include_in_schema=False)
    async def internal_shutdown(request: Request):
        _assert_internal_shutdown_localhost(request)
        threading.Thread(target=_internal_shutdown_after_response, daemon=True).start()
        return {"ok": True, "message": "shutting down"}

    @created.get("/")
    async def root():
        frontend_dir = globals().get("_FRONTEND_DIR", app_settings.frontend_dir)
        index_html = globals().get("_INDEX_HTML", frontend_dir / "index.html")
        if frontend_dir.exists() and index_html.exists():
            return FileResponse(str(index_html), media_type="text/html")
        return {"message": "PlotPilot API", "release": APP_RELEASE_VERSION}

    @created.get("/health")
    async def health_check():
        uptime = time.time() - STARTUP_TIME
        daemon_status = _get_daemon_manager().status()
        return {
            "status": "healthy",
            "version": APP_RELEASE_VERSION,
            "build_id": BACKEND_BUILD_ID,
            "uptime_seconds": round(uptime, 2),
            "daemon_process": {
                "running": daemon_status.running,
                "pid": daemon_status.pid,
            },
        }

    frontend_dir = app_settings.frontend_dir
    index_html = frontend_dir / "index.html"
    if frontend_dir.exists() and index_html.exists():
        _register_spa_fallback(created)

    return created


app = create_app(settings)

def _assert_internal_shutdown_localhost(request: Request) -> None:
    if not request.client:
        raise HTTPException(status_code=403, detail="forbidden")
    host = request.client.host or ""
    if host not in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
        raise HTTPException(status_code=403, detail="forbidden")


def _internal_shutdown_after_response() -> None:
    """HTTP 响应已发出后再触发进程级退出，避免截断响应体。"""
    time.sleep(get_backend_lifecycle_settings().shutdown_response_delay_seconds)
    if os.name == "nt":
        _get_lifecycle().windows_forced_shutdown()
    os.kill(os.getpid(), signal.SIGINT)

# 守护进程进程管理（使用独立进程避免阻塞主事件循环）
_daemon_process = None
_daemon_stop_event = None

def _start_autopilot_daemon_thread():
    """兼容入口：启动自动驾驶守护进程。"""
    _get_daemon_manager().start()
    _sync_daemon_compat_state()


def _cleanup_orphan_python_processes():
    """兼容入口：清理 Windows 残留后端进程。"""
    _get_daemon_manager().cleanup_orphans()


def _stop_autopilot_daemon_thread():
    """兼容入口：停止自动驾驶守护进程。"""
    _get_daemon_manager().stop()
    _sync_daemon_compat_state()


def restart_autopilot_daemon():
    """重启守护进程以拾取新的 LLM / 嵌入配置（跨进程 env 不可共享，必须重启）。"""
    _get_daemon_manager().restart()
    _sync_daemon_compat_state()


# HTTP 访问日志由 uvicorn.access 输出（与 uvicorn 默认格式一致：IP + 请求行 + 状态码）


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
    - 在 shutdown event 触发时启动看门狗，给优雅关闭一段配置化的时间
    - 超时后直接 os._exit(0)，确保进程能退出
    """
    global _shutdown_deadline
    if _shutdown_deadline is None:
        return
    settings = get_backend_lifecycle_settings()
    # 等待优雅关闭完成或超时
    while time.time() < _shutdown_deadline:
        remaining = _shutdown_deadline - time.time()
        time.sleep(min(settings.force_exit_watchdog_poll_seconds, max(remaining, 0.0)))
    # 超时，强制退出
    logger.warning("看门狗：优雅关闭超时（%.1fs），强制退出", settings.force_exit_timeout_seconds)
    logging.shutdown()
    os._exit(0)


def _start_force_exit_watchdog() -> None:
    """在关闭流程开始时启动看门狗线程。"""
    global _shutdown_deadline
    _shutdown_deadline = time.time() + get_backend_lifecycle_settings().force_exit_timeout_seconds
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
