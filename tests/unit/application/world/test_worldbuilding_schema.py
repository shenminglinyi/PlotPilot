"""世界观 schema 归一化：LLM 自创键 → 规范字段"""
from application.world.worldbuilding_schema import canonicalize_dimension_fields


def test_llm_flat_english_keys_merge_to_canonical_fields():
    """用户反馈的 name/essence/core_cost 应合并为 power_system / cost_and_limitation。"""
    raw = {
        "name": "劫力体系",
        "essence": "修行者通过吸收劫气提升境界",
        "core_cost": "每次境界突破必须渡劫，失败率随境界指数级上升",
    }
    out = canonicalize_dimension_fields("core_rules", raw)
    assert "name" not in out
    assert "essence" not in out
    assert "core_cost" not in out
    assert "power_system" in out
    assert "劫力体系" in out["power_system"]
    assert "劫气" in out["power_system"]
    assert "cost_and_limitation" in out
    assert "渡劫" in out["cost_and_limitation"]
