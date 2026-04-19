# tests/integration/interfaces/api/v1/test_foreshadow_ledger_api.py
import pytest
from fastapi.testclient import TestClient

from domain.novel.value_objects.novel_id import NovelId
from interfaces.api.dependencies import get_foreshadowing_repository


class TestForeshadowLedgerAPI:
    """伏笔手账本 API（SQLite）"""

    @pytest.fixture
    def novel_id(self):
        return "test-novel-123"

    @pytest.fixture
    def setup_registry(self, db, client, novel_id):
        db.execute(
            "INSERT OR IGNORE INTO novels (id, title, slug, target_chapters) VALUES (?, ?, ?, ?)",
            (novel_id, "Foreshadow Ledger Test", novel_id, 100),
        )
        db.get_connection().commit()

        repo = get_foreshadowing_repository()
        registry = repo.get_by_novel_id(NovelId(novel_id))
        assert registry is not None

        for e in list(registry.subtext_entries):
            try:
                registry.remove_subtext_entry(e.id)
            except Exception:
                pass
        repo.save(registry)

        yield registry

        registry = repo.get_by_novel_id(NovelId(novel_id))
        if registry:
            for e in list(registry.subtext_entries):
                try:
                    registry.remove_subtext_entry(e.id)
                except Exception:
                    pass
            repo.save(registry)

    def test_create_subtext_entry(self, client: TestClient, novel_id, setup_registry):
        response = client.post(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger",
            json={
                "entry_id": "entry-001",
                "chapter": 5,
                "character_id": "char-001",
                "question": "主角的真实身份究竟是什么？",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "entry-001"
        assert data["chapter"] == 5
        assert data["character_id"] == "char-001"
        assert data["question"] == "主角的真实身份究竟是什么？"
        assert data["status"] == "pending"
        assert data["consumed_at_chapter"] is None

    def test_create_duplicate_entry(self, client, novel_id, setup_registry):
        client.post(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger",
            json={
                "entry_id": "entry-002",
                "chapter": 5,
                "character_id": "char-001",
                "question": "线索A",
            },
        )

        response = client.post(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger",
            json={
                "entry_id": "entry-002",
                "chapter": 6,
                "character_id": "char-002",
                "question": "线索B",
            },
        )

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_list_subtext_entries(self, client, novel_id, setup_registry):
        client.post(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger",
            json={
                "entry_id": "entry-003",
                "chapter": 5,
                "character_id": "char-001",
                "question": "疑问1",
            },
        )
        client.post(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger",
            json={
                "entry_id": "entry-004",
                "chapter": 6,
                "character_id": "char-002",
                "question": "疑问2",
            },
        )

        response = client.get(f"/api/v1/novels/{novel_id}/foreshadow-ledger")

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2
        assert any(e["id"] == "entry-003" for e in data)
        assert any(e["id"] == "entry-004" for e in data)

    def test_list_subtext_entries_by_status(self, client, novel_id, setup_registry):
        client.post(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger",
            json={
                "entry_id": "entry-005",
                "chapter": 5,
                "character_id": "char-001",
                "question": "疑问",
            },
        )

        response = client.get(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger",
            params={"status": "pending"},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(e["status"] == "pending" for e in data)

    def test_get_subtext_entry(self, client, novel_id, setup_registry):
        client.post(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger",
            json={
                "entry_id": "entry-006",
                "chapter": 5,
                "character_id": "char-001",
                "question": "疑问",
            },
        )

        response = client.get(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger/entry-006",
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "entry-006"
        assert data["question"] == "疑问"

    def test_get_nonexistent_entry(self, client, novel_id, setup_registry):
        response = client.get(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger/nonexistent",
        )

        assert response.status_code == 404

    def test_update_subtext_entry(self, client, novel_id, setup_registry):
        client.post(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger",
            json={
                "entry_id": "entry-007",
                "chapter": 5,
                "character_id": "char-001",
                "question": "原始疑问",
            },
        )

        response = client.put(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger/entry-007",
            json={
                "question": "更新后的疑问",
                "status": "consumed",
                "consumed_at_chapter": 10,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["question"] == "更新后的疑问"
        assert data["status"] == "consumed"
        assert data["consumed_at_chapter"] == 10

    def test_delete_subtext_entry(self, client, novel_id, setup_registry):
        client.post(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger",
            json={
                "entry_id": "entry-008",
                "chapter": 5,
                "character_id": "char-001",
                "question": "疑问",
            },
        )

        response = client.delete(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger/entry-008",
        )

        assert response.status_code == 204

        response = client.get(
            f"/api/v1/novels/{novel_id}/foreshadow-ledger/entry-008",
        )
        assert response.status_code == 404
