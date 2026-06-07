"""Outline beat partition JSON parsing tests."""
import json

import pytest

from application.engine.dag.plan.outline_beat_planner import _extract_json_payload


def test_extract_json_payload_repairs_missing_comma():
    broken = """
    {
      "atoms": [
        {
          "id": "b1",
          "intent": "主角遭遇伏击"
          "weight": 1,
          "focus": "action"
        }
      ]
    }
    """
    data = _extract_json_payload(broken)
    assert isinstance(data.get("atoms"), list)
    assert len(data["atoms"]) == 1
    assert data["atoms"][0]["intent"] == "主角遭遇伏击"


def test_extract_json_payload_strips_markdown_fence():
    wrapped = """```json
{"atoms": [{"id": "b1", "intent": "开场", "weight": 1}]}
```"""
    data = _extract_json_payload(wrapped)
    assert len(data["atoms"]) == 1


def test_extract_json_payload_raises_on_unrecoverable():
    with pytest.raises(json.JSONDecodeError):
        _extract_json_payload("not json at all")
