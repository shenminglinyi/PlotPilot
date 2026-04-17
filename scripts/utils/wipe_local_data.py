"""清空本地 SQLite 中所有业务表（保留表结构）。请先停止占用 aitext.db 的后端进程。"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from application.paths import DATA_DIR, get_db_path  # noqa: E402


def main() -> int:
    path = get_db_path()
    try:
        conn = sqlite3.connect(path)
    except sqlite3.Error as e:
        print(f"无法打开数据库 {path}: {e}", file=sys.stderr)
        return 1

    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    tables = [r[0] for r in cur.fetchall()]
    conn.execute("PRAGMA foreign_keys=OFF")
    for t in tables:
        cur.execute('DELETE FROM [t]')
    conn.commit()
    try:
        conn.execute("VACUUM")
    except sqlite3.Error:
        pass
    conn.close()
    print(f"已清空 {len(tables)} 张表: {path}")

    # 文件型缓存（Cast 图、旧 Bible 快照、旧伏笔 JSON）
    for sub in ("bibles", "foreshadowings"):
        d = DATA_DIR / sub
        if d.is_dir():
            for f in d.iterdir():
                if f.is_file():
                    f.unlink()
            print(f"已删除 {d} 下文件")

    novels_dir = DATA_DIR / "novels"
    if novels_dir.is_dir():
        shutil.rmtree(novels_dir, ignore_errors=True)
        print(f"已删除目录 {novels_dir}（含 cast_graph 等）")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
