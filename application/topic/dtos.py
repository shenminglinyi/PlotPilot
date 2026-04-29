"""选题立项 DTO。"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from domain.topic.entities import TopicIdea


@dataclass
class TopicGenerateRequestDTO:
    """选题生成请求。"""

    brief: str = ""
    genre: str = ""
    world_preset: str = ""
    length_tier: str = ""
    keywords: list[str] = field(default_factory=list)
    desired_selling_points: list[str] = field(default_factory=list)
    avoid_patterns: list[str] = field(default_factory=list)
    market_signals: list[dict[str, Any]] = field(default_factory=list)
    count: int = 3

    def normalized_count(self) -> int:
        return max(3, min(int(self.count or 3), 5))

    def to_source_brief(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TopicIdeaDTO:
    """选题候选 DTO。"""

    id: str
    title: str
    status: str
    genre: str = ""
    world_preset: str = ""
    length_tier: str = ""
    logline: str = ""
    premise: str = ""
    protagonist_hook: str = ""
    core_conflict: str = ""
    opening_hook: str = ""
    selling_points: list[str] = field(default_factory=list)
    long_term_potential: str = ""
    risk_notes: list[str] = field(default_factory=list)
    market_tags: list[str] = field(default_factory=list)
    score: int = 0
    adopted_novel_id: Optional[str] = None
    source_brief: dict[str, Any] = field(default_factory=dict)
    development_notes: dict[str, Any] = field(default_factory=dict)
    evaluation: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_domain(cls, idea: TopicIdea) -> "TopicIdeaDTO":
        return cls(
            id=idea.id,
            title=idea.title,
            status=idea.status.value if hasattr(idea.status, "value") else str(idea.status),
            genre=idea.genre,
            world_preset=idea.world_preset,
            length_tier=idea.length_tier,
            logline=idea.logline,
            premise=idea.premise,
            protagonist_hook=idea.protagonist_hook,
            core_conflict=idea.core_conflict,
            opening_hook=idea.opening_hook,
            selling_points=list(idea.selling_points),
            long_term_potential=idea.long_term_potential,
            risk_notes=list(idea.risk_notes),
            market_tags=list(idea.market_tags),
            score=idea.score,
            adopted_novel_id=idea.adopted_novel_id,
            source_brief=idea.source_brief,
            development_notes=idea.development_notes,
            evaluation=idea.evaluation,
            created_at=idea.created_at.isoformat() if hasattr(idea.created_at, "isoformat") else str(idea.created_at or ""),
            updated_at=idea.updated_at.isoformat() if hasattr(idea.updated_at, "isoformat") else str(idea.updated_at or ""),
        )


@dataclass
class CompareTopicIdeasRequestDTO:
    """选题对比请求。"""

    topic_ids: list[str] = field(default_factory=list)


@dataclass
class TopicIdeaRankingDTO:
    """选题对比排序项。"""

    topic_id: str
    title: str
    score: int
    reason: str
    risks: list[str] = field(default_factory=list)


@dataclass
class TopicIdeaCompareResultDTO:
    """选题对比结果。"""

    recommended_topic_id: str
    summary: str
    rankings: list[TopicIdeaRankingDTO] = field(default_factory=list)


@dataclass
class TopicMarketSignalImportRequestDTO:
    """市场观察导入请求。"""

    raw_text: str = ""
    source: str = "手动观察"


@dataclass
class TopicMarketSignalCollectRequestDTO:
    """公开来源采集请求。"""

    source_keys: list[str] = field(default_factory=list)
    limit_per_source: int = 10


@dataclass
class TopicMarketSignalSourceConnectionDTO:
    """市场信号来源连接诊断 DTO。"""

    source_key: str
    source_name: str
    ok: bool = False
    count: int = 0
    message: str = ""
    sample_titles: list[str] = field(default_factory=list)


@dataclass
class TopicMarketSignalSourceHealthDTO:
    """市场信号来源采集健康状态 DTO。"""

    source_key: str
    source_name: str
    status: str = "unknown"
    last_run_at: str = ""
    last_success_at: str = ""
    last_count: int = 0
    last_error: str = ""
    next_run_at: str = ""


@dataclass
class TopicMarketSignalSourceDTO:
    """市场信号来源配置 DTO。"""

    key: str
    name: str
    url: str
    category: str = "novel"
    source_type: str = "public_page"
    requires_auth: bool = False
    rank_urls: dict[str, str] = field(default_factory=dict)


@dataclass
class TopicMarketSignalDTO:
    """选题市场信号 DTO。"""

    id: str
    source: str
    title: str = ""
    genre: str = ""
    tags: list[str] = field(default_factory=list)
    summary: str = ""
    raw_text: str = ""
    created_at: str = ""


@dataclass
class TopicMarketSignalSummaryDTO:
    """选题市场信号摘要 DTO。"""

    total: int = 0
    source_counts: dict[str, int] = field(default_factory=dict)
    genre_counts: dict[str, int] = field(default_factory=dict)
    tag_counts: dict[str, int] = field(default_factory=dict)
    category_counts: dict[str, int] = field(default_factory=dict)
    window_days: int = 30
    weighted_source_scores: dict[str, float] = field(default_factory=dict)
    weighted_genre_scores: dict[str, float] = field(default_factory=dict)
    weighted_tag_scores: dict[str, float] = field(default_factory=dict)
    comic_opportunities: list[str] = field(default_factory=list)
    daily_counts: list[dict[str, Any]] = field(default_factory=list)
    recent_samples: list[TopicMarketSignalDTO] = field(default_factory=list)


@dataclass
class TopicMarketSignalAutomationSettingsDTO:
    """市场信号自动采集设置 DTO。"""

    enabled: bool = False
    interval_minutes: int = 180
    limit_per_source: int = 8
    lookback_days: int = 30
    source_weights: dict[str, float] = field(default_factory=dict)
    selected_source_keys: list[str] = field(default_factory=list)
    last_run_at: str = ""
    last_status: str = "idle"
    last_error: str = ""
    updated_at: str = ""


@dataclass
class TopicMarketSignalSourceCredentialDTO:
    """市场信号来源凭据 DTO，仅在服务端内部保存明文。"""

    source_key: str
    api_key: str = ""
    cookie: str = ""
    endpoint_url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    updated_at: str = ""


@dataclass
class TopicMarketSignalSourceCredentialStatusDTO:
    """市场信号来源凭据脱敏状态 DTO。"""

    source_key: str
    api_key_configured: bool = False
    cookie_configured: bool = False
    endpoint_configured: bool = False
    header_keys: list[str] = field(default_factory=list)
    updated_at: str = ""
