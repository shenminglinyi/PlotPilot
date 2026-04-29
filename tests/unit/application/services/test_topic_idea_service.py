"""TopicIdeaService 测试。"""

from dataclasses import dataclass
from unittest.mock import Mock

import pytest

from application.topic.dtos import (
    TopicGenerateRequestDTO,
    TopicMarketSignalCollectRequestDTO,
    TopicMarketSignalDTO,
    TopicMarketSignalImportRequestDTO,
    TopicMarketSignalSourceHealthDTO,
)
from application.topic.services.topic_idea_service import (
    TopicIdeaGenerationError,
    TopicIdeaService,
)
from domain.ai.services.llm_service import GenerationResult
from domain.ai.value_objects.token_usage import TokenUsage
from domain.topic.entities import TopicIdea, TopicIdeaStatus


class InMemoryTopicIdeaRepository:
    def __init__(self):
        self.items = {}
        self.signal_settings = None
        self.signal_credentials = {}
        self.signal_health = {}

    def save(self, idea):
        self.items[idea.id] = idea

    def get_by_id(self, idea_id):
        return self.items.get(idea_id)

    def list(self, status=None):
        values = list(self.items.values())
        if status:
            values = [item for item in values if item.status.value == status]
        return sorted(values, key=lambda item: item.created_at, reverse=True)

    def update_status(self, idea_id, status, adopted_novel_id=None):
        idea = self.items.get(idea_id)
        if idea is None:
            return None
        idea.update_status(status, adopted_novel_id)
        return idea

    def update(self, idea):
        self.items[idea.id] = idea
        return idea

    def save_market_signals(self, signals):
        self.signals = getattr(self, "signals", [])
        self.signals.extend(signals)

    def list_market_signals(self, limit=20):
        return list(reversed(getattr(self, "signals", [])))[:limit]

    def get_market_signal_settings(self):
        return self.signal_settings

    def save_market_signal_settings(self, settings):
        self.signal_settings = settings
        return settings

    def list_market_signal_credentials(self):
        return list(self.signal_credentials.values())

    def save_market_signal_credentials(self, credentials):
        self.signal_credentials[credentials.source_key] = credentials
        return credentials

    def save_market_signal_source_health(self, health):
        self.signal_health[health.source_key] = health
        return health

    def list_market_signal_source_health(self):
        return list(self.signal_health.values())


class FailingLLM:
    async def generate(self, prompt, config):
        raise RuntimeError("llm down")


class InvalidJsonLLM:
    async def generate(self, prompt, config):
        return GenerationResult(
            content="不是 JSON",
            token_usage=TokenUsage(1, 1),
        )


class PartialLLM:
    async def generate(self, prompt, config):
        return GenerationResult(
            content='{"topic_ideas":[{"title":"AI 选题","score":80}]}',
            token_usage=TokenUsage(1, 1),
        )


class CapturingLLM:
    def __init__(self):
        self.prompt = None

    async def generate(self, prompt, config):
        self.prompt = prompt
        return GenerationResult(
            content='{"topic_ideas":[{"title":"信号选题","score":82}]}',
            token_usage=TokenUsage(1, 1),
        )


class DeepenLLM:
    async def generate(self, prompt, config):
        return GenerationResult(
            content='{"topic_idea":{"premise":"AI 深化后的完整设定","score":88,"selling_points":["强钩子","系列潜力"],"risk_notes":["设定需控量"],"market_tags":["玄幻","升级"],"development_notes":{"定位":"升级流","首卷目标":["入局","破局"]}}}',
            token_usage=TokenUsage(1, 1),
        )


class EvaluateLLM:
    async def generate(self, prompt, config):
        return GenerationResult(
            content='{"evaluation":{"score":77,"risk_notes":["开局需更强"],"evaluation":{"hook":7,"market_fit":"中高","risks":["开局慢热"]}}}',
            token_usage=TokenUsage(1, 1),
        )


class NaturalEvaluationLLM:
    async def generate(self, prompt, config):
        return GenerationResult(
            content='{"score":81,"evaluation":{"hook":8,"market_fit":"高","risks":["设定密度高"]}}',
            token_usage=TokenUsage(1, 1),
        )


