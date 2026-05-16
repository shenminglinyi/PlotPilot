"""SQLite Knowledge Repository — 三元组扩展字段用子表，库内不存 JSON 文本列。"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from domain.novel.value_objects.novel_id import NovelId
from domain.knowledge.story_knowledge import StoryKnowledge
from domain.knowledge.chapter_summary import ChapterSummary
from domain.knowledge.knowledge_triple import KnowledgeTriple
from infrastructure.persistence.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)


# 事务内 execute 接口：sqlite3.Connection 与 write_dispatch.TxnCollectingConnection 对齐
_SqlExec = Any


def _dedupe_provenance_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """同一批内按 (triple_id, rule_id, story_node, element) 去重。"""
    seen: set[Tuple[Any, ...]] = set()
    out: List[Dict[str, Any]] = []
    for r in rows:
        key = (
            r.get("triple_id"),
            r.get("rule_id"),
            r.get("story_node_id"),
            r.get("chapter_element_id"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


class SqliteKnowledgeRepository:
    """知识图谱与章节摘要（关系化存储）。"""

    def __init__(self, db: DatabaseConnection):
        self.db = db

    def save_knowledge(self, novel_id: str, premise_lock: str = "") -> None:
        sql = """
            INSERT INTO knowledge (id, novel_id, version, premise_lock, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(novel_id) DO UPDATE SET
                premise_lock = excluded.premise_lock,
                updated_at = excluded.updated_at
        """
        now = datetime.utcnow().isoformat()
        knowledge_id = f"{novel_id}-knowledge"
        self.db.execute(sql, (knowledge_id, novel_id, 1, premise_lock, now, now))

    def _load_triple_children(self, novel_id: str) -> tuple[
        Dict[str, List[int]], Dict[str, List[str]], Dict[str, Dict[str, str]]
    ]:
        more: Dict[str, List[int]] = defaultdict(list)
        rows_m = self.db.fetch_all(
            """
            SELECT tmc.triple_id, tmc.chapter_number
            FROM triple_more_chapters tmc
            JOIN triples t ON t.id = tmc.triple_id AND t.novel_id = ?
            ORDER BY tmc.chapter_number
            """,
            (novel_id,),
        )
        for r in rows_m:
            more[r["triple_id"]].append(int(r["chapter_number"]))

        tags: Dict[str, List[str]] = defaultdict(list)
        rows_t = self.db.fetch_all(
            """
            SELECT tt.triple_id, tt.tag
            FROM triple_tags tt
            JOIN triples t ON t.id = tt.triple_id AND t.novel_id = ?
            ORDER BY tt.tag
            """,
            (novel_id,),
        )
        for r in rows_t:
            tags[r["triple_id"]].append(r["tag"])

        attrs: Dict[str, Dict[str, str]] = defaultdict(dict)
        rows_a = self.db.fetch_all(
            """
            SELECT ta.triple_id, ta.attr_key, ta.attr_value
            FROM triple_attr ta
            JOIN triples t ON t.id = ta.triple_id AND t.novel_id = ?
            """,
            (novel_id,),
        )
        for r in rows_a:
            attrs[r["triple_id"]][r["attr_key"]] = r["attr_value"]

        return dict(more), dict(tags), dict(attrs)

    def _load_provenance_grouped(self, novel_id: str) -> Dict[str, List[Dict[str, Any]]]:
        rows = self.db.fetch_all(
            """
            SELECT id, triple_id, story_node_id, chapter_element_id, rule_id, role
            FROM triple_provenance
            WHERE novel_id = ?
            ORDER BY created_at ASC
            """,
            (novel_id,),
        )
        out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for r in rows:
            out[r["triple_id"]].append(
                {
                    "id": r["id"],
                    "story_node_id": r["story_node_id"],
                    "chapter_element_id": r["chapter_element_id"],
                    "rule_id": r["rule_id"],
                    "role": r["role"],
                }
            )
        return dict(out)

    @staticmethod
    def _sanitize_fact_dict_for_write(triple: Dict[str, Any]) -> Dict[str, Any]:
        t = dict(triple)
        t.pop("provenance", None)
        return t

    @staticmethod
    def _delete_triples_for_merge(exe: _SqlExec, novel_id: str, payload_ids: Set[str]) -> None:
        """删除「可被合并覆盖」且不在 payload 中的三元组；保留推断/Bible/AI 来源。"""
        if payload_ids:
            placeholders = ",".join("?" * len(payload_ids))
            exe.execute(
                f"""
                DELETE FROM triples
                WHERE novel_id = ?
                  AND id NOT IN ({placeholders})
                  AND (
                    source_type IS NULL
                    OR TRIM(source_type) = ''
                    OR source_type NOT IN ('chapter_inferred', 'bible_generated', 'ai_generated')
                  )
                """,
                (novel_id, *tuple(payload_ids)),
            )
        else:
            exe.execute(
                """
                DELETE FROM triples
                WHERE novel_id = ?
                  AND (
                    source_type IS NULL
                    OR TRIM(source_type) = ''
                    OR source_type NOT IN ('chapter_inferred', 'bible_generated', 'ai_generated')
                  )
                """,
                (novel_id,),
            )

    def _replace_triple_provenance(
        self, exe: _SqlExec, rows: List[Dict[str, Any]]
    ) -> None:
        if not rows:
            return
        exe.execute("DELETE FROM triple_provenance WHERE triple_id = ?", (rows[0]["triple_id"],))
        for r in _dedupe_provenance_rows(rows):
            exe.execute(
                """
                INSERT OR IGNORE INTO triple_provenance (
                    id, triple_id, novel_id, story_node_id, chapter_element_id, rule_id, role
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    r["id"],
                    r["triple_id"],
                    r["novel_id"],
                    r.get("story_node_id"),
                    r.get("chapter_element_id"),
                    r["rule_id"],
                    r.get("role") or "primary",
                ),
            )

    def _append_triple_provenance(
        self, exe: _SqlExec, rows: List[Dict[str, Any]]
    ) -> None:
        for r in _dedupe_provenance_rows(rows):
            exe.execute(
                """
                INSERT OR IGNORE INTO triple_provenance (
                    id, triple_id, novel_id, story_node_id, chapter_element_id, rule_id, role
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    r["id"],
                    r["triple_id"],
                    r["novel_id"],
                    r.get("story_node_id"),
                    r.get("chapter_element_id"),
                    r["rule_id"],
                    r.get("role") or "primary",
                ),
            )

    def get_triple_side_data_for_novel(self, novel_id: str) -> tuple[
        dict[str, list[int]], dict[str, list[str]], dict[str, dict[str, str]]
    ]:
        """供 TripleRepository 等与 triples 子表对齐的读取。"""
        return self._load_triple_children(novel_id)

    def _build_facts_from_triple_rows(
        self, novel_id_str: str, triples_rows: List[Any]
    ) -> List[KnowledgeTriple]:
        if not triples_rows:
            return []
        more, tags, attrs = self._load_triple_children(novel_id_str)
        prov_by_triple = self._load_provenance_grouped(novel_id_str)
        facts: List[KnowledgeTriple] = []
        for row in triples_rows:
            tid = row["id"]
            facts.append(
                KnowledgeTriple(
                    id=tid,
                    subject=row["subject"],
                    predicate=row["predicate"],
                    object=row["object"],
                    chapter_id=row["chapter_number"],
                    note=row["note"] or "",
                    entity_type=row.get("entity_type"),
                    importance=row.get("importance"),
                    location_type=row.get("location_type"),
                    description=row.get("description"),
                    first_appearance=row.get("first_appearance"),
                    related_chapters=list(more.get(tid, [])),
                    tags=tags.get(tid, []),
                    attributes=dict(attrs.get(tid, {})),
                    confidence=row["confidence"] if row.get("confidence") is not None else None,
                    source_type=row.get("source_type"),
                    subject_entity_id=row.get("subject_entity_id"),
                    object_entity_id=row.get("object_entity_id"),
                    provenance=list(prov_by_triple.get(tid, [])),
                )
            )
        return facts

    def get_by_novel_id(self, novel_id: NovelId) -> Optional[StoryKnowledge]:
        novel_id_str = novel_id.value if hasattr(novel_id, "value") else novel_id

        triples_sql = """
            SELECT id, subject, predicate, object, chapter_number, note,
                   entity_type, importance, location_type, description, first_appearance,
                   confidence, source_type, subject_entity_id, object_entity_id
            FROM triples
            WHERE novel_id = ?
            ORDER BY created_at ASC
        """
        triples_rows = self.db.fetch_all(triples_sql, (novel_id_str,))
        facts = self._build_facts_from_triple_rows(novel_id_str, triples_rows)

        knowledge = self.db.fetch_one("SELECT * FROM knowledge WHERE novel_id = ?", (novel_id_str,))
        if not knowledge:
            # 尚无 knowledge 行但已有 triples（如仅 Bible 地点同步写入）时仍返回事实，供 GET/可视化编辑
            if not facts:
                return None
            return StoryKnowledge(
                novel_id=novel_id_str,
                version=1,
                premise_lock="",
                chapters=[],
                facts=facts,
            )

        summaries_sql = """
            SELECT chapter_number, summary, key_events, open_threads, 
                   consistency_note, beat_sections, micro_beats, sync_status
            FROM chapter_summaries
            WHERE knowledge_id = ?
            ORDER BY chapter_number ASC
        """
        summaries_rows = self.db.fetch_all(summaries_sql, (knowledge["id"],))

        import json
        chapters = []
        for row in summaries_rows:
            # 解析JSON字段
            beat_sections = []
            micro_beats = []
            try:
                if row["beat_sections"]:
                    beat_sections = json.loads(row["beat_sections"])
                if row["micro_beats"]:
                    micro_beats = json.loads(row["micro_beats"])
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("解析节拍数据失败: %s", e)
            
            chapters.append(ChapterSummary(
                chapter_id=row["chapter_number"],
                summary=row["summary"] or "",
                key_events=row["key_events"] or "",
                open_threads=row["open_threads"] or "",
                consistency_note=row["consistency_note"] or "",
                beat_sections=beat_sections,
                micro_beats=micro_beats,
                sync_status=row["sync_status"] or "synced",
            ))

        return StoryKnowledge(
            novel_id=novel_id_str,
            version=knowledge["version"],
            premise_lock=knowledge["premise_lock"] or "",
            chapters=chapters,
            facts=facts,
        )

    @staticmethod
    def _chapter_number_from_fact(triple: Dict[str, Any]) -> Optional[int]:
        v = triple.get("chapter_number")
        if v is None:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    def _insert_triple_children(
        self,
        exe: _SqlExec,
        novel_id: str,
        triple_id: str,
        triple: Dict[str, Any],
        primary_chapter: Optional[int],
    ) -> None:
        seen: set[int] = set()
        for cn in triple.get("related_chapters") or []:
            try:
                n = int(cn)
            except (TypeError, ValueError):
                continue
            if primary_chapter is not None and n == primary_chapter:
                continue
            if n in seen:
                continue
            seen.add(n)
            exe.execute(
                """
                INSERT OR IGNORE INTO triple_more_chapters (triple_id, novel_id, chapter_number)
                VALUES (?, ?, ?)
                """,
                (triple_id, novel_id, n),
            )

        for tag in triple.get("tags") or []:
            if not tag:
                continue
            exe.execute(
                "INSERT OR IGNORE INTO triple_tags (triple_id, tag) VALUES (?, ?)",
                (triple_id, str(tag)),
            )

        for k, v in (triple.get("attributes") or {}).items():
            exe.execute(
                """
                INSERT INTO triple_attr (triple_id, attr_key, attr_value)
                VALUES (?, ?, ?)
                ON CONFLICT(triple_id, attr_key) DO UPDATE SET
                    attr_value = excluded.attr_value
                """,
                (triple_id, str(k), "" if v is None else str(v)),
            )

    @staticmethod
    def _clear_triple_children(exe: _SqlExec, triple_id: str) -> None:
        exe.execute("DELETE FROM triple_more_chapters WHERE triple_id = ?", (triple_id,))
        exe.execute("DELETE FROM triple_tags WHERE triple_id = ?", (triple_id,))
        exe.execute("DELETE FROM triple_attr WHERE triple_id = ?", (triple_id,))

    def _insert_triple_row(
        self,
        exe: _SqlExec,
        novel_id: str,
        triple: Dict[str, Any],
        now: str,
    ) -> None:
        self._clear_triple_children(exe, triple["id"])
        ch = self._chapter_number_from_fact(triple)
        exe.execute(
            """
            INSERT INTO triples (
                id, novel_id, subject, predicate, object, chapter_number, note,
                entity_type, importance, location_type, description, first_appearance,
                confidence, source_type, subject_entity_id, object_entity_id,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                subject = excluded.subject,
                predicate = excluded.predicate,
                object = excluded.object,
                chapter_number = excluded.chapter_number,
                note = excluded.note,
                entity_type = excluded.entity_type,
                importance = excluded.importance,
                location_type = excluded.location_type,
                description = excluded.description,
                first_appearance = excluded.first_appearance,
                confidence = excluded.confidence,
                source_type = excluded.source_type,
                subject_entity_id = excluded.subject_entity_id,
                object_entity_id = excluded.object_entity_id,
                updated_at = excluded.updated_at
            """,
            (
                triple["id"],
                novel_id,
                triple["subject"],
                triple["predicate"],
                triple["object"],
                ch,
                triple.get("note", ""),
                triple.get("entity_type"),
                triple.get("importance"),
                triple.get("location_type"),
                triple.get("description"),
                triple.get("first_appearance"),
                triple.get("confidence"),
                triple.get("source_type"),
                triple.get("subject_entity_id"),
                triple.get("object_entity_id"),
                now,
                now,
            ),
        )
        self._insert_triple_children(exe, novel_id, triple["id"], triple, ch)

    def save_triple(
        self,
        novel_id: str,
        triple: dict,
        *,
        provenance_rows: Optional[List[Dict[str, Any]]] = None,
        provenance_mode: str = "skip",
    ) -> None:
        now = datetime.utcnow().isoformat()
        with self.db.transaction() as exe:
            self._insert_triple_row(exe, novel_id, triple, now)
            if provenance_rows and provenance_mode == "replace":
                self._replace_triple_provenance(exe, provenance_rows)
            elif provenance_rows and provenance_mode == "append":
                self._append_triple_provenance(exe, provenance_rows)

    def save_triples_batch(
        self,
        novel_id: str,
        triples: List[dict],
        *,
        batch_size: int = 50,
        provenance_rows_map: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> None:
        """批量保存三元组，拆分为 micro-transactions 避免长事务锁表。

        🔥 关键优化：将大批量 INSERT 拆分为多次小批量提交，
        每批之间主动释放 DB 锁，允许 API 进程的读请求"插队"。

        Args:
            novel_id: 小说 ID
            triples: 三元组字典列表
            batch_size: 每批提交数量，默认 50
            provenance_rows_map: triple_id -> provenance_rows 的映射
        """
        import time

        now = datetime.utcnow().isoformat()
        total = len(triples)
        if total == 0:
            return

        for i in range(0, total, batch_size):
            batch = triples[i:i + batch_size]
            with self.db.transaction() as exe:
                for triple in batch:
                    self._insert_triple_row(exe, novel_id, triple, now)
                    if provenance_rows_map:
                        rows = provenance_rows_map.get(triple["id"])
                        if rows:
                            self._replace_triple_provenance(exe, rows)

            # 🔥 微事务间隙主动让出时间片，允许读请求插队
            if i + batch_size < total:
                time.sleep(0.01)

    def append_triple_provenance_only(self, novel_id: str, triple_id: str, rows: List[Dict[str, Any]]) -> None:
        """仅追加溯源行（三元组行已存在）。"""
        if not rows:
            return
        with self.db.transaction() as exe:
            normalized = [
                {
                    **r,
                    "triple_id": r.get("triple_id") or triple_id,
                    "novel_id": r.get("novel_id") or novel_id,
                }
                for r in rows
            ]
            for r in _dedupe_provenance_rows(normalized):
                exe.execute(
                    """
                    INSERT OR IGNORE INTO triple_provenance (
                        id, triple_id, novel_id, story_node_id, chapter_element_id, rule_id, role
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        r["id"],
                        r["triple_id"],
                        r["novel_id"],
                        r.get("story_node_id"),
                        r.get("chapter_element_id"),
                        r["rule_id"],
                        r.get("role") or "primary",
                    ),
                )

    def find_story_node_id_for_chapter_number(
        self, novel_id: str, chapter_number: int
    ) -> Optional[str]:
        row = self.db.fetch_one(
            """
            SELECT id FROM story_nodes
            WHERE novel_id = ? AND node_type = 'chapter' AND number = ?
            LIMIT 1
            """,
            (novel_id, chapter_number),
        )
        return row["id"] if row else None

    def list_chapter_inference_evidence(
        self, novel_id: str, story_node_id: str
    ) -> List[Dict[str, Any]]:
        """本章 story_node 参与推断的 chapter_inferred 三元组及本节点下的证据行。"""
        id_rows = self.db.fetch_all(
            """
            SELECT DISTINCT t.id FROM triples t
            INNER JOIN triple_provenance p ON p.triple_id = t.id AND p.story_node_id = ?
            WHERE t.novel_id = ? AND t.source_type = 'chapter_inferred'
            ORDER BY t.created_at ASC
            """,
            (story_node_id, novel_id),
        )
        out: List[Dict[str, Any]] = []
        for r in id_rows:
            tid = r["id"]
            t = self.db.fetch_one("SELECT * FROM triples WHERE id = ?", (tid,))
            if not t:
                continue
            prov = self.db.fetch_all(
                """
                SELECT id, chapter_element_id, rule_id, role
                FROM triple_provenance
                WHERE triple_id = ? AND story_node_id = ?
                ORDER BY rule_id, role
                """,
                (tid, story_node_id),
            )
            out.append(
                {
                    "fact": {
                        "id": t["id"],
                        "subject": t["subject"],
                        "predicate": t["predicate"],
                        "object": t["object"],
                        "chapter_number": t["chapter_number"],
                        "confidence": t["confidence"],
                        "source_type": t["source_type"],
                    },
                    "provenance": [dict(p) for p in prov],
                }
            )
        return out

    def revoke_chapter_inference_for_story_node(
        self, novel_id: str, story_node_id: str
    ) -> Dict[str, int]:
        """删除本章节节点下的溯源；若无剩余证据且为 chapter_inferred 则删除三元组。

        读操作在本地连接完成，写操作合并为单事务入队（API 线程）或 writer 直连，避免跨连接无法表达 SELECT/DELETE 交错事务。
        """
        from infrastructure.persistence.database.write_dispatch import (
            allow_direct_sqlite_writes,
            enqueue_txn_batch,
            is_sqlite_writer_thread,
        )

        affected_rows = self.db.fetch_all(
            """
            SELECT DISTINCT triple_id FROM triple_provenance
            WHERE story_node_id = ? AND novel_id = ?
            """,
            (story_node_id, novel_id),
        )
        tids = [r["triple_id"] for r in affected_rows]

        ops: List[Tuple[str, tuple]] = [
            (
                "DELETE FROM triple_provenance WHERE story_node_id = ? AND novel_id = ?",
                (story_node_id, novel_id),
            )
        ]
        deleted_triples = 0
        for tid in tids:
            cnt_all = self.db.fetch_one(
                "SELECT COUNT(*) AS c FROM triple_provenance WHERE triple_id = ?",
                (tid,),
            )
            cnt_rm = self.db.fetch_one(
                """
                SELECT COUNT(*) AS c FROM triple_provenance
                WHERE triple_id = ? AND story_node_id = ? AND novel_id = ?
                """,
                (tid, story_node_id, novel_id),
            )
            n_total = int(cnt_all["c"]) if cnt_all and cnt_all.get("c") is not None else 0
            n_remove = int(cnt_rm["c"]) if cnt_rm and cnt_rm.get("c") is not None else 0
            if n_total - n_remove > 0:
                continue
            src = self.db.fetch_one(
                "SELECT source_type FROM triples WHERE id = ? AND novel_id = ?",
                (tid, novel_id),
            )
            if not src or src.get("source_type") != "chapter_inferred":
                continue
            ops.append(("DELETE FROM triples WHERE id = ?", (tid,)))
            deleted_triples += 1

        if allow_direct_sqlite_writes() or is_sqlite_writer_thread():
            conn = self.db.get_connection()
            try:
                conn.execute("BEGIN IMMEDIATE")
                for sql, params in ops:
                    conn.execute(sql, params)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            self.db.commit()
        else:
            if not enqueue_txn_batch(ops):
                raise RuntimeError("持久化队列未就绪，无法撤销章节推断溯源")

        return {
            "removed_provenance_triples": len(tids),
            "deleted_inferred_facts": deleted_triples,
        }

    def try_delete_chapter_inferred_triple(self, novel_id: str, triple_id: str) -> str:
        """删除 chapter_inferred 三元组。返回 deleted | not_found | not_inferred。"""
        row = self.db.fetch_one(
            "SELECT id, source_type FROM triples WHERE id = ? AND novel_id = ?",
            (triple_id, novel_id),
        )
        if not row:
            return "not_found"
        if row["source_type"] != "chapter_inferred":
            return "not_inferred"
        with self.db.transaction() as exe:
            exe.execute("DELETE FROM triples WHERE id = ?", (triple_id,))
        return "deleted"

    def delete_triple(self, triple_id: str) -> None:
        self.db.execute("DELETE FROM triples WHERE id = ?", (triple_id,))

    def list_triples_by_subject(self, novel_id: str, subject: str) -> List[dict]:
        sql = """
            SELECT id, subject, predicate, object, chapter_number AS chapter_id, note,
                   entity_type, importance, location_type
            FROM triples
            WHERE novel_id = ? AND subject = ?
            ORDER BY created_at ASC
        """
        return self.db.fetch_all(sql, (novel_id, subject))

    def list_triples_by_predicate(self, novel_id: str, predicate: str) -> List[dict]:
        sql = """
            SELECT id, subject, predicate, object, chapter_number AS chapter_id, note,
                   entity_type, importance, location_type
            FROM triples
            WHERE novel_id = ? AND predicate = ?
            ORDER BY created_at ASC
        """
        return self.db.fetch_all(sql, (novel_id, predicate))

    def list_triples_by_entity_type(self, novel_id: str, entity_type: str) -> List[dict]:
        sql = """
            SELECT id, subject, predicate, object, chapter_number AS chapter_id, note,
                   entity_type, importance, location_type
            FROM triples
            WHERE novel_id = ? AND entity_type = ?
            ORDER BY created_at ASC
        """
        return self.db.fetch_all(sql, (novel_id, entity_type))

    def save_chapter_summary(self, knowledge_id: str, chapter_number: int, summary: str) -> None:
        sql = """
            INSERT INTO chapter_summaries (id, knowledge_id, chapter_number, summary, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(knowledge_id, chapter_number) DO UPDATE SET
                summary = excluded.summary,
                updated_at = excluded.updated_at
        """
        now = datetime.utcnow().isoformat()
        summary_id = f"{knowledge_id}-ch{chapter_number}"
        self.db.execute(sql, (summary_id, knowledge_id, chapter_number, summary, now, now))

    def save(self, knowledge: StoryKnowledge) -> None:
        novel_id = knowledge.novel_id
        knowledge_id = f"{novel_id}-knowledge"
        now = datetime.utcnow().isoformat()

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO knowledge (id, novel_id, version, premise_lock, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(novel_id) DO UPDATE SET
                    premise_lock = excluded.premise_lock,
                    updated_at = excluded.updated_at
                """,
                (knowledge_id, novel_id, 1, knowledge.premise_lock, now, now),
            )
            payload_ids = {f.id for f in knowledge.facts if f.id}
            self._delete_triples_for_merge(conn, novel_id, payload_ids)

            for fact in knowledge.facts:
                d = {
                    "id": fact.id,
                    "subject": fact.subject,
                    "predicate": fact.predicate,
                    "object": fact.object,
                    "chapter_id": fact.chapter_id,
                    "note": fact.note,
                    "entity_type": fact.entity_type,
                    "importance": fact.importance,
                    "location_type": fact.location_type,
                    "description": fact.description,
                    "first_appearance": fact.first_appearance,
                    "related_chapters": fact.related_chapters,
                    "tags": fact.tags,
                    "attributes": fact.attributes,
                    "confidence": getattr(fact, "confidence", None),
                    "source_type": getattr(fact, "source_type", None),
                    "subject_entity_id": getattr(fact, "subject_entity_id", None),
                    "object_entity_id": getattr(fact, "object_entity_id", None),
                }
                self._insert_triple_row(conn, novel_id, d, now)

            import json as _json
            conn.execute("DELETE FROM chapter_summaries WHERE knowledge_id = ?", (knowledge_id,))
            for chapter in knowledge.chapters:
                cn = chapter.chapter_id
                summary_id = f"{knowledge_id}-ch{cn}"
                beat_sections_json = _json.dumps(
                    list(getattr(chapter, "beat_sections", None) or []), ensure_ascii=False
                )
                micro_beats_json = _json.dumps(
                    list(getattr(chapter, "micro_beats", None) or []), ensure_ascii=False
                )
                conn.execute(
                    """
                    INSERT INTO chapter_summaries
                    (id, knowledge_id, chapter_number, summary, key_events, open_threads,
                     consistency_note, beat_sections, micro_beats, sync_status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(knowledge_id, chapter_number) DO UPDATE SET
                        summary = excluded.summary,
                        key_events = excluded.key_events,
                        open_threads = excluded.open_threads,
                        consistency_note = excluded.consistency_note,
                        beat_sections = excluded.beat_sections,
                        micro_beats = excluded.micro_beats,
                        sync_status = excluded.sync_status,
                        updated_at = excluded.updated_at
                    """,
                    (
                        summary_id, knowledge_id, cn,
                        chapter.summary or "",
                        getattr(chapter, "key_events", "") or "",
                        getattr(chapter, "open_threads", "") or "",
                        getattr(chapter, "consistency_note", "") or "",
                        beat_sections_json,
                        micro_beats_json,
                        getattr(chapter, "sync_status", "draft") or "draft",
                        now, now,
                    ),
                )

        logger.info("Saved StoryKnowledge for novel: %s", novel_id)

    def save_all(self, novel_id: str, data: dict) -> None:
        logger.info("save_all called for %s, facts count: %s", novel_id, len(data.get("facts", [])))
        knowledge_id = f"{novel_id}-knowledge"
        now = datetime.utcnow().isoformat()

        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO knowledge (id, novel_id, version, premise_lock, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    premise_lock = excluded.premise_lock,
                    updated_at = excluded.updated_at
                """,
                (knowledge_id, novel_id, 1, data.get("premise_lock", ""), now, now),
            )

            raw_facts = data.get("facts", [])
            payload_ids = {f.get("id") for f in raw_facts if f.get("id")}
            self._delete_triples_for_merge(conn, novel_id, payload_ids)

            for triple in raw_facts:
                self._insert_triple_row(
                    conn, novel_id, self._sanitize_fact_dict_for_write(triple), now
                )

            conn.execute("DELETE FROM chapter_summaries WHERE knowledge_id = ?", (knowledge_id,))
            for chapter in data.get("chapters", []):
                chapter_number = chapter.get("number") or chapter.get("chapter_id")
                summary_id = f"{knowledge_id}-ch{chapter_number}"
                
                # 将节拍数据转换为JSON字符串
                import json
                beat_sections_json = json.dumps(chapter.get("beat_sections", []), ensure_ascii=False)
                micro_beats_json = json.dumps(chapter.get("micro_beats", []), ensure_ascii=False)
                
                conn.execute(
                    """
                    INSERT INTO chapter_summaries 
                    (id, knowledge_id, chapter_number, summary, key_events, open_threads, 
                     consistency_note, beat_sections, micro_beats, sync_status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(knowledge_id, chapter_number) DO UPDATE SET
                        summary = excluded.summary,
                        key_events = excluded.key_events,
                        open_threads = excluded.open_threads,
                        consistency_note = excluded.consistency_note,
                        beat_sections = excluded.beat_sections,
                        micro_beats = excluded.micro_beats,
                        sync_status = excluded.sync_status,
                        updated_at = excluded.updated_at
                    """,
                    (
                        summary_id, knowledge_id, chapter_number, 
                        chapter.get("summary", ""), chapter.get("key_events", ""),
                        chapter.get("open_threads", ""), chapter.get("consistency_note", ""),
                        beat_sections_json, micro_beats_json, 
                        chapter.get("sync_status", "draft"), now, now
                    ),
                )

        logger.info("Saved complete knowledge for novel: %s", novel_id)
