from application.codex.chronicles_service import build_chronicles_rows


def test_build_chronicles_rows_marks_candidate_accept_snapshot():
    rows = build_chronicles_rows(
        timeline_notes=[],
        snapshots=[
            {
                "id": "snapshot-1",
                "trigger_type": "MANUAL",
                "name": "[候选稿采纳] 第1章 · kimi",
                "branch_name": "main",
                "created_at": "2026-04-27T12:00:00",
                "description": "采纳 Kimi 候选稿",
                "chapter_pointers": ["chapter-1"],
            }
        ],
        id_to_number={"chapter-1": 1},
    )

    snapshots = rows[0]["snapshots"]
    assert snapshots[0]["origin_type"] == "candidate_accept"
    assert snapshots[0]["candidate_source"] == "kimi"
