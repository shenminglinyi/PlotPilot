from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional

from domain.evolution.contracts import ActionType
from domain.evolution.models import EvolutionAction


class EvolutionActionExtractor:
    """First-stage action dispatcher.

    This deterministic adapter consumes chapter text and existing evidence refs.
    Later versions can replace internals with an LLM JSON action extractor while
    keeping the action contract stable.
    """

    def extract(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
        evidence: Optional[Dict[str, Any]] = None,
    ) -> List[EvolutionAction]:
        text = (content or "").strip()
        if not text:
            return []

        refs = [{"type": "chapter", "novel_id": novel_id, "chapter_number": chapter_number}]
        if evidence:
            refs.append({"type": "aftermath_flags", "payload": evidence})

        actions: List[EvolutionAction] = []
        tail = text[-500:]
        actions.append(
            EvolutionAction(
                action_id=self._aid(novel_id, chapter_number, "scene", tail),
                type=ActionType.SET_SCENE_STATE.value,
                payload={
                    "time_anchor": f"chapter:{chapter_number}",
                    "location": self._infer_location(tail),
                    "unresolved_actions": self._infer_unresolved_actions(tail),
                },
                confidence=0.45,
                source_refs=refs,
            )
        )
        residue = self._infer_emotional_residue(tail)
        if residue:
            actions.append(
                EvolutionAction(
                    action_id=self._aid(novel_id, chapter_number, "residue", residue),
                    type=ActionType.SET_EMOTIONAL_RESIDUE.value,
                    payload={"description": residue},
                    confidence=0.5,
                    source_refs=refs,
                )
            )

        actions.append(
            EvolutionAction(
                action_id=self._aid(novel_id, chapter_number, "complete", str(len(text))),
                type=ActionType.COMPLETE_EVENT.value,
                payload={
                    "event_id": f"chapter:{chapter_number}:saved:{hashlib.sha1(text.encode('utf-8')).hexdigest()[:12]}"
                },
                confidence=1.0,
                source_refs=refs,
            )
        )
        return actions

    @staticmethod
    def _aid(novel_id: str, chapter_number: int, kind: str, value: str) -> str:
        raw = f"{novel_id}:{chapter_number}:{kind}:{value}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _infer_location(text: str) -> str:
        match = re.search(r"(在|于|回到|来到)([^，。！？\n]{2,18})(?:里|中|前|后|外|内|。|，)", text)
        return match.group(2).strip() if match else ""

    @staticmethod
    def _infer_unresolved_actions(text: str) -> List[str]:
        if any(mark in text[-80:] for mark in ["？", "?", "拔剑", "冲向", "推开", "正要", "尚未"]):
            return [text[-120:].strip()]
        return []

    @staticmethod
    def _infer_emotional_residue(text: str) -> str:
        cues = ["沉默", "杀机", "戒备", "不信任", "愤怒", "恐惧", "痛苦", "犹豫", "僵住"]
        hits = [cue for cue in cues if cue in text]
        if not hits:
            return ""
        return "章末残留情绪/张力：" + "、".join(hits[:4])
