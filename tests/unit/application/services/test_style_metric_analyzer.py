"""写作手法知识库指标分析测试。"""

from application.style_bible.services.style_metric_analyzer import StyleMetricAnalyzer


def test_style_metric_analyzer_computes_core_metrics():
    text = """
雨落在窗上，灯光从门缝里漏出来。

林晚推开门，看见桌边的人影。

“你终于来了？”他低声问。

她心里一紧，意识到这不是偶然。
""".strip()

    metrics = StyleMetricAnalyzer().analyze(text)

    assert metrics["char_count"] > 0
    assert metrics["sentence_count"] >= 4
    assert metrics["avg_sentence_length"] > 0
    assert metrics["paragraph_count"] == 4
    assert metrics["dialogue_ratio"] > 0
    assert set(["action_ratio", "psychology_ratio", "environment_ratio"]).issubset(metrics)
    assert metrics["action_ratio"] > 0
    assert metrics["psychology_ratio"] > 0
    assert metrics["environment_ratio"] > 0


def test_style_metric_analyzer_counts_ai_cliche_hits():
    text = "他眼中闪过一丝复杂，心中五味杂陈。"

    metrics = StyleMetricAnalyzer().analyze(text)

    assert metrics["cliche_hit_count"] >= 2
    assert "眼神闪过系列" in metrics["cliche_patterns"]
    assert "五味杂陈系列" in metrics["cliche_patterns"]


def test_style_metric_analyzer_empty_text_returns_zero_metrics():
    metrics = StyleMetricAnalyzer().analyze("")

    assert metrics["char_count"] == 0
    assert metrics["sentence_count"] == 0
    assert metrics["avg_sentence_length"] == 0.0
    assert metrics["dialogue_ratio"] == 0.0
    assert metrics["cliche_hit_count"] == 0


def test_style_metric_analyzer_aggregates_multiple_metric_dicts():
    analyzer = StyleMetricAnalyzer()
    first = analyzer.analyze("林晚推门。")
    second = analyzer.analyze("“来了？”他问。\n\n雨声停了。")

    metrics = analyzer.aggregate([first, second])

    assert metrics["sample_count"] == 2
    assert metrics["char_count"] == first["char_count"] + second["char_count"]
    assert metrics["paragraph_count"] == first["paragraph_count"] + second["paragraph_count"]
    assert metrics["dialogue_ratio"] > 0
