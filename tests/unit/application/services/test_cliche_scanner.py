# tests/unit/application/services/test_cliche_scanner.py
import pytest

from application.services.cliche_scanner import ClicheScanner, ClicheHit


class TestClicheScanner:
    """测试俗套句式扫描器"""

    @pytest.fixture
    def scanner(self):
        return ClicheScanner()

    def test_detects_bears_fire(self, scanner):
        """测试检测"熊熊怒火"类俗套"""
        text = "他心中燃起熊熊怒火，眼神变得凌厉。"

        hits = scanner.scan_cliches(text)

        assert len(hits) > 0
        assert any("熊熊" in hit.text for hit in hits)
        assert hits[0].pattern is not None

    def test_detects_multiple_cliches(self, scanner):
        """测试检测多个俗套句式"""
        text = "他眼中闪过一丝惊讶，嘴角勾起一抹笑意，心中五味杂陈。"

        hits = scanner.scan_cliches(text)

        # 应该检测到至少 3 个俗套
        assert len(hits) >= 3

    def test_no_cliches_returns_empty(self, scanner):
        """测试无俗套句式返回空列表"""
        text = "他走进房间，坐下来，开始工作。"

        hits = scanner.scan_cliches(text)

        assert len(hits) == 0

    def test_cliche_hit_contains_position(self, scanner):
        """测试返回位置信息"""
        text = "前面是正常文字。他眼中闪过一丝惊讶。后面也是正常文字。"

        hits = scanner.scan_cliches(text)

        assert len(hits) > 0
        hit = hits[0]
        assert hit.start >= 0
        assert hit.end > hit.start
        assert hit.text == text[hit.start:hit.end]

    def test_case_insensitive(self, scanner):
        """测试大小写不敏感（虽然中文没有大小写，但测试英文标点等）"""
        text = "他心中燃起熊熊烈火。"

        hits = scanner.scan_cliches(text)

        assert len(hits) > 0

    def test_detects_eye_flash_pattern(self, scanner):
        """测试检测"眼中闪过"类俗套"""
        text = "她眸中闪过一丝悲伤。"

        hits = scanner.scan_cliches(text)

        assert len(hits) > 0
        assert any("闪过" in hit.text for hit in hits)

    def test_detects_smile_pattern(self, scanner):
        """测试检测"嘴角勾起"类俗套"""
        text = "他嘴角扬起一个弧度。"

        hits = scanner.scan_cliches(text)

        assert len(hits) > 0
        assert any("嘴角" in hit.text for hit in hits)

    def test_detects_heart_mixed_feelings(self, scanner):
        """测试检测"心中五味杂陈"类俗套"""
        text = "听到这个消息，她内心五味杂陈。"

        hits = scanner.scan_cliches(text)

        assert len(hits) > 0
        assert any("五味杂陈" in hit.text for hit in hits)

    def test_detects_like_pattern(self, scanner):
        """测试检测"如同...一般"类俗套"""
        text = "他的速度如同闪电一般迅猛。"

        hits = scanner.scan_cliches(text)

        assert len(hits) > 0
        assert any("如同" in hit.text and "一般" in hit.text for hit in hits)

    def test_severity_is_warning(self, scanner):
        """测试严重程度默认为 warning"""
        text = "他心中燃起熊熊怒火。"

        hits = scanner.scan_cliches(text)

        assert len(hits) > 0
        assert hits[0].severity == "warning"

    def test_overlapping_patterns(self, scanner):
        """测试重叠模式的处理"""
        text = "他眼中闪过一丝复杂的情绪，如同暴风雨一般汹涌。"

        hits = scanner.scan_cliches(text)

        # 应该检测到多个俗套
        assert len(hits) >= 2

    def test_detects_ai_flavor_summary_and_atmosphere_patterns(self, scanner):
        """测试检测常见 AI 味总结句和氛围套话"""
        text = "空气仿佛凝固了。他知道，自己再也回不去了。命运的齿轮开始转动。"

        hits = scanner.scan_cliches(text)

        assert len(hits) >= 3
        assert any("空气" in hit.text and "凝固" in hit.text for hit in hits)
        assert any("再也回不去" in hit.text for hit in hits)
        assert any("命运的齿轮" in hit.text for hit in hits)

    def test_detects_compressed_expression_patterns(self, scanner):
        """测试检测把情节压成概括句的表达"""
        text = "一番交谈后，两人很快达成共识。随后他简单说明了情况。"

        hits = scanner.scan_cliches(text)

        assert len(hits) >= 2
        assert any("一番交谈后" in hit.text for hit in hits)
        assert any("简单说明了情况" in hit.text for hit in hits)
