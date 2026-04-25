"""读者模拟 Agent 单元测试"""
import json
import pytest
from datetime import datetime

from application.reader.schema import (
    ReaderDimensionScores,
    ReaderSimulationLlmPayload,
    SingleReaderFeedbackPayload,
)
from application.reader.dtos.reader_feedback_dto import (
    ChapterReaderReportDTO,
    ReaderDimensionScoresDTO,
    ReaderFeedbackDTO,
    PERSONA_LABELS,
)


# ─── Schema 测试 ──────────────────────────────────────────────


class TestReaderDimensionScores:
    """测试四维度评分归一化"""

    def test_normal_scores(self):
        scores = ReaderDimensionScores(
            suspense_retention=75, thrill_score=60,
            churn_risk=20, emotional_resonance=80,
        )
        assert scores.suspense_retention == 75.0
        assert scores.churn_risk == 20.0

    def test_clamp_high(self):
        scores = ReaderDimensionScores(
            suspense_retention=150, thrill_score=-10,
            churn_risk=200, emotional_resonance=100,
        )
        assert scores.suspense_retention == 100.0
        assert scores.thrill_score == 0.0
        assert scores.churn_risk == 100.0

    def test_none_defaults(self):
        scores = ReaderDimensionScores(
            suspense_retention=None, thrill_score=None,
            churn_risk=None, emotional_resonance=None,
        )
        assert scores.suspense_retention == 50.0

    def test_string_input(self):
        scores = ReaderDimensionScores(
            suspense_retention="85", thrill_score="abc",
            churn_risk="30", emotional_resonance="70",
        )
        assert scores.suspense_retention == 85.0
        assert scores.thrill_score == 50.0  # 无法解析时默认 50


class TestSingleReaderFeedbackPayload:
    """测试读者人设归一化"""

    def test_normalize_chinese_persona(self):
        fb = SingleReaderFeedbackPayload(
            persona="硬核粉",
            scores=ReaderDimensionScores(),
        )
        assert fb.persona == "hardcore"

    def test_normalize_english_persona(self):
        fb = SingleReaderFeedbackPayload(
            persona="NITPICKER",
            scores=ReaderDimensionScores(),
        )
        assert fb.persona == "nitpicker"

    def test_unknown_persona_passthrough(self):
        fb = SingleReaderFeedbackPayload(
            persona="custom_reader",
            scores=ReaderDimensionScores(),
        )
        assert fb.persona == "custom_reader"


class TestReaderSimulationLlmPayload:
    """测试完整 LLM 输出解析"""

    def test_full_payload_parse(self):
        data = {
            "feedbacks": [
                {
                    "persona": "hardcore",
                    "scores": {
                        "suspense_retention": 80,
                        "thrill_score": 65,
                        "churn_risk": 10,
                        "emotional_resonance": 75,
                    },
                    "one_line_verdict": "伏笔埋得不错，但战斗系统还需强化",
                    "highlights": ["伏笔回收巧妙"],
                    "pain_points": ["打斗描写略显空泛"],
                    "suggestions": ["增加功法细节"],
                },
                {
                    "persona": "casual",
                    "scores": {
                        "suspense_retention": 70,
                        "thrill_score": 85,
                        "churn_risk": 15,
                        "emotional_resonance": 60,
                    },
                    "one_line_verdict": "够爽！继续加油",
                    "highlights": ["节奏快"],
                    "pain_points": [],
                    "suggestions": [],
                },
                {
                    "persona": "挑刺党",
                    "scores": {
                        "suspense_retention": 55,
                        "thrill_score": 40,
                        "churn_risk": 35,
                        "emotional_resonance": 50,
                    },
                    "one_line_verdict": "用词重复太多，「不由自主」出现了5次",
                    "highlights": [],
                    "pain_points": ["用词重复", "比喻老套"],
                    "suggestions": ["减少重复用词"],
                },
            ],
            "overall_readability": 68,
            "chapter_hook_strength": "strong",
            "pacing_verdict": "前慢后快，整体尚可",
        }
        payload = ReaderSimulationLlmPayload(**data)
        assert len(payload.feedbacks) == 3
        assert payload.feedbacks[0].persona == "hardcore"
        assert payload.feedbacks[2].persona == "nitpicker"
        assert payload.overall_readability == 68.0
        assert payload.chapter_hook_strength == "strong"

    def test_hook_strength_normalization(self):
        payload = ReaderSimulationLlmPayload(
            feedbacks=[], chapter_hook_strength="弱",
        )
        assert payload.chapter_hook_strength == "weak"

    def test_extra_fields_ignored(self):
        payload = ReaderSimulationLlmPayload(
            feedbacks=[], unknown_field="should be ignored",
        )
        assert not hasattr(payload, "unknown_field")


