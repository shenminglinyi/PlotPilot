"""Real SQLite + actual PersistenceConsumer, fake LLM, no API keys/network."""
import asyncio
import copy
import json
import time
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from application.engine.services.persistence_queue import PersistenceQueue, register_persistence_handlers
from application.plugin_pilot.contracts import CharacterPatch, PilotError, RunRequest
from application.plugin_pilot.loader import _load_directory, load_official
from application.plugin_pilot.service import PilotService
from domain.ai.services.llm_service import GenerationResult, LLMService
from domain.ai.value_objects.token_usage import TokenUsage
from domain.bible.entities.bible import Bible
from domain.bible.entities.character import Character
from domain.bible.value_objects.character_id import CharacterId
from domain.novel.entities.chapter import Chapter
from domain.novel.value_objects.novel_id import NovelId
from infrastructure.ai.plugin_pilot_model import PilotGenerationConfig, RequestBudget
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.plugin_pilot_store import PilotStore
from infrastructure.persistence.database.sqlite_bible_repository import SqliteBibleRepository
from infrastructure.persistence.database.sqlite_chapter_repository import SqliteChapterRepository
from interfaces.api.v1.plugin_pilot import get_pilot_service, router

QUOTE = "她挡在同伴身前，仍谨慎观察门外。"
OUTPUT = {"artifact_type": "character_card_patch@1", "patch": {"personality": "谨慎且保护同伴"},
          "evidence": [{"field": "personality", "quote": QUOTE}]}


class FakeLLM(LLMService):
    def __init__(self):
        self.content = json.dumps(OUTPUT, ensure_ascii=False)
        self.calls = 0
        self.usage = TokenUsage(100, 80)

    async def generate(self, prompt, config):
        self.calls += 1
        assert config.max_tokens == 2048
        assert QUOTE in prompt.user
        return GenerationResult(self.content, self.usage)

    async def stream_generate(self, prompt, config):
        raise AssertionError("Pilot must not stream")
        yield ""


class FakeModel:
    def __init__(self):
        self.llm = FakeLLM()

    async def identity(self):
        return {"profile_id": "test", "name": "Fake LLM", "model": "test-only", "protocol": "openai", "signature": "test-signature"}

    async def generate(self, prompt, signature):
        if signature != "test-signature":
            raise PilotError("Model configuration changed")
        return await self.llm.generate(prompt, PilotGenerationConfig(max_tokens=2048)), await self.identity()


@pytest.fixture
def pilot(tmp_path, monkeypatch):
    db = DatabaseConnection(str(tmp_path / "pilot.db"))
    conn = db.get_connection()
    for project in ("p1", "p2"):
        conn.execute("INSERT INTO novels(id,slug,title) VALUES(?,?,?)", (project, project, project))
        conn.execute("INSERT INTO chapters(id,novel_id,number,title,content) VALUES(?,?,1,'第一章',?)", ("ch-" + project, project, QUOTE))
        conn.execute("INSERT INTO unified_characters(id,novel_id,name,personality,created_at,updated_at) VALUES(?,?,'小林','原有性格','now','now')", ("char-" + project, project))
    conn.commit()
    monkeypatch.setenv("PLOTPILOT_ALLOW_DIRECT_SQLITE_WRITES", "0")
    pq = PersistenceQueue()
    pq.initialize()
    # Legacy dispatch uses the same writer, rather than a test-only bypass.
    import application.engine.services.persistence_queue as queue_module
    import infrastructure.persistence.database.connection as connection_module
    monkeypatch.setattr(queue_module, "_persistence_queue", pq)
    monkeypatch.setattr(connection_module, "get_database", lambda db_path=None: db)
    register_persistence_handlers()

    def legacy(p):
        if p["kind"] == "chapter":
            SqliteChapterRepository(db).save(Chapter("ch-p1", NovelId("p1"), 1, "第一章", p["content"]))
            db.commit()
        elif p["kind"] == "bible":
            bible = Bible("bible-p1", NovelId("p1"))
            bible.add_character(Character(CharacterId("char-p1"), "小林", "", personality="原有性格"))
            SqliteBibleRepository(db).save(bible)
        elif p["kind"] == "sql":
            db.get_connection().executescript(p["sql"])
    pq.register_handler("test_legacy", legacy)
    pq.start_consumer()
    model = FakeModel()
    service = PilotService(pq, model)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_pilot_service] = lambda: service
    with TestClient(app) as client:
        yield SimpleNamespace(db=db, pq=pq, service=service, model=model, client=client)
    pq.stop_consumer()
    db.close_all()


