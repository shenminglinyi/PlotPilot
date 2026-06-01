from application.blueprint.services.setup_main_plot_suggestion_service import SetupMainPlotSuggestionService


def test_parse_suggested_options_normalizes_declared_options():
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
        },
        {
          "id": "option_b_conspiracy",
          "type": "阴谋求真",
          "title": "表象之下的齿轮",
          "logline": "log2",
          "core_conflict": "conflict2",
          "starting_hook": "hook2"
        },
        {
          "id": "option_c_anomaly",
          "type": "异类觉醒",
          "title": "规则的裂缝",
          "logline": "log3",
          "core_conflict": "conflict3",
          "starting_hook": "hook3"
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

