from __future__ import annotations

import re
import uuid
from dataclasses import replace
from typing import Any

from application.governance.models import (
    CanonicalStoryline,
    ChapterNarrativeBudget,
    GovernanceIssue,
    GovernanceReport,
    NarrativeContract,
    utc_now_iso,
)
from application.governance.storyline_registry import (
    canonical_id_for,
    merge_aliases,
    normalize_storyline_key,
)
from application.world.services.narrative_promise import extract_narrative_promise


_EARLY_PAYOFF_TERMS = (
    "真相大白",
    "彻底平反",
    "彻底解决",
    "身份揭晓",
    "幕后黑手现身",
    "大仇得报",
    "飞升成功",
    "终局",
)


class NarrativeGovernanceService:
    """Book-level narrative coordinator.

    This first production slice is deliberately deterministic. It creates a
    stable contract, canonical storyline surface, chapter budget and report
    records without taking over generation internals in one risky move.
    """

    def __init__(
        self,
        repository: Any,
        novel_repository: Any | None = None,
        legacy_storyline_repository: Any | None = None,
        db: Any | None = None,
    ) -> None:
        self.repository = repository
        self.novel_repository = novel_repository
        self.legacy_storyline_repository = legacy_storyline_repository
        self.db = db

    def get_state(self, novel_id: str) -> dict[str, Any]:
        contract = self.get_or_create_contract(novel_id)
        self.backfill_canonical_storylines(novel_id)
        latest_report = self.repository.latest_report(novel_id)
        return {
            "contract": contract.to_dict(),
            "canonical_storylines": [s.to_dict() for s in self.repository.list_storylines(novel_id)],
            "open_debts": self.repository.list_open_debts(novel_id),
            "latest_report": latest_report.to_dict() if latest_report else None,
            "chapter_budget_preview": self.preview_chapter_budget(novel_id).to_dict(),
        }

    def get_or_create_contract(self, novel_id: str) -> NarrativeContract:
        existing = self.repository.get_contract(novel_id)
        if existing:
            return existing

        novel = self._load_novel(novel_id)
        title = getattr(novel, "title", "") if novel is not None else ""
        premise = getattr(novel, "premise", "") if novel is not None else ""
        promise = extract_narrative_promise(title, premise)
        anchors = list(promise.promise_keywords)
        if promise.genre_signal:
            anchors.insert(0, promise.genre_signal)

        contract = NarrativeContract(
            novel_id=novel_id,
            title_promise=promise.title or title or "未命名叙事承诺",
            core_question=promise.core_conflict or promise.opening_hook or premise[:180],
            theme_anchors=anchors[:8],
            forbidden_early_payoffs=[
                "前12章彻底解决书名反差",
                "前12章让核心敌人无代价退场",
                "前12章一次性公开身份/冤案/传承全部真相",
            ],
            reveal_budget={
                "opening": "hint",
                "development": "partial",
                "convergence": "major",
                "finale": "payoff",
            },
        )
        self.repository.save_contract(contract)
        self._emit(novel_id, "NarrativeContractCreated", None, contract.to_dict())
        return contract

    def update_contract(self, novel_id: str, payload: dict[str, Any]) -> NarrativeContract:
        current = self.get_or_create_contract(novel_id)
        contract = replace(
            current,
            title_promise=str(payload.get("title_promise", current.title_promise) or ""),
            core_question=str(payload.get("core_question", current.core_question) or ""),
            theme_anchors=list(payload.get("theme_anchors", current.theme_anchors) or []),
            forbidden_early_payoffs=list(
                payload.get("forbidden_early_payoffs", current.forbidden_early_payoffs) or []
            ),
            reveal_budget=dict(payload.get("reveal_budget", current.reveal_budget) or {}),
            updated_at=utc_now_iso(),
        )
        self.repository.save_contract(contract)
        self._emit(novel_id, "NarrativeContractUpdated", None, contract.to_dict())
        return contract

    def prepare_chapter(self, novel_id: str, chapter_number: int | None = None) -> dict[str, Any]:
        budget = self.preview_chapter_budget(novel_id, chapter_number)
        self._emit(novel_id, "ChapterPreparedEvent", budget.chapter_number, budget.to_dict())
        return {
            "budget": budget.to_dict(),
            "context_request": {
                "novel_id": novel_id,
                "chapter_number": budget.chapter_number,
                "promise_tags": budget.must_serve_promise_tags,
                "debt_ids": budget.carry_over_debt_ids,
            },
        }

    def preview_chapter_budget(
        self,
        novel_id: str,
        chapter_number: int | None = None,
    ) -> ChapterNarrativeBudget:
        if chapter_number is None:
            chapter_number = self._next_chapter_number(novel_id)
        contract = self.get_or_create_contract(novel_id)
        latest_report = self.repository.latest_report(novel_id)
        debts = self.repository.list_open_debts(novel_id, limit=8)
        stage = self._stage_for(novel_id, chapter_number)

        if stage == "opening":
            max_new = 1
            max_close = 1
            reveal = "hint"
        elif stage == "development":
            max_new = 2
            max_close = 2
            reveal = "partial"
        else:
            max_new = 0
            max_close = 3
            reveal = "major" if stage == "convergence" else "payoff"

        notes = []
        if latest_report and latest_report.severity in ("medium", "high", "critical"):
            notes.append("上一章治理报告要求本章优先修复承诺漂移或叙事债务。")
            max_new = max(0, max_new - 1)

        return ChapterNarrativeBudget(
            novel_id=novel_id,
            chapter_number=int(chapter_number),
            max_new_storylines=max_new,
            max_debt_closures=max_close,
            allowed_reveal_level=reveal,
            must_serve_promise_tags=contract.theme_anchors[:4],
            carry_over_debt_ids=[str(d.get("debt_id") or d.get("id") or "") for d in debts[:5]],
            notes=notes,
        )

    def commit_chapter(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> GovernanceReport:
        self._emit(
            novel_id,
            "ChapterCommittedEvent",
            chapter_number,
            {"content_length": len(content or ""), "metadata": metadata or {}},
        )
        return self.evaluate_after_chapter(novel_id, chapter_number, content)

    def evaluate_after_chapter(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
        sync_flags: dict[str, Any] | None = None,
    ) -> GovernanceReport:
        contract = self.get_or_create_contract(novel_id)
        issues: list[GovernanceIssue] = []
        hit_rate = self._promise_hit_rate(contract, content)

        if hit_rate <= 0:
            issues.append(
                GovernanceIssue(
                    code="promise_drift",
                    severity="high" if chapter_number <= 12 else "medium",
                    title="承诺漂移",
                    detail="本章正文没有命中书名承诺、核心问题或主题锚点。",
                    suggestion="下一章预算必须服务至少一个承诺标签，并减少新增支线。",
                )
            )
        elif hit_rate < 0.25:
            issues.append(
                GovernanceIssue(
                    code="promise_drift",
                    severity="medium",
                    title="承诺命中不足",
                    detail="本章只弱命中核心承诺，容易让读者感到主线退场。",
                    suggestion="补一处与书名反差或核心冲突直接相关的行动后果。",
                )
            )

        payoff_terms = [term for term in _EARLY_PAYOFF_TERMS if term in (content or "")]
        if chapter_number <= 12 and payoff_terms:
            issues.append(
                GovernanceIssue(
                    code="premature_payoff",
                    severity="high",
                    title="过早结清",
                    detail="开篇阶段出现疑似终局式兑现词。",
                    evidence=payoff_terms[:4],
                    suggestion="改为局部证据、误导性线索或带代价的小胜。",
                )
            )

        storylines = self.repository.list_storylines(novel_id)
        active_count = len([s for s in storylines if s.status == "active"])
        if chapter_number <= 20 and active_count > max(4, chapter_number // 3 + 2):
            issues.append(
                GovernanceIssue(
                    code="storyline_inflation",
                    severity="medium",
                    title="故事线膨胀",
                    detail=f"当前活跃 canonical storylines={active_count}，超过开篇承载能力。",
                    suggestion="合并同义线，下一章不要新增支线。",
                )
            )

        if sync_flags and sync_flags.get("causal_edges_stored") is False and chapter_number > 1:
            issues.append(
                GovernanceIssue(
                    code="causal_gap",
                    severity="low",
                    title="因果链偏弱",
                    detail="章后抽取未写入因果边，可能存在事件推进但缺少明确因果。",
                    suggestion="下一章强化上一章行动导致的具体后果。",
                )
            )

        severity = self._max_severity(issues)
        should_pause = severity in ("critical",) or (
            chapter_number <= 12
            and any(i.code == "promise_drift" and i.severity == "high" for i in issues)
            and any(i.code == "premature_payoff" for i in issues)
        )
        if should_pause and severity != "critical":
            severity = "critical"

        report = GovernanceReport(
            report_id=f"gov_{uuid.uuid4().hex}",
            novel_id=novel_id,
            chapter_number=chapter_number,
            severity=severity,
            promise_hit_rate=hit_rate,
            issues=issues,
            budget_patch=self._budget_patch_from_issues(issues),
            should_pause_autopilot=should_pause,
        )
        self.repository.save_report(report)
        self._emit(novel_id, "GovernanceEvaluatedEvent", chapter_number, report.to_dict())
        if should_pause:
            self._pause_autopilot(novel_id)
            self._emit(novel_id, "AutopilotPausedForGovernanceEvent", chapter_number, report.to_dict())
        return report

    def merge_storylines(self, novel_id: str, payload: dict[str, Any]) -> CanonicalStoryline:
        source_ids = [str(x) for x in payload.get("source_ids", []) if str(x).strip()]
        target_id = str(payload.get("target_id") or "").strip()
        title = str(payload.get("title") or "").strip()
        target = self.repository.get_storyline(target_id) if target_id else None
        sources = [self.repository.get_storyline(sid) for sid in source_ids]
        sources = [s for s in sources if s is not None]

        if not target:
            title = title or (sources[0].title if sources else "未命名故事线")
            target = CanonicalStoryline(
                canonical_id=canonical_id_for(novel_id, title),
                novel_id=novel_id,
                canonical_key=normalize_storyline_key(title),
                title=title,
            )

        target.aliases = merge_aliases(
            target.aliases,
            [s.title for s in sources],
            *(s.aliases for s in sources),
            payload.get("aliases", []),
        )
        target.source_storyline_ids = merge_aliases(
            target.source_storyline_ids,
            *(s.source_storyline_ids for s in sources),
            source_ids,
        )
        target.promise_tags = merge_aliases(target.promise_tags, payload.get("promise_tags", []))
        target.updated_at = utc_now_iso()
        self.repository.upsert_storyline(target)
        for source in sources:
            if source.canonical_id != target.canonical_id:
                self.repository.delete_storyline(source.canonical_id)
        self._emit(novel_id, "CanonicalStorylinesMerged", None, target.to_dict())
        return target

    def review_action(self, novel_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        report_id = str(payload.get("report_id") or "").strip()
        action = str(payload.get("action") or "accepted").strip()
        status = {
            "accept": "accepted",
            "accepted": "accepted",
            "ignore": "ignored",
            "ignored": "ignored",
            "modify": "modified",
            "modified": "modified",
        }.get(action, action or "accepted")
        if report_id:
            self.repository.update_report_status(novel_id, report_id, status)
        self._emit(novel_id, "GovernanceReviewAction", None, {"report_id": report_id, "status": status})
        return {"report_id": report_id, "status": status}

    def backfill_canonical_storylines(self, novel_id: str) -> None:
        if not self.legacy_storyline_repository:
            return
        try:
            from domain.novel.value_objects.novel_id import NovelId

            legacy = self.legacy_storyline_repository.get_by_novel_id(NovelId(novel_id))
        except Exception:
            return
        existing_keys = {s.canonical_key for s in self.repository.list_storylines(novel_id)}
        for item in legacy:
            title = getattr(item, "name", "") or getattr(item, "description", "")[:40] or getattr(item, "id", "")
            key = normalize_storyline_key(title)
            if key in existing_keys:
                continue
            canonical = CanonicalStoryline(
                canonical_id=canonical_id_for(novel_id, title, [getattr(item, "id", "")]),
                novel_id=novel_id,
                canonical_key=key,
                title=title,
                aliases=merge_aliases([getattr(item, "description", "")]),
                goal=getattr(item, "progress_summary", "") or "",
                span={
                    "start": getattr(item, "estimated_chapter_start", None),
                    "end": getattr(item, "estimated_chapter_end", None),
                    "last_active": getattr(item, "last_active_chapter", None),
                },
                source_storyline_ids=[getattr(item, "id", "")],
            )
            self.repository.upsert_storyline(canonical)
            existing_keys.add(key)

    def _load_novel(self, novel_id: str) -> Any | None:
        if self.novel_repository:
            try:
                from domain.novel.value_objects.novel_id import NovelId

                return self.novel_repository.get_by_id(NovelId(novel_id))
            except Exception:
                return None
        if self.db:
            row = self.db.fetch_one("SELECT title, premise, target_chapters FROM novels WHERE id = ?", (novel_id,))
            return type("NovelRow", (), dict(row))() if row else None
        return None

    def _next_chapter_number(self, novel_id: str) -> int:
        if self.db:
            try:
                row = self.db.fetch_one("SELECT MAX(number) AS n FROM chapters WHERE novel_id = ?", (novel_id,))
                return int((row or {}).get("n") or 0) + 1
            except Exception:
                return 1
        return 1

    def _stage_for(self, novel_id: str, chapter_number: int) -> str:
        target = 0
        novel = self._load_novel(novel_id)
        if novel is not None:
            target = int(getattr(novel, "target_chapters", 0) or 0)
        if target <= 0:
            target = 80
        progress = max(0.0, min(1.0, chapter_number / target))
        if chapter_number <= 12 or progress <= 0.25:
            return "opening"
        if progress <= 0.75:
            return "development"
        if progress <= 0.9:
            return "convergence"
        return "finale"

    def _promise_hit_rate(self, contract: NarrativeContract, content: str) -> float:
        text = re.sub(r"\s+", "", content or "")
        if not text:
            return 0.0
        anchors = []
        anchors.extend(contract.theme_anchors)
        anchors.extend([contract.title_promise, contract.core_question])
        anchors = [a for a in anchors if a and len(str(a).strip()) >= 2]
        if not anchors:
            return 1.0
        hits = 0
        for anchor in anchors:
            terms = [anchor] if len(anchor) <= 12 else re.split(r"[，,。；;：:\s]+", anchor)
            if any(term and len(term) >= 2 and term in text for term in terms):
                hits += 1
        return round(hits / max(1, len(anchors)), 3)

    def _max_severity(self, issues: list[GovernanceIssue]) -> str:
        if not issues:
            return "info"
        order = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
        return max((issue.severity for issue in issues), key=lambda x: order.get(x, 0))

    def _budget_patch_from_issues(self, issues: list[GovernanceIssue]) -> dict[str, Any]:
        if not issues:
            return {}
        patch: dict[str, Any] = {"must_reduce_new_storylines": False, "must_retouch_promise": False}
        for issue in issues:
            if issue.code in ("promise_drift", "premature_payoff"):
                patch["must_retouch_promise"] = True
                patch["allowed_reveal_level"] = "hint"
            if issue.code == "storyline_inflation":
                patch["must_reduce_new_storylines"] = True
                patch["max_new_storylines_delta"] = -1
        return patch

    def _pause_autopilot(self, novel_id: str) -> None:
        if not self.db:
            return
        try:
            conn = self.db.get_connection()
            conn.execute(
                """
                UPDATE novels
                SET autopilot_status = 'stopped',
                    current_stage = 'paused_for_review',
                    audit_progress = ?
                WHERE id = ?
                """,
                ("叙事治理发现严重结构风险，已暂停自动驾驶。", novel_id),
            )
            conn.commit()
        except Exception:
            return

    def _emit(
        self,
        novel_id: str,
        event_type: str,
        chapter_number: int | None,
        payload: dict[str, Any],
    ) -> None:
        try:
            self.repository.append_event(
                f"gevt_{uuid.uuid4().hex}",
                novel_id,
                event_type,
                chapter_number,
                payload,
            )
        except Exception:
            return
