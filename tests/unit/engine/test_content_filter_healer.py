"""内容风控自动诊断修复(content_filter_healer)测试"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from engine.runtime.content_filter_healer import (
    HealOutcome,
    heal_latest_chapter,
    is_content_filter_error,
    localize_flagged_fragments,
)


def _filter_error(text="x"):
    return RuntimeError(
        f"Failed to generate text: Error code: 500 - {{'error': {{'message': 'input new_sensitive (1026)'}}}}"
    )


class FakeProbe:
    """按关键字判定是否触发风控的假探测器"""

    def __init__(self, triggers):
        self.triggers = triggers  # set of substrings
        self.calls = []

    async def __call__(self, text):
        self.calls.append(text)
        if any(k in text for k in self.triggers):
            raise _filter_error()


def test_is_content_filter_error_matches_variants():
    assert is_content_filter_error(_filter_error())
    assert is_content_filter_error(RuntimeError("output new_sensitive (1027)"))
    assert is_content_filter_error(RuntimeError("Internal Server Error: new_sensitive"))
    assert not is_content_filter_error(RuntimeError("Error code: 500 - api_error"))
    assert not is_content_filter_error(RuntimeError("connect timeout"))


@pytest.mark.asyncio
async def test_localize_returns_empty_when_probe_passes():
    probe = FakeProbe(triggers=set())
    assert await localize_flagged_fragments(probe, "正常内容") == []


@pytest.mark.asyncio
async def test_localize_pinpoints_single_trigger_fragment():
    probe = FakeProbe(triggers={"违禁词XYZ"})
    content = "开头正常。" * 20 + "这里出现违禁词XYZ在中间。" + "结尾正常。" * 20
    frags = await localize_flagged_fragments(probe, content)
    assert frags and len(frags) == 1
    assert "违禁词XYZ" in frags[0]


@pytest.mark.asyncio
async def test_localize_returns_none_for_combinatorial_trigger():
    # 两半单独都不触发,拼在一起才触发 → 无法定位
    class ComboProbe:
        async def __call__(self, text):
            if "甲" in text and "乙" in text:
                raise _filter_error()

    result = await localize_flagged_fragments(ComboProbe(), "甲。" + "正常内容。"*20 + "乙。")
    assert result is None


@pytest.mark.asyncio
async def test_heal_rewrites_flagged_fragment_and_persists():
    probe = FakeProbe(triggers={"违禁词XYZ"})
    healed_text = "这里出现替代说法在中间。"

    rewriter = AsyncMock()
    rewriter.return_value = SimpleNamespace(content=healed_text)

    chapter = SimpleNamespace(content="开头。" * 30 + "这里出现违禁词XYZ在中间。" + "结尾。" * 30)
    host = MagicMock()
    host._latest_completed_chapter_number.return_value = 222
    host.chapter_repository.get_by_novel_and_number.return_value = chapter
    host.llm_service.generate = rewriter

    novel = SimpleNamespace(novel_id=SimpleNamespace(value="n-1"))

    outcome = await heal_latest_chapter(host, novel, probe)

    assert outcome.ok is True
    assert "违禁词XYZ" not in chapter.content
    assert healed_text in chapter.content
    host.chapter_repository.save.assert_called_once_with(chapter)


@pytest.mark.asyncio
async def test_heal_gives_up_when_rewrite_still_trips():
    # 改写输出仍含触发词 → 整章复检不过 → MAX_HEAL_ROUNDS 后放弃
    probe = FakeProbe(triggers={"违禁词XYZ"})
    rewriter = AsyncMock()
    rewriter.side_effect = [
        SimpleNamespace(content="第一版仍含违禁词XYZ。"),
        SimpleNamespace(content="第二版仍含违禁词XYZ。"),
        SimpleNamespace(content="第三版仍含违禁词XYZ。"),
    ]

    chapter = SimpleNamespace(content="违禁词XYZ")
    host = MagicMock()
    host._latest_completed_chapter_number.return_value = 1
    host.chapter_repository.get_by_novel_and_number.return_value = chapter
    host.llm_service.generate = rewriter

    novel = SimpleNamespace(novel_id=SimpleNamespace(value="n-1"))

    outcome = await heal_latest_chapter(host, novel, probe)

    assert outcome.ok is False
    assert "复检仍触发" in outcome.note
    host.chapter_repository.save.assert_not_called()


@pytest.mark.asyncio
async def test_heal_reports_missing_chapter():
    host = MagicMock()
    host._latest_completed_chapter_number.return_value = None
    outcome = await heal_latest_chapter(host, SimpleNamespace(novel_id=SimpleNamespace(value="n-1")), FakeProbe(set()))
    assert outcome.ok is False
    assert "找不到已完成章节" in outcome.note


def test_heal_outcome_defaults():
    o = HealOutcome(ok=False, note="x")
    assert o.content == ""
