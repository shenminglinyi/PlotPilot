from __future__ import annotations

from dataclasses import dataclass

from application.governance.models import CanonicalStoryline
from application.governance.service import NarrativeGovernanceService
from application.governance.storyline_registry import canonical_id_for, normalize_storyline_key


@dataclass
class FakeNovel:
    title: str
    premise: str
    target_chapters: int = 80


class FakeNovelRepo:
    def get_by_id(self, _novel_id):
        return FakeNovel(
            title="我不是剑仙",
            premise="【类型：东方玄幻】核心冲突：无根仙体被迫走上反剑仙之路\n开篇钩子：黑市冤案牵出宗门旧债",
        )


class FakeGovernanceRepo:
    def __init__(self):
        self.contract = None
        self.storylines = {}
        self.reports = []
        self.events = []
        self.debts = []

    def get_contract(self, novel_id):
        return self.contract if self.contract and self.contract.novel_id == novel_id else None

    def save_contract(self, contract):
        self.contract = contract

    def list_storylines(self, novel_id):
        return [line for line in self.storylines.values() if line.novel_id == novel_id]

    def upsert_storyline(self, storyline):
        self.storylines[storyline.canonical_id] = storyline

    def get_storyline(self, canonical_id):
        return self.storylines.get(canonical_id)

    def delete_storyline(self, canonical_id):
        self.storylines.pop(canonical_id, None)

    def save_report(self, report):
        self.reports.append(report)

    def latest_report(self, novel_id):
        matches = [r for r in self.reports if r.novel_id == novel_id]
        return matches[-1] if matches else None

    def update_report_status(self, novel_id, report_id, status):
        for report in self.reports:
            if report.novel_id == novel_id and report.report_id == report_id:
                report.review_status = status

    def append_event(self, event_id, novel_id, event_type, chapter_number, payload):
        self.events.append((event_id, novel_id, event_type, chapter_number, payload))

    def list_open_debts(self, novel_id, limit=50):
        return self.debts[:limit]


def make_service():
    repo = FakeGovernanceRepo()
    return NarrativeGovernanceService(repo, FakeNovelRepo()), repo


def test_contract_generated_from_title_and_premise():
    service, _repo = make_service()

    contract = service.get_or_create_contract("n1")

    assert contract.title_promise == "我不是剑仙"
    assert "无根仙体" in contract.core_question
    assert "东方玄幻" in contract.theme_anchors
    assert "剑仙" in contract.theme_anchors


def test_opening_budget_limits_new_lines_and_reveal_level():
    service, _repo = make_service()

    budget = service.preview_chapter_budget("n1", chapter_number=3)

    assert budget.max_new_storylines == 1
    assert budget.max_debt_closures == 1
    assert budget.allowed_reveal_level == "hint"
    assert "剑仙" in budget.must_serve_promise_tags


def test_governance_report_flags_drift_and_premature_payoff_as_pause():
    service, _repo = make_service()

    report = service.evaluate_after_chapter("n1", 5, "配角闲谈许久，最后身份揭晓，真相大白。")

    assert report.should_pause_autopilot is True
    assert report.severity == "critical"
    assert {issue.code for issue in report.issues} == {"promise_drift", "premature_payoff"}
    assert report.budget_patch["must_retouch_promise"] is True


def test_storyline_registry_merges_aliases_into_canonical_line():
    service, repo = make_service()
    sid1 = canonical_id_for("n1", "黑市线")
    sid2 = canonical_id_for("n1", "黑市故事线")
    repo.upsert_storyline(
        CanonicalStoryline(
            canonical_id=sid1,
            novel_id="n1",
            canonical_key=normalize_storyline_key("黑市线"),
            title="黑市线",
            aliases=["鬼市交易"],
        )
    )
    repo.upsert_storyline(
        CanonicalStoryline(
            canonical_id=sid2,
            novel_id="n1",
            canonical_key=normalize_storyline_key("黑市故事线"),
            title="黑市故事线",
            aliases=["黑市追查"],
        )
    )

    merged = service.merge_storylines("n1", {"target_id": sid1, "source_ids": [sid2]})

    assert merged.canonical_id == sid1
    assert "黑市故事线" in merged.aliases
    assert "黑市追查" in merged.aliases
    assert repo.get_storyline(sid2) is None
