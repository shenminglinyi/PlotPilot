"""Pilot transactions executed exclusively by the existing persistence writer."""
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

from application.plugin_pilot.contracts import (
    CharacterPatch, FIELDS, MAX_INPUT_CHARS, PilotError,
)
from infrastructure.persistence.database.write_dispatch import is_sqlite_writer_thread


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value) -> str:
    return hashlib.sha256(encode(value).encode("utf-8")).hexdigest()


def _normalize_sql(sql):
    return re.sub(r"\s+", "", sql.replace("IF NOT EXISTS", "")).rstrip(";").lower()


@lru_cache(maxsize=1)
def _expected_triggers():
    sql = (Path(__file__).parent / "migrations/z_plugin_pilot_v1.sql").read_text(encoding="utf-8")
    return {match.group(1): _normalize_sql(match.group(0)) for match in re.finditer(
        r"CREATE TRIGGER IF NOT EXISTS (plugin_pilot_\w+) .*?END;", sql, re.DOTALL)}


class PilotStore:
    def __init__(self, db):
        self.db = db

    def handle(self, payload):
        if not is_sqlite_writer_thread():
            raise RuntimeError("Pilot commands require the real persistence writer")
        actions = {"projects": self._projects, "inputs": self._inputs,
                   "snapshot": self._snapshot, "store": self._store,
                   "candidates": self._candidates, "adopt": self._adopt,
                   "command": self._command}
        action = actions.get(payload.get("action"))
        if action is None:
            raise PilotError("Unknown pilot command", 400)
        conn = self.db.get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            result = action(conn, payload)
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise

    @staticmethod
    def _coverage(conn):
        expected = _expected_triggers()
        actual = {r["name"]: _normalize_sql(r["sql"]) for r in conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND name LIKE 'plugin_pilot_%'")}
        if len(expected) != 6 or any(actual.get(k) != v for k, v in expected.items()):
            raise PilotError("Revision coverage unavailable; adoption disabled", 503)

    @staticmethod
    def _revision(conn, kind, object_id):
        row = conn.execute("SELECT revision FROM plugin_pilot_revisions WHERE kind=? AND object_id=?",
                           (kind, object_id)).fetchone()
        if row is None:
            raise PilotError("Object has no verified revision; adoption disabled", 409)
        return row["revision"]

    @staticmethod
    def _project(conn, project_id):
        row = conn.execute("SELECT id FROM novels WHERE id=?", (project_id,)).fetchone()
        if row is None:
            raise PilotError("Project not found", 404)

    def _projects(self, conn, p):
        return [dict(r) for r in conn.execute("SELECT id, slug, title FROM novels ORDER BY updated_at DESC")]

    def _inputs(self, conn, p):
        self._project(conn, p["project_id"])
        self._coverage(conn)
        return {"chapters": [dict(r) for r in conn.execute(
            "SELECT id, number, title, length(content) AS characters FROM chapters "
            "WHERE novel_id=? AND trim(COALESCE(content,''))<>'' ORDER BY number", (p["project_id"],))],
            "characters": [dict(r) for r in conn.execute(
                "SELECT id, name FROM unified_characters WHERE novel_id=? ORDER BY name", (p["project_id"],))]}

    def _snapshot(self, conn, p):
        self._project(conn, p["project_id"])
        self._coverage(conn)
        chapter = conn.execute("SELECT id, number, title, content FROM chapters WHERE id=? AND novel_id=?",
                               (p["chapter_id"], p["project_id"])).fetchone()
        character = conn.execute(
            "SELECT id, name, appearance, personality, core_motivation FROM unified_characters WHERE id=? AND novel_id=?",
            (p["character_id"], p["project_id"])).fetchone()
        if chapter is None or character is None:
            raise PilotError("Saved chapter or canonical character not found in this project", 404)
        chapter, character = dict(chapter), dict(character)
        if not (chapter["content"] or "").strip():
            raise PilotError("Select a saved nonempty chapter", 422)
        if len(chapter["content"]) > MAX_INPUT_CHARS:
            raise PilotError("Chapter exceeds pilot input limit (8000 characters)", 422)
        chapter["revision"] = self._revision(conn, "chapter", chapter["id"])
        character["revision"] = self._revision(conn, "character", character["id"])
        return {"project_id": p["project_id"], "chapter": chapter, "character": character}

    def _store(self, conn, p):
        candidate = p["candidate"]
        CharacterPatch.model_validate(candidate["output"])
        raw = encode(candidate)
        if len(raw.encode("utf-8")) > 100000:
            raise PilotError("Candidate exceeds storage limit", 422)
        conn.execute("INSERT INTO plugin_pilot_candidates(id,project_id,payload_json,payload_hash) VALUES(?,?,?,?)",
                     (candidate["id"], candidate["snapshot"]["project_id"], raw, digest(candidate)))
        return candidate

    def _candidates(self, conn, p):
        self._project(conn, p["project_id"])
        rows = conn.execute("SELECT * FROM plugin_pilot_candidates WHERE project_id=? ORDER BY created_at DESC, rowid DESC LIMIT 100",
                            (p["project_id"],)).fetchall()
        return [dict(json.loads(r["payload_json"]), adopted_command_id=r["adopted_command_id"],
                     created_at=r["created_at"]) for r in rows]

    def _command(self, conn, p):
        row = conn.execute("SELECT result_json FROM plugin_pilot_commands WHERE id=? AND project_id=?",
                           (p["command_id"], p["project_id"])).fetchone()
        return json.loads(row["result_json"]) if row else {"command_id": p["command_id"], "status": "unknown"}

    def _adopt(self, conn, p):
        request_hash = digest({k: p[k] for k in ("project_id", "candidate_id", "confirm")})
        old = conn.execute("SELECT * FROM plugin_pilot_commands WHERE id=?", (p["command_id"],)).fetchone()
        if old:
            if old["request_hash"] != request_hash or old["project_id"] != p["project_id"]:
                raise PilotError("command_id already belongs to a different payload")
            return json.loads(old["result_json"])
        result = {"command_id": p["command_id"], "candidate_id": p["candidate_id"]}
        conn.execute("SAVEPOINT pilot_adoption")
        try:
            if p.get("confirm") is not True:
                raise PilotError("Explicit confirmation required", 422)
            self._project(conn, p["project_id"])
            self._coverage(conn)
            row = conn.execute("SELECT * FROM plugin_pilot_candidates WHERE id=? AND project_id=?",
                               (p["candidate_id"], p["project_id"])).fetchone()
            if row is None:
                raise PilotError("Candidate not found in this project", 404)
            if row["adopted_command_id"]:
                raise PilotError("Candidate was already adopted")
            candidate = json.loads(row["payload_json"])
            if digest(candidate) != row["payload_hash"]:
                raise PilotError("Candidate integrity check failed")
            snapshot = candidate["snapshot"]
            current = self._snapshot(conn, {"project_id": p["project_id"],
                "chapter_id": snapshot["chapter"]["id"], "character_id": snapshot["character"]["id"]})
            if current != snapshot:
                raise PilotError("Source chapter or target character changed. Generate a new candidate.")
            output = CharacterPatch.model_validate(candidate["output"])
            if any(e.quote not in snapshot["chapter"]["content"] for e in output.evidence):
                raise PilotError("Evidence no longer matches source")
            # Field names come exclusively from the host schema, never SQL paths.
            keys = [key for key in FIELDS if key in output.patch]
            character = snapshot["character"]
            cursor = conn.execute(
                "UPDATE unified_characters SET " + ", ".join(f"{key}=?" for key in keys) +
                ", updated_at=CURRENT_TIMESTAMP WHERE id=? AND novel_id=? AND EXISTS "
                "(SELECT 1 FROM plugin_pilot_revisions WHERE kind='character' AND object_id=? AND revision=?)",
                [output.patch[k] for k in keys] + [character["id"], p["project_id"], character["id"], character["revision"]])
            if cursor.rowcount != 1:
                raise PilotError("Conditional character update did not affect exactly one row")
            revision = self._revision(conn, "character", character["id"])
            conn.execute("INSERT INTO plugin_pilot_adoptions(command_id,candidate_id,project_id,character_id,old_revision,new_revision) VALUES(?,?,?,?,?,?)",
                         (p["command_id"], p["candidate_id"], p["project_id"], character["id"], character["revision"], revision))
            cursor = conn.execute("UPDATE plugin_pilot_candidates SET adopted_command_id=? WHERE id=? AND adopted_command_id IS NULL",
                                  (p["command_id"], p["candidate_id"]))
            if cursor.rowcount != 1:
                raise PilotError("Candidate adoption relation changed")
            result.update(status="committed", new_revision=revision, affected_rows=1)
        except PilotError as exc:
            conn.execute("ROLLBACK TO pilot_adoption")
            result.update(status="conflict", message=str(exc))
        except Exception:
            conn.execute("ROLLBACK TO pilot_adoption")
            # Do not return raw SQL/paths or provider errors to clients.
            result.update(status="failed", message="Adoption transaction rolled back; no character change")
        finally:
            conn.execute("RELEASE pilot_adoption")
        conn.execute("INSERT INTO plugin_pilot_commands(id,project_id,request_hash,result_json) VALUES(?,?,?,?)",
                     (p["command_id"], p["project_id"], request_hash, encode(result)))
        return result
