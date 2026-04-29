"""选题立项池 API 测试。"""
import importlib
import sys
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from application.core.dtos.novel_dto import NovelDTO


class FakeTopicGenerateRequestDTO(BaseModel):
    seed: str = ""


class FakeTopicIdeaDTO(BaseModel):
    id: str
    title: str
    status: str


class FakeTopicMarketSignalImportRequestDTO(BaseModel):
    raw_text: str = ""
    source: str = "手动观察"


class FakeTopicMarketSignalCollectRequestDTO(BaseModel):
    source_keys: list[str] = []
    limit_per_source: int = 10


class FakeTopicMarketSignalSourceDTO(BaseModel):
    key: str
    name: str
    url: str
    category: str = "novel"
    source_type: str = "public_page"
    requires_auth: bool = False


class FakeTopicMarketSignalSourceConnectionDTO(BaseModel):
    source_key: str
    source_name: str
    ok: bool = False
    count: int = 0
    message: str = ""
    sample_titles: list[str] = []


class FakeTopicMarketSignalSourceHealthDTO(BaseModel):
    source_key: str
    source_name: str
    status: str = "unknown"
    last_run_at: str = ""
    last_success_at: str = ""
    last_count: int = 0
    last_error: str = ""
    next_run_at: str = ""


class FakeTopicMarketSignalDTO(BaseModel):
    id: str
    source: str
    title: str = ""
    genre: str = ""
    tags: list[str] = []
    summary: str = ""
    raw_text: str = ""
    created_at: str = ""


class FakeTopicMarketSignalSummaryDTO(BaseModel):
    total: int
    source_counts: dict[str, int]
    genre_counts: dict[str, int]
    tag_counts: dict[str, int]
    category_counts: dict[str, int]
    window_days: int = 30
    weighted_source_scores: dict[str, float] = {}
    weighted_genre_scores: dict[str, float] = {}
    weighted_tag_scores: dict[str, float] = {}
    daily_counts: list[dict[str, int | str]] = []
    recent_samples: list[FakeTopicMarketSignalDTO]


class FakeTopicMarketSignalAutomationSettingsDTO(BaseModel):
    enabled: bool = False
    interval_minutes: int = 180
    limit_per_source: int = 8
    lookback_days: int = 30
    source_weights: dict[str, float] = {"qidian_rank": 1.0}
    selected_source_keys: list[str] = ["qidian_rank"]
    last_run_at: str = ""
    last_status: str = "idle"
    last_error: str = ""
    updated_at: str = ""


class FakeTopicMarketSignalSourceCredentialStatusDTO(BaseModel):
    source_key: str
    api_key_configured: bool = False
    cookie_configured: bool = False
    header_keys: list[str] = []
    updated_at: str = ""


class FakeCompareTopicIdeasRequestDTO(BaseModel):
    topic_ids: list[str]


class FakeTopicIdeaRankingDTO(BaseModel):
    topic_id: str
    title: str
    score: int
    reason: str
    risks: list[str]


class FakeTopicIdeaCompareResultDTO(BaseModel):
    recommended_topic_id: str
    summary: str
    rankings: list[FakeTopicIdeaRankingDTO]


