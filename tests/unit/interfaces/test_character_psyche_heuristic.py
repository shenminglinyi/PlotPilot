"""案卷同源 Bible 锚点：启发式种子（无 LLM）"""

from types import SimpleNamespace

from interfaces.api.v1.engine.checkpoint_routes import _build_heuristic_seed_dict


def test_build_heuristic_seed_dict_fills_from_description():
    target = SimpleNamespace(
        description="他坚信世间有公道。绝不背叛同伴。说话冷冷的，惜字如金。",
        core_belief="",
        moral_taboos=[],
        voice_profile={},
        verbal_tic="",
        idle_behavior="",
        active_wounds=[],
        mental_state="NORMAL",
    )
    data = _build_heuristic_seed_dict(target)
    assert "core_belief" in data
    assert data["moral_taboos"]
    assert "voice_profile" in data
    assert data["voice_profile"].get("style")


def test_build_heuristic_seed_dict_respects_existing_fields():
    target = SimpleNamespace(
        description="备用简介里也有禁忌词绝不撒谎。",
        core_belief="已有人写",
        moral_taboos=["已有"],
        voice_profile={"style": "已定"},
        verbal_tic="",
        idle_behavior="",
        active_wounds=[{"trigger": "x", "effect": "y"}],
        mental_state="NORMAL",
    )
    data = _build_heuristic_seed_dict(target)
    assert data == {}
