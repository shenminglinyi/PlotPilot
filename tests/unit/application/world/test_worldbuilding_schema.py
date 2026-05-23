"""世界观 schema 归一化：只接受约定字段。"""
from application.world.worldbuilding_schema import (
    canonicalize_dimension_fields,
    validate_complete_dimension_fields,
)


def test_only_contract_keys_are_kept():
    raw = {
        "power_system": "修行者通过吸收劫气提升境界",
        "cost_and_limitation": "每次境界突破必须渡劫，失败率随境界指数级上升",
        "physics_rules": "劫云会改变局部重力，普通人靠近渡劫区会失去方向感",
        "name": "劫力体系",
        "essence": "自创字段不应被猜测合并",
        "存在": "中文自创字段不应生成额外框",
    }

    out = canonicalize_dimension_fields("core_rules", raw)

    assert "name" not in out
    assert "essence" not in out
    assert "存在" not in out
    assert "cost_and_limitation" not in out
    assert set(out) == {"power_system", "physics_rules"}
    assert "劫气" in out["power_system"]
    assert "劫云" in out["physics_rules"]


def test_validate_complete_dimension_rejects_short_or_missing_fields():
    raw = {
        "terrain": "游戏内分九大剑域,从新手村",
        "climate": "赛季天气由服务器动态渲染，雨战会放大身法误差，雪图压低远程视野",
        "resources": "高阶材料集中在联赛副本和训练服隐藏节点，普通玩家只能兑换碎片",
        "ecology": "野区机关与镜像怪会模拟职业队常用压迫路线，逼迫选手移动判断",
    }

    assert validate_complete_dimension_fields("geography", raw) == {}


def test_validate_complete_dimension_accepts_contract_shape_in_order():
    raw = {
        "terrain": "主城、赛场和训练基地围绕服务器节点分布，地下网吧藏在监管薄弱旧城区",
        "climate": "赛季天气由服务器动态渲染，雨战会放大身法误差，雪图压低远程视野",
        "resources": "高阶材料集中在联赛副本和训练服隐藏节点，普通玩家只能兑换碎片",
        "ecology": "野区机关与镜像怪会模拟职业队常用压迫路线，逼迫选手移动判断",
    }

    out = validate_complete_dimension_fields("geography", raw)

    assert list(out) == ["terrain", "climate", "resources", "ecology"]
    assert out["terrain"].startswith("主城")