class PureEvaluationLLM:
    async def generate(self, prompt, config):
        return GenerationResult(
            content='{"evaluation":{"hook":6,"market_fit":"中","risks":["开局慢热"]}}',
            token_usage=TokenUsage(1, 1),
        )


class InvalidShapeLLM:
    async def generate(self, prompt, config):
        return GenerationResult(
            content='{"topic_ideas":[{"title":"错误形状"}]}',
            token_usage=TokenUsage(1, 1),
        )


@dataclass
class NovelDTOStub:
    id: str
    title: str


def test_collect_market_signals_fetches_public_source_and_persists_titles():
    repo = InMemoryTopicIdeaRepository()

    def fetcher(url):
        assert "qidian.com" in url
        return """
        <html>
          <h2>没钱修什么仙？</h2><p>仙侠·修真文明</p>
          <h2>苟在初圣魔门当人材</h2><p>玄幻·东方玄幻</p>
        </html>
        """

    service = TopicIdeaService(repo, fetch_text=fetcher)

    result = service.collect_market_signals(
        TopicMarketSignalCollectRequestDTO(source_keys=["qidian_rank"], limit_per_source=2)
    )

    assert len(result) == 6
    assert result[0].source == "起点-小说榜"
    assert result[0].title == "没钱修什么仙？"
    assert result[1].title == "苟在初圣魔门当人材"
    assert {tag for item in result for tag in item.tags} >= {"热门榜", "新书榜", "快速上榜"}
    assert len(service.list_market_signals(limit=6)) == 6


def test_fetch_url_text_uses_response_charset(monkeypatch):
    class FakeHeaders:
        def get_content_charset(self):
            return "gb18030"

    class FakeResponse:
        headers = FakeHeaders()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return "春夜困渡".encode("gb18030")

    def fake_urlopen(_request, timeout):
        assert timeout == 10
        return FakeResponse()

    monkeypatch.setattr(
        "application.topic.services.topic_idea_service.urlopen",
        fake_urlopen,
    )

    assert TopicIdeaService._fetch_url_text("https://example.com") == "春夜困渡"


def test_list_market_signal_sources_exposes_source_type_metadata():
    repo = InMemoryTopicIdeaRepository()
    service = TopicIdeaService(repo)

    sources = service.list_market_signal_sources()

    qidian = next(source for source in sources if source.key == "qidian_rank")
    assert qidian.source_type == "public_page"
    assert qidian.requires_auth is False


def test_list_market_signal_sources_uses_qimao_rank_page():
    repo = InMemoryTopicIdeaRepository()
    service = TopicIdeaService(repo)

    sources = service.list_market_signal_sources()

    qimao = next(source for source in sources if source.key == "qimao_rank")
    assert qimao.url == "https://www.qimao.com/paihang"


def test_list_market_signal_sources_uses_kuaikan_ranking_page():
    repo = InMemoryTopicIdeaRepository()
    service = TopicIdeaService(repo)

    sources = service.list_market_signal_sources()

    kuaikan = next(source for source in sources if source.key == "kuaikan_comic")
    assert kuaikan.url == "https://www.kuaikanmanhua.com/ranking/"


def test_import_market_signals_parses_and_persists_lines():
    repo = InMemoryTopicIdeaRepository()
    service = TopicIdeaService(repo)

    result = service.import_market_signals(
        TopicMarketSignalImportRequestDTO(
            source="手动观察",
            raw_text=(
                "灵气复苏债务流 | 都市爽文 | 负债, 逆袭 | 主角背债后靠异能翻盘\n"
                "榜单热词：御兽学院，标签：御兽、学院、升级"
            ),
        )
    )

    assert len(result) == 2
    assert result[0].title == "灵气复苏债务流"
    assert result[0].genre == "都市爽文"
    assert result[0].tags == ["负债", "逆袭"]
    assert result[0].summary == "主角背债后靠异能翻盘"
    assert result[1].summary == "榜单热词：御兽学院，标签：御兽、学院、升级"

    listed = service.list_market_signals()
    assert [item.id for item in listed] == [result[1].id, result[0].id]


