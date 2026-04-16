from unittest.mock import Mock

from application.blueprint.services.continuous_planning_service import (
    ContinuousPlanningService,
    _extract_outer_json_value,
)


def _make_service() -> ContinuousPlanningService:
    return ContinuousPlanningService(
        story_node_repo=Mock(),
        chapter_element_repo=Mock(),
        llm_service=Mock(),
    )


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
