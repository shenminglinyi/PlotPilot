from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from domain.ai.services.llm_service import GenerationConfig, GenerationResult
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_ai_invocation_repository import SqliteVariableHubRepository
from infrastructure.persistence.database.write_dispatch import sqlite_writes_bypass_queue
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
    assert input_repo.get_value("novel.title", "novel_id:novel-http").value == "HTTP小说"
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
