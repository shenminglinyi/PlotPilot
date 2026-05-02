"""写作手法知识库提示词 overlay 服务。"""
from __future__ import annotations

import re
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
        anchor_lines = self._collect_style_anchor_lines(profile)

        blocks = [
            "【写作手法库】",
            f"使用风格包：{profile.name}",
            "",
            "节奏约束：",
            *rhythm_lines,
            "",
            "技法卡：",
            *card_lines,
        ]
        if anchor_lines:
            blocks.extend(
                [
                    "",
                    "风格锚点（检索，不可复刻原句）：",
                    *anchor_lines,
                ]
            )
        blocks.extend(
            [
                "",
                "禁用项：",
                *forbidden_lines,
                "",
                "执行要求：",
                "- 只学习写法和节奏，不复刻样本文字、角色、设定或专有表达。",
                "- 风格锚点只能学“句法动作与节奏手法”，不得抄词复用。",
                "- 本章必须服从当前小说 Bible、章节大纲和连续性约束。",
            ]
        )
        return "\n".join(blocks)

    def _collect_style_anchor_lines(self, profile: StyleProfile) -> list[str]:
        raw_max = (profile.profile or {}).get("anchor_max")
        try:
            max_anchors = int(raw_max) if raw_max is not None else 6
        except (TypeError, ValueError):
            max_anchors = 6
        max_anchors = max(0, min(10, max_anchors))
        if max_anchors <= 0:
            return []

        sample_ids = []
        for item in (profile.profile or {}).get("source_sample_ids", []) or []:
            sid = str(item or "").strip()
            if sid and sid not in sample_ids:
                sample_ids.append(sid)
        if not sample_ids:
            return []

        anchors: list[str] = []
        seen_norms: set[str] = set()
        for sample_id in sample_ids:
            sample = self.repository.get_sample(sample_id)
            if sample is None:
                continue
            if not bool(getattr(sample, "allowed_for_generation", False)):
                continue
            for line in self._extract_anchor_candidates(sample.content):
                norm = re.sub(r"\s+", "", line)
                if norm in seen_norms:
                    continue
                seen_norms.add(norm)
                anchors.append(f"- {line}")
                if len(anchors) >= max_anchors:
                    return anchors
        return anchors

    @staticmethod
    def _extract_anchor_candidates(text: str) -> list[str]:
        source = str(text or "").strip()
        if not source:
            return []
        # 优先对白与动作短句，避免抽样成大段总结。
        raw = re.split(r"[\n\r。！？!?；;]", source)
        candidates: list[str] = []
        for chunk in raw:
            line = chunk.strip(" \t\"'“”‘’")
            if not line:
                continue
            length = len(line)
            if length < 14 or length > 56:
                continue
            score = 0
            if "“" in chunk or "”" in chunk or "：" in chunk:
                score += 3
            if re.search(r"(抬|看|停|停住|拧|攥|贴|压|拽|敲|咬|盯|笑|喘|退|靠|转|转身|沉默|没说话)", line):
                score += 2
            if re.search(r"(于是|然后|最终|总之|事实上|可以看出|显然)", line):
                score -= 2
            if score <= 0:
                continue
            candidates.append((score, line))
        candidates.sort(key=lambda item: (-item[0], len(item[1])))
        return [line for _, line in candidates[:16]]

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
