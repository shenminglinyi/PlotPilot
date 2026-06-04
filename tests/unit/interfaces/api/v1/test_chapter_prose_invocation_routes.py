from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from application.core.v1_length_tiers import build_v1_structure_black_box_hint
from domain.ai.services.llm_service import GenerationConfig, GenerationResult
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_ai_invocation_repository import SqliteVariableHubRepository
from infrastructure.persistence.database.write_dispatch import sqlite_writes_bypass_queue
from application.ai_invocation.variable_hub import VariableWrite
from interfaces.api.v1.engine import ai_invocation_routes


class _StreamingLLM:
    async def generate(self, prompt: Prompt, config: GenerationConfig) -> GenerationResult:
        return GenerationResult(
            content="HTTP正文",
            token_usage=TokenUsage(input_tokens=1, output_tokens=1),
        )

    async def stream_generate(self, prompt: Prompt, config: GenerationConfig):
        yield "HTTP"
        yield "正文"


def _wait_for_status(client: TestClient, session_id: str, expected: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    latest = {}
    while time.monotonic() < deadline:
        latest = client.get(f"/ai-invocations/{session_id}").json()
        if latest["session"]["status"] == expected:
            return latest
        time.sleep(0.05)
    raise AssertionError(f"session {session_id} did not reach {expected}: {latest}")


def test_chapter_prose_invocation_http_lifecycle_writes_variable_hub_and_chapters(tmp_path, monkeypatch):
    db = DatabaseConnection(str(tmp_path / "plotpilot-test.db"))

    monkeypatch.setattr(ai_invocation_routes, "get_database", lambda db_path=None: db)
    monkeypatch.setattr("infrastructure.persistence.database.connection.get_database", lambda db_path=None: db)
    monkeypatch.setattr(ai_invocation_routes, "get_llm_service", lambda: _StreamingLLM())

    import infrastructure.ai.prompt_manager as prompt_manager_module
    import infrastructure.ai.prompt_registry as prompt_registry_module

    prompt_manager_module._manager_instance = prompt_manager_module.PromptManager(db)
    prompt_registry_module._registry_instance = prompt_registry_module.PromptRegistry(
        prompt_manager=prompt_manager_module._manager_instance
    )
    with sqlite_writes_bypass_queue():
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO novels (id, title, slug, target_chapters) VALUES (?, ?, ?, ?)",
                ("novel-http", "HTTP小说", "novel-http", 12),
            )

    app = FastAPI()
    app.include_router(ai_invocation_routes.router)
    client = TestClient(app)

    create_payload = {
        "operation": "chapter.generate.prose",
        "node_key": "chapter-prose-generation",
        "policy": "FULL_INTERACTIVE",
        "context": {"novel_id": "novel-http", "chapter_number": 6},
        "variables": {
            "novel_title": "HTTP小说",
            "chapter_number": 6,
            "chapter_outline": "从审阅面板生成正文",
        },
    }
    created = client.post("/ai-invocations", json=create_payload)
    assert created.status_code == 200, created.text
    session_id = created.json()["session"]["id"]
    assert created.json()["session"]["status"] == "awaiting_pre_call_review"

    input_repo = SqliteVariableHubRepository(db)
    assert input_repo.get_value("novel.setup.title", "novel_id:novel-http").value == "HTTP小说"
    assert input_repo.get_value("chapter.outline", "novel_id:novel-http|chapter_number:6").value == "从审阅面板生成正文"

    resumed = client.post(f"/ai-invocations/{session_id}/resume", json={"resumed_by": "test"})
    assert resumed.status_code == 200, resumed.text
    accepted_ready = _wait_for_status(client, session_id, "awaiting_acceptance")
    attempt_id = accepted_ready["attempt"]["id"]
    assert accepted_ready["attempt"]["content"] == "HTTP正文"

    accepted = client.post(
        f"/ai-invocations/{session_id}/accept",
        json={"attempt_id": attempt_id, "accepted_by": "test"},
    )
    assert accepted.status_code == 200, accepted.text
    decision_id = accepted.json()["decision"]["id"]

    committed = client.post(f"/ai-invocations/{session_id}/commits", json={"decision_id": decision_id})
    assert committed.status_code == 200, committed.text
    assert committed.json()["session"]["status"] == "completed"
    assert committed.json()["commit"]["status"] == "succeeded"

    output_repo = SqliteVariableHubRepository(db)
    assert output_repo.get_value("chapter.prose.generated", "novel_id:novel-http|chapter_number:6").value == "HTTP正文"
    assert output_repo.get_value("chapter.prose.accepted", "novel_id:novel-http|chapter_number:6").value == "HTTP正文"
    row = db.fetch_one(
        "SELECT content, status, word_count FROM chapters WHERE novel_id = ? AND number = ?",
        ("novel-http", 6),
    )
    assert row == {"content": "HTTP正文", "status": "draft", "word_count": 6}

    db.close_all(skip_checkpoint=True)


