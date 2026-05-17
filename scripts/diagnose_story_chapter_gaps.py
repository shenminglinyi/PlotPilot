"""诊断 story_nodes 幕区间与 chapters 表章号是否连续（章号断层核对）。"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

# 允许显式传入库路径；否则与 get_db_path 一致：plotpilot.db 优先，否则 aitext.db
ROOT = Path(__file__).resolve().parents[1]


def _resolve_db_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).expanduser().resolve()
    data = ROOT / "data"
    primary = data / "plotpilot.db"
    legacy = data / "aitext.db"
    if primary.is_file():
        return primary
    if legacy.is_file():
        return legacy
    return primary


def main() -> None:
    db_path = _resolve_db_path()
    if not db_path.is_file():
        print(f"No database at {db_path}")
        sys.exit(1)
    print(f"Database: {db_path}\n")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    novels = cur.execute("SELECT id, title FROM novels ORDER BY updated_at DESC LIMIT 50").fetchall()
    print(f"=== novels ({len(novels)}) ===\n")

    for novel in novels:
        nid = novel["id"]
        title = novel["title"]
        print(f"--- {nid} | {title!r} ---")

        acts = cur.execute(
            """
            SELECT id, node_type, number, title, chapter_start, chapter_end, order_index
            FROM story_nodes
            WHERE novel_id = ? AND node_type = 'act'
            ORDER BY order_index, number
            """,
            (nid,),
        ).fetchall()

        if acts:
            prev_end: int | None = None
            act_gaps: list[tuple[int, int, int]] = []
            for a in acts:
                cs, ce = a["chapter_start"], a["chapter_end"]
                print(
                    f"  act#{a['number']} order={a['order_index']}: "
                    f"{a['title']!r}  chapter_start-end={cs}-{ce}"
                )
                if cs is not None and ce is not None and prev_end is not None:
                    if cs > prev_end + 1:
                        act_gaps.append((prev_end + 1, cs - 1, a["number"]))
                if ce is not None:
                    prev_end = ce
            if act_gaps:
                print(
                    "  [!] GAPS between consecutive act ranges (unassigned chapter numbers):"
                )
                for lo, hi, act_after in act_gaps:
                    if lo == hi:
                        print(f"      missing ch {lo} (before act#{act_after})")
                    else:
                        print(f"      missing ch {lo}-{hi} (before act#{act_after})")
        else:
            print("  (no act nodes)")

        chaps = cur.execute(
            "SELECT number, status FROM chapters WHERE novel_id = ? ORDER BY number",
            (nid,),
        ).fetchall()
        if chaps:
            nums = [c["number"] for c in chaps]
            print(f"  chapters table: {len(chaps)} rows, numbers {min(nums)}..{max(nums)}")
            gaps: list[int] = []
            for i in range(len(nums) - 1):
                if nums[i + 1] - nums[i] > 1:
                    for g in range(nums[i] + 1, nums[i + 1]):
                        gaps.append(g)
            if gaps:
                print(f"  [!] GAPS in chapters.number sequence: {gaps}")
            else:
                print("  chapters.number: contiguous")
        else:
            print("  (no chapters rows)")
        print()

    conn.close()


if __name__ == "__main__":
    main()
