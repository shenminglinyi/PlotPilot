from unittest.mock import AsyncMock, Mock

import pytest

from application.blueprint.services.continuous_planning_service import (
    ContinuousPlanningService,
    _extract_outer_json_value,
    _incremental_macro_parts_trustworthy,
    _try_parse_parts_from_llm_buffer,
    get_macro_plan_progress,
)


def _make_service() -> ContinuousPlanningService:
    return ContinuousPlanningService(
        story_node_repo=Mock(),
        chapter_element_repo=Mock(),
        llm_service=Mock(),
    )


def test_quick_macro_prompt_for_long_book_uses_leading_volume_detail():
    svc = _make_service()

    prompt = svc._build_quick_macro_prompt({"premise": "主角在高武世界成长。"}, 500)

    assert "只为开篇前导卷规划幕节点" in prompt.system
    assert "后续卷的幕节点留给写作过程中动态生成" in prompt.system
    assert "开篇前导卷标题" in prompt.user
    assert "前 1-2 部" not in prompt.system


def test_parse_llm_response_repairs_truncated_macro_plan_json():
    svc = _make_service()

    response = """```json
{
  "parts": [
    {
      "title": "第一部",
      "volumes": [
        {
          "title": "卷一",
          "acts": [
            {
              "title": "初入京城",
              "description": "主角进入京城，卷入风暴",
              "core_conflict": "必须在权斗中站稳脚跟"
            }
          ]
        }
      ]
    }
  ],
  "theme": "权谋成长"
"""

    result = svc._parse_llm_response(response)

    assert result["theme"] == "权谋成长"
    assert result["parts"][0]["volumes"][0]["acts"][0]["title"] == "初入京城"


def test_parse_llm_response_repairs_unterminated_string():
    svc = _make_service()

    response = """{
  "parts": [
    {
      "title": "第一部",
      "volumes": [
        {
          "title": "卷一",
          "acts": [
            {
              "title": "初入京城",
              "description": "主角进入京城",
              "core_conflict": "站稳脚跟"
            },
            {
              "title": "风暴将至",
              "description": "主角发现
"""

    result = svc._parse_llm_response(response)

    acts = result["parts"][0]["volumes"][0]["acts"]
    assert len(acts) == 2
    assert acts[0]["title"] == "初入京城"
    assert acts[1]["title"] == "风暴将至"


def test_parse_llm_response_repairs_missing_comma_between_fields():
    svc = _make_service()

    response = """{
  "parts": [
    {
      "title": "第一部"
      "volumes": [
        {
          "title": "卷一",
          "acts": []
        }
      ]
    }
  ],
  "theme": "权谋成长"
}"""

    result = svc._parse_llm_response(response)

    assert result["theme"] == "权谋成长"
    assert result["parts"][0]["title"] == "第一部"
    assert result["parts"][0]["volumes"][0]["title"] == "卷一"


def test_extract_outer_json_value_prefers_object_root_over_leading_array():
    text = '["noise"] {"parts": [], "theme": "x"}'

    result = _extract_outer_json_value(text)

    assert result == '{"parts": [], "theme": "x"}'


def test_incremental_macro_parts_trustworthy_rejects_single_char_titles():
    bad = [
        {
            "title": "第一部",
            "volumes": [
                {"title": "卷一", "acts": [{"title": "X", "description": ""}]},
            ],
        }
    ]
    assert _incremental_macro_parts_trustworthy(bad) is False

    ok = [
        {
            "title": "第一部",
            "volumes": [
                {"title": "卷一", "acts": [{"title": "初入山门", "description": ""}]},
            ],
        }
    ]
    assert _incremental_macro_parts_trustworthy(ok) is True


def test_try_parse_parts_from_llm_buffer_accepts_complete_valid_minimal_json():
    raw = '{"parts": [{"title": "第一部", "volumes": [{"title": "卷一", "acts": [{"title": "序幕", "description": ""}]}]}], "theme": "x"}'
    parts = _try_parse_parts_from_llm_buffer(raw)
    assert parts is not None
    assert parts[0]["title"] == "第一部"
    assert parts[0]["volumes"][0]["acts"][0]["title"] == "序幕"


