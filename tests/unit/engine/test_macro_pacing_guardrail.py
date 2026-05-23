from engine.runtime.quality_guardrails.macro_pacing_guardrail import MacroPacingGuardrail
from engine.runtime.quality_guardrails.quality_guardrail import QualityGuardrail


def test_macro_pacing_flags_early_full_resolution():
    text = (
        "执法堂钟声响起，宗主亲临宣布裁决。"
        "神识烙印证明真凶就是西门长老，十年冤案终于昭雪。"
        "芦沉舟恢复身份，谷梁卿羽被废去修为逐出宗门。"
        "所有人都知道案件真相大白，幕后靠山当场败露逃走。"
    )

    score, violations = MacroPacingGuardrail().check(
        text,
        scene_info={"chapter_number": 8},
    )

    assert score < 1.0
    assert {v.violation_type for v in violations} >= {
        "early_full_resolution",
        "reveal_overload",
    }


def test_quality_guardrail_surfaces_macro_pacing_dimension():
    text = (
        "第八章里，宗主亲临宣布平反。"
        "真凶败露，十年冤案彻底昭雪，主角恢复身份。"
        "长老逃走，谷梁卿羽跪地认输又被逐出宗门。"
    ) * 8

    report = QualityGuardrail().check(
        text,
        chapter_goal="第8章 重回内门",
        scene_info={"chapter_number": 8},
    )

    assert report.macro_pacing_score < 1.0
    assert any(v["dimension"] == "macro_pacing" for v in report.all_violations)
