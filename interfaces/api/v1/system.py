"""系统管理 API（内部工具端点）

提供扩展包安装、环境检测等系统级操作。
所有端点仅允许本机访问（localhost）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["system"], include_in_schema=False)

# ════════════════════════════════════════════
# 常量
# ════════════════════════════════════════════

PIP_MIRRORS = [
    {"name": "阿里云",   "url": "https://mirrors.aliyun.com/pypi/simple/",        "host": "mirrors.aliyun.com"},
    {"name": "清华大学", "url": "https://pypi.tuna.tsinghua.edu.cn/simple/",       "host": "pypi.tuna.tsinghua.edu.cn"},
    {"name": "中科大",   "url": "https://pypi.mirrors.ustc.edu.cn/simple/",         "host": "pypi.mirrors.ustc.edu.cn"},
    {"name": "腾讯云",   "url": "https://mirrors.cloud.tencent.com/pypi/simple/",   "host": "mirrors.cloud.tencent.com"},
    {"name": "华为云",   "url": "https://repo.huaweicloud.com/repository/pypi/simple/", "host": "repo.huaweicloud.com"},
    {"name": "官方源",   "url": "https://pypi.org/simple/",                          "host": "pypi.org"},
]

# 全局安装锁：防止并发执行多个 pip install
_install_lock = threading.Lock()
_install_status: dict = {
    "running": False,
    "started_at": None,
    "progress_msg": "",
}


def _assert_localhost(request: Request) -> None:
    """仅允许本机访问"""
    if not request.client:
        raise HTTPException(status_code=403, detail="Forbidden")
    host = request.client.host or ""
    if host not in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
        raise HTTPException(status_code=403, detail="Only localhost access allowed")


def _get_project_root() -> Path:
    """获取项目根目录"""
    return Path(__file__).resolve().parents[3]


def _get_python_executable() -> str:
    """获取当前 Python 解释器路径"""
    return sys.executable


def _check_extensions_installed() -> dict:
    """检查扩展依赖是否已安装"""
    result = {
        "faiss": False,
        "numpy": False,
        "sentence_transformers": False,
        "all_installed": False,
    }
    for pkg in list(result.keys())[:-1]:
        try:
            __import__(pkg.replace("-", "_"))
            result[pkg] = True
        except ImportError:
            pass
    result["all_installed"] = all(result[pkg] for pkg in list(result.keys())[:-1])
    return result


def _tail_log_file_lines(
    log_path_raw: str,
    max_lines: int,
    max_bytes: int = 768_000,
) -> Tuple[List[str], str, bool, bool]:
    """尾部若干行：(lines, resolved_path, missing, truncated_early_content)"""
    raw = Path(log_path_raw)
    path = raw.resolve() if raw.is_absolute() else (Path.cwd() / raw).resolve()
    resolved = str(path)
    if not path.is_file():
        return [], resolved, True, False
    try:
        size = path.stat().st_size
    except OSError:
        return [], resolved, True, False
    start = max(0, size - max_bytes)
    truncated_window = start > 0
    try:
        with path.open("rb") as fh:
            fh.seek(start)
            chunk = fh.read()
    except OSError:
        return [], resolved, True, truncated_window
    if start > 0 and b"\n" in chunk:
        chunk = chunk.split(b"\n", 1)[1]
    text = chunk.decode("utf-8", errors="replace")
    lines = text.splitlines()
    line_truncated = len(lines) > max_lines
    if line_truncated:
        lines = lines[-max_lines:]
    return lines, resolved, False, truncated_window or line_truncated


def _snapshot_feedback_bundle_sync(max_lines: int, ring_limit: int) -> Dict[str, Any]:
    """运行于线程池，避免磁盘 IO 卡住事件循环。"""
    log_env = os.getenv("LOG_FILE", "logs/plotpilot.log")
    lines, resolved, missing, log_truncated = _tail_log_file_lines(log_env, max_lines)

    backend_release = "unknown"
    backend_build_id = "unknown"
    uptime_sec: Any = None
    try:
        from interfaces import main as app_main

        backend_release = getattr(app_main, "APP_RELEASE_VERSION", backend_release)
        backend_build_id = getattr(app_main, "BACKEND_BUILD_ID", backend_build_id)
        st = getattr(app_main, "STARTUP_TIME", None)
        if isinstance(st, (int, float)):
            uptime_sec = round(time.time() - st, 2)
    except Exception:
        pass

    ring_out: List[Dict[str, Any]] = []
    if ring_limit > 0:
        try:
            from application.engine.services.autopilot_log_ring import snapshot_global_ring

            for entry in snapshot_global_ring(ring_limit):
                ring_out.append(
                    {
                        "seq": entry.seq,
                        "timestamp": entry.timestamp_iso,
                        "level": entry.level,
                        "logger": entry.logger_name,
                        "novel_id": entry.novel_id,
                        "message": (entry.message or "")[:4000],
                    }
                )
        except Exception as e:
            logger.warning("snapshot_global_ring failed: %s", e)

    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "backend_release": backend_release,
        "backend_build_id": backend_build_id,
        "backend_uptime_seconds": uptime_sec,
        "log_file_env": log_env,
        "log_file_resolved": resolved,
        "log_file_missing": missing,
        "log_truncated": log_truncated,
        "log_tail_line_count": len(lines),
        "log_tail_lines": lines,
        "memory_ring_recent": ring_out,
    }


# ════════════════════════════════════════════
# Schema
# ════════════════════════════════════════════


class InstallExtensionsResponse(BaseModel):
    status: str  # "already_running" | "started"
    message: str


# ════════════════════════════════════════════
# 端点
# ════════════════════════════════════════════


@router.get("/feedback-log-snapshot")
async def feedback_log_snapshot(
    request: Request,
    max_lines: int = Query(600, ge=1, le=2500),
    ring_limit: int = Query(200, ge=0, le=800),
):
    """供前端一键反馈：LOG_FILE 尾部 + API 进程内存日志环。

    与 /system/extensions-* 一致，仅限本机（127.0.0.1 / ::1）访问，减轻远程泄漏风险。
    """
    _assert_localhost(request)
    return await asyncio.to_thread(_snapshot_feedback_bundle_sync, max_lines, ring_limit)


@router.get("/extensions-status")
async def get_extensions_status(request: Request):
    """检查本地 AI 扩展包的安装状态"""
    _assert_localhost(request)
    installed = _check_extensions_installed()
    return {
        **installed,
        "install_running": _install_status["running"],
        "install_progress": _install_status["progress_msg"] if _install_status["running"] else "",
    }


@router.post("/install-extensions")
async def install_extensions(request: Request):
    """安装本地 AI 扩展包（SSE 流式返回日志）

    执行 `pip install -r requirements-local.txt`，
    通过 Server-Sent Events 实时推送安装进度和日志。
    """
    _assert_localhost(request)

    # 检查是否已在运行
    if _install_lock.locked() and _install_status["running"]:
        return InstallExtensionsResponse(
            status="already_running",
            message="安装任务已在运行中，请等待完成",
        )

    def _generate_events():
        """生成 SSE 事件流（就地更新模块级 _install_status 字典，无需 global）"""

        # 加锁
        acquired = _install_lock.acquire(timeout=0.1)
        if not acquired:
            yield f"data: {json.dumps({'type': 'error', 'message': '安装任务已在运行中'}, ensure_ascii=False)}\n\n"
            return

        try:
            _install_status["running"] = True
            _install_status["started_at"] = time.time()
            _install_status["progress_msg"] = "准备安装..."

            project_root = _get_project_root()
            python_exe = _get_python_executable()
            req_file = project_root / "requirements-local.txt"

            # ── 检查 requirements 文件 ──
            if not req_file.exists():
                yield f"data: {json.dumps({'type': 'error', 'message': f'找不到 {req_file.name}'}, ensure_ascii=False)}\n\n"
                return

            yield f"data: {json.dumps({'type': 'info', 'message': f'📦 开始安装本地 AI 扩展包...'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'info', 'message': f'📄 文件: {req_file.name} (~2GB)'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'info', 'message': f'🐍 Python: {python_exe}'}, ensure_ascii=False)}\n\n"
            _install_status["progress_msg"] = "正在升级 pip..."

            # ── 升级 pip ──
            mirror = PIP_MIRRORS[0]
            upgrade_cmd = [
                python_exe, "-m", "pip", "install",
                "--upgrade", "pip", "setuptools", "wheel",
                "-i", mirror["url"],
                "--trusted-host", mirror["host"],
                "--no-cache-dir",
                "-q",
            ]
            try:
                proc = subprocess.Popen(
                    upgrade_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
                )
                proc.communicate(timeout=300)
            except Exception as e:
                yield f"data: {json.dumps({'type': 'warn', 'message': f'pip 升级跳过: {e}'}, ensure_ascii=False)}\n\n"

            _install_status["progress_msg"] = "正在下载扩展包..."

            # ── 安装扩展依赖（多镜像 fallback）──
            max_mirrors = len(PIP_MIRRORS)
            success = False

            for attempt in range(max_mirrors):
                m = PIP_MIRRORS[attempt]
                if attempt > 0:
                    mirror_name = m["name"]
                    yield f"data: {json.dumps({'type': 'warn', 'message': f'🔄 切换镜像源 [{mirror_name}] ({attempt+1}/{max_mirrors})'}, ensure_ascii=False)}\n\n"

                cmd = [
                    python_exe, "-m", "pip", "install", "-r", str(req_file),
                    "-i", m["url"],
                    "--trusted-host", m["host"],
                    "--timeout", "600",
                    "--retries", "1",
                    "--no-cache-dir",
                    "--progress-bar", "off",
                    "--disable-pip-version-check",
                ]

                _install_status["progress_msg"] = f"正在下载 [{m['name']}]..."

                try:
                    proc = subprocess.Popen(
                        cmd,
                        cwd=str(project_root),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        bufsize=1,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
                    )

                    collecting_count = 0
                    current_pkg = ""

                    for line in proc.stdout:
                        line = line.rstrip()
                        if not line:
                            continue

                        # 解析关键行
                        if "Successfully installed" in line:
                            yield f"data: {json.dumps({'type': 'success', 'message': f'✅ {line.strip()}'}, ensure_ascii=False)}\n\n"
                        elif ("error" in line.lower() and "ERROR" in line) or line.startswith("ERROR"):
                            yield f"data: {json.dumps({'type': 'error', 'message': line[:200]}, ensure_ascii=False)}\n\n"
                        elif "warning" in line.lower() or line.startswith("WARNING"):
                            # 过滤掉过多噪音 warning
                            if "version" not in line.lower() and "deprecated" not in line.lower():
                                yield f"data: {json.dumps({'type': 'warn', 'message': line[:150]}, ensure_ascii=False)}\n\n"
                        elif line.startswith("Collecting"):
                            collecting_count += 1
                            pkg = line.replace("Collecting", "").strip().split(" ")[0]
                            current_pkg = pkg
                            pct = min(collecting_count * 4, 80)
                            _install_status["progress_msg"] = f"正在获取: {pkg}"
                            yield f"data: {json.dumps({'type': 'progress', 'message': f'⏳ 获取: {pkg}', 'percent': pct}, ensure_ascii=False)}\n\n"
                        elif line.startswith("Downloading"):
                            fname_match = re.search(r'/([^/]+\.(?:whl|tar\.gz|zip))', line)
                            pkg_name = fname_match.group(1) if fname_match else line.strip()[11:60]
                            current_pkg = pkg_name
                            _install_status["progress_msg"] = f"正在下载: {pkg_name}"
                            yield f"data: {json.dumps({'type': 'progress', 'message': f'📥 下载: {pkg_name}', 'percent': -1}, ensure_ascii=False)}\n\n"
                        elif "Installing collected packages" in line:
                            _install_status["progress_msg"] = "正在写入文件..."
                            yield f"data: {json.dumps({'type': 'info', 'message': '⏳ 正在写入文件...（此过程可能需要 1~5 分钟）'}, ensure_ascii=False)}\n\n"
                            yield f"data: {json.dumps({'type': 'progress', 'message': '写入中...', 'percent': 88}, ensure_ascii=False)}\n\n"
                        else:
                            # 其他信息行（限制频率）
                            if len(line) < 200:
                                yield f"data: {json.dumps({'type': 'log', 'message': line}, ensure_ascii=False)}\n\n"

                    proc.wait()

                    if proc.returncode == 0:
                        success = True
                        break
                    else:
                        fail_mirror = m["name"]
                        yield f"data: {json.dumps({'type': 'warn', 'message': f'❌ 镜像 [{fail_mirror}] 失败 (code={proc.returncode})'}, ensure_ascii=False)}\n\n"

                except subprocess.TimeoutExpired:
                    yield f"data: {json.dumps({'type': 'error', 'message': '⏰ 安装超时（>10分钟）'}, ensure_ascii=False)}\n\n"
                    if 'proc' in locals():
                        proc.kill()
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'message': f'异常: {e}'}, ensure_ascii=False)}\n\n"

            # ── 最终结果 ──
            _install_status["progress_msg"] = "完成" if success else "失败"

            if success:
                # 验证安装结果
                verify = _check_extensions_installed()
                yield f"data: {json.dumps({'type': 'done', 'success': True, 'message': '🎉 本地 AI 引擎安装完成！', 'installed': verify}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'done', 'success': False, 'message': '❌ 所有镜像源均失败，请检查网络后重试'}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"安装扩展包异常: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': f'安装异常: {e}'}, ensure_ascii=False)}\n\n"
        finally:
            _install_status["running"] = False
            _install_status["progress_msg"] = ""

    return StreamingResponse(
        _generate_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 禁止 nginx 缓冲
            "Connection": "keep-alive",
        },
    )
