"""写作手法档案生成服务。"""
from __future__ import annotations

from typing import Any, Callable, Optional

from application.style_bible.dtos import (
    StyleChunkDTO,
    StyleProfileDTO,
    StyleProfileGenerateRequestDTO,
    StyleProfileGenerateResultDTO,
    StyleSampleDTO,
    StyleSampleImportRequestDTO,
    StyleSampleImportResultDTO,
    StyleTechniqueCardDTO,
)
from application.style_bible.services.style_metric_analyzer import StyleMetricAnalyzer
from application.style_bible.services.text_splitter import StyleTextSplitter
from domain.style_bible.entities import (
    StyleProfile,
    StyleSample,
    StyleTechniqueCard,
)
from domain.style_bible.repositories import StyleBibleRepository


LlmExtractor = Callable[[list[StyleSample], dict[str, Any]], dict[str, Any]]


class StyleProfileService:
    """协调样本导入、指标分析和风格档案生成。"""

    def __init__(
        self,
        repository: StyleBibleRepository,
        splitter: Optional[StyleTextSplitter] = None,
        analyzer: Optional[StyleMetricAnalyzer] = None,
        llm_extractor: Optional[LlmExtractor] = None,
    ):
        self.repository = repository
        self.splitter = splitter or StyleTextSplitter()
        self.analyzer = analyzer or StyleMetricAnalyzer()
        self.llm_extractor = llm_extractor

    def import_sample(
        self,
        request: StyleSampleImportRequestDTO,
    ) -> StyleSampleImportResultDTO:
        sample = StyleSample(
            title=request.title,
            content=request.content,
            source_type=request.source_type,
            genre=request.genre,
            scene_type=request.scene_type,
            pov=request.pov,
            allowed_for_generation=request.allowed_for_generation,
            novel_id=request.novel_id,
            profile_id=request.profile_id,
        )
        chunks = self.splitter.split(sample.id, sample.content)
        for chunk in chunks:
            chunk.metrics = self.analyzer.analyze(chunk.content)

        saved_sample = self.repository.save_sample(sample, chunks)
        profile_result: StyleProfileGenerateResultDTO | None = None
        if request.create_profile:
            profile_result = self.generate_profile_from_samples(
                StyleProfileGenerateRequestDTO(
                    novel_id=request.novel_id,
                    name=request.profile_name or request.title,
                    sample_ids=[saved_sample.id],
                    use_llm=False,
                )
            )

        return StyleSampleImportResultDTO(
            sample=self._sample_to_dto(saved_sample),
            chunks=[self._chunk_to_dto(chunk) for chunk in chunks],
            profile=profile_result.profile if profile_result else None,
            cards=profile_result.cards if profile_result else [],
        )

    def generate_profile_from_samples(
        self,
        request: StyleProfileGenerateRequestDTO,
    ) -> StyleProfileGenerateResultDTO:
        samples = self._resolve_samples(request)
        metrics = self.analyzer.aggregate(
            [self.analyzer.analyze(sample.content) for sample in samples]
        )
        payload = self._extract_llm_payload(request, samples, metrics)
        if payload:
            summary = payload["profile_summary"]
            rhythm_rules = payload["rhythm_rules"]
            forbidden_patterns = payload["forbidden_patterns"]
            cards = self._cards_from_payload("", payload["technique_cards"])
        else:
            summary = self._fallback_summary(metrics)
            rhythm_rules = self._fallback_rules(metrics)
            forbidden_patterns = self._fallback_forbidden_patterns(metrics)
            cards = self._fallback_cards("", metrics, samples)

        profile = StyleProfile(
            name=request.name,
            description=request.description or summary,
            novel_id=request.novel_id,
            profile={
                "summary": summary,
                "source_sample_ids": [sample.id for sample in samples],
            },
            metrics=metrics,
            rules=rhythm_rules,
            forbidden_patterns=forbidden_patterns,
        )
        saved_profile = self.repository.save_profile(profile)

        cards = [
            StyleTechniqueCard(
                id=card.id,
                profile_id=saved_profile.id,
                title=card.title,
                category=card.category,
                scene_type=card.scene_type,
                rule_text=card.rule_text,
                example_summary=card.example_summary,
                prompt_instruction=card.prompt_instruction,
                enabled=card.enabled,
                weight=card.weight,
                created_at=card.created_at,
                updated_at=card.updated_at,
            )
            for card in cards
        ]
        saved_cards = self.repository.save_technique_cards(saved_profile.id, cards)
        return StyleProfileGenerateResultDTO(
            profile=self._profile_to_dto(saved_profile),
            cards=[self._card_to_dto(card) for card in saved_cards],
        )

    def normalize_llm_profile_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized_cards: list[dict[str, str]] = []
        for item in self._as_list(payload.get("technique_cards")):
            if not isinstance(item, dict):
                continue
            card = {
                "title": self._as_text(item.get("title")),
                "category": self._as_text(item.get("category")) or "pacing",
                "scene_type": self._as_text(item.get("scene_type")),
                "rule_text": self._as_text(item.get("rule_text")),
                "example_summary": self._as_text(item.get("example_summary")),
                "prompt_instruction": self._as_text(item.get("prompt_instruction")),
            }
            if card["title"] and card["rule_text"] and card["prompt_instruction"]:
                normalized_cards.append(card)

        return {
            "profile_summary": self._as_text(payload.get("profile_summary")),
            "rhythm_rules": [self._as_text(item) for item in self._as_list(payload.get("rhythm_rules")) if self._as_text(item)],
            "forbidden_patterns": [
                self._as_text(item)
                for item in self._as_list(payload.get("forbidden_patterns"))
                if self._as_text(item)
            ],
            "technique_cards": normalized_cards,
        }

    def _resolve_samples(
        self,
        request: StyleProfileGenerateRequestDTO,
    ) -> list[StyleSample]:
        samples: list[StyleSample] = []
        for sample_id in request.sample_ids:
            sample = self.repository.get_sample(sample_id)
            if sample is not None:
                samples.append(sample)
        if not samples and request.novel_id:
            samples = self.repository.list_samples(novel_id=request.novel_id)
        if not samples:
            raise ValueError("No style samples available for profile generation")
        return samples

    def _extract_llm_payload(
        self,
        request: StyleProfileGenerateRequestDTO,
        samples: list[StyleSample],
        metrics: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not request.use_llm or self.llm_extractor is None:
            return None
        try:
            payload = self.llm_extractor(samples, metrics)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        normalized = self.normalize_llm_profile_payload(payload)
        if normalized["profile_summary"] and normalized["technique_cards"]:
            return normalized
        return None

    def _fallback_summary(self, metrics: dict[str, Any]) -> str:
        sentence_len = metrics.get("avg_sentence_length") or 0
        dialogue_ratio = metrics.get("dialogue_ratio") or 0
        return (
            f"平均句长约 {sentence_len:.1f} 字，对白占比约 {dialogue_ratio:.0%}，"
            "以可执行的节奏和动作细节学习样本写法。"
        )

    def _fallback_rules(self, metrics: dict[str, Any]) -> list[str]:
        avg_paragraph = int(metrics.get("avg_paragraph_length") or 0)
        avg_sentence = int(metrics.get("avg_sentence_length") or 0)
        rules = [
            f"平均句长控制在 {max(8, avg_sentence - 4)}-{max(12, avg_sentence + 4)} 字附近",
            f"段落以 {max(40, avg_paragraph - 80)}-{max(80, avg_paragraph + 80)} 字为主",
            "每 600-900 字至少出现一次信息、关系或目标变化",
        ]
        if metrics.get("dialogue_ratio", 0) > 0:
            rules.append("对白必须承担试探、冲突或信息推进，不写空泛寒暄")
        return rules

    def _fallback_forbidden_patterns(self, metrics: dict[str, Any]) -> list[str]:
        patterns = [str(item) for item in metrics.get("cliche_patterns") or []]
        base = ["五味杂陈", "眼中闪过一丝复杂", "空气仿佛凝固"]
        result: list[str] = []
        for item in patterns + base:
            if item and item not in result:
                result.append(item)
        return result

    def _fallback_cards(
        self,
        profile_id: str,
        metrics: dict[str, Any],
        samples: list[StyleSample],
    ) -> list[StyleTechniqueCard]:
        sample_scene_type = next((sample.scene_type for sample in samples if sample.scene_type), "")
        cards = [
            StyleTechniqueCard(
                profile_id=profile_id or "pending",
                title="节奏推进",
                category="pacing",
                scene_type=sample_scene_type,
                rule_text="用短目标、动作和信息变化推动段落。",
                example_summary="从样本句长和段落长度提取节奏边界。",
                prompt_instruction="每 600-900 字安排一次信息、关系或目标变化，避免连续解释。",
                weight=1.0,
            ),
            StyleTechniqueCard(
                profile_id=profile_id or "pending",
                title="对白试探",
                category="dialogue",
                scene_type=sample_scene_type,
                rule_text="对白必须带有试探、反问、隐瞒或信息交换。",
                example_summary="根据样本对白占比生成对白约束。",
                prompt_instruction="对白不要只表达态度，每两轮对白释放一个新信息或改变关系压力。",
                weight=0.9 if metrics.get("dialogue_ratio", 0) > 0 else 0.55,
            ),
            StyleTechniqueCard(
                profile_id=profile_id or "pending",
                title="去AI味禁用",
                category="anti_ai",
                scene_type="",
                rule_text="禁用总结式抒情和常见套话。",
                example_summary="结合样本或系统俗套扫描器形成禁用项。",
                prompt_instruction="不要写五味杂陈、眼神复杂、空气凝固等套话；情绪必须落到动作、选择和对白上。",
                weight=1.0 if metrics.get("cliche_hit_count", 0) > 0 else 0.7,
            ),
            StyleTechniqueCard(
                profile_id=profile_id or "pending",
                title="章尾钩子",
                category="hook",
                scene_type=sample_scene_type,
                rule_text="章尾保留未解信息或关系压力。",
                example_summary="根据样本末句疑问、转折或新信息形成钩子规则。",
                prompt_instruction="结尾保留一个未确认事实、异常细节或关系压力，不要用总结收束。",
                weight=0.85,
            ),
        ]
        return cards

    def _cards_from_payload(
        self,
        profile_id: str,
        cards_payload: list[dict[str, str]],
    ) -> list[StyleTechniqueCard]:
        return [
            StyleTechniqueCard(
                profile_id=profile_id or "pending",
                title=item["title"],
                category=item["category"],
                scene_type=item["scene_type"],
                rule_text=item["rule_text"],
                example_summary=item["example_summary"],
                prompt_instruction=item["prompt_instruction"],
            )
            for item in cards_payload
        ]

    @staticmethod
    def _as_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            return "；".join(
                str(item).strip() for item in value.values() if str(item).strip()
            )
        if isinstance(value, (list, tuple, set)):
            return "；".join(
                str(item).strip() for item in value if str(item).strip()
            )
        return str(value).strip()

    @staticmethod
    def _as_list(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        if isinstance(value, set):
            return list(value)
        if isinstance(value, dict):
            return list(value.values())
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        return [value]

    @staticmethod
    def _sample_to_dto(sample: StyleSample) -> StyleSampleDTO:
        return StyleSampleDTO(
            id=sample.id,
            title=sample.title,
            content=sample.content,
            source_type=sample.source_type,
            genre=sample.genre,
            scene_type=sample.scene_type,
            pov=sample.pov,
            allowed_for_generation=sample.allowed_for_generation,
            novel_id=sample.novel_id,
            profile_id=sample.profile_id,
            content_hash=sample.content_hash,
            char_count=sample.char_count,
        )

    @staticmethod
    def _chunk_to_dto(chunk) -> StyleChunkDTO:
        return StyleChunkDTO(
            id=chunk.id,
            sample_id=chunk.sample_id,
            chunk_type=chunk.chunk_type,
            sequence=chunk.sequence,
            chapter_number=chunk.chapter_number,
            title=chunk.title,
            content=chunk.content,
            char_count=chunk.char_count,
            metrics=chunk.metrics,
        )

    @staticmethod
    def _profile_to_dto(profile: StyleProfile) -> StyleProfileDTO:
        return StyleProfileDTO(
            id=profile.id,
            name=profile.name,
            description=profile.description,
            status=profile.status,
            novel_id=profile.novel_id,
            profile=profile.profile,
            metrics=profile.metrics,
            rules=profile.rules,
            forbidden_patterns=profile.forbidden_patterns,
            version=profile.version,
        )

    @staticmethod
    def _card_to_dto(card: StyleTechniqueCard) -> StyleTechniqueCardDTO:
        return StyleTechniqueCardDTO(
            id=card.id,
            profile_id=card.profile_id,
            title=card.title,
            category=card.category,
            scene_type=card.scene_type,
            rule_text=card.rule_text,
            example_summary=card.example_summary,
            prompt_instruction=card.prompt_instruction,
            enabled=card.enabled,
            weight=card.weight,
        )
