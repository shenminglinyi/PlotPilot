"""写作手法知识库提示词 overlay 服务。"""
from __future__ import annotations

from typing import Optional

from application.style_bible.dtos import StylePromptOverlayDTO
from domain.style_bible.entities import StyleProfile, StyleTechniqueCard
from domain.style_bible.repositories import StyleBibleRepository


class StylePromptOverlayService:
    """把风格档案压缩为章节生成可用的提示词片段。"""

    def __init__(self, repository: StyleBibleRepository):
        self.repository = repository

    def build_overlay(
        self,
        novel_id: str,
        style_profile_id: str,
        *,
        scene_type: str = "",
        max_cards: int = 6,
    ) -> StylePromptOverlayDTO:
        profile_id = (style_profile_id or "").strip()
        if not profile_id:
            return StylePromptOverlayDTO(prompt="")

        profile = self.repository.get_profile(profile_id)
        if profile is None or profile.status != "active":
            return StylePromptOverlayDTO(prompt="")
        if novel_id and profile.novel_id and profile.novel_id != novel_id:
            return StylePromptOverlayDTO(prompt="")

        cards = self._rank_cards(
            self.repository.list_technique_cards(profile.id, enabled=True),
            scene_type,
        )[: max(1, int(max_cards or 6))]
        prompt = self._render_prompt(profile, cards)
        return StylePromptOverlayDTO(
            prompt=prompt,
            profile_id=profile.id,
            profile_name=profile.name,
            card_ids=[card.id for card in cards],
        )

    def _render_prompt(
        self,
        profile: StyleProfile,
        cards: list[StyleTechniqueCard],
    ) -> str:
        metrics = profile.metrics or {}
        sentence_len = metrics.get("avg_sentence_length")
        paragraph_len = metrics.get("avg_paragraph_length")
        rhythm_lines: list[str] = []
        if sentence_len:
            rhythm_lines.append(f"- 平均句长靠近 {float(sentence_len):.1f} 字，关键动作可短句单独成段")
        if paragraph_len:
            rhythm_lines.append(f"- 段落以 {int(float(paragraph_len))} 字附近为主，避免连续长段解释")
        for rule in profile.rules[:3]:
            rhythm_lines.append(f"- {rule}")
        if not rhythm_lines:
            rhythm_lines.append("- 用动作、对白和信息变化推动节奏，避免解释性空转")

        card_lines = [
            f"- {card.prompt_instruction}"
            for card in cards
            if card.prompt_instruction
        ]
        if not card_lines:
            card_lines.append("- 每个场景至少产生一次信息、关系或目标变化")

        forbidden_lines = [
            f"- {item}" for item in profile.forbidden_patterns[:6] if str(item).strip()
        ]
        if not forbidden_lines:
            forbidden_lines.append("- 总结式抒情、空泛心理、套路化氛围句")

        return "\n".join(
            [
                "【写作手法库】",
                f"使用风格包：{profile.name}",
                "",
                "节奏约束：",
                *rhythm_lines,
                "",
                "技法卡：",
                *card_lines,
                "",
                "禁用项：",
                *forbidden_lines,
                "",
                "执行要求：",
                "- 只学习写法和节奏，不复刻样本文字、角色、设定或专有表达。",
                "- 本章必须服从当前小说 Bible、章节大纲和连续性约束。",
            ]
        )

    @staticmethod
    def _rank_cards(
        cards: list[StyleTechniqueCard],
        scene_type: Optional[str],
    ) -> list[StyleTechniqueCard]:
        wanted_scene = (scene_type or "").strip()

        def key(card: StyleTechniqueCard) -> tuple[int, float, str]:
            scene_match = 1 if wanted_scene and card.scene_type == wanted_scene else 0
            return (scene_match, card.weight, card.title)

        return sorted(cards, key=key, reverse=True)
