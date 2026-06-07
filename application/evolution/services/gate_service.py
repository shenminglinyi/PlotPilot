from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from domain.evolution.models import EvolutionState


@dataclass
class EvolutionGateViolation:
    level: str
    type: str
    message: str
    suggestion: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class EvolutionGateReport:
    is_pass: bool
    violations: List[EvolutionGateViolation] = field(default_factory=list)
    required_continuations: List[str] = field(default_factory=list)
    repair_plan: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_pass": self.is_pass,
            "violations": [v.to_dict() for v in self.violations],
            "required_continuations": list(self.required_continuations),
            "repair_plan": list(self.repair_plan),
        }


class EvolutionGateBlockedError(RuntimeError):
    def __init__(self, report: EvolutionGateReport):
        super().__init__("evolution_gate_blocked")
        self.report = report


class EvolutionGateService:
    def __init__(self, snapshot_repository: Any = None, character_repository: Any = None):
        self.snapshot_repository = snapshot_repository
        self.character_repository = character_repository

    def check(
        self,
        novel_id: str,
        chapter_number: int,
        outline_content: str,
        branch_id: str = "main",
        pov_character_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        state: Optional[EvolutionState] = None,
    ) -> EvolutionGateReport:
        tags = tags or []
        outline = outline_content or ""
        if state is None and self.snapshot_repository:
            prev = self.snapshot_repository.get_latest_active_before(
                novel_id, branch_id, chapter_number
            )
            state = prev.ending_state if prev else EvolutionState.empty()
        state = state or EvolutionState.empty()

        violations: List[EvolutionGateViolation] = []
        required: List[str] = []
        bypass = self._has_bypass(tags, outline)
        character_labels = self._character_labels(novel_id, state)

        for char_id, char in (state.characters or {}).items():
            status = char.get("status")
            labels = character_labels.get(char_id) or {char_id}
            hit = next((label for label in labels if label and label in outline), "")
            if status == "dead" and hit:
                violations.append(
                    EvolutionGateViolation(
                        level="blocking",
                        type="DEAD_CHARACTER_REAPPEARS",
                        message=f"角色 {hit} 已死亡，但当前大纲仍让其以活跃人物出现。",
                        suggestion="改为回忆/遗物/传闻，或由作者 override 明确复活规则。",
                    )
                )

        unresolved = state.scene.get("unresolved_actions") or []
        for action in unresolved:
            required.append(f"未完成动作：{str(action)[:160]}")
            violations.append(
                EvolutionGateViolation(
                    level="info" if bypass else "blocking",
                    type="UNRESOLVED_ACTION",
                    message=(
                        "上一章存在未完成动作，当前大纲已声明艺术性跳跃豁免。"
                        if bypass
                        else "上一章存在未完成动作，当前大纲未声明 TimeSkip/HardCut 豁免。"
                    ),
                    suggestion="开篇承接该动作，或添加 [TimeSkip] / [HardCut]。",
                )
            )

        completed = set(state.completed_events or [])
        for event_id in completed:
            token = event_id.split(":")[-1]
            if token and len(token) > 6 and token in outline:
                violations.append(
                    EvolutionGateViolation(
                        level="blocking",
                        type="DUPLICATE_EVENT",
                        message=f"大纲疑似重复已完成事件 {event_id}。",
                        suggestion="将其写成回忆/后果，避免当作新事件再次发生。",
                    )
                )

        if pov_character_id:
            known = set((state.facts.get("character_known") or {}).get(pov_character_id, []))
            reader_known = set(state.facts.get("reader_known") or [])
            leaked = [fact for fact in reader_known if fact in outline and fact not in known]
            for fact in leaked[:5]:
                violations.append(
                    EvolutionGateViolation(
                        level="warning",
                        type="POV_LEAK",
                        message=f"当前 POV {pov_character_id} 尚未知晓读者事实：{fact}",
                        suggestion="让角色通过线索推断，或切换 POV / 添加 [POVSwitch]。",
                    )
                )

        repair = [v.suggestion for v in violations if v.level == "blocking" and v.suggestion]
        return EvolutionGateReport(
            is_pass=not any(v.level == "blocking" for v in violations),
            violations=violations,
            required_continuations=required,
            repair_plan=repair,
        )

    @staticmethod
    def _has_bypass(tags: List[str], outline: str) -> bool:
        text = " ".join(tags) + " " + outline
        return any(token in text for token in ["[TimeSkip", "[HardCut", "[POVSwitch", "[AmbiguousFate"])

    def _character_labels(self, novel_id: str, state: EvolutionState) -> Dict[str, set[str]]:
        labels: Dict[str, set[str]] = {}
        for char_id, char in (state.characters or {}).items():
            labels.setdefault(char_id, set()).add(char_id)
            if isinstance(char, dict) and char.get("name"):
                labels[char_id].add(str(char["name"]))
        if not self.character_repository:
            return labels
        try:
            for character in self.character_repository.list_by_novel(novel_id):
                cid = getattr(getattr(character, "id", None), "value", None) or str(getattr(character, "id", ""))
                if not cid:
                    continue
                labels.setdefault(cid, set()).add(cid)
                name = getattr(character, "name", "")
                if name:
                    labels[cid].add(str(name))
        except Exception:
            return labels
        return labels