# ─── DTO 测试 ─────────────────────────────────────────────────


class TestChapterReaderReportDTO:
    """测试报告 DTO 序列化"""

    def _make_report(self) -> ChapterReaderReportDTO:
        feedbacks = []
        for persona, label in PERSONA_LABELS.items():
            feedbacks.append(ReaderFeedbackDTO(
                persona=persona,
                persona_label=label,
                scores=ReaderDimensionScoresDTO(
                    suspense_retention=70,
                    thrill_score=60,
                    churn_risk=25,
                    emotional_resonance=65,
                ),
                one_line_verdict=f"{label}觉得还行",
                highlights=["亮点A"],
                pain_points=["痛点B"],
                suggestions=["建议C"],
            ))
        return ChapterReaderReportDTO(
            novel_id="test-novel-123",
            chapter_number=5,
            feedbacks=feedbacks,
            overall_readability=72.5,
            chapter_hook_strength="strong",
            pacing_verdict="节奏紧凑",
            analyzed_at=datetime(2026, 4, 20, 20, 0, 0),
        )

    def test_to_dict(self):
        report = self._make_report()
        d = report.to_dict()
        assert d["novel_id"] == "test-novel-123"
        assert d["chapter_number"] == 5
        assert len(d["feedbacks"]) == 3
        assert d["overall_readability"] == 72.5
        assert d["chapter_hook_strength"] == "strong"
        assert "avg_scores" in d

    def test_avg_scores(self):
        report = self._make_report()
        avg = report._compute_avg_scores()
        assert avg["suspense_retention"] == 70.0
        assert avg["thrill_score"] == 60.0
        assert avg["churn_risk"] == 25.0

    def test_empty_feedbacks_avg(self):
        report = ChapterReaderReportDTO(
            novel_id="test", chapter_number=1,
        )
        avg = report._compute_avg_scores()
        assert avg["suspense_retention"] == 0

    def test_serialization_roundtrip(self):
        report = self._make_report()
        d = report.to_dict()
        json_str = json.dumps(d, ensure_ascii=False, default=str)
        parsed = json.loads(json_str)
        assert parsed["feedbacks"][0]["persona"] == "hardcore"
        assert parsed["avg_scores"]["churn_risk"] == 25.0


class TestPersonaLabels:
    """测试人设标签映射"""

    def test_all_personas_have_labels(self):
        assert "hardcore" in PERSONA_LABELS
        assert "casual" in PERSONA_LABELS
        assert "nitpicker" in PERSONA_LABELS

    def test_label_values(self):
        assert PERSONA_LABELS["hardcore"] == "硬核粉"
        assert PERSONA_LABELS["casual"] == "休闲读者"
        assert PERSONA_LABELS["nitpicker"] == "挑刺党"


class TestFallbackReport:
    """测试降级报告标识（LLM 失败 / 章节不存在等场景）"""

    def test_default_report_not_fallback(self):
        """正常构造的报告默认 is_fallback=False"""
        report = ChapterReaderReportDTO(novel_id="x", chapter_number=1)
        assert report.is_fallback is False
        assert report.error_message == ""

    def test_fallback_fields_serialized(self):
        """is_fallback 和 error_message 应该出现在 to_dict 输出中"""
        report = ChapterReaderReportDTO(
            novel_id="x",
            chapter_number=1,
            is_fallback=True,
            error_message="LLM 调用失败",
        )
        d = report.to_dict()
        assert d["is_fallback"] is True
        assert d["error_message"] == "LLM 调用失败"

    def test_empty_report_factory_marks_fallback(self):
        """Service._empty_report 必须标记 is_fallback=True"""
        from application.reader.services.reader_simulation_service import (
            ReaderSimulationService,
        )
        report = ReaderSimulationService._empty_report(
            "novel-1", 3, "章节不存在"
        )
        assert report.is_fallback is True
        assert report.error_message == "章节不存在"
        assert len(report.feedbacks) == 3  # 三个人设都填充
        # 每个读者的 verdict 应该包含 reason
        for fb in report.feedbacks:
            assert fb.one_line_verdict == "章节不存在"