def test_summarize_market_signals_counts_recent_samples_and_categories():
    repo = InMemoryTopicIdeaRepository()
    repo.save_market_signals(
        [
            TopicMarketSignalDTO(
                id="signal-1",
                source="起点-小说榜",
                title="债务修仙",
                genre="玄幻",
                tags=["负债", "升级"],
                summary="债务驱动升级",
                created_at="2026-04-29T10:00:00+00:00",
            ),
            TopicMarketSignalDTO(
                id="signal-2",
                source="快看漫画-漫画",
                title="契约少女",
                genre="恋爱",
                tags=["漫画", "契约"],
                summary="快看漫画热榜",
                created_at="2026-04-29T11:00:00+00:00",
            ),
            TopicMarketSignalDTO(
                id="signal-3",
                source="手动观察",
                summary="榜单热词：御兽学院，标签：御兽、学院、升级",
                created_at="2026-04-29T12:00:00+00:00",
            ),
        ]
    )
    service = TopicIdeaService(repo)

    summary = service.summarize_market_signals(limit=10)

    assert summary.total == 3
    assert summary.source_counts == {
        "手动观察": 1,
        "快看漫画-漫画": 1,
        "起点-小说榜": 1,
    }
    assert summary.genre_counts == {"恋爱": 1, "玄幻": 1}
    assert summary.tag_counts == {"升级": 1, "契约": 1, "漫画": 1, "负债": 1}
    assert summary.category_counts == {"comic": 1, "novel": 2}
    assert [item.id for item in summary.recent_samples] == [
        "signal-3",
        "signal-2",
        "signal-1",
    ]
    assert summary.window_days == 30
    assert summary.weighted_source_scores == {
        "手动观察": 0.8,
        "快看漫画-漫画": 0.7,
        "起点-小说榜": 1.0,
    }
    assert summary.weighted_tag_scores == {
        "升级": 1.0,
        "契约": 0.7,
        "漫画": 0.7,
        "负债": 1.0,
    }
    assert summary.weighted_genre_scores == {"恋爱": 0.7, "玄幻": 1.0}
    assert summary.daily_counts == [
        {"date": "2026-04-29", "count": 3},
    ]


def test_summarize_market_signals_includes_comic_topic_opportunities():
    repo = InMemoryTopicIdeaRepository()
    repo.save_market_signals(
        [
            TopicMarketSignalDTO(
                id="comic-signal-1",
                source="快看漫画-漫画",
                title="错撩",
                genre="漫画",
                tags=["漫画", "人气榜"],
                summary="财经美女记者遭遇渣男劈腿，转身开启泡总裁计划。",
                created_at="2026-04-29T12:00:00+00:00",
            ),
        ]
    )
    service = TopicIdeaService(repo)

    summary = service.summarize_market_signals(limit=10)

    assert any("总裁职场" in item for item in summary.comic_opportunities)
    assert any("错撩" in item and "误会钩子" in item for item in summary.comic_opportunities)
    assert not any("热词“人气榜”" in item for item in summary.comic_opportunities)


def test_market_signal_settings_defaults_and_update():
    repo = InMemoryTopicIdeaRepository()
    service = TopicIdeaService(repo)

    defaults = service.get_market_signal_settings()

    assert defaults.enabled is False
    assert defaults.interval_minutes == 180
    assert defaults.lookback_days == 30
    assert "qidian_rank" in defaults.selected_source_keys
    assert defaults.source_weights["qidian_rank"] == 1.0

    updated = service.update_market_signal_settings(
        {
            "enabled": True,
            "interval_minutes": 60,
            "lookback_days": 14,
            "selected_source_keys": ["qidian_rank", "kuaikan_comic"],
            "source_weights": {"qidian_rank": 1.4, "kuaikan_comic": 0.9},
        }
    )

    assert updated.enabled is True
    assert updated.interval_minutes == 60
    assert updated.lookback_days == 14
    assert updated.selected_source_keys == ["qidian_rank", "kuaikan_comic"]
    assert updated.source_weights["qidian_rank"] == 1.4
    assert updated.source_weights["kuaikan_comic"] == 0.9
    assert service.get_market_signal_settings().enabled is True