def call(pilot, action, **kwargs):
    return asyncio.run(pilot.service.command(action, **kwargs))


def run(pilot, **kwargs):
    data = {"plugin_id": "official-character-candidate", "project_id": "p1", "chapter_id": "ch-p1",
            "character_id": "char-p1", "model_signature": "test-signature", "consent": True, **kwargs}
    return pilot.client.post("/api/v1/plugin-pilot/runs", json=data)


def adopt(pilot, candidate, command_id="command-001", project="p1"):
    return pilot.client.post(f"/api/v1/plugin-pilot/candidates/{candidate}/adopt",
                            json={"project_id": project, "command_id": command_id, "confirm": True})


def legacy(pilot, **kwargs):
    return asyncio.run(pilot.pq.execute_confirmed("test_legacy", kwargs))


def test_api_vertical_slice_persistent_preview_and_manual_adoption(pilot):
    assert pilot.client.get("/api/v1/plugin-pilot/projects").status_code == 200
    assert pilot.client.get("/api/v1/plugin-pilot/projects/p1/inputs").json()["characters"][0]["id"] == "char-p1"
    assert pilot.client.get("/api/v1/plugin-pilot/catalog").json()["limits"]["output_tokens"] == 2048
    response = run(pilot)
    assert response.status_code == 200, response.text
    candidate = response.json()
    assert candidate["diff"] == [{"field": "personality", "before": "原有性格", "after": "谨慎且保护同伴"}]
    assert pilot.db.fetch_one("SELECT personality FROM unified_characters WHERE id='char-p1'")["personality"] == "原有性格"
    listed = pilot.client.get("/api/v1/plugin-pilot/projects/p1/candidates").json()
    assert listed[0]["id"] == candidate["id"]
    assert listed[0]["output_schema"]["additionalProperties"] is False
    assert pilot.client.get("/api/v1/plugin-pilot/projects/p2/candidates").json() == []
    result = adopt(pilot, candidate["id"])
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "committed" and result.json()["affected_rows"] == 1
    assert pilot.db.fetch_one("SELECT personality FROM unified_characters WHERE id='char-p1'")["personality"] == "谨慎且保护同伴"
    assert pilot.db.fetch_one("SELECT content FROM chapters WHERE id='ch-p1'")["content"] == QUOTE
    assert pilot.db.fetch_one("SELECT count(*) AS n FROM plugin_pilot_adoptions")["n"] == 1
    assert pilot.model.llm.calls == 1


def test_adoption_idempotent_same_id_different_payload_rejected(pilot):
    first = run(pilot).json()["id"]
    second = run(pilot).json()["id"]
    committed = adopt(pilot, first).json()
    assert adopt(pilot, first).json() == committed
    assert adopt(pilot, second).status_code == 409
    assert adopt(pilot, first, command_id="command-002").status_code == 409
    assert pilot.client.get("/api/v1/plugin-pilot/projects/p1/commands/command-001").json() == committed
    assert pilot.client.get("/api/v1/plugin-pilot/projects/p2/commands/command-001").json()["status"] == "unknown"


@pytest.mark.parametrize("chapter,character", [("ch-p2", "char-p1"), ("ch-p1", "char-p2")])
def test_cross_project_inputs_rejected_before_model(pilot, chapter, character):
    assert run(pilot, chapter_id=chapter, character_id=character).status_code == 404
    assert pilot.model.llm.calls == 0


def test_cross_project_adoption_rejected(pilot):
    candidate = run(pilot).json()["id"]
    assert adopt(pilot, candidate, project="p2").status_code == 409
    assert pilot.db.fetch_one("SELECT personality FROM unified_characters WHERE id='char-p1'")["personality"] == "原有性格"


