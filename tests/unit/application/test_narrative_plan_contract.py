import json

import pytest

from application.narrative_plan_contract import (
    build_plan_contract_section,
    build_state_lock_section,
    load_plan_contract,
    normalize_micro_beats,
    preflight_plan_contract,
)
from infrastructure.persistence.database.connection import DatabaseConnection


@pytest.fixture()
def db(tmp_path):
    conn = DatabaseConnection(str(tmp_path / "plan.db"))
    conn.execute("INSERT INTO novels (id, title, slug) VALUES (?, ?, ?)", ("n1", "测试小说", "n1"))
    conn.execute("INSERT INTO knowledge (id, novel_id) VALUES (?, ?)", ("k1", "n1"))
    conn.execute(
        "INSERT INTO chapters (id, novel_id, number, title, content) VALUES (?, ?, ?, ?, ?)",
        ("c1", "n1", 1, "第一章", ""),
    )
    conn.commit()
    return conn


def test_old_micro_beat_refs_normalize_to_plan_contract():
    contract = normalize_micro_beats(
        "n1",
        1,
        [
            {
                "cast_refs": ["[[char:aqing|阿青]]"],
                "location_refs": ["青云山"],
                "prop_refs": ["[[prop:net|天罗地网]]"],
                "visible_action": "阿青祭出天罗地网。",
            }
        ],
    )

    assert [(e.kind, e.id, e.label, e.bound) for e in contract.active_entities] == [
        ("char", "aqing", "阿青", True),
        ("loc", "青云山", "青云山", False),
        ("prop", "net", "天罗地网", True),
    ]
    assert contract.text_promises[0]["field"] == "visible_action"
    assert "天罗地网" in build_plan_contract_section(contract)


def test_new_contract_fields_are_preserved():
    contract = normalize_micro_beats(
        "n1",
        1,
        [
            {
                "active_entities": [{"kind": "char", "id": "aqing", "label": "阿青"}],
                "state_requirements": [
                    {"entity": "prop:net|天罗地网", "key": "lifecycle_state", "must_be": "ACTIVE"}
                ],
                "state_changes": [
                    {"entity": "prop:net|天罗地网", "key": "lifecycle_state", "from": "ACTIVE", "to": "DAMAGED"}
                ],
                "fact_intents": [
                    {"subject": "char:aqing|阿青", "predicate": "使用", "object": "prop:net|天罗地网"}
                ],
                "forbidden_overrides": ["不可改变林渊身份"],
            }
        ],
    )

    assert contract.state_requirements[0].must_be == "ACTIVE"
    assert contract.state_changes[0].to_value == "DAMAGED"
    assert contract.fact_intents[0].predicate == "使用"
    assert contract.forbidden_overrides == ["不可改变林渊身份"]


def test_preflight_does_not_crash_when_legacy_prop_table_is_absent(db):
    beats = [
        {
            "active_entities": ["prop:net|天罗地网"],
        }
    ]
    db.execute(
        """
        INSERT INTO chapter_summaries (id, knowledge_id, chapter_number, micro_beats)
        VALUES ('cs1', 'k1', 1, ?)
        """,
        (json.dumps(beats, ensure_ascii=False),),
    )
    db.commit()

    result = preflight_plan_contract(db, "n1", 1)

    assert result["missing_entity_ids"] == 1
    assert any(i["type"] == "unknown_entity_anchor" for i in result["issues"])


def test_preflight_reports_missing_anchor_and_state_mismatch(db):
    beats = [
        {
            "active_entities": ["青云山", "prop:net|天罗地网"],
            "state_requirements": [
                {"entity": "prop:net|天罗地网", "key": "lifecycle_state", "must_be": "ACTIVE"}
            ],
        }
    ]
    db.execute(
        """
        INSERT INTO chapter_summaries (id, knowledge_id, chapter_number, micro_beats)
        VALUES ('cs1', 'k1', 1, ?)
        """,
        (json.dumps(beats, ensure_ascii=False),),
    )
    db.execute(
        """
        INSERT INTO unified_props (
            id, novel_id, name, description, aliases_json, prop_category, lifecycle_state,
            introduced_chapter, attributes_json, created_at, updated_at
        ) VALUES ('net', 'n1', '天罗地网', '', '[]', 'OTHER', 'DAMAGED', 1, '{}', 'now', 'now')
        """
    )
    db.commit()

    result = preflight_plan_contract(db, "n1", 1)

    assert result["missing_entity_ids"] == 1
    assert any(i["type"] == "state_requirement_mismatch" for i in result["issues"])
    assert "天罗地网" in result["state_lock"]


def test_state_lock_uses_authoritative_prop_state(db):
    db.execute(
        """
        INSERT INTO chapter_summaries (id, knowledge_id, chapter_number, micro_beats)
        VALUES ('cs1', 'k1', 1, ?)
        """,
        (json.dumps([{"active_entities": ["prop:net|天罗地网"]}], ensure_ascii=False),),
    )
    db.execute(
        """
        INSERT INTO unified_props (
            id, novel_id, name, description, aliases_json, prop_category, lifecycle_state,
            introduced_chapter, attributes_json, created_at, updated_at
        ) VALUES ('net', 'n1', '天罗地网', '', '[]', 'OTHER', 'ACTIVE', 1, '{}', 'now', 'now')
        """
    )
    db.commit()

    assert "当前状态=ACTIVE" in build_state_lock_section(db, "n1", 1)
    assert load_plan_contract(db, "n1", 1).active_entities[0].ref == "prop:net"