def test_market_signal_source_credentials_save_status_without_secret_values():
    repo = InMemoryTopicIdeaRepository()
    service = TopicIdeaService(repo)

    status = service.update_market_signal_source_credentials(
        "qidian_rank",
        {
            "api_key": " key-123 ",
            "cookie": " session=abc ",
            "endpoint_url": " https://example.com/qidian/rank ",
            "headers": {"X-Platform": " qidian ", "Empty": " "},
        },
    )

    assert status.source_key == "qidian_rank"
    assert status.api_key_configured is True
    assert status.cookie_configured is True
    assert status.endpoint_configured is True
    assert status.header_keys == ["X-Platform"]
    assert not hasattr(status, "api_key")
    assert repo.signal_credentials["qidian_rank"].api_key == "key-123"
    assert repo.signal_credentials["qidian_rank"].cookie == "session=abc"
    assert repo.signal_credentials["qidian_rank"].endpoint_url == "https://example.com/qidian/rank"
    assert repo.signal_credentials["qidian_rank"].headers == {"X-Platform": "qidian"}


def test_market_signal_source_credentials_partial_update_preserves_existing_values():
    repo = InMemoryTopicIdeaRepository()
    service = TopicIdeaService(repo)
    service.update_market_signal_source_credentials(
        "qidian_rank",
        {
            "api_key": "old-key",
            "cookie": "session=abc",
            "endpoint_url": "https://example.com/qidian/rank",
            "headers": {"X-Platform": "qidian"},
        },
    )

    status = service.update_market_signal_source_credentials(
        "qidian_rank",
        {"api_key": "new-key"},
    )

    assert status.api_key_configured is True
    assert status.cookie_configured is True
    assert status.header_keys == ["X-Platform"]
    assert repo.signal_credentials["qidian_rank"].api_key == "new-key"
    assert repo.signal_credentials["qidian_rank"].cookie == "session=abc"
    assert repo.signal_credentials["qidian_rank"].endpoint_url == "https://example.com/qidian/rank"
    assert repo.signal_credentials["qidian_rank"].headers == {"X-Platform": "qidian"}


def test_list_market_signal_source_credentials_includes_unconfigured_sources():
    repo = InMemoryTopicIdeaRepository()
    service = TopicIdeaService(repo)
    service.update_market_signal_source_credentials("qidian_rank", {"api_key": "key-123"})

    statuses = service.list_market_signal_source_credentials()

    qidian_status = next(item for item in statuses if item.source_key == "qidian_rank")
    kuaikan_status = next(item for item in statuses if item.source_key == "kuaikan_comic")
    assert qidian_status.api_key_configured is True
    assert qidian_status.cookie_configured is False
    assert kuaikan_status.api_key_configured is False
    assert kuaikan_status.cookie_configured is False


def test_market_signal_source_credentials_reject_unknown_source():
    service = TopicIdeaService(InMemoryTopicIdeaRepository())

    with pytest.raises(ValueError, match="Unknown market signal source"):
        service.update_market_signal_source_credentials("missing_source", {"api_key": "key"})


def test_collect_market_signals_uses_configured_endpoint_url_and_json_parser():
    repo = InMemoryTopicIdeaRepository()
    service = TopicIdeaService(repo)
    service.update_market_signal_source_credentials(
        "qidian_rank",
        {
            "endpoint_url": "https://example.com/qidian/api/rank",
            "api_key": "key-123",
        },
    )
    captured = {}
    service._fetch_text = lambda url, headers: (
        captured.update({"url": url, "headers": headers})
        or '{"data":{"rankName":"热读榜","books":[{"bookName":"债务修仙","category":"玄幻","tags":["负债"],"intro":"债务规则推动升级。"}]}}'
    )

    signals = service.collect_market_signals(
        TopicMarketSignalCollectRequestDTO(source_keys=["qidian_rank"], limit_per_source=1)
    )

    assert captured["url"] == "https://example.com/qidian/api/rank"
    assert captured["headers"]["Authorization"] == "Bearer key-123"
    assert signals[0].source == "起点-小说榜"
    assert signals[0].title == "债务修仙"
    assert signals[0].genre == "玄幻"
    assert signals[0].tags == ["负债", "热读榜"]


