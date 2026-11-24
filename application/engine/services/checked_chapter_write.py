"""Compare a writing decision and the author's current draft on the SQLite writer."""
from dataclasses import asdict, dataclass, replace
from contextvars import ContextVar
import json

from domain.novel.value_objects.novel_id import NovelId
from domain.structure.narrative_progress import NarrativeProgressError, NarrativeProgressPolicy
from domain.structure.writing_target import WritingTarget, fingerprint, plan_revision, select_writing_target

current_writing_session = ContextVar("current_writing_session", default=None)


def manuscript_stamp(chapter) -> str:
    if chapter is None:
        return fingerprint(None)
    return fingerprint([str(chapter.id), chapter.title, chapter.outline, chapter.content,
                        chapter.status.value, chapter.generation_hint, chapter.manuscript_revision])


@dataclass
class ChapterWritingSession:
    novel_id: str
    epoch: int
    target: WritingTarget
    node: object
    manuscript: str

    def binding(self):
        return dict(novel_id=self.novel_id, epoch=self.epoch, target=asdict(self.target), manuscript=self.manuscript)

    def input_revision(self):
        return fingerprint([asdict(self.target), self.manuscript])

    def submit(self, action: str, **changes):
        result = submit_checked_chapter(self.binding(), action, **changes)
        self.manuscript = result["manuscript"]
        if action == "preplan":
            self.target = replace(self.target, plan_revision=result["plan_revision"])


def submit_checked_chapter(binding, action, **changes):
    from application.engine.services.persistence_queue import get_persistence_queue, PersistenceCommandType
    from infrastructure.persistence.database.connection import get_sqlite_pragma_settings

    payload = {**binding, "action": action, **changes}
    result = get_persistence_queue().submit_from_daemon(
        PersistenceCommandType.WRITE_CHECKED_CHAPTER.value, payload,
        max(1.0, get_sqlite_pragma_settings().busy_timeout_ms / 1000),
    )
    if "conflict" in result:
        raise NarrativeProgressError(result["conflict"])
    return result


def commit_checked_chapter(payload: dict) -> dict:
    from infrastructure.persistence.database.connection import get_database
    from infrastructure.persistence.database.sqlite_chapter_repository import SqliteChapterRepository
    from infrastructure.persistence.database.story_node_repository import StoryNodeRepository

    db = get_database()
    conn = db.get_connection()
    manuscripts, tree = SqliteChapterRepository(db), StoryNodeRepository(db)
    novel_id = NovelId(payload["novel_id"])
    target = WritingTarget(**payload["target"])
    number = target.chapter_number
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            novel = conn.execute(
                "SELECT target_chapters, autopilot_run_epoch, autopilot_status FROM novels WHERE id=?",
                (novel_id.value,),
            ).fetchone()
            if not novel or novel["autopilot_status"] != "running" or novel["autopilot_run_epoch"] != payload["epoch"]:
                raise NarrativeProgressError("本轮托管已停止或已被新轮次替代")
            nodes = tree.get_plan_nodes_sync(novel_id.value)
            revisions = manuscripts.completed_revisions(novel_id)
            policy = NarrativeProgressPolicy(nodes, novel["target_chapters"], revisions)
            if select_writing_target(policy) != target:
                raise NarrativeProgressError("卷、章、篇幅或大纲已变化，请重新确认写作目标")
            existing = manuscripts.get_by_novel_and_number(novel_id, number)
            if manuscript_stamp(existing) != payload["manuscript"]:
                raise NarrativeProgressError(f"第{number}章的正文或写作要求已被修改，请核对后继续")

            action = payload["action"]
            node = policy.by_id[target.chapter_id]
            if action == "preplan":
                node.outline = payload["outline"]
                node.metadata = {**node.metadata, "chapter_preplan": payload["preplan"]}
                conn.execute(
                    "UPDATE story_nodes SET outline=?, metadata=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (node.outline, json.dumps(node.metadata, ensure_ascii=False), node.id),
                )
                conn.execute(
                    """INSERT INTO chapters (id,novel_id,number,title,outline,content,status)
                       VALUES (?,?,?,?,?,'','draft') ON CONFLICT(novel_id,number) DO UPDATE SET
                       outline=excluded.outline, updated_at=CURRENT_TIMESTAMP""",
                    (str(existing.id) if existing is not None else node.id,
                     novel_id.value, number, node.title, node.outline),
                )
            elif action in ("draft", "completed", "adopt_beat"):
                content = payload["content"]
                if action == "adopt_beat":
                    if not content.strip():
                        raise NarrativeProgressError("采纳的节拍正文为空")
                    prior = (existing.content if existing is not None else "").strip()
                    content = "\n\n".join(part for part in (prior, content.strip()) if part)
                    action = "draft"
                if action == "completed" and not content.strip():
                    raise NarrativeProgressError("不能提交空白正文")
                chapter_id = str(existing.id) if existing is not None else node.id
                conn.execute(
                    """INSERT INTO chapters (id,novel_id,number,title,outline,content,status,word_count)
                       VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(novel_id,number) DO UPDATE SET
                       title=excluded.title, outline=excluded.outline, content=excluded.content,
                       status=excluded.status, word_count=excluded.word_count, updated_at=CURRENT_TIMESTAMP""",
                    (chapter_id, novel_id.value, number, node.title, payload.get("outline") or node.outline or "",
                     content, action, len(content)),
                )
                if action == "completed":
                    conn.execute(
                        """UPDATE novels SET pending_audit_chapter_number=?,current_stage='auditing',
                                  last_stable_stage='auditing' WHERE id=?""",
                        (number, novel_id.value),
                    )
            elif action not in ("validate", "adopt_prose"):
                raise ValueError(f"Unknown checked chapter operation {action}")

            if payload["action"] in ("adopt_prose", "adopt_beat"):
                conn.execute(
                    "UPDATE novels SET current_stage='writing',current_beat_index=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (payload["next_beat_index"], novel_id.value),
                )
            updated = manuscripts.get_by_novel_and_number(novel_id, number)
            result = {"manuscript": manuscript_stamp(updated),
                      "word_count": len(updated.content) if updated is not None else 0}
            if action == "preplan":
                result["plan_revision"] = plan_revision(policy)
            return result
    except NarrativeProgressError as error:
        return {"conflict": str(error)}