@pytest.mark.parametrize("kind", ["chapter-upsert", "bible-delete-reinsert", "chapter-aba", "character-aba", "replace", "target-update", "missing-coverage", "missing-revision"])
def test_legacy_paths_and_aba_reject_adoption(pilot, kind):
    candidate = run(pilot).json()
    if kind == "chapter-upsert":
        # Exercise the actual old API caller enqueue path, not only raw SQL.
        SqliteChapterRepository(pilot.db).save(Chapter("ch-p1", NovelId("p1"), 1, "第一章", "章节已改"))
        call(pilot, "inputs", project_id="p1")  # FIFO writer barrier, not a queue-empty guess.
        assert pilot.db.fetch_one("SELECT content FROM chapters WHERE id='ch-p1'")["content"] == "章节已改"
    elif kind == "bible-delete-reinsert":
        legacy(pilot, kind="bible")
    elif kind == "chapter-aba":
        legacy(pilot, kind="sql", sql="DELETE FROM chapters WHERE id='ch-p1'; INSERT INTO chapters(id,novel_id,number,title,content) VALUES('ch-p1','p1',1,'第一章','" + QUOTE + "');")
    elif kind == "character-aba":
        legacy(pilot, kind="sql", sql="DELETE FROM unified_characters WHERE id='char-p1'; INSERT INTO unified_characters(id,novel_id,name,personality,created_at,updated_at) VALUES('char-p1','p1','小林','原有性格','now','now');")
    elif kind == "replace":
        legacy(pilot, kind="sql", sql="INSERT OR REPLACE INTO unified_characters(id,novel_id,name,personality,created_at,updated_at) VALUES('char-p1','p1','小林','原有性格','now','now');")
    elif kind == "target-update":
        legacy(pilot, kind="sql", sql="UPDATE unified_characters SET appearance='已改' WHERE id='char-p1';")
    elif kind == "missing-coverage":
        legacy(pilot, kind="sql", sql="DROP TRIGGER plugin_pilot_character_update;")
    else:
        legacy(pilot, kind="sql", sql="DELETE FROM plugin_pilot_revisions WHERE object_id='char-p1';")
    response = adopt(pilot, candidate["id"])
    assert response.status_code == 409, response.text
    assert pilot.db.fetch_one("SELECT count(*) AS n FROM plugin_pilot_adoptions")["n"] == 0
    assert pilot.db.fetch_one("SELECT adopted_command_id FROM plugin_pilot_candidates")["adopted_command_id"] is None


def test_atomic_rollback_includes_character_revision_and_relation(pilot):
    candidate = run(pilot).json()
    legacy(pilot, kind="sql", sql="CREATE TRIGGER reject_pilot_record BEFORE INSERT ON plugin_pilot_adoptions BEGIN SELECT RAISE(ABORT,'injected'); END;")
    response = adopt(pilot, candidate["id"])
    assert response.status_code == 409 and response.json()["detail"]["status"] == "failed"
    assert pilot.db.fetch_one("SELECT personality FROM unified_characters WHERE id='char-p1'")["personality"] == "原有性格"
    revision = pilot.db.fetch_one("SELECT revision FROM plugin_pilot_revisions WHERE kind='character' AND object_id='char-p1'")["revision"]
    assert revision == candidate["snapshot"]["character"]["revision"]
    assert pilot.db.fetch_one("SELECT adopted_command_id FROM plugin_pilot_candidates")["adopted_command_id"] is None
    assert pilot.db.fetch_one("SELECT count(*) AS n FROM plugin_pilot_adoptions")["n"] == 0
    assert pilot.client.get("/api/v1/plugin-pilot/projects/p1/commands/command-001").json()["status"] == "failed"


def test_real_zero_rowcount_is_conflict_not_success(pilot):
    candidate = run(pilot).json()["id"]
    legacy(pilot, kind="sql", sql="CREATE TRIGGER ignore_character_update BEFORE UPDATE ON unified_characters BEGIN SELECT RAISE(IGNORE); END;")
    response = adopt(pilot, candidate)
    assert response.status_code == 409
    assert "exactly one row" in response.json()["detail"]["message"]
    assert pilot.db.fetch_one("SELECT count(*) AS n FROM plugin_pilot_adoptions")["n"] == 0


def test_command_result_failure_rolls_back_entire_commit(pilot):
    candidate = run(pilot).json()
    legacy(pilot, kind="sql", sql="CREATE TRIGGER reject_command_result BEFORE INSERT ON plugin_pilot_commands BEGIN SELECT RAISE(ABORT,'injected result failure'); END;")
    with pytest.raises(sqlite3.IntegrityError):
        call(pilot, "adopt", candidate_id=candidate["id"], project_id="p1", command_id="result-failure", confirm=True)
    assert pilot.db.fetch_one("SELECT personality FROM unified_characters WHERE id='char-p1'")["personality"] == "原有性格"
    assert pilot.db.fetch_one("SELECT count(*) AS n FROM plugin_pilot_adoptions")["n"] == 0
    assert call(pilot, "command", project_id="p1", command_id="result-failure")["status"] == "unknown"
    assert pilot.db.fetch_one("SELECT adopted_command_id FROM plugin_pilot_candidates")["adopted_command_id"] is None