def test_test_market_signal_sources_reports_success_and_empty_sources_without_saving():
    repo = InMemoryTopicIdeaRepository()
    service = TopicIdeaService(repo)
    service.update_market_signal_source_credentials(
        "qidian_rank",
        {"endpoint_url": "https://example.com/qidian/api/rank"},
    )
    service._fetch_text = lambda _url, _headers: (
        '{"data":{"rankName":"热读榜","books":[{"bookName":"债务修仙","category":"玄幻"}]}}'
    )

    results = service.test_market_signal_sources(
        TopicMarketSignalCollectRequestDTO(
            source_keys=["qidian_rank", "missing_source"],
            limit_per_source=1,
        )
    )

    assert len(results) == 2
    assert results[0].source_key == "qidian_rank"
    assert results[0].ok is True
    assert results[0].count == 1
    assert results[0].sample_titles == ["债务修仙"]
    assert results[1].source_key == "missing_source"
    assert results[1].ok is False
    assert "Unknown source" in results[1].message
    assert not hasattr(repo, "signals")


def test_collect_market_signals_records_source_health_for_success_and_empty_source():
    repo = InMemoryTopicIdeaRepository()

    def fetcher(url, _headers=None):
        if "qidian.com" in url:
            return "<html><h2>债务修仙</h2></html>"
        return "<html></html>"

    service = TopicIdeaService(repo, fetch_text=fetcher)

    service.collect_market_signals(
        TopicMarketSignalCollectRequestDTO(
            source_keys=["qidian_rank", "qimao_rank"],
            limit_per_source=1,
        )
    )

    health = service.list_market_signal_source_health()
    by_key = {item.source_key: item for item in health}
    assert by_key["qidian_rank"].status == "success"
    assert by_key["qidian_rank"].last_count == 3
    assert by_key["qidian_rank"].last_run_at
    assert by_key["qidian_rank"].last_success_at
    assert by_key["qidian_rank"].last_error == ""
    assert by_key["qimao_rank"].status == "error"
    assert by_key["qimao_rank"].last_count == 0
    assert by_key["qimao_rank"].last_error == "No signals collected"


def test_list_market_signal_source_health_includes_next_run_for_selected_enabled_sources():
    repo = InMemoryTopicIdeaRepository()
    repo.save_market_signal_source_health(
        TopicMarketSignalSourceHealthDTO(
            source_key="qidian_rank",
            source_name="起点-小说榜",
            status="success",
            last_run_at="2026-04-29T12:00:00+00:00",
            last_success_at="2026-04-29T12:00:00+00:00",
            last_count=5,
        )
    )
    service = TopicIdeaService(repo)
    service.update_market_signal_settings(
        {
            "enabled": True,
            "interval_minutes": 60,
            "selected_source_keys": ["qidian_rank"],
            "last_run_at": "2026-04-29T12:00:00+00:00",
        }
    )

    health = service.list_market_signal_source_health()
    qidian = next(item for item in health if item.source_key == "qidian_rank")
    qimao = next(item for item in health if item.source_key == "qimao_rank")

    assert qidian.status == "success"
    assert qidian.next_run_at == "2026-04-29T13:00:00+00:00"
    assert qimao.status == "unknown"
    assert qimao.next_run_at == ""


@pytest.mark.asyncio
async def test_generate_falls_back_when_llm_fails():
    repo = InMemoryTopicIdeaRepository()
    service = TopicIdeaService(repo, llm_service=InvalidJsonLLM())

    ideas = await service.generate(
        TopicGenerateRequestDTO(brief="赛博修仙", genre="科幻", count=2)
    )

    assert len(ideas) == 3
    assert all(idea.status == "draft" for idea in ideas)
    assert all(idea.genre == "科幻" for idea in ideas)
    assert len(repo.items) == 3


@pytest.mark.asyncio
async def test_generate_raises_and_does_not_save_when_llm_call_fails():
    repo = InMemoryTopicIdeaRepository()
    service = TopicIdeaService(repo, llm_service=FailingLLM())

    with pytest.raises(TopicIdeaGenerationError, match="选题生成调用失败"):
        await service.generate(TopicGenerateRequestDTO(brief="赛博修仙", count=3))

    assert repo.items == {}