def test_bible_setup_invocation_materializes_inputs_and_get_refreshes_snapshot(tmp_path, monkeypatch):
    db = DatabaseConnection(str(tmp_path / "plotpilot-test-bible-vars.db"))

    monkeypatch.setattr(ai_invocation_routes, "get_database", lambda db_path=None: db)
    monkeypatch.setattr("infrastructure.persistence.database.connection.get_database", lambda db_path=None: db)
    monkeypatch.setattr(ai_invocation_routes, "get_llm_service", lambda: _StreamingLLM())

    import infrastructure.ai.prompt_manager as prompt_manager_module
    import infrastructure.ai.prompt_registry as prompt_registry_module

    prompt_manager_module._manager_instance = prompt_manager_module.PromptManager(db)
    prompt_registry_module._registry_instance = prompt_registry_module.PromptRegistry(
        prompt_manager=prompt_manager_module._manager_instance
    )

    app = FastAPI()
    app.include_router(ai_invocation_routes.router)
    client = TestClient(app)
    internal_hint = build_v1_structure_black_box_hint("standard", 500, 2000)
    author_premise = "旧设定：少年在海底城觉醒"

    created = client.post(
        "/ai-invocations",
        json={
            "operation": "bible.setup.worldbuilding",
            "node_key": "bible-worldbuilding",
            "policy": "FULL_INTERACTIVE",
            "context": {"novel_id": "novel-bible-vars"},
            "variables": {
                "novel_title": "变量小说",
                "premise": f"{internal_hint}\n\n{author_premise}",
                "target_chapters": 120,
                "target_words_per_chapter": 2500,
                "genre_opening_profile": {"source_level": "test", "opening_mechanism": "压迫开局"},
                "genre_reader_contract": {"reader_promise": "升级破局"},
                "genre_rhythm_constraints": {"payoff_interval": "三章一回收"},
            },
        },
    )
    assert created.status_code == 200, created.text
    session_id = created.json()["session"]["id"]

    repo = SqliteVariableHubRepository(db)
    assert repo.get_value("novel.setup.premise", "novel_id:novel-bible-vars").value == author_premise
    assert repo.get_value("novel.setup.summary", "novel_id:novel-bible-vars") is None
    assert repo.get_value("system.worldbuilding.fields_desc", "novel_id:novel-bible-vars") is None
    assert repo.get_value("novel.worldbuilding.full", "novel_id:novel-bible-vars") is None
    assert repo.get_value("novel.genre.opening_profile", "novel_id:novel-bible-vars") is None
    assert repo.get_value("novel.genre.reader_contract", "novel_id:novel-bible-vars") is None

    repo.set_value(
        VariableWrite(
            key="novel.setup.premise",
            value="新设定：变量中心改为天空城债务法则",
            context_key="novel_id:novel-bible-vars",
            source_node_key="test",
        )
    )
    refreshed = client.get(f"/ai-invocations/{session_id}")
    assert refreshed.status_code == 200, refreshed.text
    plan = refreshed.json()["session"]["variable_plan"]
    assert plan["aliases"]["premise"] == "新设定：变量中心改为天空城债务法则"
    assert plan["aliases"]["genre_reader_contract"]["reader_promise"] == "升级破局"
    assert any(
        item["key"] == "premise" and item["value"] == "新设定：变量中心改为天空城债务法则"
        for item in plan["snapshot_items"]
    )
    assert all(item["key"] != "fields_desc" for item in plan["snapshot_items"])
    assert all(item["key"] != "genre_reader_contract" for item in plan["snapshot_items"])
    assert "新设定：变量中心改为天空城债务法则" in refreshed.json()["session"]["prompt_snapshot"]["prompt"]["user"]

    db.close_all(skip_checkpoint=True)