def test_unknown_result_is_queryable_after_late_commit(pilot):
    candidate = run(pilot).json()["id"]
    original = pilot.pq._handlers["plugin_pilot"]
    def slow(payload):
        if payload["action"] == "adopt":
            time.sleep(.1)
        return original(payload)
    pilot.pq.register_handler("plugin_pilot", slow)
    async def exercise():
        with pytest.raises(asyncio.TimeoutError):
            await pilot.pq.execute_confirmed("plugin_pilot", {"action": "adopt", "candidate_id": candidate,
                "project_id": "p1", "command_id": "late-command", "confirm": True}, timeout=.01)
        # Event loop remains live while writer is waiting, then drains in order.
        return await pilot.service.command("command", project_id="p1", command_id="late-command")
    assert asyncio.run(exercise())["status"] == "committed"


def test_unknown_after_prequeue_failure_can_manually_retry_same_payload(pilot, monkeypatch):
    candidate = run(pilot).json()["id"]
    original_id = "manual-retry-original"
    with monkeypatch.context() as offline:
        offline.setattr(pilot.pq, "is_consumer_running", lambda: False)
        assert adopt(pilot, candidate, command_id=original_id).status_code == 503
    assert call(pilot, "command", project_id="p1", command_id=original_id)["status"] == "unknown"
    result = adopt(pilot, candidate, command_id=original_id)
    assert result.status_code == 200 and result.json()["status"] == "committed"
    assert adopt(pilot, candidate, command_id=original_id).json() == result.json()
    assert pilot.db.fetch_one("SELECT count(*) AS n FROM plugin_pilot_adoptions")["n"] == 1
    assert pilot.db.fetch_one("SELECT count(*) AS n FROM plugin_pilot_commands")["n"] == 1


@pytest.mark.parametrize("change", ["extra-field", "wrong-type", "too-long", "missing-evidence", "fabricated-quote", "oversized-output", "over-token-usage"])
def test_schema_and_model_bounds_never_write_character(pilot, change):
    output = copy.deepcopy(OUTPUT)
    if change == "extra-field": output["patch"]["name"] = "hacked"
    elif change == "wrong-type": output["patch"]["personality"] = 123
    elif change == "too-long": output["patch"]["personality"] = "x" * 601
    elif change == "missing-evidence": output["evidence"] = []
    elif change == "fabricated-quote": output["evidence"][0]["quote"] = "不在章节里的证据"
    elif change == "over-token-usage": pilot.model.llm.usage = TokenUsage(16001, 2049)
    pilot.model.llm.content = "x" * 12001 if change == "oversized-output" else json.dumps(output)
    assert run(pilot).status_code == 422
    assert pilot.db.fetch_one("SELECT count(*) AS n FROM plugin_pilot_candidates")["n"] == 0
    assert pilot.db.fetch_one("SELECT personality FROM unified_characters WHERE id='char-p1'")["personality"] == "原有性格"


def test_consent_model_identity_and_input_bounds(pilot):
    assert run(pilot, consent=False).status_code == 422
    assert run(pilot, consent=1).status_code == 422
    assert run(pilot, model_signature="outdated-signature").status_code == 409
    legacy(pilot, kind="chapter", content="x" * 8001)
    assert run(pilot).status_code == 422
    legacy(pilot, kind="chapter", content="中" * 6000)
    assert run(pilot).status_code == 422
    assert pilot.model.llm.calls == 0


def test_store_requires_writer_even_in_direct_write_environment(pilot, monkeypatch):
    monkeypatch.setenv("PLOTPILOT_ALLOW_DIRECT_SQLITE_WRITES", "1")
    with pytest.raises(RuntimeError, match="real persistence writer"):
        PilotStore(pilot.db).handle({"action": "projects"})


@pytest.mark.parametrize("mutation", ["version", "host", "path", "absolute", "action", "type", "unknown", "duplicate", "template-size", "manifest-size"])
def test_manifest_rejections(tmp_path, mutation):
    package = next(iter(load_official().values()))
    manifest = package.manifest.model_dump()
    if mutation == "version": manifest["version"] = "1.0.0"
    elif mutation == "host": manifest["host_api"] = "9.0"
    elif mutation == "path": manifest["template"] = "../outside.txt"
    elif mutation == "absolute": manifest["template"] = "C:/outside.txt"
    elif mutation == "action": manifest["steps"][2] = "eval"
    elif mutation == "type": manifest["artifact_type"] = "arbitrary_sql@1"
    elif mutation == "unknown": manifest["code"] = "exec(...)"
    folder = tmp_path / "example"
    folder.mkdir()
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (folder / "prompt.txt").write_text("x" * 6001 if mutation == "template-size" else package.template, encoding="utf-8")
    if mutation == "manifest-size":
        (folder / "manifest.json").write_text("x" * 8193)
    if mutation == "duplicate":
        other = tmp_path / "duplicate"
        other.mkdir()
        (other / "manifest.json").write_text(json.dumps(manifest))
        (other / "prompt.txt").write_text(package.template, encoding="utf-8")
    with pytest.raises((ValueError, ValidationError)):
        _load_directory(tmp_path)