@pytest.mark.asyncio
async def test_generate_fallback_can_fill_five_ideas():
    repo = InMemoryTopicIdeaRepository()
    service = TopicIdeaService(repo, llm_service=InvalidJsonLLM())

    ideas = await service.generate(TopicGenerateRequestDTO(brief="边城异能", count=5))

    assert len(ideas) == 5
    assert len(repo.items) == 5


@pytest.mark.asyncio
async def test_generate_uses_llm_and_fills_shortage():
    repo = InMemoryTopicIdeaRepository()
    service = TopicIdeaService(repo, llm_service=PartialLLM())

    ideas = await service.generate(TopicGenerateRequestDTO(brief="边城异能", count=3))

    assert len(ideas) == 3
    assert ideas[0].title == "AI 选题"
    assert len(repo.items) == 3


@pytest.mark.asyncio
async def test_generate_prompt_includes_manual_brief_and_market_signals():
    repo = InMemoryTopicIdeaRepository()
    llm = CapturingLLM()
    service = TopicIdeaService(repo, llm_service=llm)

    await service.generate(
        TopicGenerateRequestDTO(
            brief="想写偏热血但不要无脑碾压",
            genre="都市爽文",
            market_signals=[
                {
                    "title": "灵气复苏债务流",
                    "genre": "都市爽文",
                    "tags": ["负债", "逆袭"],
                    "summary": "主角背债后靠异能翻盘",
                }
            ],
        )
    )

    assert llm.prompt is not None
    assert "想写偏热血但不要无脑碾压" in llm.prompt.user
    assert "市场观察" in llm.prompt.user
    assert "灵气复苏债务流" in llm.prompt.user
    assert "负债" in llm.prompt.user


def test_adopt_is_idempotent_when_already_adopted():
    repo = InMemoryTopicIdeaRepository()
    idea = TopicIdea(
        title="已采纳选题",
        status=TopicIdeaStatus.ADOPTED,
        adopted_novel_id="novel-existing",
    )
    repo.save(idea)
    novel_service = Mock()
    novel_service.get_novel.return_value = NovelDTOStub(
        id="novel-existing",
        title="已采纳选题",
    )
    service = TopicIdeaService(repo, novel_service=novel_service)

    result = service.adopt(idea.id)

    assert result.id == "novel-existing"
    novel_service.get_novel.assert_called_once_with("novel-existing")
    novel_service.create_novel.assert_not_called()


def test_adopt_creates_novel_and_marks_idea_adopted():
    repo = InMemoryTopicIdeaRepository()
    idea = TopicIdea(
        title="新选题",
        genre="玄幻",
        world_preset="宗门",
        length_tier="short",
        logline="一句话卖点",
        development_notes={
            "首卷目标": ["入宗门", "破旧案"],
            "角色关系": {"盟友": "旧案证人"},
        },
        evaluation={
            "开篇钩子": "已具备",
            "主要风险": ["设定解释过多"],
        },
    )
    repo.save(idea)
    novel_service = Mock()
    novel_service.create_novel.return_value = NovelDTOStub(
        id="novel-created",
        title="新选题",
    )
    service = TopicIdeaService(repo, novel_service=novel_service)

    result = service.adopt(idea.id, author="作者")

    assert result.id == "novel-created"
    saved = repo.get_by_id(idea.id)
    assert saved.status == TopicIdeaStatus.ADOPTED
    assert saved.adopted_novel_id == "novel-created"
    kwargs = novel_service.create_novel.call_args.kwargs
    assert kwargs["title"] == "新选题"
    assert kwargs["author"] == "作者"
    assert kwargs["length_tier"] == "short"
    assert "立项案" in kwargs["premise"]
    assert "首卷目标" in kwargs["premise"]
    assert "入宗门" in kwargs["premise"]
    assert "立项评估" in kwargs["premise"]
    assert "设定解释过多" in kwargs["premise"]


@pytest.mark.asyncio
async def test_deepen_fallback_updates_and_returns_complete_fields():
    repo = InMemoryTopicIdeaRepository()
    idea = TopicIdea(title="档案管理员", genre="悬疑", logline="旧档案预告未来灾难")
    repo.save(idea)
    service = TopicIdeaService(repo)

    result = await service.deepen(idea.id)

    assert result.id == idea.id
    assert len(result.premise) > len("旧档案预告未来灾难")
    assert result.protagonist_hook
    assert result.core_conflict
    assert result.opening_hook
    assert result.selling_points
    assert result.long_term_potential
    assert result.risk_notes
    assert result.market_tags
    assert 0 <= result.score <= 100
    assert result.development_notes
    assert "立项定位" in result.development_notes


