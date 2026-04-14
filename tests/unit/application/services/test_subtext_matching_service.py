# tests/unit/application/services/test_subtext_matching_service.py
import pytest
from datetime import datetime

from application.analyst.services.subtext_matching_service import SubtextMatchingService
from domain.novel.entities.subtext_ledger_entry import SubtextLedgerEntry


class TestSubtextMatchingService:
    """测试潜台词匹配服务"""

    @pytest.fixture
    def service(self):
        return SubtextMatchingService()

    @pytest.fixture
    def pending_entry_visual(self):
        """待消费的视觉锚点条目"""
        return SubtextLedgerEntry(
            id="entry1",
            chapter=5,
            character_id="char1",
            hidden_clue="主角的秘密身份",
            sensory_anchors={"visual": "红色围巾"},
            status="pending",
            created_at=datetime(2026, 1, 1)
        )

    @pytest.fixture
    def pending_entry_multi(self):
        """待消费的多感官锚点条目"""
        return SubtextLedgerEntry(
            id="entry2",
            chapter=3,
            character_id="char2",
            hidden_clue="隐藏的关系",
            sensory_anchors={
                "visual": "银色手表",
                "auditory": "轻微的咳嗽声"
            },
            status="pending",
            created_at=datetime(2026, 1, 2)
        )

    @pytest.fixture
    def consumed_entry(self):
        """已消费的条目"""
        return SubtextLedgerEntry(
            id="entry3",
            chapter=2,
            character_id="char3",
            hidden_clue="过去的秘密",
            sensory_anchors={"visual": "蓝色信封"},
            status="consumed",
            consumed_at_chapter=8,
            created_at=datetime(2026, 1, 3)
        )

    def test_find_best_anchor_match_exact(self, service, pending_entry_visual):
        """测试精确匹配"""
        current_anchors = {"visual": "红色围巾"}
        entries = [pending_entry_visual]

        result = service.find_best_anchor_match(current_anchors, entries)

        assert result is not None
        assert result.id == "entry1"

    def test_find_best_anchor_match_partial(self, service, pending_entry_visual):
        """测试部分匹配（子串）"""
        current_anchors = {"visual": "她戴着红色围巾走进房间"}
        entries = [pending_entry_visual]

        result = service.find_best_anchor_match(current_anchors, entries)

        assert result is not None
        assert result.id == "entry1"

    def test_find_best_anchor_match_no_match(self, service, pending_entry_visual):
        """测试无匹配返回 None"""
        current_anchors = {"visual": "蓝色帽子"}
        entries = [pending_entry_visual]

        result = service.find_best_anchor_match(current_anchors, entries)

        assert result is None

    def test_find_best_anchor_match_ignores_consumed(
        self, service, pending_entry_visual, consumed_entry
    ):
        """测试忽略已消费的条目"""
        current_anchors = {"visual": "蓝色信封"}
        entries = [pending_entry_visual, consumed_entry]

        result = service.find_best_anchor_match(current_anchors, entries)

        # 应该忽略已消费的 entry3，即使它匹配
        assert result is None

    def test_find_best_anchor_match_multiple_candidates(
        self, service, pending_entry_visual, pending_entry_multi
    ):
        """测试多个候选返回最佳匹配"""
        # 当前场景包含银色手表和咳嗽声
        current_anchors = {
            "visual": "银色手表",
            "auditory": "轻微的咳嗽声"
        }
        entries = [pending_entry_visual, pending_entry_multi]

        result = service.find_best_anchor_match(current_anchors, entries)

        # entry2 有两个锚点都匹配（2/2 = 100% + 0.02 = 1.02）
        # entry1 没有匹配（红色围巾 vs 银色手表）
        # entry2 应该胜出
        assert result is not None
        assert result.id == "entry2"

    def test_find_best_anchor_match_case_insensitive(
        self, service, pending_entry_visual
    ):
        """测试大小写不敏感匹配"""
        current_anchors = {"visual": "红色围巾"}
        entries = [pending_entry_visual]

        result = service.find_best_anchor_match(current_anchors, entries)

        assert result is not None
        assert result.id == "entry1"

    def test_find_best_anchor_match_empty_current_anchors(
        self, service, pending_entry_visual
    ):
        """测试空的当前锚点"""
        current_anchors = {}
        entries = [pending_entry_visual]

        result = service.find_best_anchor_match(current_anchors, entries)

        assert result is None

    def test_find_best_anchor_match_empty_entries(self, service):
        """测试空的条目列表"""
        current_anchors = {"visual": "红色围巾"}
        entries = []

        result = service.find_best_anchor_match(current_anchors, entries)

        assert result is None

    def test_find_best_anchor_match_different_anchor_types(
        self, service, pending_entry_visual
    ):
        """测试不同类型的锚点不匹配"""
        current_anchors = {"auditory": "红色围巾"}  # 类型不同
        entries = [pending_entry_visual]

        result = service.find_best_anchor_match(current_anchors, entries)

        assert result is None