def test_chapter_prose_prompt_draft_custom_variable_can_be_filled_and_resumed(tmp_path, monkeypatch):
    db = DatabaseConnection(str(tmp_path / "plotpilot-test-custom-var.db"))

    monkeypatch.setattr(ai_invocation_routes, "get_database", lambda db_path=None: db)
    monkeypatch.setattr("infrastructure.persistence.database.connection.get_database", lambda db_path=None: db)
    monkeypatch.setattr(ai_invocation_routes, "get_llm_service", lambda: _StreamingLLM())

    import infrastructure.ai.prompt_manager as prompt_manager_module
    import infrastructure.ai.prompt_registry as prompt_registry_module

    prompt_manager_module._manager_instance = prompt_manager_module.PromptManager(db)
    prompt_registry_module._registry_instance = prompt_registry_module.PromptRegistry(
        prompt_manager=prompt_manager_module._manager_instance
    )
    with sqlite_writes_bypass_queue():
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO novels (id, title, slug, target_chapters) VALUES (?, ?, ?, ?)",
                ("novel-custom", "变量小说", "novel-custom", 12),
            )

    app = FastAPI()
    app.include_router(ai_invocation_routes.router)
    client = TestClient(app)

    created = client.post(
        "/ai-invocations",
        json={
            "operation": "chapter.generate.prose",
            "node_key": "chapter-prose-generation",
            "policy": "FULL_INTERACTIVE",
            "context": {"novel_id": "novel-custom", "chapter_number": 3},
            "variables": {
                "novel_title": "变量小说",
                "chapter_number": 3,
                "chapter_outline": "补齐自定义变量后生成正文",
            },
        },
    )
    assert created.status_code == 200, created.text
    session_id = created.json()["session"]["id"]
    template = created.json()["session"]["prompt_snapshot"]["template_prompt"]

    saved = client.put(
        f"/ai-invocations/{session_id}/prompt-draft",
        json={
            "system_template": template["system"],
            "user_template": template["user"] + "\n特殊要求：{{chapter.special_requirement}}",
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["session"]["status"] == "blocked"
    assert "chapter_special_requirement" in saved.json()["session"]["variable_plan"]["required_missing"]

    updated = client.put(
        f"/ai-invocations/{session_id}/variables",
        json={"values": {"chapter_special_requirement": "雨夜压迫感"}, "updated_by": "test"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["session"]["status"] == "awaiting_pre_call_review"
    assert updated.json()["session"]["variable_plan"]["required_missing"] == []

    variable_repo = SqliteVariableHubRepository(db)
    stored = variable_repo.get_value(
        "chapter.special_requirement",
        "novel_id:novel-custom|chapter_number:3",
    )
    assert stored is not None and stored.value == "雨夜压迫感"

    resumed = client.post(f"/ai-invocations/{session_id}/resume", json={"resumed_by": "test"})
    assert resumed.status_code == 200, resumed.text
    accepted_ready = _wait_for_status(client, session_id, "awaiting_acceptance")
    assert accepted_ready["attempt"]["content"] == "HTTP正文"

    db.close_all(skip_checkpoint=True)


def test_chapter_prose_commit_can_promote_prompt_draft_to_cpms(tmp_path, monkeypatch):
    db = DatabaseConnection(str(tmp_path / "plotpilot-test-prose-commit-prompt.db"))

    monkeypatch.setattr(ai_invocation_routes, "get_database", lambda db_path=None: db)
    monkeypatch.setattr("infrastructure.persistence.database.connection.get_database", lambda db_path=None: db)
    monkeypatch.setattr(ai_invocation_routes, "get_llm_service", lambda: _StreamingLLM())

    import infrastructure.ai.prompt_manager as prompt_manager_module
    import infrastructure.ai.prompt_registry as prompt_registry_module

    prompt_manager_module._manager_instance = prompt_manager_module.PromptManager(db)
    prompt_registry_module._registry_instance = prompt_registry_module.PromptRegistry(
        prompt_manager=prompt_manager_module._manager_instance
    )
    with sqlite_writes_bypass_queue():
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO novels (id, title, slug, target_chapters) VALUES (?, ?, ?, ?)",
                ("novel-commit-prompt", "提示词小说", "novel-commit-prompt", 12),
            )

    app = FastAPI()
    app.include_router(ai_invocation_routes.router)
    client = TestClient(app)

    manager = prompt_manager_module._manager_instance
    before_node = manager.get_node("chapter-prose-generation", by_key=True)
    assert before_node is not None
    before_version_id = before_node.active_version_id
    before_user_template = before_node.get_active_user_template()

    created = client.post(
        "/ai-invocations",
        json={
            "operation": "chapter.generate.prose",
            "node_key": "chapter-prose-generation",
            "policy": "FULL_INTERACTIVE",
            "context": {"novel_id": "novel-commit-prompt", "chapter_number": 2},
            "variables": {
                "novel_title": "提示词小说",
                "chapter_number": 2,
                "chapter_outline": "提交后应覆写 CPMS 提示词",
            },
        },
    )
    assert created.status_code == 200, created.text
    session_id = created.json()["session"]["id"]
    template = created.json()["session"]["prompt_snapshot"]["template_prompt"]

    suffix = "\n额外要求：生成时增强临场感与压迫感。"
    saved = client.put(
        f"/ai-invocations/{session_id}/prompt-draft",
        json={
            "system_template": template["system"],
            "user_template": template["user"] + suffix,
        },
    )
    assert saved.status_code == 200, saved.text

    resumed = client.post(f"/ai-invocations/{session_id}/resume", json={"resumed_by": "test"})
    assert resumed.status_code == 200, resumed.text
    accepted_ready = _wait_for_status(client, session_id, "awaiting_acceptance")
    attempt_id = accepted_ready["attempt"]["id"]

    accepted = client.post(
        f"/ai-invocations/{session_id}/accept",
        json={
            "attempt_id": attempt_id,
            "accepted_by": "test",
            "commit_prompt_version": True,
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["decision"]["commit_prompt_version"] is True
    decision_id = accepted.json()["decision"]["id"]

    committed = client.post(f"/ai-invocations/{session_id}/commits", json={"decision_id": decision_id})
    assert committed.status_code == 200, committed.text
    steps = committed.json()["commit"]["steps"]
    prompt_step = next(step for step in steps if step["name"] == "commit_prompt_version")
    assert prompt_step["status"] == "succeeded"
    assert prompt_step["result"]["skipped"] is False

    after_node = manager.get_node("chapter-prose-generation", by_key=True)
    assert after_node is not None
    assert after_node.active_version_id != before_version_id
    assert after_node.get_active_user_template() == before_user_template + suffix

    created_again = client.post(
        "/ai-invocations",
        json={
            "operation": "chapter.generate.prose",
            "node_key": "chapter-prose-generation",
            "policy": "FULL_INTERACTIVE",
            "context": {"novel_id": "novel-commit-prompt", "chapter_number": 3},
            "variables": {
                "novel_title": "提示词小说",
                "chapter_number": 3,
                "chapter_outline": "下一章应读取 CPMS 新提示词",
            },
        },
    )
    assert created_again.status_code == 200, created_again.text
    next_template = created_again.json()["session"]["prompt_snapshot"]["template_prompt"]["user"]
    assert next_template == before_user_template + suffix

    db.close_all(skip_checkpoint=True)


def test_chapter_prose_get_refresh_keeps_setup_snapshot_without_prompt_injection(tmp_path, monkeypatch):
    db = DatabaseConnection(str(tmp_path / "plotpilot-test-prose-snapshot.db"))

    monkeypatch.setattr(ai_invocation_routes, "get_database", lambda db_path=None: db)
    monkeypatch.setattr("infrastructure.persistence.database.connection.get_database", lambda db_path=None: db)
    monkeypatch.setattr(ai_invocation_routes, "get_llm_service", lambda: _StreamingLLM())

    import infrastructure.ai.prompt_manager as prompt_manager_module
    import infrastructure.ai.prompt_registry as prompt_registry_module

    prompt_manager_module._manager_instance = prompt_manager_module.PromptManager(db)
    prompt_registry_module._registry_instance = prompt_registry_module.PromptRegistry(
        prompt_manager=prompt_manager_module._manager_instance
    )
    with sqlite_writes_bypass_queue():
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO novels (id, title, slug, target_chapters) VALUES (?, ?, ?, ?)",
                ("novel-snapshot", "快照小说", "novel-snapshot", 12),
            )

    variable_repo = SqliteVariableHubRepository(db)
    variable_repo.set_value(
        VariableWrite(
            key="novel.characters.list",
            value=[{"name": "变量角色"}],
            context_key="novel_id:novel-snapshot",
            source_node_key="test",
            value_type="list",
            display_name="角色列表",
            scope="novel",
            stage="characters",
        )
    )
    variable_repo.set_value(
        VariableWrite(
            key="novel.worldbuilding.core_rules",
            value={"power_system": "变量武道"},
            context_key="novel_id:novel-snapshot",
            source_node_key="test",
            value_type="object",
            display_name="核心法则",
            scope="novel",
            stage="worldbuilding",
        )
    )

    app = FastAPI()
    app.include_router(ai_invocation_routes.router)
    client = TestClient(app)

    created = client.post(
        "/ai-invocations",
        json={
            "operation": "chapter.generate.prose",
            "node_key": "chapter-prose-generation",
            "policy": "FULL_INTERACTIVE",
            "context": {"novel_id": "novel-snapshot", "chapter_number": 1},
            "variables": {
                "novel_title": "快照小说",
                "chapter_number": 1,
                "chapter_outline": "生成正文",
            },
        },
    )
    assert created.status_code == 200, created.text
    session_id = created.json()["session"]["id"]

    refreshed = client.get(f"/ai-invocations/{session_id}")
    assert refreshed.status_code == 200, refreshed.text
    plan = refreshed.json()["session"]["variable_plan"]
    keys = {item["variable_key"] for item in plan["snapshot_items"]}
    group_ids = {group["id"] for group in plan["snapshot_groups"]}

    assert "novel.characters.list" in keys
    assert "novel.worldbuilding.core_rules" in keys
    assert "novel:characters" in group_ids
    assert "novel:worldbuilding" in group_ids
    prompt_user = refreshed.json()["session"]["prompt_snapshot"]["prompt"]["user"]
    assert "变量角色" not in prompt_user
    assert "变量武道" not in prompt_user

    db.close_all(skip_checkpoint=True)