class FakeTopicIdeaService:
    def __init__(self):
        self.generated_request = None
        self.list_status = None
        self.updated = None
        self.adopted = None
        self.deepened = None
        self.evaluated = None
        self.compared = None
        self.imported = None
        self.collected = None
        self.credential_update = None

    def generate(self, request):
        self.generated_request = request
        return [
            FakeTopicIdeaDTO(id="topic-1", title="云海剑宗", status="draft"),
        ]

    def list(self, status=None):
        self.list_status = status
        return [
            FakeTopicIdeaDTO(id="topic-2", title="赛博长安", status=status or "draft"),
        ]

    def get(self, topic_id):
        if topic_id == "missing":
            raise ValueError("topic not found")
        return FakeTopicIdeaDTO(id=topic_id, title="拾荒星舰", status="draft")

    def update_status(self, topic_id, status):
        self.updated = (topic_id, status)
        return FakeTopicIdeaDTO(id=topic_id, title="拾荒星舰", status=status)

    def update(self, topic_id, changes):
        self.updated = (topic_id, changes)
        if changes.get("status") == "bad":
            raise ValueError("Invalid topic idea status: bad")
        return FakeTopicIdeaDTO(
            id=topic_id,
            title=changes.get("title", "拾荒星舰"),
            status=changes.get("status", "draft"),
        )

    def adopt(self, topic_id):
        self.adopted = topic_id
        return NovelDTO(
            id="novel-1",
            title=f"采纳 {topic_id}",
            author="",
            target_chapters=30,
            stage="planning",
            premise="",
            chapters=[],
            total_word_count=0,
        )

    def deepen(self, topic_id):
        self.deepened = topic_id
        return FakeTopicIdeaDTO(id=topic_id, title="深化选题", status="draft")

    def evaluate(self, topic_id):
        self.evaluated = topic_id
        return FakeTopicIdeaDTO(id=topic_id, title="评估选题", status="draft")

    def compare(self, topic_ids):
        self.compared = topic_ids
        if "missing" in topic_ids:
            raise ValueError("topic not found")
        return FakeTopicIdeaCompareResultDTO(
            recommended_topic_id=topic_ids[0],
            summary="推荐第一条",
            rankings=[
                FakeTopicIdeaRankingDTO(
                    topic_id=topic_ids[0],
                    title="选题 A",
                    score=82,
                    reason="字段完整且评分较高",
                    risks=["风险 A"],
                ),
                FakeTopicIdeaRankingDTO(
                    topic_id=topic_ids[1],
                    title="选题 B",
                    score=70,
                    reason="潜力一般",
                    risks=[],
                ),
            ],
        )

    def import_market_signals(self, request):
        self.imported = request
        return [
            FakeTopicMarketSignalDTO(
                id="signal-1",
                source=request.source,
                title="债务修仙",
                genre="玄幻",
                tags=["负债"],
                summary="债务驱动升级",
                raw_text=request.raw_text,
                created_at="2026-04-29T10:00:00+00:00",
            )
        ]

    def list_market_signals(self, limit=20):
        return [
            FakeTopicMarketSignalDTO(
                id="signal-2",
                source="手动观察",
                summary="榜单热词：御兽学院",
                raw_text="榜单热词：御兽学院",
                created_at="2026-04-29T11:00:00+00:00",
            )
        ][:limit]

    def summarize_market_signals(self, limit=100):
        return FakeTopicMarketSignalSummaryDTO(
            total=1,
            source_counts={"手动观察": 1},
            genre_counts={},
            tag_counts={"御兽": 1},
            category_counts={"novel": 1},
            window_days=30,
            weighted_source_scores={"手动观察": 0.8},
            weighted_genre_scores={},
            weighted_tag_scores={"御兽": 0.8},
            daily_counts=[{"date": "2026-04-29", "count": 1}],
            recent_samples=self.list_market_signals(limit=limit),
        )

    def get_market_signal_settings(self):
        return FakeTopicMarketSignalAutomationSettingsDTO()

    def update_market_signal_settings(self, changes):
        return FakeTopicMarketSignalAutomationSettingsDTO(**changes)

    def collect_market_signals(self, request):
        self.collected = request
        return [
            FakeTopicMarketSignalDTO(
                id="signal-collected",
                source="起点-小说榜",
                title="榜单标题",
                summary="公开榜单采集",
                raw_text="榜单标题",
                created_at="2026-04-29T12:00:00+00:00",
            )
        ]

    def test_market_signal_sources(self, request):
        self.collected = request
        return [
            FakeTopicMarketSignalSourceConnectionDTO(
                source_key=key,
                source_name=key,
                ok=key != "bad_source",
                count=1 if key != "bad_source" else 0,
                message="ok" if key != "bad_source" else "No signals collected",
                sample_titles=["债务修仙"] if key != "bad_source" else [],
            )
            for key in request.source_keys
        ]

    def list_market_signal_source_health(self):
        return [
            FakeTopicMarketSignalSourceHealthDTO(
                source_key="qidian_rank",
                source_name="起点-小说榜",
                status="success",
                last_run_at="2026-04-29T12:00:00+00:00",
                last_success_at="2026-04-29T12:00:00+00:00",
                last_count=5,
                next_run_at="2026-04-29T13:00:00+00:00",
            )
        ]

    def list_market_signal_sources(self):
        return [
            FakeTopicMarketSignalSourceDTO(
                key="qidian_rank",
                name="起点-小说榜",
                url="https://www.qidian.com/rank/",
            )
        ]

    def list_market_signal_source_credentials(self):
        return [
            FakeTopicMarketSignalSourceCredentialStatusDTO(
                source_key="qidian_rank",
                api_key_configured=True,
                cookie_configured=False,
                header_keys=["X-Platform"],
                updated_at="2026-04-29T12:00:00+00:00",
            )
        ]

    def update_market_signal_source_credentials(self, source_key, changes):
        self.credential_update = (source_key, changes)
        if source_key == "missing":
            raise ValueError("Unknown market signal source: missing")
        return FakeTopicMarketSignalSourceCredentialStatusDTO(
            source_key=source_key,
            api_key_configured=bool(changes.get("api_key")),
            cookie_configured=bool(changes.get("cookie")),
            header_keys=sorted((changes.get("headers") or {}).keys()),
            updated_at="2026-04-29T12:00:00+00:00",
        )


