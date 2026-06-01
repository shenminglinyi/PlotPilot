"""Bible 快照状态采集。

该模块只采集 Bible 结构化状态，不读取章节正文。Snapshot / Checkpoint
共同使用这里的确定性采集逻辑，避免各自维护一份“存在性占位”的简化状态。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def collect_bible_snapshot_state(db: Any, novel_id: str) -> Dict[str, Any]:
    """从持久化层采集可序列化 Bible 状态。

    返回值保持轻量：包含 Bible 元数据、角色/世界/地点/时间线/风格笔记等结构化
    信息，不包含章节正文。若当前数据库还没有 Bible 表或该作品尚未创建 Bible，
    返回 ``exists=False`` 的明确状态，而不是伪造存在。
    """

    captured_at = _now_iso()
    try:
        bible = _fetch_one(
            db,
            """
            SELECT id, schema_version, extensions, created_at, updated_at
            FROM bibles
            WHERE novel_id = ?
            """,
            (novel_id,),
        )
    except Exception as exc:
        logger.warning("Bible 状态采集不可用 novel=%s: %s", novel_id, exc)
        return {
            "exists": False,
            "captured_at": captured_at,
            "source": "database_unavailable",
        }

    if not bible:
        return {
            "exists": False,
            "captured_at": captured_at,
            "source": "bible_tables",
        }

    state = {
        "exists": True,
        "captured_at": captured_at,
        "source": "bible_tables",
        "bible_id": bible.get("id", ""),
        "schema_version": bible.get("schema_version") or 1,
        "extensions": _loads(bible.get("extensions"), {}),
        "created_at": bible.get("created_at") or "",
        "updated_at": bible.get("updated_at") or "",
        "characters": _characters(db, novel_id),
        "world_settings": _world_settings(db, novel_id),
        "locations": _locations(db, novel_id),
        "timeline_notes": _timeline_notes(db, novel_id),
        "style_notes": _style_notes(db, novel_id),
    }
    state["summary"] = {
        "characters": len(state["characters"]),
        "world_settings": len(state["world_settings"]),
        "locations": len(state["locations"]),
        "timeline_notes": len(state["timeline_notes"]),
        "style_notes": len(state["style_notes"]),
    }
    return state


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_one(db: Any, sql: str, params: tuple[Any, ...]) -> Dict[str, Any] | None:
    if hasattr(db, "fetch_one"):
        row = db.fetch_one(sql, params)
    else:
        cursor = db.execute(sql, params)
        row = cursor.fetchone()
    return _row_to_dict(row) if row else None


def _fetch_all(db: Any, sql: str, params: tuple[Any, ...]) -> List[Dict[str, Any]]:
    if hasattr(db, "fetch_all"):
        rows = db.fetch_all(sql, params)
    else:
        cursor = db.execute(sql, params)
        rows = cursor.fetchall()
    return [_row_to_dict(row) for row in rows]


def _row_to_dict(row: Any) -> Dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    try:
        return dict(row)
    except TypeError:
        keys = getattr(row, "keys", lambda: [])()
        return {key: row[key] for key in keys}


def _loads(raw: Any, default: Any) -> Any:
    if raw is None or raw == "":
        return default
    if isinstance(raw, type(default)):
        return raw
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default
    return value if isinstance(value, type(default)) else default


def _characters(db: Any, novel_id: str) -> List[Dict[str, Any]]:
    rows = _fetch_all(
        db,
        """
        SELECT id, name, description, public_profile, hidden_profile, reveal_chapter,
               role, verbal_tic, idle_behavior, voice_style, sentence_pattern,
               speech_tempo, core_belief, moral_taboos_json, active_wounds_json,
               mental_state, mental_state_reason, current_state_summary,
               last_updated_chapter, updated_at
        FROM unified_characters
        WHERE novel_id = ?
        ORDER BY id
        """,
        (novel_id,),
    )
    return [
        {
            "id": row.get("id") or "",
            "name": row.get("name") or "",
            "description": row.get("description") or "",
            "public_profile": row.get("public_profile") or "",
            "hidden_profile": row.get("hidden_profile") or "",
            "reveal_chapter": row.get("reveal_chapter"),
            "role": row.get("role") or "",
            "verbal_tic": row.get("verbal_tic") or "",
            "idle_behavior": row.get("idle_behavior") or "",
            "voice_profile": {
                key: value
                for key, value in {
                    "style": row.get("voice_style") or "",
                    "sentence_pattern": row.get("sentence_pattern") or "",
                    "speech_tempo": row.get("speech_tempo") or "",
                }.items()
                if value
            },
            "core_belief": row.get("core_belief") or "",
            "moral_taboos": _loads(row.get("moral_taboos_json"), []),
            "active_wounds": _loads(row.get("active_wounds_json"), []),
            "mental_state": row.get("mental_state") or "NORMAL",
            "mental_state_reason": row.get("mental_state_reason") or "",
            "current_state_summary": row.get("current_state_summary") or "",
            "last_updated_chapter": row.get("last_updated_chapter") or 0,
            "updated_at": row.get("updated_at") or "",
        }
        for row in rows
    ]


def _world_settings(db: Any, novel_id: str) -> List[Dict[str, Any]]:
    rows = _fetch_all(
        db,
        """
        SELECT id, name, description, setting_type, updated_at
        FROM bible_world_settings
        WHERE novel_id = ?
        ORDER BY id
        """,
        (novel_id,),
    )
    return [
        {
            "id": row.get("id") or "",
            "name": row.get("name") or "",
            "description": row.get("description") or "",
            "setting_type": row.get("setting_type") or "other",
            "updated_at": row.get("updated_at") or "",
        }
        for row in rows
    ]


def _locations(db: Any, novel_id: str) -> List[Dict[str, Any]]:
    rows = _fetch_all(
        db,
        """
        SELECT id, name, description, location_type, parent_id, updated_at
        FROM bible_locations
        WHERE novel_id = ?
        ORDER BY id
        """,
        (novel_id,),
    )
    return [
        {
            "id": row.get("id") or "",
            "name": row.get("name") or "",
            "description": row.get("description") or "",
            "location_type": row.get("location_type") or "other",
            "parent_id": row.get("parent_id"),
            "updated_at": row.get("updated_at") or "",
        }
        for row in rows
    ]


def _timeline_notes(db: Any, novel_id: str) -> List[Dict[str, Any]]:
    rows = _fetch_all(
        db,
        """
        SELECT id, event, time_point, description, sort_order, updated_at
        FROM bible_timeline_notes
        WHERE novel_id = ?
        ORDER BY sort_order, id
        """,
        (novel_id,),
    )
    return [
        {
            "id": row.get("id") or "",
            "event": row.get("event") or "",
            "time_point": row.get("time_point") or "",
            "description": row.get("description") or "",
            "sort_order": row.get("sort_order") or 0,
            "updated_at": row.get("updated_at") or "",
        }
        for row in rows
    ]


def _style_notes(db: Any, novel_id: str) -> List[Dict[str, Any]]:
    rows = _fetch_all(
        db,
        """
        SELECT id, category, content, updated_at
        FROM bible_style_notes
        WHERE novel_id = ?
        ORDER BY id
        """,
        (novel_id,),
    )
    return [
        {
            "id": row.get("id") or "",
            "category": row.get("category") or "",
            "content": row.get("content") or "",
            "updated_at": row.get("updated_at") or "",
        }
        for row in rows
    ]
