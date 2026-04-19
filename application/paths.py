"""仓库内路径（不依赖进程当前工作目录）。"""
from __future__ import annotations

import os
from pathlib import Path

# application/paths.py → 仓库根目录 aitext/
AITEXT_ROOT = Path(__file__).resolve().parents[1]

# 环境变量名：由 Tauri 生产构建在启动 Python 子进程时注入，指向用户可写目录（如 AppData）
AITEXT_PROD_DATA_DIR_ENV = "AITEXT_PROD_DATA_DIR"


def _resolve_data_dir() -> Path:
    """
    解析持久化数据根目录。

    - 若设置 AITEXT_PROD_DATA_DIR：桌面安装版，使用用户数据目录（由 Rust 注入）。
    - 否则：本地开发 / CLI，使用仓库内 data/。
    """
    raw = os.environ.get(AITEXT_PROD_DATA_DIR_ENV, "").strip()
    if raw:
        p = Path(raw).expanduser().resolve()
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
