"""触发词目录单元测试"""
import pytest
from application.engine.services.trigger_keyword_catalog import expand_triggers


def test_combat_maps_to_weapon_and_skill():
    result = expand_triggers(["战斗"])
    assert "武器" in result
    assert "战斗技能" in result


def test_cultivation_maps_to_realm_and_technique():
    result = expand_triggers(["修炼"])
    assert "功法" in result
    assert "境界" in result


def test_multiple_triggers_union():
    result = expand_triggers(["战斗", "修炼"])
    assert "武器" in result
    assert "功法" in result


def test_unknown_trigger_falls_back_to_self():
    result = expand_triggers(["未知词汇XYZ"])
    assert "未知词汇XYZ" in result


def test_empty_list_returns_empty_set():
    assert expand_triggers([]) == set()


def test_english_trigger():
    result = expand_triggers(["combat"])
    assert "weapon" in result
    assert "skill" in result


def test_magic_trigger():
    result = expand_triggers(["魔法"])
    assert "魔力" in result
    assert "魔法系统" in result
