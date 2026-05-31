from application.blueprint.services.setup_main_plot_suggestion_service import SetupMainPlotSuggestionService


def test_parse_suggested_options_normalizes_and_falls_back():
    svc = SetupMainPlotSuggestionService.__new__(SetupMainPlotSuggestionService)
    ctx = {
        "target_chapters": 60,
        "fusion_axis": {
            "core_promise": "核心承诺",
            "central_conflict": "中心冲突",
            "false_mystery": "表层谜团",
            "true_mystery": "真实谜团",
            "forbidden_mainline_competitors": ["竞品A"],
            "taboos": ["禁忌A"],
        },
    }

    raw = """
    {
      "plot_options": [
        {
          "id": "option_a_survival",
          "type": "生存求证",
          "title": "绝境中的第一枪",
          "logline": "log",
          "core_conflict": "conflict",
          "starting_hook": "hook"
        }
      ]
    }
    """

    parsed = svc.parse_suggested_options(raw, ctx=ctx)

    assert len(parsed) == 3
    assert parsed[0]["id"] == "option_a_survival"
    assert parsed[0]["main_axis"]
    assert parsed[0]["opening_pressure"]
    assert parsed[0]["forbidden_drift"]
    assert parsed[0]["sublines"]