def test_network_budget_blocks_legacy_retry_and_token_override():
    assert PilotGenerationConfig(max_tokens=2048).max_tokens == 2048
    with pytest.raises(ValueError): PilotGenerationConfig(max_tokens=120000)
    async def exercise():
        budget = RequestBudget("openai")
        await budget.before_request(httpx.Request("POST", "http://fake", json={"max_tokens": 2048}))
        with pytest.raises(PilotError, match="budget"):
            await budget.before_request(httpx.Request("POST", "http://fake", json={"max_tokens": 2048}))
        for protocol, body in [("openai", {"max_output_tokens": 120000}),
                               ("gemini", {"generationConfig": {"maxOutputTokens": 120000}})]:
            with pytest.raises(PilotError, match="output limit"):
                await RequestBudget(protocol).before_request(httpx.Request("POST", "http://fake", json=body))
    asyncio.run(exercise())


@pytest.mark.parametrize("http_status", [200, 500])
def test_real_provider_request_cap_despite_legacy_profile_minimum(http_status):
    from application.ai.llm_control_service import LLMProfile
    from infrastructure.ai.plugin_pilot_model import ConfiguredPilotModel
    from infrastructure.ai.providers.openai_provider import OpenAIProvider
    from infrastructure.ai.config.settings import Settings
    from domain.ai.value_objects.prompt import Prompt

    async def exercise():
        profile = LLMProfile(id="test", name="test", model="fake", api_key="test-only",
                             base_url="http://local-fake/v1", max_tokens=1,
                             use_legacy_chat_completions=True)
        assert profile.max_tokens == 120000
        requests = []
        def respond(request):
            requests.append(json.loads(request.content))
            return httpx.Response(http_status, json={"id": "test", "object": "chat.completion", "created": 1,
                "model": "fake", "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(OUTPUT)}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 80, "total_tokens": 180}})
        client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        provider = OpenAIProvider(Settings(api_key="test-only", default_model="fake", base_url="http://local-fake/v1", use_legacy_chat_completions=True))
        await provider._http_client.aclose()
        provider._http_client = client
        provider.async_client = provider.async_client.with_options(http_client=client, max_retries=0)
        control = SimpleNamespace(resolve_active_profile=lambda: profile)
        factory = SimpleNamespace(create_from_profile=lambda p: provider)
        adapter = ConfiguredPilotModel(control, factory)
        signature = (await adapter.identity())["signature"]
        if http_status == 200:
            result, _ = await adapter.generate(Prompt("system", QUOTE), signature)
            assert result.content == json.dumps(OUTPUT)
        else:
            with pytest.raises(Exception):
                await adapter.generate(Prompt("system", QUOTE), signature)
        assert len(requests) == 1
        assert requests[0]["max_tokens"] == 2048
    asyncio.run(exercise())


def test_model_timeout_discards_result(pilot, monkeypatch):
    import application.plugin_pilot.service as module
    monkeypatch.setattr(module, "TIMEOUT_SECONDS", .01)
    async def slow(prompt, signature):
        await asyncio.sleep(.1)
        return GenerationResult(json.dumps(OUTPUT), TokenUsage(1, 1)), await pilot.model.identity()
    monkeypatch.setattr(pilot.model, "generate", slow)
    assert run(pilot).status_code == 504
    assert pilot.db.fetch_one("SELECT count(*) AS n FROM plugin_pilot_candidates")["n"] == 0


def test_confirmed_lane_is_bounded_and_requires_running_writer():
    pq = PersistenceQueue()
    with pytest.raises(RuntimeError, match="unavailable"):
        asyncio.run(pq.execute_confirmed("anything", {}))
    pq.initialize()
    pq.start_consumer()
    try:
        # Capacity checking is independent of unbounded legacy queue qsize().
        pq._receipts = {str(i): None for i in range(32)}
        with pytest.raises(RuntimeError, match="capacity"):
            asyncio.run(pq.execute_confirmed("anything", {}))
    finally:
        pq._receipts = {}
        pq.stop_consumer()