@pytest.fixture
def topic_client(monkeypatch):
    """构造只包含 topic ideas router 的测试应用。"""
    topic_pkg = types.ModuleType("application.topic")
    topic_pkg.__path__ = []
    topic_dtos = types.ModuleType("application.topic.dtos")
    topic_dtos.TopicGenerateRequestDTO = FakeTopicGenerateRequestDTO
    topic_dtos.TopicIdeaDTO = FakeTopicIdeaDTO
    topic_dtos.TopicMarketSignalCollectRequestDTO = FakeTopicMarketSignalCollectRequestDTO
    topic_dtos.TopicMarketSignalDTO = FakeTopicMarketSignalDTO
    topic_dtos.TopicMarketSignalImportRequestDTO = FakeTopicMarketSignalImportRequestDTO
    topic_dtos.TopicMarketSignalSummaryDTO = FakeTopicMarketSignalSummaryDTO
    topic_dtos.TopicMarketSignalSourceConnectionDTO = FakeTopicMarketSignalSourceConnectionDTO
    topic_dtos.TopicMarketSignalSourceHealthDTO = FakeTopicMarketSignalSourceHealthDTO
    topic_dtos.TopicMarketSignalAutomationSettingsDTO = FakeTopicMarketSignalAutomationSettingsDTO
    topic_dtos.TopicMarketSignalSourceDTO = FakeTopicMarketSignalSourceDTO
    topic_dtos.TopicMarketSignalSourceCredentialStatusDTO = FakeTopicMarketSignalSourceCredentialStatusDTO
    topic_dtos.CompareTopicIdeasRequestDTO = FakeCompareTopicIdeasRequestDTO
    topic_dtos.TopicIdeaCompareResultDTO = FakeTopicIdeaCompareResultDTO

    topic_services_pkg = types.ModuleType("application.topic.services")
    topic_services_pkg.__path__ = []
    topic_service_mod = types.ModuleType("application.topic.services.topic_idea_service")
    topic_service_mod.TopicIdeaGenerationError = RuntimeError
    topic_service_mod.TopicIdeaService = FakeTopicIdeaService

    monkeypatch.setitem(sys.modules, "application.topic", topic_pkg)
    monkeypatch.setitem(sys.modules, "application.topic.dtos", topic_dtos)
    monkeypatch.setitem(sys.modules, "application.topic.services", topic_services_pkg)
    monkeypatch.setitem(
        sys.modules,
        "application.topic.services.topic_idea_service",
        topic_service_mod,
    )

    module_name = "interfaces.api.v1.topic.topic_ideas"
    sys.modules.pop(module_name, None)
    topic_ideas = importlib.import_module(module_name)

    service = FakeTopicIdeaService()
    app = FastAPI()
    app.include_router(topic_ideas.router, prefix="/api/v1")
    app.dependency_overrides[topic_ideas.get_topic_idea_service] = lambda: service

    return TestClient(app), service


def test_generate_topic_ideas(topic_client):
    client, service = topic_client

    response = client.post("/api/v1/topics/generate", json={"seed": "仙侠"})

    assert response.status_code == 200
    assert response.json() == [
        {"id": "topic-1", "title": "云海剑宗", "status": "draft"},
    ]
    assert service.generated_request.seed == "仙侠"


def test_import_market_signals(topic_client):
    client, service = topic_client

    response = client.post(
        "/api/v1/topics/signals/import",
        json={"source": "手动观察", "raw_text": "债务修仙 | 玄幻 | 负债 | 债务驱动升级"},
    )

    assert response.status_code == 200
    assert response.json()[0]["id"] == "signal-1"
    assert response.json()[0]["tags"] == ["负债"]
    assert service.imported.raw_text.startswith("债务修仙")


def test_collect_market_signals(topic_client):
    client, service = topic_client

    response = client.post(
        "/api/v1/topics/signals/collect",
        json={"source_keys": ["qidian_rank"], "limit_per_source": 3},
    )

    assert response.status_code == 200
    assert response.json()[0]["id"] == "signal-collected"
    assert service.collected.source_keys == ["qidian_rank"]


