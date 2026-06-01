"""世界观字段展平为中文正文"""
from application.world.services.worldbuilding_field_text import (
    normalize_dimension_fields,
    worldbuilding_value_to_prose,
)


def test_nested_dict_becomes_chinese_prose_not_python_repr():
    raw = {
        "power_system": {
            "name": "劫力体系",
            "essence": "吸收劫气修炼",
            "realm_structure": [
                {"tier": 1, "name": "凝劫境", "description": "凝聚劫核", "cost": "留下劫痕"},
            ],
        }
    }
    out = normalize_dimension_fields(raw)
    assert "power_system" in out
    text = out["power_system"]
    assert "劫力体系" in text
    assert "凝劫境" in text
    assert "tier" not in text
    assert "realm_structure" not in text
    assert "{" not in text


def test_list_of_regions_flattened():
    prose = worldbuilding_value_to_prose(
        [{"name": "北荒", "terrain": "雷暴平原", "survival_rule": "猎杀劫兽"}]
    )
    assert "北荒" in prose
    assert "雷暴" in prose
    assert "name" not in prose


def test_json_key_labels_are_loaded_from_worldbuilding_contract():
    prose = worldbuilding_value_to_prose({"underground_trade": "只作为字段标签配置验证"})

    assert "非公开交易" in prose
    assert "underground_trade" not in prose
