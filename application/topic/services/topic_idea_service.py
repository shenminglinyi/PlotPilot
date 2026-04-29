"""选题立项应用服务。"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Any, Optional
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from application.ai.knowledge_llm_contract import parse_json_from_response
from application.core.services.novel_service import NovelService
from application.topic.dtos import (
    TopicMarketSignalCollectRequestDTO,
    TopicMarketSignalAutomationSettingsDTO,
    TopicMarketSignalSourceCredentialDTO,
    TopicMarketSignalSourceCredentialStatusDTO,
    TopicMarketSignalSourceConnectionDTO,
    TopicMarketSignalSourceHealthDTO,
    TopicMarketSignalDTO,
    TopicMarketSignalImportRequestDTO,
    TopicMarketSignalSummaryDTO,
    TopicMarketSignalSourceDTO,
    TopicGenerateRequestDTO,
    TopicIdeaCompareResultDTO,
    TopicIdeaDTO,
    TopicIdeaRankingDTO,
)
from application.topic.services.topic_signal_collectors import (
    build_market_signal_collectors,
    collect_market_signals_from_source,
)
from application.topic.services.topic_signal_sources import (
    DEFAULT_MARKET_SIGNAL_SOURCE_WEIGHTS,
    MARKET_SIGNAL_SOURCES,
)
from domain.ai.services.llm_service import GenerationConfig, LLMService
from domain.ai.value_objects.prompt import Prompt
from domain.topic.entities import TopicIdea, TopicIdeaStatus
from domain.topic.repositories import TopicIdeaRepository

logger = logging.getLogger(__name__)

ENRICHMENT_FIELDS = {
    "premise",
    "protagonist_hook",
    "core_conflict",
    "opening_hook",
    "selling_points",
    "long_term_potential",
    "risk_notes",
    "market_tags",
    "score",
    "development_notes",
    "evaluation",
}
TEXT_ENRICHMENT_FIELDS = {
    "premise",
    "protagonist_hook",
    "core_conflict",
    "opening_hook",
    "long_term_potential",
}
LIST_ENRICHMENT_FIELDS = {"selling_points", "risk_notes", "market_tags"}
DICT_ENRICHMENT_FIELDS = {"development_notes", "evaluation"}

class TopicIdeaGenerationError(RuntimeError):
    """LLM 选题生成调用失败。"""


class TopicIdeaService:
    """选题立项池核心用例。"""

    def __init__(
        self,
        repository: TopicIdeaRepository,
        llm_service: Optional[LLMService] = None,
        novel_service: Optional[NovelService] = None,
        fetch_text: Any = None,
    ):
        self._repository = repository
        self._llm = llm_service
        self._novel_service = novel_service
        self._fetch_text = fetch_text or self._fetch_url_text
        self._collectors = build_market_signal_collectors()

    async def generate(self, request: TopicGenerateRequestDTO) -> list[TopicIdeaDTO]:
        """生成选题候选，不足时用本地候选补足。"""
        count = request.normalized_count()
        raw_items = await self._generate_with_llm(request) if self._llm else []
        ideas = self._build_ideas(raw_items, request, count)
        for idea in ideas:
            self._repository.save(idea)
        return [TopicIdeaDTO.from_domain(idea) for idea in ideas]

    def import_market_signals(
        self,
        request: TopicMarketSignalImportRequestDTO,
    ) -> list[TopicMarketSignalDTO]:
        """从粘贴文本导入市场观察信号。"""
        signals = [
            self._market_signal_from_line(line, request.source)
            for line in (request.raw_text or "").splitlines()
            if line.strip()
        ]
        if not signals:
            raise ValueError("No market signal text provided")
        self._repository.save_market_signals(signals)
        return signals

    def collect_market_signals(
        self,
        request: TopicMarketSignalCollectRequestDTO,
    ) -> list[TopicMarketSignalDTO]:
        """从公开来源手动触发采集市场信号。"""
        source_keys = request.source_keys or list(MARKET_SIGNAL_SOURCES)
        limit = max(1, min(int(request.limit_per_source or 10), 30))
        signals: list[TopicMarketSignalDTO] = []
        credentials_by_source = self._market_signal_credentials_by_source()
        for source_key in source_keys:
            source = MARKET_SIGNAL_SOURCES.get(str(source_key).strip())
            if source is None:
                continue
            credentials = credentials_by_source.get(source.key)
            collected = collect_market_signals_from_source(
                source=self._source_with_credentials(source, credentials),
                fetch_text=self._fetch_text,
                limit=limit,
                collectors=self._collectors,
                credentials=credentials,
            )
            signals.extend(collected)
            self._record_market_signal_source_health(source, collected)
        if not signals:
            raise ValueError("No market signals collected")
        self._repository.save_market_signals(signals)
        return signals

    def test_market_signal_sources(
        self,
        request: TopicMarketSignalCollectRequestDTO,
    ) -> list[TopicMarketSignalSourceConnectionDTO]:
        """测试市场信号来源连接，不入库。"""
        source_keys = request.source_keys or list(MARKET_SIGNAL_SOURCES)
        limit = max(1, min(int(request.limit_per_source or 1), 5))
        credentials_by_source = self._market_signal_credentials_by_source()
        results: list[TopicMarketSignalSourceConnectionDTO] = []
        for source_key in source_keys:
            key = str(source_key or "").strip()
            source = MARKET_SIGNAL_SOURCES.get(key)
            if source is None:
                results.append(
                    TopicMarketSignalSourceConnectionDTO(
                        source_key=key,
                        source_name=key,
                        ok=False,
                        message=f"Unknown source: {key}",
                    )
                )
                continue
            credentials = credentials_by_source.get(source.key)
            signals = collect_market_signals_from_source(
                source=self._source_with_credentials(source, credentials),
                fetch_text=self._fetch_text,
                limit=limit,
                collectors=self._collectors,
                credentials=credentials,
            )
            results.append(
                TopicMarketSignalSourceConnectionDTO(
                    source_key=source.key,
                    source_name=source.name,
                    ok=bool(signals),
                    count=len(signals),
                    message="ok" if signals else "No signals collected",
                    sample_titles=[signal.title or signal.summary for signal in signals[:3]],
                )
            )
        return results

    def list_market_signals(self, limit: int = 20) -> list[TopicMarketSignalDTO]:
        safe_limit = max(1, min(int(limit or 20), 100))
        return self._repository.list_market_signals(safe_limit)

    def list_market_signal_source_health(self) -> list[TopicMarketSignalSourceHealthDTO]:
        getter = getattr(self._repository, "list_market_signal_source_health", None)
        saved = getter() if callable(getter) else []
        saved_by_key = {
            item.source_key: item
            for item in saved
            if isinstance(item, TopicMarketSignalSourceHealthDTO)
        }
        settings = self.get_market_signal_settings()
        return [
            self._source_health_for(source, saved_by_key.get(source_key), settings)
            for source_key, source in MARKET_SIGNAL_SOURCES.items()
        ]

    def summarize_market_signals(self, limit: int = 100) -> TopicMarketSignalSummaryDTO:
        """汇总最近市场信号，用于快速判断来源、题材和分类趋势。"""
        safe_limit = max(1, min(int(limit or 100), 300))
        settings = self.get_market_signal_settings()
        signals = self._recent_market_signals(
            limit=max(safe_limit, 200),
            lookback_days=settings.lookback_days,
        )[:safe_limit]
        source_counts: dict[str, int] = {}
        genre_counts: dict[str, int] = {}
        tag_counts: dict[str, int] = {}
        category_counts: dict[str, int] = {}
        weighted_source_scores: dict[str, float] = {}
        weighted_genre_scores: dict[str, float] = {}
        weighted_tag_scores: dict[str, float] = {}
        comic_opportunities: list[str] = []
        daily_counts: dict[str, int] = {}
        for signal in signals:
            self._increment_count(source_counts, signal.source or "未知来源")
            if signal.genre:
                self._increment_count(genre_counts, signal.genre)
            for tag in signal.tags:
                if tag:
                    self._increment_count(tag_counts, tag)
            self._increment_count(category_counts, self._infer_market_signal_category(signal))
            weight = self._source_weight_for_signal(signal, settings)
            self._increment_float(weighted_source_scores, signal.source or "未知来源", weight)
            if signal.genre:
                self._increment_float(weighted_genre_scores, signal.genre, weight)
            for tag in signal.tags:
                if tag:
                    self._increment_float(weighted_tag_scores, tag, weight)
            day_key = self._signal_date(signal)
            if day_key:
                daily_counts[day_key] = daily_counts.get(day_key, 0) + 1
            if self._infer_market_signal_category(signal) == "comic":
                comic_opportunities.extend(
                    self._comic_opportunities_for_signal(signal, "小说")
                )
        return TopicMarketSignalSummaryDTO(
            total=len(signals),
            source_counts=source_counts,
            genre_counts=genre_counts,
            tag_counts=tag_counts,
            category_counts=category_counts,
            window_days=settings.lookback_days,
            weighted_source_scores=self._rounded_scores(weighted_source_scores),
            weighted_genre_scores=self._rounded_scores(weighted_genre_scores),
            weighted_tag_scores=self._rounded_scores(weighted_tag_scores),
            comic_opportunities=self._merge_unique([], comic_opportunities)[:6],
            daily_counts=[
                {"date": date, "count": daily_counts[date]}
                for date in sorted(daily_counts)
            ],
            recent_samples=signals[:10],
        )

    def list_market_signal_sources(self) -> list[TopicMarketSignalSourceDTO]:
        return list(MARKET_SIGNAL_SOURCES.values())

    def get_market_signal_settings(self) -> TopicMarketSignalAutomationSettingsDTO:
        getter = getattr(self._repository, "get_market_signal_settings", None)
        settings = getter() if callable(getter) else None
        if not isinstance(settings, TopicMarketSignalAutomationSettingsDTO):
            settings = TopicMarketSignalAutomationSettingsDTO()
        return self._normalize_market_signal_settings(settings)

    def update_market_signal_settings(
        self,
        changes: dict[str, Any],
    ) -> TopicMarketSignalAutomationSettingsDTO:
        settings = self.get_market_signal_settings()
        for key, value in (changes or {}).items():
            if hasattr(settings, key):
                setattr(settings, key, value)
        normalized = self._normalize_market_signal_settings(settings)
        saver = getattr(self._repository, "save_market_signal_settings", None)
        if callable(saver):
            return saver(normalized)
        return normalized

    def list_market_signal_source_credentials(self) -> list[TopicMarketSignalSourceCredentialStatusDTO]:
        by_source = self._market_signal_credentials_by_source()
        return [
            self._credential_status_for(
                by_source.get(source_key)
                or TopicMarketSignalSourceCredentialDTO(source_key=source_key)
            )
            for source_key in MARKET_SIGNAL_SOURCES
        ]

    def _market_signal_credentials_by_source(self) -> dict[str, TopicMarketSignalSourceCredentialDTO]:
        getter = getattr(self._repository, "list_market_signal_credentials", None)
        credentials = getter() if callable(getter) else []
        return {
            credential.source_key: credential
            for credential in credentials
            if isinstance(credential, TopicMarketSignalSourceCredentialDTO)
        }

    def update_market_signal_source_credentials(
        self,
        source_key: str,
        changes: dict[str, Any],
    ) -> TopicMarketSignalSourceCredentialStatusDTO:
        key = str(source_key or "").strip()
        if key not in MARKET_SIGNAL_SOURCES:
            raise ValueError(f"Unknown market signal source: {source_key}")
        existing = self._market_signal_credentials_by_source().get(key)
        api_key = (
            str(changes.get("api_key") or "").strip()
            if "api_key" in changes
            else (existing.api_key if existing else "")
        )
        cookie = (
            str(changes.get("cookie") or "").strip()
            if "cookie" in changes
            else (existing.cookie if existing else "")
        )
        endpoint_url = (
            str(changes.get("endpoint_url") or "").strip()
            if "endpoint_url" in changes
            else (existing.endpoint_url if existing else "")
        )
        headers = (
            self._normalize_credential_headers(changes.get("headers") or {})
            if "headers" in changes
            else (existing.headers if existing else {})
        )
        credentials = TopicMarketSignalSourceCredentialDTO(
            source_key=key,
            api_key=api_key,
            cookie=cookie,
            endpoint_url=endpoint_url,
            headers=headers,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        saver = getattr(self._repository, "save_market_signal_credentials", None)
        if callable(saver):
            credentials = saver(credentials)
        return self._credential_status_for(credentials)

    def list(self, status: str | None = None) -> list[TopicIdeaDTO]:
        return [
            TopicIdeaDTO.from_domain(idea)
            for idea in self._repository.list(status)
        ]

    def get(self, idea_id: str) -> Optional[TopicIdeaDTO]:
        idea = self._repository.get_by_id(idea_id)
        return TopicIdeaDTO.from_domain(idea) if idea else None

    def update_status(
        self,
        idea_id: str,
        status: str,
        adopted_novel_id: Optional[str] = None,
    ) -> Optional[TopicIdeaDTO]:
        idea = self._repository.update_status(idea_id, status, adopted_novel_id)
        return TopicIdeaDTO.from_domain(idea) if idea else None

    def update(self, idea_id: str, changes: dict[str, Any]) -> Optional[TopicIdeaDTO]:
        idea = self._repository.get_by_id(idea_id)
        if idea is None:
            return None

        editable = {
            "title",
            "genre",
            "world_preset",
            "length_tier",
            "logline",
            "premise",
            "protagonist_hook",
            "core_conflict",
            "opening_hook",
            "selling_points",
            "long_term_potential",
            "risk_notes",
            "market_tags",
            "score",
            "development_notes",
            "evaluation",
        }
        for key, value in changes.items():
            if key in editable:
                setattr(idea, key, value)
        if "status" in changes:
            idea.update_status(changes["status"])
        idea.__post_init__()
        idea.updated_at = datetime.now(timezone.utc)
        updated = self._repository.update(idea)
        return TopicIdeaDTO.from_domain(updated)

    async def deepen(self, idea_id: str) -> TopicIdeaDTO:
        """深化单条选题，补齐立项案核心字段。"""
        idea = self._get_required(idea_id)
        payload = await self._enrich_with_llm(idea, "deepen") if self._llm else None
        if payload is None:
            payload = self._fallback_deepen_payload(idea)
        updated = self._apply_enrichment(idea, payload, fill_missing=False)
        return TopicIdeaDTO.from_domain(updated)

    async def evaluate(self, idea_id: str) -> TopicIdeaDTO:
        """评估单条选题，把结果落到现有立项字段。"""
        idea = self._get_required(idea_id)
        payload = await self._enrich_with_llm(idea, "evaluate") if self._llm else None
        if payload is None:
            payload = self._fallback_evaluate_payload(idea)
        payload = self._merge_market_evaluation(idea, payload)
        updated = self._apply_enrichment(idea, payload, fill_missing=False)
        return TopicIdeaDTO.from_domain(updated)

    def compare(self, topic_ids: list[str]) -> TopicIdeaCompareResultDTO:
        """对比多个选题，不落库。"""
        clean_ids = []
        for topic_id in topic_ids:
            clean_id = str(topic_id).strip()
            if clean_id and clean_id not in clean_ids:
                clean_ids.append(clean_id)
        if len(clean_ids) < 2:
            raise ValueError("At least two topic_ids are required")
        if len(clean_ids) > 5:
            raise ValueError("At most five topic_ids are supported")

        ideas = [self._get_required(topic_id) for topic_id in clean_ids]
        rankings = sorted(
            (self._ranking_for(idea) for idea in ideas),
            key=lambda item: item.score,
            reverse=True,
        )
        recommended = rankings[0]
        summary = (
            f"推荐《{recommended.title}》优先立项：综合评分 {recommended.score}，"
            f"{recommended.reason}"
        )
        return TopicIdeaCompareResultDTO(
            recommended_topic_id=recommended.topic_id,
            summary=summary,
            rankings=rankings,
        )

    def adopt(self, idea_id: str, author: str = "未知作者") -> Any:
        """采纳选题创建小说；已采纳过则返回既有小说，避免重复创建。"""
        if self._novel_service is None:
            raise ValueError("NovelService is required to adopt a topic idea")

        idea = self._repository.get_by_id(idea_id)
        if idea is None:
            raise ValueError(f"Topic idea not found: {idea_id}")

        if idea.status == TopicIdeaStatus.ADOPTED and idea.adopted_novel_id:
            existing = self._novel_service.get_novel(idea.adopted_novel_id)
            if existing is not None:
                return existing

        novel_id = f"novel-{uuid4().hex}"
        dto = self._novel_service.create_novel(
            novel_id=novel_id,
            title=idea.title,
            author=author,
            target_chapters=self._target_chapters_for(idea.length_tier),
            premise=self._compose_premise(idea),
            genre=idea.genre,
            world_preset=idea.world_preset,
            length_tier=idea.length_tier or None,
        )
        self._repository.update_status(
            idea.id,
            TopicIdeaStatus.ADOPTED,
            adopted_novel_id=getattr(dto, "id", novel_id),
        )
        return dto

    async def _generate_with_llm(
        self,
        request: TopicGenerateRequestDTO,
    ) -> list[dict[str, Any]]:
        prompt = Prompt(
            system=(
                "你是华语类型小说选题编辑。请输出严格 JSON，根字段为 topic_ideas。"
                "每个候选包含 title、genre、world_preset、length_tier、logline、premise、"
                "protagonist_hook、core_conflict、opening_hook、selling_points、"
                "long_term_potential、risk_notes、market_tags、score。"
            ),
            user=json.dumps(
                {
                    **request.to_source_brief(),
                    "brief_text": self._brief_text(request),
                },
                ensure_ascii=False,
            ),
        )
        config = GenerationConfig(
            max_tokens=4096,
            temperature=0.8,
            response_format={"type": "json_object"},
        )
        try:
            result = await self._llm.generate(prompt, config)
        except Exception as exc:
            raise TopicIdeaGenerationError("选题生成调用失败，请检查模型配置或稍后重试") from exc

        try:
            data = parse_json_from_response(result.content)
        except Exception as exc:
            logger.warning("topic idea JSON parse failed, using fallback: %s", exc)
            return []
        items = data.get("topic_ideas") if isinstance(data, dict) else None
        return items if isinstance(items, list) else []

    async def _enrich_with_llm(self, idea: TopicIdea, mode: str) -> Optional[dict[str, Any]]:
        action = "深化" if mode == "deepen" else "评估"
        prompt = Prompt(
            system=(
                f"你是华语类型小说选题编辑。请对给定选题做{action}，输出严格 JSON。"
                "允许字段：premise、protagonist_hook、core_conflict、opening_hook、"
                "selling_points、long_term_potential、risk_notes、market_tags、score、"
                "development_notes、evaluation。"
                "score 必须是 0-100 的整数。不要创建 Bible 或章节正文。"
            ),
            user=json.dumps(
                {
                    "mode": mode,
                    "topic_idea": TopicIdeaDTO.from_domain(idea).__dict__,
                },
                ensure_ascii=False,
            ),
        )
        config = GenerationConfig(
            max_tokens=3072,
            temperature=0.55 if mode == "evaluate" else 0.75,
            response_format={"type": "json_object"},
        )
        try:
            result = await self._llm.generate(prompt, config)
        except Exception as exc:
            raise TopicIdeaGenerationError(f"选题{action}调用失败，请检查模型配置或稍后重试") from exc

        try:
            data = parse_json_from_response(result.content)
        except Exception as exc:
            logger.warning("topic idea %s JSON parse failed, using fallback: %s", mode, exc)
            return None
        if not isinstance(data, dict):
            return None
        root_fields = ENRICHMENT_FIELDS.intersection(data)
        if root_fields - {"evaluation"} or (root_fields and len(data) > 1):
            return data
        for key in ("topic_idea", "evaluation", "result"):
            nested = data.get(key)
            if isinstance(nested, dict):
                if ENRICHMENT_FIELDS.intersection(nested):
                    return nested
                if key == "evaluation":
                    return {"evaluation": nested}
        return None

    def _build_ideas(
        self,
        raw_items: list[dict[str, Any]],
        request: TopicGenerateRequestDTO,
        count: int,
    ) -> list[TopicIdea]:
        ideas: list[TopicIdea] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            try:
                ideas.append(self._idea_from_payload(item, request))
            except ValueError:
                continue
            if len(ideas) >= count:
                return ideas

        for item in self._fallback_payloads(request):
            if len(ideas) >= count:
                break
            ideas.append(self._idea_from_payload(item, request))
        return ideas[:count]

    def _get_required(self, idea_id: str) -> TopicIdea:
        idea = self._repository.get_by_id(idea_id)
        if idea is None:
            raise ValueError(f"Topic idea not found: {idea_id}")
        return idea

    def _apply_enrichment(
        self,
        idea: TopicIdea,
        payload: dict[str, Any],
        fill_missing: bool,
    ) -> TopicIdea:
        for key in ENRICHMENT_FIELDS:
            if key not in payload:
                continue
            value = self._normalize_enrichment_value(key, payload[key])
            if fill_missing and getattr(idea, key):
                continue
            setattr(idea, key, value)
        idea.__post_init__()
        idea.updated_at = datetime.now(timezone.utc)
        return self._repository.update(idea)

    @staticmethod
    def _normalize_enrichment_value(key: str, value: Any) -> Any:
        if key in TEXT_ENRICHMENT_FIELDS:
            return TopicIdeaService._format_report_value(value)
        if key in LIST_ENRICHMENT_FIELDS:
            if isinstance(value, list):
                return [
                    text
                    for item in value
                    for text in [TopicIdeaService._format_report_value(item)]
                    if text
                ]
            text = TopicIdeaService._format_report_value(value)
            return [text] if text else []
        if key in DICT_ENRICHMENT_FIELDS:
            return value if isinstance(value, dict) else {}
        return value

    @staticmethod
    def _fallback_deepen_payload(idea: TopicIdea) -> dict[str, Any]:
        genre = idea.genre or "类型小说"
        base = idea.premise or idea.logline or f"《{idea.title}》围绕一次高压选择展开。"
        protagonist = idea.protagonist_hook or "主角带着一个被低估的能力或身份缺口入局。"
        conflict = idea.core_conflict or "主角的自我证明与既有秩序、利益集团持续碰撞。"
        opening = idea.opening_hook or "开篇用一次失败交易、公开误判或迫近危机把主角推到台前。"
        selling_points = TopicIdeaService._merge_unique(
            idea.selling_points,
            ["高压开局", "成长反馈明确", "冲突可连续升级"],
        )
        market_tags = TopicIdeaService._merge_unique(
            idea.market_tags,
            [genre, "强钩子", "可系列化"],
        )
        risks = TopicIdeaService._merge_unique(
            idea.risk_notes,
            ["需要尽早明确核心规则与代价，避免设定空转。"],
        )
        return {
            "premise": (
                f"{base} 立项可从主角被迫接下一个看似无解的局面切入，"
                f"通过连续选择展示能力边界、关系压力和世界规则。中段以资源争夺与身份反转扩大格局，"
                f"长期主线则落在主角能否把个人优势转化为改变秩序的筹码。"
            ),
            "protagonist_hook": protagonist,
            "core_conflict": conflict,
            "opening_hook": opening,
            "selling_points": selling_points,
            "long_term_potential": idea.long_term_potential
            or "适合从个人危机扩展到组织、规则和终局真相三层结构，具备连载延展空间。",
            "risk_notes": risks,
            "market_tags": market_tags,
            "score": max(idea.score, TopicIdeaService._fallback_score(idea) + 6),
            "development_notes": {
                "立项定位": f"{genre}方向，优先突出主角入局压力和连续升级反馈。",
                "首卷抓手": [
                    opening,
                    "用一次阶段性胜利确认主角能力边界。",
                    "在胜利后追加更高代价，推动进入长期主线。",
                ],
                "角色关系": "围绕主角的短期盟友、利益对手和隐藏规则知情者建立张力。",
                "连载策略": "每个阶段保留一个未兑现承诺，并用新规则或新债务推动追读。",
            },
        }

    @staticmethod
    def _fallback_evaluate_payload(idea: TopicIdea) -> dict[str, Any]:
        score = TopicIdeaService._fallback_score(idea)
        risks: list[str] = []
        if not idea.opening_hook:
            risks.append("开篇钩子不足，需要补一个能在第一章成立的强事件。")
        if not idea.core_conflict:
            risks.append("核心冲突还不够具体，容易变成泛泛升级。")
        if len(idea.selling_points) < 2:
            risks.append("卖点数量偏少，建议补足情绪爽点和长期追读点。")
        if not risks:
            risks.append("需控制信息密度，避免前期解释多于行动。")
        return {
            "score": score,
            "risk_notes": TopicIdeaService._merge_unique(idea.risk_notes, risks),
            "market_tags": TopicIdeaService._merge_unique(
                idea.market_tags,
                [idea.genre or "类型小说", "立项评估", "可打磨"],
            ),
            "selling_points": TopicIdeaService._merge_unique(
                idea.selling_points,
                ["核心钩子可视化", "追读目标清晰"],
            ),
            "long_term_potential": idea.long_term_potential
            or "可通过阶段目标、对手升级和规则揭示维持中长篇连载张力。",
            "evaluation": {
                "综合评分": score,
                "开篇钩子": "已具备" if idea.opening_hook else "需补强",
                "核心冲突": "已具备" if idea.core_conflict else "需具体化",
                "卖点密度": "充足" if len(idea.selling_points) >= 2 else "偏少",
                "主要风险": risks,
            },
        }

    def _ranking_for(self, idea: TopicIdea) -> TopicIdeaRankingDTO:
        completeness_bonus = TopicIdeaService._completeness_bonus(idea)
        market_fit = self._market_fit_score_from_evaluation(idea.evaluation)
        market_bonus = max(-3, min(8, round((market_fit - 50) / 10))) if market_fit is not None else 0
        score = max(0, min(100, int(idea.score) + completeness_bonus + market_bonus))
        strengths = []
        if idea.opening_hook:
            strengths.append("开篇钩子明确")
        if idea.selling_points:
            strengths.append("卖点可见")
        if idea.long_term_potential:
            strengths.append("长线空间较清楚")
        if idea.development_notes:
            strengths.append("立项案更完整")
        if idea.evaluation:
            strengths.append("评估维度已补齐")
        if market_fit is not None and market_fit >= 65:
            strengths.append("市场趋势贴合")
        reason = "、".join(strengths) if strengths else "基础信息仍需补齐"
        return TopicIdeaRankingDTO(
            topic_id=idea.id,
            title=idea.title,
            score=score,
            reason=reason,
            risks=list(idea.risk_notes),
        )

    @staticmethod
    def _fallback_score(idea: TopicIdea) -> int:
        score = int(idea.score or 0)
        score = max(score, 52)
        score += TopicIdeaService._completeness_bonus(idea)
        if len(idea.selling_points) >= 2:
            score += 6
        if idea.risk_notes:
            score -= min(10, len(idea.risk_notes) * 3)
        return max(0, min(100, score))

    @staticmethod
    def _completeness_bonus(idea: TopicIdea) -> int:
        fields = [
            idea.premise,
            idea.protagonist_hook,
            idea.core_conflict,
            idea.opening_hook,
            idea.long_term_potential,
        ]
        filled = sum(1 for value in fields if value)
        filled += min(len(idea.selling_points), 3)
        filled += min(len(idea.market_tags), 2)
        if idea.development_notes:
            filled += min(len(idea.development_notes), 3)
        if idea.evaluation:
            filled += min(len(idea.evaluation), 3)
        return min(24, filled * 3)

    @staticmethod
    def _merge_unique(existing: list[str], additions: list[str]) -> list[str]:
        result: list[str] = []
        for value in [*existing, *additions]:
            text = str(value or "").strip()
            if text and text not in result:
                result.append(text)
        return result

    @staticmethod
    def _increment_count(counts: dict[str, int], key: str) -> None:
        text = str(key or "").strip()
        if text:
            counts[text] = counts.get(text, 0) + 1

    @staticmethod
    def _increment_float(counts: dict[str, float], key: str, value: float) -> None:
        text = str(key or "").strip()
        if text:
            counts[text] = counts.get(text, 0.0) + float(value or 0.0)

    @staticmethod
    def _rounded_scores(values: dict[str, float]) -> dict[str, float]:
        return {
            key: round(value, 2)
            for key, value in values.items()
        }

    @staticmethod
    def _infer_market_signal_category(signal: TopicMarketSignalDTO) -> str:
        source = signal.source or ""
        content = " ".join(
            [
                source,
                signal.title or "",
                signal.genre or "",
                signal.summary or "",
                " ".join(signal.tags or []),
            ]
        )
        if "漫画" in content or any(word in source for word in ("快看", "动漫")):
            return "comic"
        if signal.title or signal.genre or signal.summary:
            return "novel"
        return "unknown"

    @staticmethod
    def _idea_from_payload(
        item: dict[str, Any],
        request: TopicGenerateRequestDTO,
    ) -> TopicIdea:
        return TopicIdea(
            title=str(item.get("title") or "未命名选题"),
            genre=str(item.get("genre") or request.genre or ""),
            world_preset=str(item.get("world_preset") or request.world_preset or ""),
            length_tier=str(item.get("length_tier") or request.length_tier or ""),
            logline=str(item.get("logline") or ""),
            premise=str(item.get("premise") or ""),
            protagonist_hook=str(item.get("protagonist_hook") or ""),
            core_conflict=str(item.get("core_conflict") or ""),
            opening_hook=str(item.get("opening_hook") or ""),
            selling_points=item.get("selling_points") or [],
            long_term_potential=str(item.get("long_term_potential") or ""),
            risk_notes=item.get("risk_notes") or [],
            market_tags=item.get("market_tags") or [],
            score=item.get("score") or 0,
            source_brief=request.to_source_brief(),
            development_notes=item.get("development_notes") or {},
            evaluation=item.get("evaluation") or {},
        )

    @staticmethod
    def _fallback_payloads(request: TopicGenerateRequestDTO) -> list[dict[str, Any]]:
        genre = request.genre or "类型小说"
        world = request.world_preset or "可扩展世界观"
        brief = TopicIdeaService._brief_text(request) or "一个具备商业潜力的新故事"
        return [
            {
                "title": "逆风开局的隐藏王牌",
                "genre": genre,
                "world_preset": world,
                "length_tier": request.length_tier,
                "logline": f"主角因{brief}被推入危局，只能用被低估的能力撬动更大的秩序。",
                "premise": f"围绕「{brief}」展开，从一次失败任务切入，逐步揭开资源、身份与规则的真相。",
                "protagonist_hook": "主角拥有一个看似鸡肋、实则能改变局面的优势。",
                "core_conflict": "个体求生与既有秩序之间的持续对抗。",
                "opening_hook": "第一章以误判、追捕或交易崩盘开场。",
                "selling_points": ["强危机开局", "成长反馈明确", "可连续升级"],
                "long_term_potential": "可扩展为势力、规则与终局真相三条长期线。",
                "risk_notes": ["需要避免金手指过早失控。"],
                "market_tags": [genre, "逆袭", "悬念"],
                "score": 72,
            },
            {
                "title": "规则裂缝中的调查者",
                "genre": genre,
                "world_preset": world,
                "length_tier": request.length_tier,
                "logline": f"主角追查{brief}背后的异常，发现世界运行规则被人为改写。",
                "premise": "以调查推进爽点，每个真相都带来新的利益交换和更高层级敌人。",
                "protagonist_hook": "主角能从普通证据里看见别人忽略的因果断点。",
                "core_conflict": "追求真相的人与维护黑箱的人之间的博弈。",
                "opening_hook": "一份本不该存在的记录出现在主角手里。",
                "selling_points": ["谜团推进", "反转空间", "角色智性爽点"],
                "long_term_potential": "适合做单元案件到主线阴谋的递进结构。",
                "risk_notes": ["需要控制信息密度，避免前期解释过多。"],
                "market_tags": [genre, "调查", "阴谋"],
                "score": 70,
            },
            {
                "title": "被选中的失败样本",
                "genre": genre,
                "world_preset": world,
                "length_tier": request.length_tier,
                "logline": f"所有人都认为主角是{brief}中的失败者，只有他知道失败本身藏着新路线。",
                "premise": "主角从低评价标签出发，把缺陷转化为独特路线，持续打破评价体系。",
                "protagonist_hook": "主角的失败记录反而是理解底层规则的钥匙。",
                "core_conflict": "标签化评价与自我证明之间的冲突。",
                "opening_hook": "主角在公开淘汰现场发现评判标准被操纵。",
                "selling_points": ["废柴逆袭", "体系突破", "情绪代偿"],
                "long_term_potential": "可持续展开学院、组织、赛场或门派阶梯。",
                "risk_notes": ["需要让配角反应真实，避免单纯降智衬托。"],
                "market_tags": [genre, "废柴流", "升级"],
                "score": 68,
            },
            {
                "title": "长夜档案管理员",
                "genre": genre,
                "world_preset": world,
                "length_tier": request.length_tier,
                "logline": f"主角整理{brief}相关旧档案时，发现每份记录都在预告一场尚未发生的灾难。",
                "premise": "主角原本只负责整理边缘档案，却发现旧记录会提前写出现实中的异常事件。为了避免灾难，也为了查清档案来源，主角被迫在记录、现实和幕后势力之间穿梭，逐渐意识到自己也是某份档案里的角色。",
                "protagonist_hook": "主角能读出档案中被抹去的空白注脚。",
                "core_conflict": "试图改写结局的记录者与制造既定命运的幕后系统对抗。",
                "opening_hook": "主角在一份十年前的档案里，看见了明天自己的死亡时间。",
                "selling_points": ["预告式悬念", "命运反抗", "单元事件推进"],
                "long_term_potential": "可由单份档案扩展到城市、时代和世界底层记录系统。",
                "risk_notes": ["预言机制要有明确代价，避免万能预知。"],
                "market_tags": [genre, "档案", "命运"],
                "score": 74,
            },
            {
                "title": "临界点上的继承人",
                "genre": genre,
                "world_preset": world,
                "length_tier": request.length_tier,
                "logline": f"主角继承了与{brief}有关的危险遗产，也继承了所有追债者和仇人。",
                "premise": "主角在最不合适的时候继承一份无人敢接的遗产：它既是资源入口，也是灾祸源头。围绕遗产的争夺让主角迅速卷入多方势力，而遗产本身隐藏的使用规则，决定了主角能否把负债变成筹码。",
                "protagonist_hook": "主角不是天选之人，只是唯一愿意接手烂摊子的人。",
                "core_conflict": "继承危险遗产的新人 vs 想瓜分遗产的旧势力。",
                "opening_hook": "遗产交接当天，所有债主比亲友更早抵达灵堂。",
                "selling_points": ["遗产争夺", "负债开局", "势力博弈"],
                "long_term_potential": "遗产可逐层解锁，每层引出新的债务、盟友和敌人。",
                "risk_notes": ["遗产能力需要分阶段开放，避免开局资源过满。"],
                "market_tags": [genre, "继承", "势力"],
                "score": 76,
            },
        ]

    @staticmethod
    def _compose_premise(idea: TopicIdea) -> str:
        parts = [
            idea.logline,
            idea.premise,
            f"主角钩子：{idea.protagonist_hook}" if idea.protagonist_hook else "",
            f"核心冲突：{idea.core_conflict}" if idea.core_conflict else "",
            f"开篇钩子：{idea.opening_hook}" if idea.opening_hook else "",
        ]
        development_notes = TopicIdeaService._format_report_block(
            "立项案",
            idea.development_notes,
        )
        evaluation = TopicIdeaService._format_report_block(
            "立项评估",
            idea.evaluation,
        )
        if development_notes:
            parts.append(development_notes)
        if evaluation:
            parts.append(evaluation)
        return "\n\n".join(part for part in parts if part)

    @staticmethod
    def _format_report_block(title: str, data: dict[str, Any]) -> str:
        if not isinstance(data, dict) or not data:
            return ""
        lines = []
        for key, value in data.items():
            text = TopicIdeaService._format_report_value(value)
            if text:
                lines.append(f"- {key}：{text}")
        if not lines:
            return ""
        return f"{title}：\n" + "\n".join(lines)

    @staticmethod
    def _format_report_value(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (int, float, bool)):
            return str(value)
        if isinstance(value, list):
            return "；".join(
                item
                for item in (
                    TopicIdeaService._format_report_value(item)
                    for item in value
                )
                if item
            )
        if isinstance(value, dict):
            return "；".join(
                f"{key}={text}"
                for key, item in value.items()
                for text in [TopicIdeaService._format_report_value(item)]
                if text
            )
        return str(value).strip()

    @staticmethod
    def _brief_text(request: TopicGenerateRequestDTO) -> str:
        parts = []
        if request.brief.strip():
            parts.append(request.brief.strip())
        if request.keywords:
            parts.append("关键词：" + "、".join(request.keywords))
        if request.desired_selling_points:
            parts.append("目标爽点：" + "、".join(request.desired_selling_points))
        if request.avoid_patterns:
            parts.append("避雷套路：" + "、".join(request.avoid_patterns))
        signal_texts = []
        for signal in request.market_signals or []:
            if not isinstance(signal, dict):
                continue
            fields = []
            title = str(signal.get("title") or "").strip()
            genre = str(signal.get("genre") or "").strip()
            summary = str(signal.get("summary") or "").strip()
            tags = signal.get("tags") or []
            if title:
                fields.append(title)
            if genre:
                fields.append(f"类型={genre}")
            if isinstance(tags, list) and tags:
                fields.append("标签=" + "、".join(str(tag).strip() for tag in tags if str(tag).strip()))
            if summary:
                fields.append(summary)
            if fields:
                signal_texts.append("；".join(fields))
        if signal_texts:
            parts.append("市场观察：" + " | ".join(signal_texts[:8]))
        return "；".join(parts)

    @staticmethod
    def _target_chapters_for(length_tier: str) -> int:
        return {
            "short": 30,
            "standard": 100,
            "epic": 200,
        }.get((length_tier or "").strip(), 100)

    @staticmethod
    def _market_signal_from_line(line: str, source: str) -> TopicMarketSignalDTO:
        text = line.strip()
        parts = [part.strip() for part in text.split("|")]
        title = parts[0] if len(parts) >= 4 else ""
        genre = parts[1] if len(parts) >= 4 else ""
        tags = TopicIdeaService._split_tags(parts[2]) if len(parts) >= 4 else []
        summary = parts[3] if len(parts) >= 4 else text
        return TopicMarketSignalDTO(
            id=f"signal-{uuid4().hex}",
            source=(source or "手动观察").strip() or "手动观察",
            title=title,
            genre=genre,
            tags=tags,
            summary=summary,
            raw_text=text,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _split_tags(value: str) -> list[str]:
        tags: list[str] = []
        for raw in (value or "").replace("，", ",").replace("、", ",").split(","):
            tag = raw.strip()
            if tag and tag not in tags:
                tags.append(tag)
        return tags

    @staticmethod
    def _fetch_url_text(url: str, headers: dict[str, str] | None = None) -> str:
        request_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
            )
        }
        request_headers.update(headers or {})
        request = Request(
            url,
            headers=request_headers,
        )
        try:
            with urlopen(request, timeout=10) as response:
                return TopicIdeaService._decode_response_body(
                    response.read(),
                    response.headers.get_content_charset(),
                )
        except HTTPError as exc:
            body = exc.read()
            if body:
                return TopicIdeaService._decode_response_body(
                    body,
                    exc.headers.get_content_charset() if exc.headers else None,
                )
            raise


    @staticmethod
    def _decode_response_body(body: bytes, charset: str | None) -> str:
        candidates = [charset] if charset else []
        candidates.extend(["utf-8", "gb18030"])
        best_text = ""
        best_errors = 10**9
        for candidate in candidates:
            if not candidate:
                continue
            text = body.decode(candidate, errors="replace")
            errors = text.count("\ufffd")
            if errors < best_errors:
                best_text = text
                best_errors = errors
            if errors == 0:
                break
        return best_text


    def _merge_market_evaluation(self, idea: TopicIdea, payload: dict[str, Any]) -> dict[str, Any]:
        evaluation = payload.get("evaluation")
        base_evaluation = dict(evaluation) if isinstance(evaluation, dict) else {}
        market_fit = self._build_market_fit_snapshot(idea, payload)
        if market_fit:
            base_evaluation.update(market_fit)
            payload["evaluation"] = base_evaluation
            market_score = self._market_fit_score_from_evaluation(base_evaluation)
            if market_score is not None:
                payload["score"] = max(
                    int(payload.get("score") or idea.score or 0),
                    max(0, min(100, int(round((payload.get("score") or idea.score or 0) * 0.7 + market_score * 0.3)))),
                )
        return payload

    def _build_market_fit_snapshot(
        self,
        idea: TopicIdea,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        settings = self.get_market_signal_settings()
        signals = self._recent_market_signals(limit=200, lookback_days=settings.lookback_days)
        if not signals:
            return {}
        genre = str(payload.get("genre") or idea.genre or "").strip()
        market_tags = self._merge_unique(
            list(idea.market_tags),
            [str(item).strip() for item in payload.get("market_tags") or []],
        )
        selling_points = self._merge_unique(
            list(idea.selling_points),
            [str(item).strip() for item in payload.get("selling_points") or []],
        )
        tokens = self._market_fit_tokens(genre, market_tags, selling_points, idea.title, idea.logline, idea.premise)
        if not tokens and not genre:
            return {}
        matched_sources: dict[str, float] = {}
        matched_tags: list[str] = []
        comic_opportunities: list[str] = []
        total_weight = 0.0
        for signal in signals:
            signal_text = " ".join(
                [signal.title, signal.genre, signal.summary, " ".join(signal.tags or [])]
            )
            token_matches = [token for token in tokens if token and token in signal_text]
            genre_match = bool(genre and genre in signal_text)
            if not token_matches and not genre_match:
                continue
            weight = self._source_weight_for_signal(signal, settings)
            total_weight += weight + min(len(token_matches) * 0.25, 1.0)
            matched_sources[signal.source] = matched_sources.get(signal.source, 0.0) + weight
            for tag in signal.tags:
                if tag in tokens and tag not in matched_tags:
                    matched_tags.append(tag)
            if self._infer_market_signal_category(signal) == "comic":
                comic_opportunities.extend(
                    self._comic_opportunities_for_signal(signal, genre or idea.genre or "当前题材")
                )
        if total_weight <= 0:
            return {}
        fit_score = max(35, min(95, int(round(48 + total_weight * 12 + len(matched_tags) * 2))))
        fit_level = "高" if fit_score >= 78 else "中高" if fit_score >= 65 else "中"
        return {
            "市场匹配度": {
                "score": fit_score,
                "level": fit_level,
                "window_days": settings.lookback_days,
                "matched_tags": matched_tags[:6],
                "matched_sources": self._top_weighted_sources(matched_sources),
            },
            "平台权重摘要": self._top_weighted_sources(matched_sources),
            "趋势窗口": f"近 {settings.lookback_days} 天",
            "漫画转题机会": comic_opportunities[:3],
        }

    def _recent_market_signals(self, limit: int, lookback_days: int) -> list[TopicMarketSignalDTO]:
        signals = self._repository.list_market_signals(max(1, min(int(limit or 100), 500)))
        if lookback_days <= 0:
            return signals
        cutoff = datetime.now(timezone.utc).timestamp() - lookback_days * 86400
        result = []
        for signal in signals:
            dt = self._parse_signal_datetime(signal.created_at)
            if dt and dt.timestamp() >= cutoff:
                result.append(signal)
        return result or signals

    def _record_market_signal_source_health(
        self,
        source: TopicMarketSignalSourceDTO,
        signals: list[TopicMarketSignalDTO],
    ) -> None:
        saver = getattr(self._repository, "save_market_signal_source_health", None)
        if not callable(saver):
            return
        now = datetime.now(timezone.utc).isoformat()
        count = len(signals)
        saver(
            TopicMarketSignalSourceHealthDTO(
                source_key=source.key,
                source_name=source.name,
                status="success" if count > 0 else "error",
                last_run_at=now,
                last_success_at=now if count > 0 else "",
                last_count=count,
                last_error="" if count > 0 else "No signals collected",
            )
        )

    def _source_health_for(
        self,
        source: TopicMarketSignalSourceDTO,
        saved: TopicMarketSignalSourceHealthDTO | None,
        settings: TopicMarketSignalAutomationSettingsDTO,
    ) -> TopicMarketSignalSourceHealthDTO:
        health = saved or TopicMarketSignalSourceHealthDTO(
            source_key=source.key,
            source_name=source.name,
        )
        return TopicMarketSignalSourceHealthDTO(
            source_key=source.key,
            source_name=source.name,
            status=str(health.status or "unknown"),
            last_run_at=str(health.last_run_at or ""),
            last_success_at=str(health.last_success_at or ""),
            last_count=max(0, int(health.last_count or 0)),
            last_error=str(health.last_error or ""),
            next_run_at=self._next_run_at_for_source(source.key, settings),
        )

    @staticmethod
    def _next_run_at_for_source(
        source_key: str,
        settings: TopicMarketSignalAutomationSettingsDTO,
    ) -> str:
        if not settings.enabled or source_key not in settings.selected_source_keys:
            return ""
        last_run_at = str(settings.last_run_at or "").strip()
        if not last_run_at:
            return ""
        try:
            last_dt = datetime.fromisoformat(last_run_at)
        except ValueError:
            return ""
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        next_dt = last_dt.astimezone(timezone.utc) + timedelta(
            minutes=max(15, int(settings.interval_minutes or 180))
        )
        return next_dt.isoformat()

    def _normalize_market_signal_settings(
        self,
        settings: TopicMarketSignalAutomationSettingsDTO,
    ) -> TopicMarketSignalAutomationSettingsDTO:
        selected_source_keys = [
            key for key in settings.selected_source_keys
            if key in MARKET_SIGNAL_SOURCES
        ] or list(MARKET_SIGNAL_SOURCES.keys())
        source_weights = dict(DEFAULT_MARKET_SIGNAL_SOURCE_WEIGHTS)
        for key, value in (settings.source_weights or {}).items():
            if key in MARKET_SIGNAL_SOURCES:
                try:
                    source_weights[key] = max(0.1, min(float(value), 3.0))
                except (TypeError, ValueError):
                    continue
        return TopicMarketSignalAutomationSettingsDTO(
            enabled=bool(settings.enabled),
            interval_minutes=max(15, min(int(settings.interval_minutes or 180), 24 * 60)),
            limit_per_source=max(1, min(int(settings.limit_per_source or 8), 30)),
            lookback_days=max(1, min(int(settings.lookback_days or 30), 90)),
            source_weights=source_weights,
            selected_source_keys=selected_source_keys,
            last_run_at=str(settings.last_run_at or ""),
            last_status=str(settings.last_status or "idle"),
            last_error=str(settings.last_error or ""),
            updated_at=str(settings.updated_at or ""),
        )

    @staticmethod
    def _normalize_credential_headers(values: dict[str, Any]) -> dict[str, str]:
        result: dict[str, str] = {}
        for key, value in (values or {}).items():
            name = str(key or "").strip()
            text = str(value or "").strip()
            if name and text:
                result[name] = text
        return result

    @staticmethod
    def _credential_status_for(
        credentials: TopicMarketSignalSourceCredentialDTO,
    ) -> TopicMarketSignalSourceCredentialStatusDTO:
        headers = TopicIdeaService._normalize_credential_headers(credentials.headers)
        return TopicMarketSignalSourceCredentialStatusDTO(
            source_key=credentials.source_key,
            api_key_configured=bool(str(credentials.api_key or "").strip()),
            cookie_configured=bool(str(credentials.cookie or "").strip()),
            endpoint_configured=bool(str(credentials.endpoint_url or "").strip()),
            header_keys=sorted(headers.keys()),
            updated_at=str(credentials.updated_at or ""),
        )

    @staticmethod
    def _source_with_credentials(
        source: TopicMarketSignalSourceDTO,
        credentials: TopicMarketSignalSourceCredentialDTO | None,
    ) -> TopicMarketSignalSourceDTO:
        endpoint_url = str(credentials.endpoint_url or "").strip() if credentials else ""
        if not endpoint_url:
            return source
        return TopicMarketSignalSourceDTO(
            key=source.key,
            name=source.name,
            url=endpoint_url,
            category=source.category,
            source_type="api",
            requires_auth=source.requires_auth,
        )

    @staticmethod
    def _signal_date(signal: TopicMarketSignalDTO) -> str:
        dt = TopicIdeaService._parse_signal_datetime(signal.created_at)
        return dt.date().isoformat() if dt else ""

    @staticmethod
    def _parse_signal_datetime(value: str) -> Optional[datetime]:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def _source_key_for_signal_name(name: str) -> str:
        for key, source in MARKET_SIGNAL_SOURCES.items():
            if source.name == name:
                return key
        return str(name or "").strip()

    def _source_weight_for_signal(
        self,
        signal: TopicMarketSignalDTO,
        settings: TopicMarketSignalAutomationSettingsDTO,
    ) -> float:
        source_key = self._source_key_for_signal_name(signal.source)
        return float(settings.source_weights.get(source_key, DEFAULT_MARKET_SIGNAL_SOURCE_WEIGHTS.get(source_key, 0.8)))

    @staticmethod
    def _market_fit_tokens(
        genre: str,
        market_tags: list[str],
        selling_points: list[str],
        *texts: str,
    ) -> list[str]:
        tokens: list[str] = []
        for value in [genre, *market_tags, *selling_points]:
            text = str(value or "").strip()
            if len(text) >= 2 and text not in tokens:
                tokens.append(text)
        for text in texts:
            for token in re.findall(r"[\u4e00-\u9fffA-Za-z]{2,8}", str(text or "")):
                if len(token) >= 2 and token not in tokens:
                    tokens.append(token)
                if len(tokens) >= 12:
                    return tokens
        return tokens

    @staticmethod
    def _comic_opportunities_for_signal(signal: TopicMarketSignalDTO, target_genre: str) -> list[str]:
        opportunities: list[str] = []
        signal_text = " ".join(
            [signal.title or "", signal.genre or "", signal.summary or "", " ".join(signal.tags or [])]
        )
        for keywords, opportunity in (
            (
                ("总裁", "豪门", "霸总", "职场"),
                f"可转译为{target_genre}里的总裁职场线：用权力差、职业目标和情感误判制造连续拉扯。",
            ),
            (
                ("错撩", "误会", "替身", "白月光"),
                f"可转译为{target_genre}里的错撩误会钩子：让第一章关系误判直接触发利益冲突。",
            ),
            (
                ("重生", "穿越", "改命", "逆袭"),
                f"可转译为{target_genre}里的重生改命线：把视觉爽点换成选择代价和阶段性翻盘。",
            ),
            (
                ("契约", "婚约", "先婚", "联姻"),
                f"可转译为{target_genre}里的契约关系线：用外部绑定制造同盟、试探和背叛成本。",
            ),
            (
                ("萌宝", "团宠", "幼崽", "公主"),
                f"可转译为{target_genre}里的亲缘守护线：用萌点入口承载身份秘密和阵营选择。",
            ),
        ):
            if any(keyword in signal_text for keyword in keywords):
                opportunities.append(opportunity)
        for tag in signal.tags or []:
            text = str(tag or "").strip()
            if text and text not in {"漫画", "人气榜", "新作榜", "飙升榜", "畅销榜", "韩漫榜", "日漫榜", "恋爱榜", "剧情榜", "投稿榜", "完结榜", "免费榜", "等免榜", "月票榜", "漫画榜"}:
                opportunities.append(f"可把漫画热词“{text}”转译成{target_genre}里的强关系或高代价主线。")
        if signal.title:
            opportunities.append(f"参考《{signal.title}》的视觉冲突感，改写成{target_genre}里的开篇爆点。")
        return TopicIdeaService._merge_unique([], opportunities)

    @staticmethod
    def _top_weighted_sources(values: dict[str, float]) -> list[str]:
        return [
            f"{key}({round(value, 2)})"
            for key, value in sorted(values.items(), key=lambda item: item[1], reverse=True)[:3]
        ]

    @staticmethod
    def _market_fit_score_from_evaluation(evaluation: dict[str, Any]) -> Optional[int]:
        market_fit = evaluation.get("市场匹配度") if isinstance(evaluation, dict) else None
        if not isinstance(market_fit, dict):
            return None
        score = market_fit.get("score")
        try:
            return max(0, min(100, int(score)))
        except (TypeError, ValueError):
            return None