def test_test_market_signal_sources(topic_client):
    client, service = topic_client

    response = client.post(
        "/api/v1/topics/signals/sources/test",
        json={"source_keys": ["qidian_rank", "bad_source"], "limit_per_source": 1},
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "source_key": "qidian_rank",
            "source_name": "qidian_rank",
            "ok": True,
            "count": 1,
            "message": "ok",
            "sample_titles": ["债务修仙"],
        },
        {
            "source_key": "bad_source",
            "source_name": "bad_source",
            "ok": False,
            "count": 0,
            "message": "No signals collected",
            "sample_titles": [],
        },
    ]
    assert service.collected.source_keys == ["qidian_rank", "bad_source"]


def test_list_market_signal_source_health(topic_client):
    client, _service = topic_client

    response = client.get("/api/v1/topics/signals/source-health")

    assert response.status_code == 200
    assert response.json() == [
        {
            "source_key": "qidian_rank",
            "source_name": "起点-小说榜",
            "status": "success",
            "last_run_at": "2026-04-29T12:00:00+00:00",
            "last_success_at": "2026-04-29T12:00:00+00:00",
            "last_count": 5,
            "last_error": "",
            "next_run_at": "2026-04-29T13:00:00+00:00",
        }
    ]


def test_list_market_signal_sources(topic_client):
    client, _service = topic_client

    response = client.get("/api/v1/topics/signals/sources")

    assert response.status_code == 200
    assert response.json()[0]["key"] == "qidian_rank"
    assert response.json()[0]["source_type"] == "public_page"


def test_list_market_signals(topic_client):
    client, _service = topic_client

    response = client.get("/api/v1/topics/signals", params={"limit": 5})

    assert response.status_code == 200
    assert response.json()[0]["id"] == "signal-2"


def test_summarize_market_signals(topic_client):
    client, _service = topic_client

    response = client.get("/api/v1/topics/signals/summary", params={"limit": 5})

    assert response.status_code == 200
    assert response.json() == {
        "total": 1,
        "source_counts": {"手动观察": 1},
        "genre_counts": {},
        "tag_counts": {"御兽": 1},
        "category_counts": {"novel": 1},
        "window_days": 30,
        "weighted_source_scores": {"手动观察": 0.8},
        "weighted_genre_scores": {},
        "weighted_tag_scores": {"御兽": 0.8},
        "daily_counts": [{"date": "2026-04-29", "count": 1}],
        "recent_samples": [
            {
                "id": "signal-2",
                "source": "手动观察",
                "title": "",
                "genre": "",
                "tags": [],
                "summary": "榜单热词：御兽学院",
                "raw_text": "榜单热词：御兽学院",
                "created_at": "2026-04-29T11:00:00+00:00",
            }
        ],
    }


def test_get_market_signal_automation_settings(topic_client):
    client, _service = topic_client

    response = client.get("/api/v1/topics/signals/automation")

    assert response.status_code == 200
    assert response.json()["interval_minutes"] == 180
    assert response.json()["selected_source_keys"] == ["qidian_rank"]


def test_patch_market_signal_automation_settings(topic_client):
    client, _service = topic_client

    response = client.patch(
        "/api/v1/topics/signals/automation",
        json={"enabled": True, "interval_minutes": 60, "selected_source_keys": ["qidian_rank", "kuaikan_comic"]},
    )

    assert response.status_code == 200
    assert response.json()["enabled"] is True
    assert response.json()["interval_minutes"] == 60


def test_list_market_signal_source_credentials(topic_client):
    client, _service = topic_client

    response = client.get("/api/v1/topics/signals/source-credentials")

    assert response.status_code == 200
    assert response.json() == [
        {
            "source_key": "qidian_rank",
            "api_key_configured": True,
            "cookie_configured": False,
            "header_keys": ["X-Platform"],
            "updated_at": "2026-04-29T12:00:00+00:00",
        }
    ]
    assert "api_key" not in response.json()[0]


def test_patch_market_signal_source_credentials(topic_client):
    client, service = topic_client

    response = client.patch(
        "/api/v1/topics/signals/sources/qidian_rank/credentials",
        json={
            "api_key": "key-123",
            "cookie": "session=abc",
            "headers": {"X-Platform": "qidian"},
        },
    )

    assert response.status_code == 200
    assert response.json()["source_key"] == "qidian_rank"
    assert response.json()["api_key_configured"] is True
    assert response.json()["cookie_configured"] is True
    assert response.json()["header_keys"] == ["X-Platform"]
    assert "api_key" not in response.json()
    assert service.credential_update == (
        "qidian_rank",
        {
            "api_key": "key-123",
            "cookie": "session=abc",
            "headers": {"X-Platform": "qidian"},
        },
    )


