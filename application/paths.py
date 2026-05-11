"""仓库内路径（不依赖进程当前工作目录）。"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# application/paths.py → PlotPilot（墨枢）仓库根目录
AITEXT_ROOT = Path(__file__).resolve().parents[1]

# 环境变量名：由 Tauri 生产构建在启动 Python 子进程时注入，指向用户可写目录（如 AppData）
AITEXT_PROD_DATA_DIR_ENV = "AITEXT_PROD_DATA_DIR"

# 须与 frontend/src-tauri/tauri.conf.json 中 identifier 一致（桌面壳 app_data_dir 下会再用 data/）
# 自 com.plotpilot.app 迁移：旧数据在 %APPDATA%/com.plotpilot.app/data，可手工复制到 com.plotpilot.desktop/data
TAURI_APP_IDENTIFIER = "com.plotpilot.desktop"


def _frozen_fallback_data_dir() -> Path:
    """PyInstaller 等冻结产物在未注入 AITEXT_PROD_DATA_DIR 时的默认数据目录。

    不可使用 AITEXT_ROOT / data：冻结时 AITEXT_ROOT 会落在 _internal/，通常只读或易被安全软件锁，
    SQLite WAL 会触发 disk I/O error。此处与 Tauri resolve_prod_data_dir 语义对齐（Roaming 下 identifier/data）。
    """
    home = Path.home()
    if sys.platform == "win32":
        roaming = os.environ.get("APPDATA", "").strip()
        base = Path(roaming) if roaming else home / "AppData" / "Roaming"
        return base / TAURI_APP_IDENTIFIER / "data"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / TAURI_APP_IDENTIFIER / "data"
    return home / ".local" / "share" / TAURI_APP_IDENTIFIER / "data"


def _resolve_data_dir() -> Path:
    """
    解析持久化数据根目录。

    - 若设置 AITEXT_PROD_DATA_DIR：桌面安装版，使用用户数据目录（由 Rust 注入）。
    - 否则若 PyInstaller 冻结：使用与 Tauri 一致的用户可写目录，避免写入 _internal。
    - 否则：本地开发 / CLI，使用仓库内 data/。
    """
    raw = os.environ.get(AITEXT_PROD_DATA_DIR_ENV, "").strip()
    if raw:
        p = Path(raw).expanduser().resolve()
    elif getattr(sys, "frozen", False):
        p = _frozen_fallback_data_dir()
        logger.info(
            "冻结进程未设置 %s，数据目录: %s",
            AITEXT_PROD_DATA_DIR_ENV,
            p,
        )
        # 曾错误地把库存放在 PyInstaller _internal/data 的用户会看到空库，提示手动迁移或设环境变量
        legacy_db = AITEXT_ROOT / "data" / "aitext.db"
        if legacy_db.is_file() and not (p / "aitext.db").is_file():
            logger.warning(
                "发现旧数据文件 %s，而当前默认目录尚无 aitext.db。"
                "若需沿用旧库，请将其中数据复制到 %s，或启动时设置环境变量 %s 指向旧库的父目录（含 aitext.db 的 data 文件夹）。",
                legacy_db,
                p,
                AITEXT_PROD_DATA_DIR_ENV,
            )
    else:
        p = AITEXT_ROOT / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


DATA_DIR = _resolve_data_dir()


def get_db_path() -> str:
    """获取数据库文件路径

    Returns:
        数据库文件的绝对路径字符串
    """
    return str(DATA_DIR / "aitext.db")
