"""推断证据全链路集成测试（SQLite + FastAPI，不经 FileKnowledge 覆盖）。

覆盖：书目创建 → story_nodes(chapter) + triples(chapter_inferred) + triple_provenance
→ GET inference-evidence → DELETE 单条推断 → 按章撤销。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from application import paths as paths_mod
from infrastructure.persistence.database import connection as conn_mod
from interfaces.main import app


NOVEL_ID = "e2e-inference-novel"
STORY_NODE_ID = "e2e-sn-chapter-1"
CHAPTER_ROW_ID = "e2e-chapter-row-1"
TRIPLE_A = "e2e-triple-inf-a"
TRIPLE_B = "e2e-triple-inf-b"


@pytest.fixture(autouse=True)
def _clear_dependency_overrides():
    """避免与其它测试文件的 dependency_overrides 串库。"""
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def isolated_sqlite(tmp_path, monkeypatch):
    """独立 SQLite 库（默认文件名 plotpilot.db）：与 application.paths.DATA_DIR 及 get_database 对齐。"""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(paths_mod, "DATA_DIR", data_dir)

    db_path = str(data_dir / "plotpilot.db")
    monkeypatch.setattr(conn_mod, "_db_instance", None)
    db = conn_mod.DatabaseConnection(db_path)
    monkeypatch.setattr(conn_mod, "_db_instance", db)

    def _get_db(*_a, **_kw):
        return db

    monkeypatch.setattr(conn_mod, "get_database", _get_db)

    yield db

    db.close()
    monkeypatch.setattr(conn_mod, "_db_instance", None)


def _seed_chapter_and_inference(conn, *, two_triples: bool = False):
    """插入章节行、结构节点、推断三元组与溯源（直接 SQL，模拟推断流水线落库结果）。"""
    cx = conn.get_connection()
    cx.execute(
        """
        INSERT INTO chapters (id, novel_id, number, title, content, outline, status)
        VALUES (?, ?, 1, '第一章', '', '', 'draft')
        """,
        (CHAPTER_ROW_ID, NOVEL_ID),
    )
    cx.execute(
        """
        INSERT INTO story_nodes (
            id, novel_id, parent_id, node_type, number, title, order_index,
            planning_status, planning_source
        ) VALUES (?, ?, NULL, 'chapter', 1, '第一章', 0, 'confirmed', 'manual')
        """,
        (STORY_NODE_ID, NOVEL_ID),
    )
    for tid, subj in [(TRIPLE_A, "甲"), (TRIPLE_B, "乙")]:
        if not two_triples and tid == TRIPLE_B:
            continue
        cx.execute(
            """
            INSERT INTO triples (
                id, novel_id, subject, predicate, object, chapter_number,
                note, source_type, confidence
            ) VALUES (?, ?, ?, '共现', '丙', 1, '', 'chapter_inferred', 0.85)
            """,
            (tid, NOVEL_ID, subj),
        )
        cx.execute(
            """
            INSERT INTO triple_provenance (
                id, triple_id, novel_id, story_node_id, chapter_element_id, rule_id, role
            ) VALUES (?, ?, ?, ?, 'elem-e2e-1', 'coappearance', 'primary')
            """,
            (f"prov-{tid}", tid, NOVEL_ID, STORY_NODE_ID),
        )
    cx.commit()


client = TestClient(app)


class TestInferenceEvidenceFullChain:
    def test_no_story_node_returns_hint(self, isolated_sqlite):
        r = client.post(
            "/api/v1/novels/",
            json={
                "novel_id": NOVEL_ID,
                "title": "E2E",
                "author": "test",
                "target_chapters": 5,
            },
        )
        assert r.status_code == 201

        resp = client.get(
            f"/api/v1/knowledge-graph/novels/{NOVEL_ID}/chapters/by-number/1/inference-evidence"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        d = body["data"]
        assert d["story_node_id"] is None
        assert d["facts"] == []
        assert "hint" in d

    def test_evidence_list_revoke_single_then_chapter(self, isolated_sqlite):
        client.post(
            "/api/v1/novels/",
            json={
                "novel_id": NOVEL_ID,
                "title": "E2E",
                "author": "test",
                "target_chapters": 5,
            },
        )
        _seed_chapter_and_inference(isolated_sqlite, two_triples=True)

        g1 = client.get(
            f"/api/v1/knowledge-graph/novels/{NOVEL_ID}/chapters/by-number/1/inference-evidence"
        )
        assert g1.status_code == 200
        b1 = g1.json()
        assert b1["data"]["story_node_id"] == STORY_NODE_ID
        assert len(b1["data"]["facts"]) == 2

        d1 = client.delete(
            f"/api/v1/knowledge-graph/novels/{NOVEL_ID}/inferred-triples/{TRIPLE_A}"
        )
        assert d1.status_code == 200

        g2 = client.get(
            f"/api/v1/knowledge-graph/novels/{NOVEL_ID}/chapters/by-number/1/inference-evidence"
        )
        ids = {x["fact"]["id"] for x in g2.json()["data"]["facts"]}
        assert ids == {TRIPLE_B}

        d2 = client.delete(
            f"/api/v1/knowledge-graph/novels/{NOVEL_ID}/chapters/by-number/1/inference"
        )
        assert d2.status_code == 200
        st = d2.json()["data"]
        assert st["deleted_inferred_facts"] >= 1

        g3 = client.get(
            f"/api/v1/knowledge-graph/novels/{NOVEL_ID}/chapters/by-number/1/inference-evidence"
        )
        assert g3.json()["data"]["facts"] == []

    def test_revoke_non_inferred_triple_400(self, isolated_sqlite):
        client.post(
            "/api/v1/novels/",
            json={
                "novel_id": NOVEL_ID,
                "title": "E2E",
                "author": "test",
                "target_chapters": 5,
            },
        )
        cx = isolated_sqlite.get_connection()
        cx.execute(
            """
            INSERT INTO chapters (id, novel_id, number, title, content, outline, status)
            VALUES (?, ?, 1, '第一章', '', '', 'draft')
            """,
            (CHAPTER_ROW_ID, NOVEL_ID),
        )
        cx.execute(
            """
            INSERT INTO triples (
                id, novel_id, subject, predicate, object, chapter_number,
                source_type, confidence
            ) VALUES (?, ?, 'X', '是', 'Y', 1, 'manual', 1.0)
            """,
            ("e2e-manual-t", NOVEL_ID),
        )
        cx.commit()

        r = client.delete(
            f"/api/v1/knowledge-graph/novels/{NOVEL_ID}/inferred-triples/e2e-manual-t"
        )
        assert r.status_code == 400
