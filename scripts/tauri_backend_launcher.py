# -*- coding: utf-8 -*-
"""Tauri 侧车进程入口：由 PyInstaller 打成 plotpilot-backend.exe。

参数：监听端口（与 Rust 传入一致）。
"""
from __future__ import annotations

import os
import sys


def _ensure_project_root_on_path() -> None:
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if base not in sys.path:
        sys.path.insert(0, base)


def _ensure_stdio_for_uvicorn_logging() -> None:
    """PyInstaller --noconsole（Windows GUI 子系统）下 stdout/stderr 可能为 None。
    uvicorn 默认日志 formatter 会执行 sys.stdout.isatty()，否则会触发 AttributeError。
    """
    if sys.stdout is None:
        sys.stdout = open(
            os.devnull, "w",
            encoding="utf-8",
            errors="replace",
        )
    if sys.stderr is None:
        sys.stderr = open(
            os.devnull, "w",
            encoding="utf-8",
            errors="replace",
        )


def main() -> None:
    _ensure_project_root_on_path()
    _ensure_stdio_for_uvicorn_logging()

    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_DATASETS_OFFLINE", "1")

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8005

    # 必须显式导入：PyInstaller 不会从 "interfaces.main:app" 字符串里追踪业务包
    import interfaces.main  # noqa: F401

    import uvicorn

    uvicorn.run(
        "interfaces.main:app",
        host="127.0.0.1",
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    import multiprocessing

    multiprocessing.freeze_support()
    main()