@pytest.mark.asyncio
async def test_stream_macro_llm_text_repairs_partial_text_when_stream_breaks():
    async def broken_stream(_prompt, _config):
        yield """{
          "parts": [
            {
              "title": "第一部",
              "volumes": [
                {
                  "title": "第一卷",
                  "acts": [
                    {
                      "title": "第一幕：灰鸦街醒来",
                      "description": "主角重生后先在灰鸦街求生",
                      "core_conflict": "隐藏异常并取得训练资格"
                    },
                    {
                      "title": "第二幕：廉价训练舱",
                      "description": "主角争夺第一批训练资源"
        """
        raise RuntimeError("peer closed connection")

    svc = _make_service()
    svc.llm_service.stream_generate = broken_stream

    raw = await svc._stream_macro_llm_text("novel-1", Mock(), Mock())
    parsed = svc._parse_llm_response(raw)

    acts = parsed["parts"][0]["volumes"][0]["acts"]
    assert acts[0]["title"] == "第一幕：灰鸦街醒来"
    assert acts[1]["title"] == "第二幕：廉价训练舱"


@pytest.mark.asyncio
async def test_generate_macro_plan_precise_mode_repairs_missing_act_fields_and_rebalances_chapters():
    llm_service = AsyncMock()
    llm_service.generate = AsyncMock(side_effect=[
        """{
          "node_updates": [
            {"node_id": "P1", "title": "寒门燃灯", "description": "寒门少年被卷入京师风暴"},
            {"node_id": "V1_1", "title": "初入京城", "description": "立足与试探"},
            {
              "node_id": "A1_1_1",
              "title": "雪夜叩门",
              "description": "主角深夜入京，撞见命案",
              "estimated_chapters": 7,
              "plot_points": ["进京", "撞见命案"],
              "setup_for": ["A1_1_2"],
              "payoff_from": []
            },
            {
              "node_id": "A1_1_2",
              "title": "朝堂余烬",
              "description": "主角被迫接触权贵",
              "estimated_chapters": 9,
              "narrative_goal": "建立主角与朝堂的冲突面",
              "plot_points": ["见权贵", "受逼迫"],
              "key_characters": ["主角-棋子"],
              "key_locations": ["都察院-压力源"],
              "emotional_arc": "紧张→压抑",
              "setup_for": ["A1_1_3"],
              "payoff_from": ["A1_1_1"]
            }
          ]
        }""",
        """{
          "node_updates": [
            {
              "node_id": "A1_1_1",
              "narrative_goal": "把主角拖入主线阴谋",
              "key_characters": ["主角-闯入者"],
              "key_locations": ["京城-漩涡入口"],
              "emotional_arc": "戒备→惊惧"
            }
          ]
        }""",
    ])
    svc = ContinuousPlanningService(
        story_node_repo=Mock(),
        chapter_element_repo=Mock(),
        llm_service=llm_service,
    )
    svc._get_bible_context = Mock(return_value={})

    result = await svc.generate_macro_plan(
        novel_id="novel-1",
        target_chapters=100,
        structure_preference={"parts": 1, "volumes_per_part": 5, "acts_per_volume": 5},
    )

    parts = result["structure"]
    assert len(parts) == 1
    assert len(parts[0]["volumes"]) == 5
    assert all(len(volume["acts"]) == 5 for volume in parts[0]["volumes"])

    first_volume = parts[0]["volumes"][0]
    assert parts[0]["title"] == "寒门燃灯"
    assert first_volume["title"] == "初入京城"
    assert first_volume["acts"][0]["title"] == "雪夜叩门"
    assert first_volume["acts"][1]["title"] == "朝堂余烬"
    assert first_volume["acts"][2]["title"] == "第3幕"
    assert first_volume["acts"][0]["narrative_goal"] == "把主角拖入主线阴谋"
    assert first_volume["acts"][0]["key_characters"] == ["主角-闯入者"]
    assert first_volume["acts"][0]["key_locations"] == ["京城-漩涡入口"]
    assert first_volume["acts"][0]["emotional_arc"] == "戒备→惊惧"

    all_acts = [act for volume in parts[0]["volumes"] for act in volume["acts"]]
    assert sum(act["estimated_chapters"] for act in all_acts) == 100
    assert llm_service.generate.await_count == 2

    progress = get_macro_plan_progress("novel-1")
    assert progress["status"] == "completed"
    assert progress["current"] == 5
    assert progress["total"] == 5