@pytest.mark.asyncio
async def test_evaluate_fallback_updates_score_and_risks():
    repo = InMemoryTopicIdeaRepository()
    idea = TopicIdea(title="边城异能", genre="都市", premise="边城少年觉醒异能")
    repo.save(idea)
    repo.save_market_signals(
        [
            TopicMarketSignalDTO(
                id="signal-a",
                source="起点-小说榜",
                title="边城债务异能",
                genre="都市",
                tags=["异能", "逆袭"],
                summary="主角背债后靠异能翻盘",
                created_at="2026-04-29T10:00:00+00:00",
            ),
            TopicMarketSignalDTO(
                id="signal-b",
                source="快看漫画-漫画",
                title="边城契约者",
                genre="漫画",
                tags=["漫画", "契约", "异能"],
                summary="视觉反差强、契约对抗明确",
                created_at="2026-04-29T11:00:00+00:00",
            ),
        ]
    )
    repo.save_market_signal_settings(
        service_settings := TopicIdeaService(repo).get_market_signal_settings()
    )
    service_settings.lookback_days = 30
    service_settings.source_weights = {"qidian_rank": 1.4, "kuaikan_comic": 0.9}
    service = TopicIdeaService(repo)

    result = await service.evaluate(idea.id)

    assert result.id == idea.id
    assert isinstance(result.score, int)
    assert 0 <= result.score <= 100
    assert result.risk_notes
    assert result.market_tags
    assert result.selling_points
    assert result.long_term_potential
    assert result.evaluation
    assert "综合评分" in result.evaluation
    assert "市场匹配度" in result.evaluation
    assert "漫画转题机会" in result.evaluation


@pytest.mark.asyncio
async def test_evaluate_translates_comic_signals_into_novel_opportunities():
    repo = InMemoryTopicIdeaRepository()
    idea = TopicIdea(
        title="错撩总裁风暴",
        genre="都市言情",
        premise="财经记者错撩总裁后卷入职场与豪门关系。",
        market_tags=["总裁", "职场"],
    )
    repo.save(idea)
    repo.save_market_signals(
        [
            TopicMarketSignalDTO(
                id="comic-signal-1",
                source="快看漫画-漫画",
                title="错撩",
                genre="漫画",
                tags=["漫画", "人气榜"],
                summary="财经美女记者遭遇渣男劈腿，转身开启泡总裁计划。",
                created_at="2026-04-29T12:00:00+00:00",
            ),
        ]
    )
    settings = TopicIdeaService(repo).get_market_signal_settings()
    settings.source_weights = {"kuaikan_comic": 1.2}
    repo.save_market_signal_settings(settings)
    service = TopicIdeaService(repo)

    result = await service.evaluate(idea.id)

    opportunities = result.evaluation["漫画转题机会"]
    assert any("总裁职场" in item for item in opportunities)
    assert any("错撩" in item and "误会钩子" in item for item in opportunities)
    assert not any("热词“人气榜”" in item for item in opportunities)


def test_compare_returns_recommended_topic_and_sorted_rankings():
    repo = InMemoryTopicIdeaRepository()
    low = TopicIdea(title="低分", score=50, premise="短")
    high = TopicIdea(
        title="高分",
        score=80,
        premise="完整设定",
        protagonist_hook="强主角",
        core_conflict="强冲突",
        opening_hook="强开局",
        selling_points=["爽点"],
        long_term_potential="长线可扩展",
        risk_notes=["风险"],
        market_tags=["标签"],
    )
    repo.save(low)
    repo.save(high)
    service = TopicIdeaService(repo)

    result = service.compare([low.id, high.id])

    assert result.recommended_topic_id == high.id
    assert [item.topic_id for item in result.rankings] == [high.id, low.id]
    assert result.rankings[0].score >= result.rankings[1].score
    assert result.rankings[0].risks == ["风险"]