def test_patch_market_signal_source_credentials_unknown_source_returns_400(topic_client):
    client, _service = topic_client

    response = client.patch(
        "/api/v1/topics/signals/sources/missing/credentials",
        json={"api_key": "key-123"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown market signal source: missing"


def test_list_topic_ideas_supports_status_query(topic_client):
    client, service = topic_client

    response = client.get("/api/v1/topics/", params={"status": "shortlisted"})

    assert response.status_code == 200
    assert response.json() == [
        {"id": "topic-2", "title": "赛博长安", "status": "shortlisted"},
    ]
    assert service.list_status == "shortlisted"


def test_patch_topic_idea_status(topic_client):
    client, service = topic_client

    response = client.patch("/api/v1/topics/topic-3", json={"status": "archived"})

    assert response.status_code == 200
    assert response.json() == {
        "id": "topic-3",
        "title": "拾荒星舰",
        "status": "archived",
    }
    assert service.updated == ("topic-3", {"status": "archived"})


def test_patch_topic_idea_content(topic_client):
    client, service = topic_client

    response = client.patch("/api/v1/topics/topic-3", json={"title": "新标题"})

    assert response.status_code == 200
    assert response.json() == {
        "id": "topic-3",
        "title": "新标题",
        "status": "draft",
    }
    assert service.updated == ("topic-3", {"title": "新标题"})


def test_patch_topic_idea_report_fields(topic_client):
    client, service = topic_client

    response = client.patch(
        "/api/v1/topics/topic-3",
        json={
            "development_notes": {"定位": "轻喜剧升级"},
            "evaluation": {"hook": 8, "risk": ["开局慢热"]},
        },
    )

    assert response.status_code == 200
    assert service.updated == (
        "topic-3",
        {
            "development_notes": {"定位": "轻喜剧升级"},
            "evaluation": {"hook": 8, "risk": ["开局慢热"]},
        },
    )


def test_patch_topic_idea_validation_error_returns_400(topic_client):
    client, _service = topic_client

    response = client.patch("/api/v1/topics/topic-3", json={"status": "bad"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid topic idea status: bad"


def test_adopt_topic_idea_returns_novel(topic_client):
    client, service = topic_client

    response = client.post("/api/v1/topics/topic-4/adopt")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "novel-1"
    assert body["title"] == "采纳 topic-4"
    assert body["stage"] == "planning"
    assert service.adopted == "topic-4"


def test_deepen_topic_idea_route_success(topic_client):
    client, service = topic_client

    response = client.post("/api/v1/topics/topic-5/deepen")

    assert response.status_code == 200
    assert response.json() == {
        "id": "topic-5",
        "title": "深化选题",
        "status": "draft",
    }
    assert service.deepened == "topic-5"


def test_evaluate_topic_idea_route_success(topic_client):
    client, service = topic_client

    response = client.post("/api/v1/topics/topic-6/evaluate")

    assert response.status_code == 200
    assert response.json() == {
        "id": "topic-6",
        "title": "评估选题",
        "status": "draft",
    }
    assert service.evaluated == "topic-6"


def test_compare_topic_ideas_route_success(topic_client):
    client, service = topic_client

    response = client.post(
        "/api/v1/topics/compare",
        json={"topic_ids": ["topic-a", "topic-b"]},
    )

    assert response.status_code == 200
    assert response.json()["recommended_topic_id"] == "topic-a"
    assert response.json()["rankings"][0]["topic_id"] == "topic-a"
    assert service.compared == ["topic-a", "topic-b"]


def test_compare_topic_ideas_requires_at_least_two_ids(topic_client):
    client, _service = topic_client

    response = client.post("/api/v1/topics/compare", json={"topic_ids": ["topic-a"]})

    assert response.status_code == 400


def test_compare_topic_ideas_value_error_returns_404(topic_client):
    client, _service = topic_client

    response = client.post(
        "/api/v1/topics/compare",
        json={"topic_ids": ["topic-a", "missing"]},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "topic not found"


def test_get_topic_idea_value_error_returns_404(topic_client):
    client, _service = topic_client

    response = client.get("/api/v1/topics/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "topic not found"
