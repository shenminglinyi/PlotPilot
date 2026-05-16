"""章节保存后：零 token 重建手稿实体提及索引。"""
from __future__ import annotations

import json
import logging
from typing import List, Tuple

from domain.novel.value_objects.novel_id import NovelId

from application.manuscript.services.entity_mention_indexer import collect_chapter_entity_rows
from infrastructure.persistence.database.connection import get_database
from infrastructure.persistence.database.manuscript_entity_repository import ManuscriptEntityRepository
from infrastructure.persistence.database.sqlite_bible_repository import SqliteBibleRepository

logger = logging.getLogger(__name__)


def reindex_chapter_entity_mentions(novel_id: str, chapter_number: int, content: str) -> None:
    try:
        db = get_database()
        bible_repo = SqliteBibleRepository(db)
        mrepo = ManuscriptEntityRepository(db)
        bible = bible_repo.get_by_novel_id(NovelId(novel_id))

        # Bible 不存在时，角色/地点留空，道具索引照常运行（不整体跳过）
        chars: List[Tuple[str, str, List[str]]] = []
        locs: List[Tuple[str, str, str, List[str]]] = []
        if bible:
            chars = [
                (c.character_id.value, c.name, []) for c in bible.characters
            ]
            locs = [
                (loc.id, loc.name, getattr(loc, "location_type", None) or "other", [])
                for loc in bible.locations
            ]

        props_rows = mrepo.list_props(novel_id)
        props: List[Tuple[str, str, List[str]]] = []
        for p in props_rows:
            aliases: list = []
            try:
                aliases = json.loads(p.get("aliases_json") or "[]")
            except json.JSONDecodeError:
                aliases = []
            props.append((p["id"], p["name"], aliases if isinstance(aliases, list) else []))

        rows = collect_chapter_entity_rows(
            content, characters=chars, locations=locs, props=props
        )
        mrepo.replace_chapter_mentions(novel_id, chapter_number, rows)
    except Exception as e:
        logger.warning("reindex chapter entities failed novel=%s ch=%s: %s", novel_id, chapter_number, e)
