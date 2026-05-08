"""双螺旋编年史 BFF：剧情时间线（Bible）× 语义快照（novel_snapshots）按 chapter_index 拉链聚合。

🔥 核心架构优化：纯内存读取，纳秒级响应，永不阻塞事件循环。

所有数据都从共享内存读取，完全不走 DB。
🔥 v2：不再读共享内存的空 chronicles 缓存 key，
改为实时从 Bible timeline_notes + snapshots + chapters 聚合，
保证数据与最新 Bible 内容同步。
"""
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/novels", tags=["chronicles"])

_CHAPTER_IN_TEXT = re.compile(r"第\s*(\d+)\s*章")


# ── Pydantic 响应模型 ────────────────────────────────────────

class StoryEventItem(BaseModel):
    note_id: str
    time: str
    title: str
    description: str
    source_chapter: Optional[int] = None


class SnapshotItem(BaseModel):
    id: str
    kind: str = Field(..., description="AUTO / MANUAL")
    name: str
    branch_name: str = "main"
    created_at: Optional[str] = None
    description: Optional[str] = None
    anchor_chapter: Optional[int] = None


class ChronicleRow(BaseModel):
    chapter_index: int
    story_events: List[StoryEventItem] = Field(default_factory=list)
    snapshots: List[SnapshotItem] = Field(default_factory=list)


class ChroniclesResponse(BaseModel):
    rows: List[ChronicleRow]
    max_chapter_in_book: int
    note: str = (
        "剧情节点来自共享内存（Bible.timeline_notes）；快照来自共享内存。"
        "chapter_index 由「第N章」文案或快照内章节指针推断。"
    )


# ── 实时聚合工具 ────────────────────────────────────────────

def _infer_chapter_from_texts(*parts: str) -> Optional[int]:
    """从文本中推断章节号（「第N章」）"""
    for p in parts:
        if not p:
            continue
        m = _CHAPTER_IN_TEXT.search(p)
        if m:
            return int(m.group(1))
    return None


def _build_chronicles_rows(
    timeline_notes: List[Dict[str, Any]],
    snapshots: List[Dict[str, Any]],
    id_to_number: Dict[str, int],
) -> List[Dict[str, Any]]:
    """按 chapter_index 拉链聚合 Bible timeline_notes + snapshots。

    纯内存操作，纳秒级，不阻塞事件循环。
    """
    max_num = max(id_to_number.values(), default=1)
    snap_fallback = max_num if max_num >= 1 else 1

    buckets: Dict[int, Dict[str, List]] = {}

    def ensure(ch: int) -> Dict[str, List]:
        if ch not in buckets:
            buckets[ch] = {"story_events": [], "snapshots": []}
        return buckets[ch]

    # 聚合 Bible timeline_notes
    for idx, note in enumerate(timeline_notes):
        tp = note.get("time_point", "") or note.get("time", "")
        ev = note.get("event", "") or note.get("title", "")
        desc = note.get("description", "")
        nid = note.get("id", f"tn-{idx}")
        inferred = _infer_chapter_from_texts(tp, ev, desc)
        ch = inferred if inferred is not None else idx + 1
        ch = max(1, ch)
        ensure(ch)["story_events"].append({
            "note_id": nid,
            "time": (tp or "").strip() or "（未标注时间）",
            "title": (ev or "").strip(),
            "description": (desc or "").strip(),
            "source_chapter": inferred,
        })

    # 聚合 snapshots
    for snap in snapshots:
        ptrs = snap.get("chapter_pointers") or []
        if not isinstance(ptrs, list):
            ptrs = []
        # 推断快照锚定章节
        anchor = None
        ptr_nums = [id_to_number[str(x)] for x in ptrs if str(x) in id_to_number]
        if ptr_nums:
            anchor = max(ptr_nums)
        ch = anchor if anchor is not None else snap_fallback
        ch = max(1, ch)
        ensure(ch)["snapshots"].append({
            "id": snap.get("id", ""),
            "kind": snap.get("trigger_type") or snap.get("kind", "AUTO"),
            "name": snap.get("name", ""),
            "branch_name": snap.get("branch_name", "main"),
            "created_at": snap.get("created_at"),
            "description": (snap.get("description") or "").strip() or None,
            "anchor_chapter": anchor,
        })

    if not buckets:
        return []

    out: List[Dict[str, Any]] = []
    for ch in sorted(buckets.keys()):
        b = buckets[ch]
        out.append({
            "chapter_index": ch,
            "story_events": b["story_events"],
            "snapshots": b["snapshots"],
        })
    return out


# ── API 端点 ────────────────────────────────────────────────

@router.get("/{novel_id}/chronicles", response_model=ChroniclesResponse)
async def get_chronicles(novel_id: str) -> ChroniclesResponse:
    """获取编年史数据。

    🔥 v2：实时从共享内存的 Bible timeline_notes + snapshots + chapters 聚合，
    纯内存操作，纳秒级响应，永不阻塞事件循环。
    """
    from application.engine.services.query_service import get_query_service

    query = get_query_service()

    # 检查小说是否存在
    novel_status = query.get_novel_status(novel_id)
    if novel_status is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")

    # 从共享内存获取原始数据（全部走内存，零 DB IO）
    bible = query.get_bible(novel_id) or {}
    snapshots_raw = query.get_snapshots(novel_id) or []
    chapters = query.get_chapters(novel_id)

    # 计算 max chapter
    max_ch = max((c.get("number", 0) for c in chapters), default=1)

    # 构建 chapter_id → chapter_number 映射（快照 chapter_pointers 用）
    id_to_number: Dict[str, int] = {}
    for c in chapters:
        cid = c.get("id", "")
        cnum = c.get("number", 0)
        if cid and cnum:
            id_to_number[cid] = cnum

    # 提取 Bible timeline_notes
    timeline_notes = bible.get("timeline_notes", []) if isinstance(bible, dict) else []

    # 🔥 实时聚合
    chronicle_rows = _build_chronicles_rows(timeline_notes, snapshots_raw, id_to_number)

    # 构建响应
    rows: List[ChronicleRow] = []
    for r in chronicle_rows:
        rows.append(
            ChronicleRow(
                chapter_index=r.get("chapter_index", 0),
                story_events=[
                    StoryEventItem(
                        note_id=e.get("note_id", ""),
                        time=e.get("time", ""),
                        title=e.get("title", ""),
                        description=e.get("description", ""),
                        source_chapter=e.get("source_chapter"),
                    )
                    for e in r.get("story_events", [])
                ],
                snapshots=[
                    SnapshotItem(
                        id=s.get("id", ""),
                        kind=s.get("kind", "AUTO"),
                        name=s.get("name", ""),
                        branch_name=s.get("branch_name", "main"),
                        created_at=s.get("created_at"),
                        description=s.get("description"),
                        anchor_chapter=s.get("anchor_chapter"),
                    )
                    for s in r.get("snapshots", [])
                ],
            )
        )

    return ChroniclesResponse(rows=rows, max_chapter_in_book=max_ch)
