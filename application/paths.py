"""仓库内路径（不依赖进程当前工作目录）。"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# application/paths.py → PlotPilot（墨枢）仓库根目录
PLOTPILOT_ROOT = Path(__file__).resolve().parents[1]

# 环境变量名：由 Tauri 生产构建在启动 Python 子进程时注入，指向用户可写目录（如 AppData）
PLOTPILOT_PROD_DATA_DIR_ENV = "PLOTPILOT_PROD_DATA_DIR"
# 旧版壳/脚本仍可能注入此名，读取时作为回退
_LEGACY_PROD_DATA_DIR_ENV = "AITEXT_PROD_DATA_DIR"

# 须与 frontend/src-tauri/tauri.conf.json 中 identifier 一致（桌面壳 app_data_dir 下会再用 data/）
# 自 com.plotpilot.app 迁移：旧数据在 %APPDATA%/com.plotpilot.app/data，可手工复制到 com.plotpilot.desktop/data
TAURI_APP_IDENTIFIER = "com.plotpilot.desktop"


def _prod_data_dir_raw() -> str:
    return (
        os.environ.get(PLOTPILOT_PROD_DATA_DIR_ENV, "").strip()
        or os.environ.get(_LEGACY_PROD_DATA_DIR_ENV, "").strip()
    )


def _frozen_fallback_data_dir() -> Path:
    """PyInstaller 等冻结产物在未注入生产数据目录环境变量时的默认数据目录。

    不可使用 PLOTPILOT_ROOT / data：冻结时 PLOTPILOT_ROOT 会落在 _internal/，通常只读或易被安全软件锁，
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

    - 若设置 PLOTPILOT_PROD_DATA_DIR（或旧名 AITEXT_PROD_DATA_DIR）：桌面安装版，使用用户数据目录（由 Rust 注入）。
    - 否则若 PyInstaller 冻结：使用与 Tauri 一致的用户可写目录，避免写入 _internal。
    - 否则：本地开发 / CLI，使用仓库内 data/。
    """
    raw = _prod_data_dir_raw()
    if raw:
        p = Path(raw).expanduser().resolve()
    elif getattr(sys, "frozen", False):
        p = _frozen_fallback_data_dir()
        logger.info(
            "冻结进程未设置 %s（或旧名 %s），数据目录: %s",
            PLOTPILOT_PROD_DATA_DIR_ENV,
            _LEGACY_PROD_DATA_DIR_ENV,
            p,
        )
        # 曾错误地把库存放在 PyInstaller _internal/data 的用户会看到空库，提示手动迁移或设环境变量
        legacy_aitext = PLOTPILOT_ROOT / "data" / "aitext.db"
        legacy_plot = PLOTPILOT_ROOT / "data" / "plotpilot.db"
        target_has = (p / "plotpilot.db").is_file() or (p / "aitext.db").is_file()
        for legacy_db in (legacy_aitext, legacy_plot):
            if legacy_db.is_file() and not target_has:
                logger.warning(
                    "发现旧数据文件 %s，而当前默认目录尚无 plotpilot.db / aitext.db。"
                    "若需沿用旧库，请将其中数据复制到 %s，或启动时设置环境变量 %s 指向旧库的父目录。",
                    legacy_db,
                    p,
                    PLOTPILOT_PROD_DATA_DIR_ENV,
                )
                break
    else:
        p = PLOTPILOT_ROOT / "data"
    p.mkdir(parents=True, exist_ok=True)
    return p


DATA_DIR = _resolve_data_dir()


def get_db_path() -> str:
    """获取数据库文件路径

    默认使用 ``plotpilot.db``；若仅有旧版 ``aitext.db`` 则继续沿用，避免静默新建空库。
    """
    primary = DATA_DIR / "plotpilot.db"
    legacy = DATA_DIR / "aitext.db"
    if primary.is_file():
        return str(primary)
    if legacy.is_file():
        return str(legacy)
    return str(primary)
