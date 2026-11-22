"""Unit & FastAPI route tests for ModSandboxTrialService (300-word A/B Sandbox Trial)."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, List, Optional, Tuple

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from application.ai.llm_control_service import LLMControlConfig, LLMControlService, LLMProfile
from application.ai.mod_sandbox_trial_service import (
    ModSandboxAbTrialRequest,
    ModSandboxTrialService,
    ModSandboxValidationError,
    ModTrialOverrideInput,
    ModTrialPackInput,
    _try_extract_well_formed_baseline,
    strip_all_mod_blocks,
)
from domain.ai.errors import LLMNotConfiguredError
from domain.ai.services.llm_service import GenerationConfig, GenerationResult, LLMService
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.write_dispatch import sqlite_writes_bypass_queue
from interfaces.api.routes import register_api_routes
from interfaces.api.settings import BackendSettings
from interfaces.main import create_app


class _FakeControlService:
    def __init__(self, profile: Optional[LLMProfile]) -> None:
        self._profile = profile

    def resolve_role_profile(self, role: str = "main") -> Optional[LLMProfile]:
        assert role == "main"
        return self._profile


class _RecordingConcurrentLLMService(LLMService):
    def __init__(
        self,
        *,
        require_concurrency: bool = False,
        raise_exc: Optional[Exception] = None,
    ) -> None:
        self.calls: List[Tuple[Prompt, GenerationConfig]] = []
        self._require_concurrency = require_concurrency
        self._raise_exc = raise_exc
        self._inflight = 0
        self._saw_concurrent = False
        self._both_entered = asyncio.Event()

    async def generate(
        self, prompt: Prompt, config: GenerationConfig
    ) -> GenerationResult:
        self.calls.append((prompt, config))
        self._inflight += 1
        if self._inflight >= 2:
            self._saw_concurrent = True
            self._both_entered.set()

        if self._require_concurrency:
            await asyncio.wait_for(self._both_entered.wait(), timeout=2.0)

        try:
            if self._raise_exc is not None:
                raise self._raise_exc
            if "PlotPilot-Mod:" in prompt.system or "同包协同规则" in prompt.system:
                text = "处理组正文：雨夜巷口灯影摇曳，陈砚指节扣紧茶杯，半句试探未落，对面黑衣客袖底寒光微露。"
            else:
                text = "对照组正文：雨落青石板，陈砚推开木窗望向街角茶肆，记起三年前那桩尚未了结的旧案。"
            return GenerationResult(
                content=f"  {text}  ",
                token_usage=TokenUsage(input_tokens=100, output_tokens=60),
            )
        finally:
            self._inflight -= 1

    async def stream_generate(self, prompt: Prompt, config: GenerationConfig):
        yield ""


_ALLOWED_READONLY_SQLITE_ACTIONS = frozenset(
    {
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_FUNCTION,
    }
)


class _RawSQLiteAdapter:
    """Minimal DatabaseConnection-compatible adapter backed by a raw empty sqlite3 file (0 schema tables)."""

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._all_connections = [self._conn]

    def get_connection(self) -> sqlite3.Connection:
        return self._conn

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def fetch_one(self, sql: str, params: tuple = ()) -> Optional[dict]:
        row = self._conn.execute(sql, params).fetchone()
        return dict(row) if row is not None else None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def commit(self) -> None:
        self._conn.commit()

    @contextmanager
    def transaction(self):
        yield self._conn
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


class _SQLiteWriteGuard:
    """Authorizer + write-queue + connection-open observer rejecting ANY SQLite write/DDL/transaction."""

    def __init__(self) -> None:
        self.violations: list[tuple[Any, ...]] = []
        self._instrumented_conns: list[sqlite3.Connection] = []

    def _authorizer(
        self,
        action_code: int,
        arg1: Optional[str],
        arg2: Optional[str],
        dbname: Optional[str],
        source: Optional[str],
    ) -> int:
        if action_code in _ALLOWED_READONLY_SQLITE_ACTIONS:
            return sqlite3.SQLITE_OK
        self.violations.append(("sqlite_authorizer", action_code, arg1, arg2, dbname, source))
        return sqlite3.SQLITE_DENY

    def attach(self, conn: sqlite3.Connection) -> sqlite3.Connection:
        if conn not in self._instrumented_conns:
            conn.set_authorizer(self._authorizer)
            self._instrumented_conns.append(conn)
        return conn

    def detach_all(self) -> None:
        for conn in self._instrumented_conns:
            try:
                conn.set_authorizer(None)
            except Exception:
                pass
        self._instrumented_conns.clear()


@contextmanager
def _forbid_sqlite_writes(db: Any, _unused_mp: Optional[pytest.MonkeyPatch] = None):
    """Guard every existing and newly opened SQLite connection + write_dispatch queue against writes."""
    from infrastructure.persistence.database import write_dispatch as wd_mod

    guard = _SQLiteWriteGuard()
    with pytest.MonkeyPatch.context() as mp:
        if db is not None:
            if hasattr(db, "get_connection"):
                guard.attach(db.get_connection())
                orig_get_conn = db.get_connection
                mp.setattr(db, "get_connection", lambda: guard.attach(orig_get_conn()))
            for existing in list(getattr(db, "_all_connections", []) or []):
                guard.attach(existing)
            if hasattr(db, "commit"):
                def _forbidden_commit():
                    guard.violations.append(("db.commit",))
                    raise AssertionError("Prohibited db.commit()")
                mp.setattr(db, "commit", _forbidden_commit)
            if hasattr(db, "transaction"):
                @contextmanager
                def _forbidden_transaction():
                    guard.violations.append(("db.transaction",))
                    raise AssertionError("Prohibited db.transaction()")
                    yield  # pragma: no cover
                mp.setattr(db, "transaction", _forbidden_transaction)

        real_sqlite_connect = sqlite3.connect
        mp.setattr(sqlite3, "connect", lambda *a, **kw: guard.attach(real_sqlite_connect(*a, **kw)))

        def _forbidden_enqueue_sql(sql: str, params: list):
            guard.violations.append(("enqueue_execute_sql", sql))
            raise AssertionError(f"Prohibited enqueue_execute_sql: {sql}")

        def _forbidden_enqueue_batch(ops: list):
            guard.violations.append(("enqueue_txn_batch", ops))
            raise AssertionError(f"Prohibited enqueue_txn_batch: {ops}")

        mp.setattr(wd_mod, "enqueue_execute_sql", _forbidden_enqueue_sql)
        mp.setattr(wd_mod, "enqueue_txn_batch", _forbidden_enqueue_batch)
        try:
            yield guard
        finally:
            guard.detach_all()


def _snapshot_tables_digest(db: Any) -> dict[str, tuple[int, str]]:
    """Hash unfiltered sqlite_master catalog plus every user table (`not startswith('sqlite_')`)."""
    conn = db.get_connection()
    schema_rows = conn.execute(
        "SELECT type, name, tbl_name, rootpage, COALESCE(sql, '') AS sql FROM sqlite_master ORDER BY type, name"
    ).fetchall()
    schema_norm = [dict(r) for r in schema_rows]
    snapshot: dict[str, tuple[int, str]] = {
        "__sqlite_master__": (
            len(schema_norm),
            hashlib.sha256(json.dumps(schema_norm, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
        )
    }
    for r in schema_norm:
        if r["type"] == "table" and not str(r["name"]).startswith("sqlite_"):
            table = str(r["name"])
            escaped = table.replace('"', '""')
            rows = conn.execute(f'SELECT * FROM "{escaped}"').fetchall()
            normalized = sorted((dict(row) for row in rows), key=lambda d: json.dumps(d, sort_keys=True, ensure_ascii=False))
            payload = json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode("utf-8")
            snapshot[table] = (len(normalized), hashlib.sha256(payload).hexdigest())
    return snapshot


def _seed_trial_db(tmp_path) -> DatabaseConnection:
    db_path = str(tmp_path / "trial.db")
    db = DatabaseConnection(db_path)
    with sqlite_writes_bypass_queue():
        conn = db.get_connection()
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute("INSERT INTO prompt_templates (id, name, description, category, is_builtin) VALUES ('tmpl-builtin', '内置模板', 'builtin', 'builtin', 1)")
            conn.execute("INSERT INTO prompt_nodes (id, template_id, node_key, name, description, category, is_builtin, active_version_id) VALUES ('node-ch', 'tmpl-builtin', 'chapter-generation-main', '主章节生成', '', 'generation', 1, 'ver-ch-v2')")
            conn.execute(
                "INSERT INTO prompt_versions (id, node_id, version_number, system_prompt, user_template, change_summary, created_by) VALUES "
                "('ver-ch-v1', 'node-ch', 1, 'CLEAN_V1_SYSTEM_PROMPT', '{context}\n{outline}', 'v1 clean', 'system'), "
                "('ver-ch-v2', 'node-ch', 2, '<!-- [PlotPilot-Mod:installed-pack:START:replaced] -->\nINSTALLED_REPLACED_PROMPT\n<!-- [PlotPilot-Mod:installed-pack:END] -->', '{context}\n{outline}', 'v2 mod replaced', 'user')"
            )
            conn.execute("INSERT INTO prompt_nodes (id, template_id, node_key, name, description, category, is_builtin, active_version_id) VALUES ('node-sc', 'tmpl-builtin', 'scene-generation', '场景生成', '', 'generation', 1, 'ver-sc-v1')")
            conn.execute(
                "INSERT INTO prompt_versions (id, node_id, version_number, system_prompt, user_template, change_summary, created_by) VALUES "
                "('ver-sc-v1', 'node-sc', 1, 'CLEAN_SCENE_BASE\n\n<!-- [PlotPilot-Mod:other-pack:START:appended] -->\nOTHER_MOD_BODY\n<!-- [PlotPilot-Mod:other-pack:END] -->', '{context}', 'v1 with appended mod', 'user')"
            )
            conn.execute("INSERT INTO novels (id, title, slug, author, target_chapters, premise) VALUES ('novel-1', '青灯诡录', 'qingdeng', '测试作者', 100, '江南雨夜茶肆中，主角陈砚追查三年前沉船旧案。')")
            conn.execute("INSERT INTO unified_characters (id, novel_id, name, role, personality) VALUES ('char-1', 'novel-1', '陈砚', '主角', '冷静克制的前刑曹书吏')")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return db


def _configured_profile() -> LLMProfile:
    return LLMProfile(
        id="prof-main",
        name="主力测试模型",
        protocol="openai",
        base_url="https://api.example.com/v1",
        api_key="sk-test-valid-key",
        model="gpt-test-main",
        temperature=0.75,
    )


def _valid_pack(**overrides_kwargs) -> ModTrialPackInput:
    override = ModTrialOverrideInput(
        nodeKey=overrides_kwargs.get("nodeKey", "chapter-generation-main"),
        nodeLabel=overrides_kwargs.get("nodeLabel", "主章节生成"),
        mode=overrides_kwargs.get("mode", "append_protocol"),
        systemContent=overrides_kwargs.get(
            "systemContent", "请强化感官细节与人物潜台词，禁止直白解释心理。"
        ),
        userTemplate=overrides_kwargs.get("userTemplate"),
    )
    return ModTrialPackInput(
        id=overrides_kwargs.get("pack_id", "candidate-pack-1"),
        name=overrides_kwargs.get("pack_name", "古风冷峻笔法包"),
        summary=overrides_kwargs.get("summary", "强化古风克制叙事与环境留白"),
        overrides=[override],
    )


def _build_route_test_client(
    *,
    db: Optional[DatabaseConnection],
    control_service: Any,
    llm_service: Any,
    client_host: str = "127.0.0.1",
    tmp_path=None,
) -> TestClient:
    if tmp_path is not None:
        app = create_app(BackendSettings(frontend_dir=tmp_path / "dist"))
    else:
        app = FastAPI()
        register_api_routes(app)

    from interfaces.api.v1.workbench.mod_sandbox_routes import get_mod_sandbox_trial_service

    service = ModSandboxTrialService(
        db_provider=(lambda: db) if db is not None else (lambda: None),
        control_service=control_service,
        llm_service=llm_service,
    )
    app.dependency_overrides[get_mod_sandbox_trial_service] = lambda: service
    return TestClient(app, client=(client_host, 54321))


@pytest.mark.asyncio
async def test_zero_sqlite_writes_and_clean_baseline_recovery_over_replaced_and_appended(tmp_path):
    db = _seed_trial_db(tmp_path)
    try:
        before_digest = _snapshot_tables_digest(db)
        llm_a = _RecordingConcurrentLLMService(require_concurrency=True)
        svc_a = ModSandboxTrialService(db_provider=lambda: db, control_service=_FakeControlService(_configured_profile()), llm_service=llm_a)
        req_a = ModSandboxAbTrialRequest(
            pack=_valid_pack(mode="append_protocol", nodeKey="chapter-generation-main"),
            novel_id="novel-1",
            scenario="雨夜茶肆对峙，黑衣客递来半枚铜符。",
            target_words=300,
        )
        res_a = await svc_a.run_ab_trial(req_a)
        assert _snapshot_tables_digest(db) == before_digest
        assert llm_a._saw_concurrent is True and len(llm_a.calls) == 2
        baseline_prompt_a, cfg_base_a = llm_a.calls[0]
        mod_prompt_a, cfg_mod_a = llm_a.calls[1]
        assert "CLEAN_V1_SYSTEM_PROMPT" in baseline_prompt_a.system
        assert "INSTALLED_REPLACED_PROMPT" not in baseline_prompt_a.system
        assert "PlotPilot-Mod" not in baseline_prompt_a.system
        assert "CLEAN_V1_SYSTEM_PROMPT" in mod_prompt_a.system
        assert "<!-- [PlotPilot-Mod:candidate-pack-1:START:appended] -->" in mod_prompt_a.system
        assert "请强化感官细节与人物潜台词" in mod_prompt_a.system
        assert "INSTALLED_REPLACED_PROMPT" not in mod_prompt_a.system
        assert cfg_base_a.role_hint == "main" and cfg_mod_a.role_hint == "main"
        assert res_a.pack_id == "candidate-pack-1" and res_a.target_node_key == "chapter-generation-main"
        assert res_a.mounted_node_keys == ["chapter-generation-main"]
        assert res_a.novel_id == "novel-1" and res_a.novel_title == "青灯诡录" and res_a.model == "gpt-test-main"
        assert res_a.baseline_char_count == len(res_a.baseline_text) and res_a.mod_char_count == len(res_a.mod_text)

        llm_b = _RecordingConcurrentLLMService()
        svc_b = ModSandboxTrialService(db_provider=lambda: db, control_service=_FakeControlService(_configured_profile()), llm_service=llm_b)
        req_b = ModSandboxAbTrialRequest(
            pack=_valid_pack(pack_id="scene-mod", nodeKey="scene-generation", mode="append_protocol", systemContent="强化环境光影与冷场留白。"),
            scenario="古刹雪夜钟响。",
            target_words=280,
        )
        await svc_b.run_ab_trial(req_b)
        assert _snapshot_tables_digest(db) == before_digest
        baseline_prompt_b, mod_prompt_b = llm_b.calls[0][0], llm_b.calls[1][0]
        assert "CLEAN_SCENE_BASE" in baseline_prompt_b.system
        assert "OTHER_MOD_BODY" not in baseline_prompt_b.system and "PlotPilot-Mod" not in baseline_prompt_b.system
        assert "<!-- [PlotPilot-Mod:scene-mod:START:appended] -->" in mod_prompt_b.system
        assert "强化环境光影与冷场留白。" in mod_prompt_b.system
    finally:
        db.close_all(skip_checkpoint=True)


@pytest.mark.asyncio
async def test_seed_fallback_when_all_db_versions_replaced_and_standalone_multi_override(tmp_path):
    db = DatabaseConnection(str(tmp_path / "all_replaced.db"))
    try:
        with sqlite_writes_bypass_queue():
            conn = db.get_connection()
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO prompt_templates (id, name, category, is_builtin) VALUES ('t1', 'builtin', 'builtin', 1)")
            conn.execute("INSERT INTO prompt_nodes (id, template_id, node_key, name, is_builtin, active_version_id) VALUES ('n1', 't1', 'chapter-generation-main', '主生成', 1, 'v1')")
            conn.execute(
                "INSERT INTO prompt_versions (id, node_id, version_number, system_prompt, user_template) VALUES "
                "('v1', 'n1', 1, '<!-- [PlotPilot-Mod:only-replaced:START:replaced] -->\nONLY_REPLACED\n<!-- [PlotPilot-Mod:only-replaced:END] -->', '')"
            )
            conn.commit()

        before = _snapshot_tables_digest(db)
        llm = _RecordingConcurrentLLMService()
        svc = ModSandboxTrialService(db_provider=lambda: db, control_service=_FakeControlService(_configured_profile()), llm_service=llm)

        pack = ModTrialPackInput(
            id="multi-pack",
            name="复合协同模组",
            summary="多节点协同",
            overrides=[
                ModTrialOverrideInput(nodeKey="custom-opening-hook", nodeLabel="开篇悬念节点", mode="standalone_node", systemContent="前三百字必须建立直接物理冲突。"),
                ModTrialOverrideInput(nodeKey="voice-guard", nodeLabel="声线守卫", mode="append_protocol", systemContent="对白保留人物口癖。"),
                ModTrialOverrideInput(nodeKey="pacing-tune", nodeLabel="节奏微调", mode="append_protocol", systemContent="短句切分紧张动作。"),
            ],
        )
        res = await svc.run_ab_trial(
            ModSandboxAbTrialRequest(pack=pack, scenario="客栈夜袭", target_words=240)
        )
        assert _snapshot_tables_digest(db) == before
        assert res.target_node_key == "custom-opening-hook"
        assert res.mounted_node_keys == ["custom-opening-hook", "voice-guard", "pacing-tune"]
        base_prompt, mod_prompt = llm.calls[0][0], llm.calls[1][0]
        # Control fell back to in-memory chapter-generation-main seed (no ONLY_REPLACED!)
        assert "ONLY_REPLACED" not in base_prompt.system
        assert "PlotPilot-Mod" not in base_prompt.system
        assert base_prompt.node_key == "chapter-generation-main"
        assert "[同包协同规则 · 声线守卫]" in mod_prompt.system
        assert "[同包协同规则 · 节奏微调]" in mod_prompt.system
    finally:
        db.close_all(skip_checkpoint=True)


def test_strip_all_mod_blocks_removes_nested_or_multiple_markers():
    # Exact F03 reproduction: dangling 'a' START followed by clean baseline,
    # complete 'b' block, more clean baseline, and a later complete 'a' block.
    text = (
        "HEAD\n"
        "<!-- [PlotPilot-Mod:a:START:appended] -->\n"
        "PRESERVE ORIGINAL BASELINE\n"
        "<!-- [PlotPilot-Mod:b:START:appended] -->\n"
        "B PAYLOAD\n"
        "<!-- [PlotPilot-Mod:b:END] -->\n"
        "PRESERVE MORE BASELINE\n"
        "<!-- [PlotPilot-Mod:a:START:appended] -->\n"
        "A PAYLOAD\n"
        "<!-- [PlotPilot-Mod:a:END] -->\n"
        "TAIL"
    )
    cleaned = strip_all_mod_blocks(text)
    assert "B PAYLOAD" not in cleaned
    assert "A PAYLOAD" not in cleaned
    assert "PlotPilot-Mod" not in cleaned
    assert "HEAD" in cleaned
    assert "PRESERVE ORIGINAL BASELINE" in cleaned
    assert "PRESERVE MORE BASELINE" in cleaned
    assert "TAIL" in cleaned


@pytest.mark.asyncio
async def test_round2_malformed_db_version_falls_back_to_earlier_clean_version_and_f04_cancel_drain_closes_provider(tmp_path):
    db = DatabaseConnection(str(tmp_path / "malformed_ver.db"))
    try:
        with sqlite_writes_bypass_queue():
            conn = db.get_connection()
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO prompt_templates (id, name, category, is_builtin) VALUES ('t1', 'builtin', 'builtin', 1)")
            conn.execute("INSERT INTO prompt_nodes (id, template_id, node_key, name, is_builtin, active_version_id) VALUES ('n1', 't1', 'chapter-generation-main', '主生成', 1, 'v2')")
            conn.execute(
                "INSERT INTO prompt_versions (id, node_id, version_number, system_prompt, user_template) VALUES "
                "('v1', 'n1', 1, 'CLEAN_V1_WELL_FORMED', ''), "
                "('v2', 'n1', 2, 'CLEAN_HEAD\n<!-- [PlotPilot-Mod:broken:START:appended] -->\nUNCLOSED_MOD_PAYLOAD', '')"
            )
            conn.commit()

        llm = _RecordingConcurrentLLMService()
        svc = ModSandboxTrialService(db_provider=lambda: db, control_service=_FakeControlService(_configured_profile()), llm_service=llm)
        await svc.run_ab_trial(ModSandboxAbTrialRequest(pack=_valid_pack(), scenario="雨夜试探", target_words=260))
        base_sys = llm.calls[0][0].system
        assert "CLEAN_V1_WELL_FORMED" in base_sys and "UNCLOSED_MOD_PAYLOAD" not in base_sys

        events: list[str] = []
        sibling_cancelled = asyncio.Event()
        release_sibling_cleanup = asyncio.Event()

        class _EphemeralRaceProvider(LLMService):
            def __init__(self) -> None:
                self._call_idx = 0
                self.closed = False

            async def generate(self, prompt: Prompt, config: GenerationConfig) -> GenerationResult:
                self._call_idx += 1
                if self._call_idx == 1:
                    await asyncio.sleep(0.01)
                    raise RuntimeError("primary branch failed")
                try:
                    await asyncio.sleep(10.0)
                except asyncio.CancelledError:
                    events.append("sibling_cancel_started")
                    sibling_cancelled.set()
                    await release_sibling_cleanup.wait()
                    events.append("sibling_cancel_finished")
                    raise
                return GenerationResult(content="unused")

            async def stream_generate(self, prompt: Prompt, config: GenerationConfig):
                yield ""

            async def aclose(self) -> None:
                events.append("provider_closed")
                self.closed = True

        race_provider = _EphemeralRaceProvider()
        from infrastructure.ai import provider_factory as pf_mod

        orig_create = pf_mod.LLMProviderFactory.create_from_resolved_profile
        pf_mod.LLMProviderFactory.create_from_resolved_profile = lambda self, prof: race_provider  # type: ignore[assignment]
        try:
            svc_race = ModSandboxTrialService(db_provider=lambda: db, control_service=_FakeControlService(_configured_profile()), llm_service=None)
            parent_task = asyncio.create_task(svc_race.run_ab_trial(ModSandboxAbTrialRequest(pack=_valid_pack(), scenario="并发取消竞态", target_words=240)))
            await asyncio.wait_for(sibling_cancelled.wait(), timeout=2.0)
            parent_task.cancel()
            await asyncio.sleep(0.02)
            assert not race_provider.closed
            release_sibling_cleanup.set()
            with pytest.raises(asyncio.CancelledError):
                await parent_task
            await asyncio.sleep(0.02)
            assert race_provider.closed is True
            assert events == ["sibling_cancel_started", "sibling_cancel_finished", "provider_closed"]
        finally:
            pf_mod.LLMProviderFactory.create_from_resolved_profile = orig_create  # type: ignore[assignment]
    finally:
        db.close_all(skip_checkpoint=True)


def test_sqlite_write_guard_rejects_deliberate_noop_update_ddl_and_enqueued_writes(
    tmp_path, monkeypatch
):
    """Self-test proving _forbid_sqlite_writes immediately detects & rejects no-op writes, DDL, transactions, and queue writes."""
    db = _seed_trial_db(tmp_path)
    try:
        with _forbid_sqlite_writes(db, monkeypatch) as guard:
            # 1) Deliberate no-op write assigning existing column value to itself (digest alone would miss this!)
            with sqlite_writes_bypass_queue():
                with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
                    db.get_connection().execute(
                        "UPDATE novels SET title = title WHERE id = 'novel-1'"
                    )
            assert any(v[0] == "sqlite_authorizer" and v[1] == sqlite3.SQLITE_UPDATE for v in guard.violations)

            # 2) Deliberate write via write_dispatch queue path (when direct writes & writer thread are off)
            from infrastructure.persistence.database import write_dispatch as wd_mod

            guard.violations.clear()
            with pytest.MonkeyPatch.context() as mp_q:
                mp_q.setattr(wd_mod, "allow_direct_sqlite_writes", lambda: False)
                mp_q.setattr(wd_mod, "is_sqlite_writer_thread", lambda: False)
                with pytest.raises(AssertionError, match="Prohibited enqueue_execute_sql"):
                    db.execute("UPDATE novels SET title = title WHERE id = 'novel-1'")
            assert any(v[0] == "enqueue_execute_sql" for v in guard.violations)

            # 3) Deliberate DDL & transaction start
            guard.violations.clear()
            with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
                db.get_connection().execute("CREATE TEMP TABLE sneaky_tmp (x INTEGER)")
            assert any(v[0] == "sqlite_authorizer" for v in guard.violations)

            guard.violations.clear()
            with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
                db.get_connection().execute("BEGIN IMMEDIATE")
            assert any(v[0] == "sqlite_authorizer" and v[1] == sqlite3.SQLITE_TRANSACTION for v in guard.violations)

        # 4) R3-B01 self-tests:
        #    (a) A managed getter that opens a fresh sqlite3.connect and attempts a no-op UPDATE BEFORE returning conn;
        #    (b) An unrelated raw sqlite3.connect opened concurrently from another thread while the managed getter is running.
        db_file = str(tmp_path / "trial.db")
        getter_entered = threading.Event()
        allow_getter_continue = threading.Event()
        concurrent_exc: list[BaseException] = []

        class _SneakyGetterAdapter:
            def __init__(self) -> None:
                self._warm = sqlite3.connect(db_file, check_same_thread=False)
                self._warm.row_factory = sqlite3.Row
                self._all_connections = [self._warm]
                self._first = True

            def get_connection(self) -> sqlite3.Connection:
                if self._first:
                    self._first = False
                    return self._warm
                getter_entered.set()
                allow_getter_continue.wait(timeout=2.0)
                fresh = sqlite3.connect(db_file, check_same_thread=False)
                try:
                    fresh.execute("UPDATE novels SET title = title WHERE id = 'novel-1'")
                    fresh.commit()
                finally:
                    fresh.close()
                return self._warm

            def close(self) -> None:
                self._warm.close()

        sneaky = _SneakyGetterAdapter()
        try:
            with _forbid_sqlite_writes(sneaky, monkeypatch) as sneaky_guard:
                def _concurrent_raw_writer() -> None:
                    assert getter_entered.wait(timeout=2.0)
                    raw_side = sqlite3.connect(db_file, check_same_thread=False)
                    try:
                        raw_side.execute("UPDATE novels SET title = title WHERE id = 'novel-1'")
                    except BaseException as exc:
                        concurrent_exc.append(exc)
                    finally:
                        raw_side.close()
                        allow_getter_continue.set()

                worker = threading.Thread(target=_concurrent_raw_writer)
                worker.start()
                try:
                    with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
                        sneaky.get_connection()
                finally:
                    allow_getter_continue.set()
                    worker.join(timeout=2.0)

                assert len(concurrent_exc) == 1
                assert isinstance(concurrent_exc[0], sqlite3.DatabaseError)
                update_violations = [
                    v for v in sneaky_guard.violations
                    if v[0] == "sqlite_authorizer" and v[1] == sqlite3.SQLITE_UPDATE
                ]
                assert len(update_violations) == 2
        finally:
            sneaky.close()

        # 5) R3-B02 self-test: valid user table `sqliteAudit` (starts with `sqlite` + non-underscore) is included & hashed
        with sqlite_writes_bypass_queue():
            conn = db.get_connection()
            conn.execute("CREATE TABLE sqliteAudit (id INTEGER PRIMARY KEY, value TEXT)")
            conn.execute("INSERT INTO sqliteAudit (id, value) VALUES (1, 'alpha')")
            conn.commit()
        snap_alpha = _snapshot_tables_digest(db)
        assert "sqliteAudit" in snap_alpha
        assert snap_alpha["sqliteAudit"][0] == 1

        with sqlite_writes_bypass_queue():
            conn = db.get_connection()
            conn.execute("UPDATE sqliteAudit SET value = 'beta' WHERE id = 1")
            conn.commit()
        snap_beta = _snapshot_tables_digest(db)
        assert snap_beta["sqliteAudit"] != snap_alpha["sqliteAudit"]
        assert snap_beta != snap_alpha
    finally:
        db.close_all(skip_checkpoint=True)


@pytest.mark.asyncio
async def test_zero_writes_across_missing_schema_unseeded_and_real_configured_states(
    tmp_path, monkeypatch
):
    """Proves 100% zero SQLite writes under authorizer + write-queue guard across:
    (1) genuinely empty/missing-schema DB (0 tables),
    (2) initialized schema but unseeded & unconfigured DB,
    (3) configured DB using REAL LLMControlService profile resolution + REAL LLMProviderFactory.
    """
    from infrastructure.ai.providers.openai_provider import OpenAIProvider

    # --- State 1: Genuinely empty / missing-schema SQLite DB (0 tables in sqlite_master) ---
    raw_empty_db = _RawSQLiteAdapter(str(tmp_path / "missing_schema.db"))
    try:
        before_empty = _snapshot_tables_digest(raw_empty_db)
        assert before_empty["__sqlite_master__"][0] == 0

        real_ctrl_empty = LLMControlService(db_provider=lambda: raw_empty_db)
        svc_empty_unconf = ModSandboxTrialService(db_provider=lambda: raw_empty_db, control_service=real_ctrl_empty)
        with _forbid_sqlite_writes(raw_empty_db, monkeypatch) as guard_s1a:
            with pytest.raises(LLMNotConfiguredError):
                await svc_empty_unconf.run_ab_trial(ModSandboxAbTrialRequest(pack=_valid_pack(), scenario="空库无表未配置测试", target_words=240))
        assert guard_s1a.violations == []
        assert _snapshot_tables_digest(raw_empty_db) == before_empty

        llm_s1b = _RecordingConcurrentLLMService()
        svc_empty_seed = ModSandboxTrialService(db_provider=lambda: raw_empty_db, control_service=_FakeControlService(_configured_profile()), llm_service=llm_s1b)
        with _forbid_sqlite_writes(raw_empty_db, monkeypatch) as guard_s1b:
            res_s1b = await svc_empty_seed.run_ab_trial(ModSandboxAbTrialRequest(pack=_valid_pack(), scenario="空库纯内存种子试写", target_words=240))
        assert guard_s1b.violations == []
        assert res_s1b.pack_id == "candidate-pack-1"
        assert _snapshot_tables_digest(raw_empty_db) == before_empty
    finally:
        raw_empty_db.close()

    unseeded_db = DatabaseConnection(str(tmp_path / "unseeded_schema_only.db"))
    try:
        before_unseeded = _snapshot_tables_digest(unseeded_db)
        assert before_unseeded["prompt_nodes"][0] == 0
        assert before_unseeded["llm_profiles"][0] == 0
        assert before_unseeded["llm_config_meta"][0] == 0

        real_ctrl_unseeded = LLMControlService(db_provider=lambda: unseeded_db)
        svc_unseeded = ModSandboxTrialService(db_provider=lambda: unseeded_db, control_service=real_ctrl_unseeded)
        with _forbid_sqlite_writes(unseeded_db, monkeypatch) as guard_s2:
            with pytest.raises(LLMNotConfiguredError):
                await svc_unseeded.run_ab_trial(ModSandboxAbTrialRequest(pack=_valid_pack(), scenario="已建表未播种未配置测试", target_words=300))
        assert guard_s2.violations == []
        assert _snapshot_tables_digest(unseeded_db) == before_unseeded
    finally:
        unseeded_db.close_all(skip_checkpoint=True)

    configured_db = _seed_trial_db(tmp_path)
    try:
        with sqlite_writes_bypass_queue():
            real_ctrl_conf = LLMControlService(db_provider=lambda: configured_db)
            real_ctrl_conf.save_config(LLMControlConfig(
                active_profile_id="prof-real-main",
                profiles=[_configured_profile().model_copy(update={"id": "prof-real-main", "model": "gpt-real-configured-main"})],
            ))

        before_configured = _snapshot_tables_digest(configured_db)
        provider_calls: list[tuple[Prompt, GenerationConfig]] = []

        async def _stub_openai_generate(self_prov: OpenAIProvider, prompt: Prompt, config: Optional[GenerationConfig] = None) -> GenerationResult:
            eff_cfg = config or GenerationConfig()
            provider_calls.append((prompt, eff_cfg))
            label = "处理组" if "PlotPilot-Mod:" in prompt.system else "对照组"
            return GenerationResult(content=f"{label}实测生成：檐角铁马随风轻响，陈砚按住案卷未发一言。", token_usage=TokenUsage(input_tokens=80, output_tokens=45))

        monkeypatch.setattr(OpenAIProvider, "generate", _stub_openai_generate)
        fresh_real_ctrl = LLMControlService(db_provider=lambda: configured_db)
        svc_real_conf = ModSandboxTrialService(db_provider=lambda: configured_db, control_service=fresh_real_ctrl, llm_service=None)
        with _forbid_sqlite_writes(configured_db, monkeypatch) as guard_s3:
            res_s3 = await svc_real_conf.run_ab_trial(ModSandboxAbTrialRequest(pack=_valid_pack(), novel_id="novel-1", scenario="真实配置解析与临时 Provider 零写验证", target_words=300))
        assert guard_s3.violations == []
        assert _snapshot_tables_digest(configured_db) == before_configured
        assert res_s3.model == "gpt-real-configured-main"
        assert res_s3.novel_title == "青灯诡录"
        assert len(provider_calls) == 2
        assert "CLEAN_V1_SYSTEM_PROMPT" in provider_calls[0][0].system
        assert "PlotPilot-Mod:" not in provider_calls[0][0].system
    finally:
        configured_db.close_all(skip_checkpoint=True)


@pytest.mark.asyncio
async def test_r2_b01_malformed_replaced_and_unsupported_start_kinds_recover_clean_history_or_seed(
    tmp_path, monkeypatch
):
    """Covers R2-B01: trailing-space START:replaced , unsupported START_BROKEN, and nested malformed markers."""
    malformed_variants = [
        "HEAD_FRAGMENT\n<!-- [PlotPilot-Mod:installed:START:replaced ] -->\nMOD_ONLY\n<!-- [PlotPilot-Mod:installed:END] -->",
        "HEAD_FRAGMENT\n<!-- [PlotPilot-Mod:installed:START_BROKEN] -->\nMOD_ONLY\n<!-- [PlotPilot-Mod:installed:END] -->",
        "HEAD_FRAGMENT\n<!-- [PlotPilot-Mod:a:START:appended] -->\n<!-- [PlotPilot-Mod:b:START_BROKEN] -->\n<!-- [PlotPilot-Mod:a:END] -->",
    ]
    for idx, bad_v2_prompt in enumerate(malformed_variants):
        db = DatabaseConnection(str(tmp_path / f"r2_b01_hist_{idx}.db"))
        try:
            with sqlite_writes_bypass_queue():
                conn = db.get_connection()
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("INSERT INTO prompt_templates (id, name, category, is_builtin) VALUES ('t1', 'builtin', 'builtin', 1)")
                conn.execute("INSERT INTO prompt_nodes (id, template_id, node_key, name, is_builtin, active_version_id) VALUES ('n1', 't1', 'chapter-generation-main', '主生成', 1, 'v2')")
                conn.execute("INSERT INTO prompt_versions (id, node_id, version_number, system_prompt, user_template) VALUES ('v1', 'n1', 1, 'CLEAN_V1_CANONICAL_FULL', ''), ('v2', 'n1', 2, ?, '')", (bad_v2_prompt,))
                conn.commit()

            llm = _RecordingConcurrentLLMService()
            svc = ModSandboxTrialService(db_provider=lambda: db, control_service=_FakeControlService(_configured_profile()), llm_service=llm)
            with _forbid_sqlite_writes(db, monkeypatch) as guard:
                await svc.run_ab_trial(ModSandboxAbTrialRequest(pack=_valid_pack(), scenario="畸形标记历史回退", target_words=250))
            assert guard.violations == []
            control_sys = llm.calls[0][0].system
            assert "CLEAN_V1_CANONICAL_FULL" in control_sys
            assert "HEAD_FRAGMENT" not in control_sys
            assert "MOD_ONLY" not in control_sys
            assert "PlotPilot-Mod" not in control_sys
        finally:
            db.close_all(skip_checkpoint=True)

    db_no_hist = DatabaseConnection(str(tmp_path / "r2_b01_seed_only.db"))
    try:
        with sqlite_writes_bypass_queue():
            conn = db_no_hist.get_connection()
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO prompt_templates (id, name, category, is_builtin) VALUES ('t1', 'builtin', 'builtin', 1)")
            conn.execute("INSERT INTO prompt_nodes (id, template_id, node_key, name, is_builtin, active_version_id) VALUES ('n1', 't1', 'chapter-generation-main', '主生成', 1, 'v1')")
            conn.execute("INSERT INTO prompt_versions (id, node_id, version_number, system_prompt, user_template) VALUES ('v1', 'n1', 1, 'HEAD_FRAGMENT\n<!-- [PlotPilot-Mod:installed:START:replaced ] -->\nMOD_ONLY\n<!-- [PlotPilot-Mod:installed:END] -->', '')")
            conn.commit()

        llm_seed = _RecordingConcurrentLLMService()
        svc_seed = ModSandboxTrialService(db_provider=lambda: db_no_hist, control_service=_FakeControlService(_configured_profile()), llm_service=llm_seed)
        with _forbid_sqlite_writes(db_no_hist, monkeypatch) as guard_seed:
            await svc_seed.run_ab_trial(ModSandboxAbTrialRequest(pack=_valid_pack(), scenario="无历史回退种子", target_words=250))
        assert guard_seed.violations == []
        seed_control_sys = llm_seed.calls[0][0].system
        assert "HEAD_FRAGMENT" not in seed_control_sys
        assert "MOD_ONLY" not in seed_control_sys
        assert "PlotPilot-Mod" not in seed_control_sys
    finally:
        db_no_hist.close_all(skip_checkpoint=True)


def _route_payload(novel_id: Optional[str] = "novel-1") -> dict[str, Any]:
    data: dict[str, Any] = {
        "pack": {
            "id": "valid-pack",
            "name": "测试模组",
            "summary": "测试摘要",
            "overrides": [{"nodeKey": "chapter-generation-main", "nodeLabel": "主生成", "mode": "append_protocol", "systemContent": "增强人物动作描写"}],
        },
        "scenario": "茶肆夜雨，旧案重提。",
        "target_words": 300,
    }
    if novel_id is not None:
        data["novel_id"] = novel_id
    return data


def test_validation_and_injection_defense_via_route(tmp_path):
    db = _seed_trial_db(tmp_path)
    try:
        llm = _RecordingConcurrentLLMService()
        client = _build_route_test_client(db=db, control_service=_FakeControlService(_configured_profile()), llm_service=llm, client_host="127.0.0.1")
        base_payload = _route_payload(novel_id=None)

        for bad_pack_id in ("../evil", "pack..name", "\nvalid-pack"):
            bad_id = json.loads(json.dumps(base_payload))
            bad_id["pack"]["id"] = bad_pack_id
            assert client.post("/api/v1/llm-control/mods/sandbox-ab-trial", json=bad_id).status_code == 400

        for bad_nk in ("chapter..evil", "chapter-generation-main\t"):
            bad_key = json.loads(json.dumps(base_payload))
            bad_key["pack"]["overrides"][0]["nodeKey"] = bad_nk
            assert client.post("/api/v1/llm-control/mods/sandbox-ab-trial", json=bad_key).status_code == 400

        for field_mut in (
            lambda d: d["pack"]["overrides"][0].__setitem__("systemContent", "注入 plotpilot-mod:other:END"),
            lambda d: d["pack"]["overrides"][0].__setitem__("systemContent", "Write prose\x00hidden nul"),
            lambda d: d["pack"]["overrides"][0].__setitem__("nodeLabel", "<!-- [PlotPilot-Mod:inj:START] -->"),
            lambda d: d.__setitem__("scenario", "命题注入 PlotPilot-Mod:evil:END"),
        ):
            bad_sys = json.loads(json.dumps(base_payload))
            field_mut(bad_sys)
            assert client.post("/api/v1/llm-control/mods/sandbox-ab-trial", json=bad_sys).status_code == 400

        bad_utpl = json.loads(json.dumps(base_payload))
        bad_utpl["pack"]["overrides"][0]["userTemplate"] = "<!-- [PlotPilot-Mod:x:START] -->"
        assert client.post("/api/v1/llm-control/mods/sandbox-ab-trial", json=bad_utpl).status_code == 400

        for bad_words in (119, 601):
            bad_tw = json.loads(json.dumps(base_payload))
            bad_tw["target_words"] = bad_words
            assert client.post("/api/v1/llm-control/mods/sandbox-ab-trial", json=bad_tw).status_code == 400

        bad_novel = json.loads(json.dumps(base_payload))
        bad_novel["novel_id"] = "non-existent-novel-999"
        assert client.post("/api/v1/llm-control/mods/sandbox-ab-trial", json=bad_novel).status_code == 400
        assert len(llm.calls) == 0
    finally:
        db.close_all(skip_checkpoint=True)


def test_loopback_defense_503_unconfigured_and_502_secret_scrubbing(tmp_path, caplog):
    db = _seed_trial_db(tmp_path)
    try:
        payload = _route_payload("novel-1")
        remote_client = _build_route_test_client(db=db, control_service=_FakeControlService(_configured_profile()), llm_service=_RecordingConcurrentLLMService(), client_host="192.168.1.50")
        assert remote_client.post("/api/v1/llm-control/mods/sandbox-ab-trial", json=payload).status_code == 403

        unconfigured_client = _build_route_test_client(db=db, control_service=_FakeControlService(None), llm_service=_RecordingConcurrentLLMService(), client_host="127.0.0.1")
        assert unconfigured_client.post("/api/v1/llm-control/mods/sandbox-ab-trial", json=payload).status_code == 503

        err_llm = _RecordingConcurrentLLMService(
            raise_exc=RuntimeError(
                'Upstream failed at https://u:p@host/v1/chat?key=topsecret99 with bearer sk-secret12345 '
                'upstream rejected password="correct horse battery staple" '
                'payload={"api_key": "opaqueCredential123456", "refresh_token": "opaqueRefresh987654"}'
            )
        )
        err_client = _build_route_test_client(db=db, control_service=_FakeControlService(_configured_profile()), llm_service=err_llm, client_host="127.0.0.1")
        with caplog.at_level(logging.WARNING, logger="interfaces.api.v1.workbench.mod_sandbox_routes"):
            r_502 = err_client.post("/api/v1/llm-control/mods/sandbox-ab-trial", json=payload)
        assert r_502.status_code == 502
        detail = r_502.json()["detail"]
        log_text = "\n".join(rec.getMessage() for rec in caplog.records)
        assert log_text
        for surface in (detail, log_text):
            for secret in ("sk-secret12345", "u:p@host", "topsecret99", "correct horse battery staple", "opaqueCredential123456", "opaqueRefresh987654"):
                assert secret not in surface
            for redacted in ('password="***"', '"api_key": "***"', '"refresh_token": "***"', "https://***:***@"):
                assert redacted in surface

        ok_llm = _RecordingConcurrentLLMService(require_concurrency=True)
        ok_client = _build_route_test_client(db=db, control_service=_FakeControlService(_configured_profile()), llm_service=ok_llm, client_host="127.0.0.1", tmp_path=tmp_path)
        r_200 = ok_client.post("/api/v1/llm-control/mods/sandbox-ab-trial", json=payload)
        assert r_200.status_code == 200
        body = r_200.json()
        assert body["novel_id"] == "novel-1" and body["novel_title"] == "青灯诡录" and body["model"] == "gpt-test-main"
        assert len(ok_llm.calls) == 2 and ok_llm._saw_concurrent is True
        assert all(cfg.role_hint == "main" for _, cfg in ok_llm.calls)
        assert "青灯诡录" in ok_llm.calls[0][0].user and "陈砚" in ok_llm.calls[0][0].user
    finally:
        db.close_all(skip_checkpoint=True)


def test_b_prod_v12_linear_malformed_marker_extraction_and_stripping():
    repeated_marker = "PlotPilot-Mod:" * 8000
    repeated_unclosed_comment = "<!-- [PlotPilot-Mod:" * 8000
    repeated_shared_bracket = (("<!-- [PlotPilot-Mod:x" * 2000) + "] NOT_ARROW ") * 2
    t0 = time.perf_counter()
    assert _try_extract_well_formed_baseline(repeated_marker) is None
    assert _try_extract_well_formed_baseline(repeated_unclosed_comment) is None
    assert _try_extract_well_formed_baseline(repeated_shared_bracket) is None
    assert strip_all_mod_blocks(repeated_marker) == repeated_marker
    assert strip_all_mod_blocks(repeated_unclosed_comment) == repeated_unclosed_comment
    assert strip_all_mod_blocks(repeated_shared_bracket) == repeated_shared_bracket.strip()
    assert time.perf_counter() - t0 < 0.25
    assert strip_all_mod_blocks("正文前\n<!-- [PlotPilot-Mod:dangling:START] -->\n正文后") == "正文前\n正文后"


