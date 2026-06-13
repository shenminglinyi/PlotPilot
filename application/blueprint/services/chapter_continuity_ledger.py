"""Compact continuity ledger for planning prompts."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from application.blueprint.services.chapter_plan_renderer import (
    render_lightweight_act_chapter_outline,
    stringify_plan_value,
)
from application.blueprint.services.chapter_planning_policy import (
    DEFAULT_CHAPTER_PLANNING_POLICY,
    ChapterPlanningPolicy,
    truncate_text,
)
from domain.novel.value_objects.novel_id import NovelId


@dataclass
class ContinuityLedger:
    recent_events: list[dict[str, Any]] = field(default_factory=list)
    recent_planning_outlines: list[dict[str, Any]] = field(default_factory=list)
    previous_ending: str = ""
    previous_handoff: str = ""
    unresolved_threads: list[str] = field(default_factory=list)
    current_location: str = ""
    character_state: list[str] = field(default_factory=list)

    def to_prompt_text(self) -> str:
        lines: list[str] = []
        if self.previous_ending:
            lines.append(f"上一章结尾承诺：{self.previous_ending}")
        if self.previous_handoff:
            lines.append(f"上一章交接：{self.previous_handoff}")
        if self.current_location:
            lines.append(f"当前位置：{self.current_location}")
        if self.unresolved_threads:
            lines.append("未完成线索：")
            lines.extend(f"- {item}" for item in self.unresolved_threads if item)
        if self.character_state:
            lines.append("角色状态：")
            lines.extend(f"- {item}" for item in self.character_state if item)
        if self.recent_events:
            lines.append("最近章节台账：")
            for item in self.recent_events:
                number = item.get("number") or "?"
                title = item.get("title") or "未命名"
                summary = item.get("summary") or ""
                lines.append(f"- 第{number}章《{title}》：{summary}")
        return "\n".join(lines).strip() or "暂无近章台账。"

    def to_planning_context_text(self) -> str:
        """Render compact recent-chapter handoff summaries for planning and prose."""
        if not self.recent_planning_outlines:
            return "暂无近3章承接摘要。"
        lines = ["最近3章承接摘要："]
        for item in self.recent_planning_outlines:
            number = item.get("number") or "?"
            title = item.get("title") or "未命名"
            outline = str(item.get("outline") or "").strip()
            if outline:
                lines.append(f"第{number}章《{title}》\n{outline}")
        return "\n\n".join(lines).strip() or "暂无近3章承接摘要。"


class ChapterContinuityLedgerService:
    def __init__(
        self,
        *,
        chapter_repository: Any = None,
        story_node_repo: Any = None,
        policy: ChapterPlanningPolicy = DEFAULT_CHAPTER_PLANNING_POLICY,
    ) -> None:
        self.chapter_repository = chapter_repository
        self.story_node_repo = story_node_repo
        self.policy = policy

    def build_for_chapter(self, novel_id: str, chapter_number: int) -> ContinuityLedger:
        recent = self._recent_chapters(novel_id, chapter_number)
        previous = next((item for item in reversed(recent) if int(item.get("number") or 0) < chapter_number), None)
        previous_ending = truncate_text(str(previous.get("content") or ""), self.policy.previous_ending_chars) if previous else ""

        story_node = self._chapter_node(novel_id, chapter_number - 1)
        metadata = getattr(story_node, "metadata", {}) if story_node is not None else {}
        previous_handoff = ""
        if isinstance(metadata, dict):
            act_plan = metadata.get("act_chapter_plan")
            if isinstance(act_plan, dict):
                previous_handoff = str(act_plan.get("handoff_to_next") or "").strip()

        ledger = ContinuityLedger(
            recent_events=[
                {
                    "number": item.get("number"),
                    "title": item.get("title"),
                    "summary": self._chapter_summary(item),
                }
                for item in recent
                if int(item.get("number") or 0) < chapter_number
            ],
            recent_planning_outlines=[
                {
                    "number": item.get("number"),
                    "title": item.get("title"),
                    "outline": self._chapter_outline(item, self.policy.recent_outline_chars),
                }
                for item in recent
                if int(item.get("number") or 0) < chapter_number
                and str(item.get("outline") or "").strip()
            ],
            previous_ending=previous_ending,
            previous_handoff=previous_handoff,
        )
        current_node = self._chapter_node(novel_id, chapter_number)
        current_meta = getattr(current_node, "metadata", {}) if current_node is not None else {}
        if isinstance(current_meta, dict):
            act_plan = current_meta.get("act_chapter_plan")
            if isinstance(act_plan, dict):
                ledger.current_location = str(act_plan.get("location_hint") or "").strip()
                ledger.unresolved_threads = [str(x) for x in (act_plan.get("required_threads") or []) if str(x).strip()]
                cast = act_plan.get("cast_hint") or act_plan.get("characters") or []
                ledger.character_state = [str(x) for x in cast if str(x).strip()] if isinstance(cast, list) else [str(cast)]
        return ledger

    def _recent_chapters(self, novel_id: str, chapter_number: int) -> list[dict[str, Any]]:
        start = max(1, chapter_number - self.policy.recent_chapter_limit)
        rows: list[dict[str, Any]] = []
        node_by_number = self._chapter_nodes_by_number(novel_id, start, chapter_number)
        if self.chapter_repository is not None:
            try:
                chapters = self.chapter_repository.list_by_novel(NovelId(novel_id))
                for chapter in chapters:
                    number = int(getattr(chapter, "number", 0) or 0)
                    if start <= number < chapter_number:
                        node = node_by_number.get(number)
                        rows.append({
                            "number": number,
                            "title": getattr(chapter, "title", "") or "",
                            "outline": getattr(chapter, "outline", "") or "",
                            "content": getattr(chapter, "content", "") or "",
                            "metadata": getattr(node, "metadata", {}) if node is not None else {},
                        })
            except Exception:
                rows = []
        if rows:
            return sorted(rows, key=lambda item: int(item.get("number") or 0))[-self.policy.recent_chapter_limit :]

        if not node_by_number:
            return []
        try:
            candidates = list(node_by_number.values())
            candidates.sort(key=lambda node: int(getattr(node, "number", 0) or 0))
            return [
                {
                    "number": getattr(node, "number", 0),
                    "title": getattr(node, "title", "") or "",
                    "outline": getattr(node, "outline", "") or getattr(node, "description", "") or "",
                    "content": getattr(node, "content", "") or "",
                    "metadata": getattr(node, "metadata", {}) or {},
                }
                for node in candidates[-self.policy.recent_chapter_limit :]
            ]
        except Exception:
            return []

    def _chapter_node(self, novel_id: str, chapter_number: int):
        if chapter_number <= 0 or self.story_node_repo is None:
            return None
        try:
            nodes = self._story_nodes(novel_id)
            return next(
                (
                    node for node in nodes
                    if getattr(getattr(node, "node_type", None), "value", "") == "chapter"
                    and int(getattr(node, "number", 0) or 0) == chapter_number
                ),
                None,
            )
        except Exception:
            return None

    def _chapter_nodes_by_number(self, novel_id: str, start: int, chapter_number: int) -> dict[int, Any]:
        if self.story_node_repo is None:
            return {}
        out: dict[int, Any] = {}
        for node in self._story_nodes(novel_id):
            if getattr(getattr(node, "node_type", None), "value", "") != "chapter":
                continue
            try:
                number = int(getattr(node, "number", 0) or 0)
            except (TypeError, ValueError):
                continue
            if start <= number < chapter_number:
                out[number] = node
        return out

    def _story_nodes(self, novel_id: str) -> list[Any]:
        if self.story_node_repo is None:
            return []
        try:
            get_tree_sync = getattr(self.story_node_repo, "get_tree_sync", None)
            if callable(get_tree_sync):
                return list(get_tree_sync(novel_id).nodes)
            tree = self.story_node_repo.get_tree(novel_id)
            if hasattr(tree, "__await__"):
                return []
            return list(getattr(tree, "nodes", []) or [])
        except Exception:
            return []

    @staticmethod
    def _chapter_summary(item: dict[str, Any]) -> str:
        content = str(item.get("content") or "").strip()
        if content:
            return truncate_text(content, 180)
        outline = str(item.get("outline") or "").strip()
        return truncate_text(outline, 180)

    @staticmethod
    def _chapter_outline(item: dict[str, Any], limit: int) -> str:
        metadata = item.get("metadata")
        planned = ChapterContinuityLedgerService._planning_summary_from_metadata(metadata, limit)
        if planned:
            return planned
        outline = str(item.get("outline") or "").strip()
        return truncate_text_start(outline, limit)

    @staticmethod
    def _planning_summary_from_metadata(metadata: Any, limit: int) -> str:
        if not isinstance(metadata, dict):
            return ""
        act_plan = metadata.get("act_chapter_plan")
        if isinstance(act_plan, dict) and act_plan:
            return truncate_text_start(render_lightweight_act_chapter_outline(act_plan), limit)

        preplan = metadata.get("chapter_preplan")
        if not isinstance(preplan, dict):
            return ""
        lines: list[str] = []
        key_points = preplan.get("key_plot_points")
        if isinstance(key_points, list) and key_points:
            points = [stringify_plan_value(point) for point in key_points[:5]]
            points = [point for point in points if point]
            if points:
                lines.append("关键情节：" + "；".join(points))
        chapter_plan = preplan.get("chapter_plan")
        if isinstance(chapter_plan, dict):
            state = chapter_plan.get("protagonist_state_change") or chapter_plan.get("state_change")
            state_text = stringify_plan_value(state)
            if state_text:
                lines.append("章末状态：" + state_text)
        return truncate_text_start("\n".join(lines), limit)


def truncate_text_start(text: str | None, limit: int) -> str:
    value = (text or "").strip()
    if not value or limit <= 0:
        return ""
    return value if len(value) <= limit else value[:limit]
