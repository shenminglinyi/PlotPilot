"""世界观 schema 归一化：只接受约定字段。"""
from application.world.worldbuilding_schema import canonicalize_dimension_fields


def test_only_contract_keys_are_kept():
    raw = {
        "power_system": "修行者通过吸收劫气提升境界",
        "cost_and_limitation": "每次境界突破必须渡劫，失败率随境界指数级上升",
        "name": "劫力体系",
        "essence": "自创字段不应被猜测合并",
        "存在": "中文自创字段不应生成额外框",
    }

    out = canonicalize_dimension_fields("core_rules", raw)

    assert "name" not in out
    assert "essence" not in out
    assert "存在" not in out
    assert set(out) == {"power_system", "cost_and_limitation"}
    assert "劫气" in out["power_system"]
    assert "渡劫" in out["cost_and_limitation"]
