"""Style constraint builder unit tests."""
import pytest
from application.engine.services.style_constraint_builder import build_style_summary


class TestBuildStyleSummary:
    """测试 build_style_summary 函数"""

    def test_build_summary_with_valid_fingerprint(self):
        """测试使用有效指纹数据构建摘要"""
        fingerprint = {
            "metrics": {
                "adjective_density": 0.052,
                "avg_sentence_length": 18.5,
                "sentence_count": 100
            },
            "sample_count": 10
        }

        summary = build_style_summary(fingerprint)

        assert summary
        assert "形容词密度" in summary
        assert "5.2%" in summary
        assert "平均句长" in summary
        assert "18" in summary or "19" in summary

    def test_build_summary_with_low_adjective_density(self):
        """测试低形容词密度"""
        fingerprint = {
            "metrics": {
                "adjective_density": 0.025,
                "avg_sentence_length": 12.0,
                "sentence_count": 50
            }
        }

        summary = build_style_summary(fingerprint)

        assert "简洁" in summary
        assert "少用修饰" in summary

    def test_build_summary_with_high_adjective_density(self):
        """测试高形容词密度"""
        fingerprint = {
            "metrics": {
                "adjective_density": 0.08,
                "avg_sentence_length": 25.0,
                "sentence_count": 50
            }
        }

        summary = build_style_summary(fingerprint)

        assert "丰富描写" in summary or "注重细节" in summary

    def test_build_summary_with_short_sentences(self):
        """测试短句风格"""
        fingerprint = {
            "metrics": {
                "adjective_density": 0.04,
                "avg_sentence_length": 12.0,
                "sentence_count": 50
            }
        }

        summary = build_style_summary(fingerprint)

        assert "短句" in summary
        assert "明快" in summary

    def test_build_summary_with_long_sentences(self):
        """测试长句风格"""
        fingerprint = {
            "metrics": {
                "adjective_density": 0.04,
                "avg_sentence_length": 28.0,
                "sentence_count": 50
            }
        }

        summary = build_style_summary(fingerprint)

        assert "长句" in summary
        assert "舒缓" in summary

    def test_build_summary_with_none_fingerprint(self):
        """测试 None 指纹"""
        summary = build_style_summary(None)
        assert summary == ""

    def test_build_summary_with_empty_fingerprint(self):
        """测试空指纹"""
        summary = build_style_summary({})
        assert summary == ""

    def test_build_summary_with_missing_metrics(self):
        """测试缺少 metrics 字段"""
        fingerprint = {
            "sample_count": 10
        }
        summary = build_style_summary(fingerprint)
        assert summary == ""

    def test_build_summary_with_zero_values(self):
        """测试零值"""
        fingerprint = {
            "metrics": {
                "adjective_density": 0.0,
                "avg_sentence_length": 0.0,
                "sentence_count": 0
            }
        }
        summary = build_style_summary(fingerprint)
        assert summary == ""

    def test_build_summary_is_concise(self):
        """测试摘要简洁性（≤1K tokens，约 2000 字符）"""
        fingerprint = {
            "metrics": {
                "adjective_density": 0.052,
                "avg_sentence_length": 18.5,
                "sentence_count": 100
            }
        }

        summary = build_style_summary(fingerprint)

        # 验证摘要长度合理（远小于 2000 字符）
        assert len(summary) < 500