def test_compare_missing_id_raises_value_error():
    repo = InMemoryTopicIdeaRepository()
    idea = TopicIdea(title="存在的选题")
    repo.save(idea)
    service = TopicIdeaService(repo)

    with pytest.raises(ValueError, match="Topic idea not found: missing"):
        service.compare([idea.id, "missing"])


def test_compare_requires_two_unique_topic_ids():
    repo = InMemoryTopicIdeaRepository()
    idea = TopicIdea(title="重复选题")
    repo.save(idea)
    service = TopicIdeaService(repo)

    with pytest.raises(ValueError, match="At least two topic_ids are required"):
        service.compare([idea.id, idea.id])


@pytest.mark.asyncio
async def test_deepen_llm_call_failure_raises_generation_error():
    repo = InMemoryTopicIdeaRepository()
    idea = TopicIdea(title="失联模型选题")
    repo.save(idea)
    service = TopicIdeaService(repo, llm_service=FailingLLM())

    with pytest.raises(TopicIdeaGenerationError, match="选题深化调用失败"):
        await service.deepen(idea.id)


@pytest.mark.asyncio
async def test_deepen_uses_llm_payload_when_available():
    repo = InMemoryTopicIdeaRepository()
    idea = TopicIdea(title="AI 深化选题", premise="原始设定")
    repo.save(idea)
    service = TopicIdeaService(repo, llm_service=DeepenLLM())

    result = await service.deepen(idea.id)

    assert result.premise == "AI 深化后的完整设定"
    assert result.score == 88
    assert result.selling_points == ["强钩子", "系列潜力"]
    assert result.development_notes == {"定位": "升级流", "首卷目标": ["入局", "破局"]}


@pytest.mark.asyncio
async def test_evaluate_uses_llm_payload_when_available():
    repo = InMemoryTopicIdeaRepository()
    idea = TopicIdea(title="AI 评估选题", premise="原始设定")
    repo.save(idea)
    service = TopicIdeaService(repo, llm_service=EvaluateLLM())

    result = await service.evaluate(idea.id)

    assert result.score == 77
    assert result.risk_notes == ["开局需更强"]
    assert result.evaluation == {
        "hook": 7,
        "market_fit": "中高",
        "risks": ["开局慢热"],
    }


def test_update_allows_manual_report_field_revision():
    repo = InMemoryTopicIdeaRepository()
    idea = TopicIdea(title="人工修订")
    repo.save(idea)
    service = TopicIdeaService(repo)

    before = idea.updated_at

    result = service.update(
        idea.id,
        {
            "development_notes": {"核心卖点": "反差主角"},
            "evaluation": {"hook": 8},
        },
    )

    assert result.development_notes == {"核心卖点": "反差主角"}
    assert result.evaluation == {"hook": 8}
    assert repo.get_by_id(idea.id).updated_at >= before


@pytest.mark.asyncio
async def test_evaluate_accepts_natural_llm_payload_shape():
    repo = InMemoryTopicIdeaRepository()
    idea = TopicIdea(title="自然评估形状")
    repo.save(idea)
    service = TopicIdeaService(repo, llm_service=NaturalEvaluationLLM())

    result = await service.evaluate(idea.id)

    assert result.score == 81
    assert result.evaluation == {
        "hook": 8,
        "market_fit": "高",
        "risks": ["设定密度高"],
    }


@pytest.mark.asyncio
async def test_evaluate_accepts_pure_evaluation_payload_shape():
    repo = InMemoryTopicIdeaRepository()
    idea = TopicIdea(title="纯评估形状")
    repo.save(idea)
    service = TopicIdeaService(repo, llm_service=PureEvaluationLLM())

    result = await service.evaluate(idea.id)

    assert result.evaluation == {
        "hook": 6,
        "market_fit": "中",
        "risks": ["开局慢热"],
    }


@pytest.mark.asyncio
async def test_deepen_falls_back_when_llm_json_shape_is_invalid():
    repo = InMemoryTopicIdeaRepository()
    idea = TopicIdea(title="形状错误选题", premise="原始设定")
    repo.save(idea)
    service = TopicIdeaService(repo, llm_service=InvalidShapeLLM())

    result = await service.deepen(idea.id)

    assert result.premise != "原始设定"
    assert result.selling_points
