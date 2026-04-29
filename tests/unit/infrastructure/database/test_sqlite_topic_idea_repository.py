"""SQLite TopicIdeaRepository 测试。"""

import sqlite3

from domain.topic.entities import TopicIdea
from application.topic.dtos import (
    TopicMarketSignalDTO,
    TopicMarketSignalSourceCredentialDTO,
    TopicMarketSignalSourceHealthDTO,
)
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_topic_idea_repository import (
    SqliteTopicIdeaRepository,
)


def test_sqlite_topic_idea_repository_persists_json_and_filters_status(tmp_path):
    db = DatabaseConnection(str(tmp_path / "topic.db"))
    repo = SqliteTopicIdeaRepository(db)
    idea = TopicIdea(
        title="星门债主",
        genre="科幻",
        selling_points=["债务驱动", "星际逃亡"],
        market_tags=["科幻", "轻喜剧"],
        development_notes={"定位": "轻喜剧星际债务流", "章节策略": ["负债", "逃亡"]},
        evaluation={"hook": 8, "risk": ["设定解释过多"]},
        score=88,
    )
    archived = TopicIdea(title="旧选题", status="archived")

    repo.save(idea)
    repo.save(archived)

    loaded = repo.get_by_id(idea.id)
    assert loaded is not None
    assert loaded.title == "星门债主"
    assert loaded.selling_points == ["债务驱动", "星际逃亡"]
    assert loaded.market_tags == ["科幻", "轻喜剧"]
    assert loaded.development_notes == {"定位": "轻喜剧星际债务流", "章节策略": ["负债", "逃亡"]}
    assert loaded.evaluation == {"hook": 8, "risk": ["设定解释过多"]}
    assert loaded.score == 88

    drafts = repo.list("draft")
    assert [item.id for item in drafts] == [idea.id]

    updated = repo.update_status(idea.id, "adopted", adopted_novel_id="novel-1")
    assert updated is not None
    assert updated.adopted_novel_id == "novel-1"
    assert repo.get_by_id(idea.id).status.value == "adopted"


def test_database_connection_migrates_existing_topic_ideas_report_columns(tmp_path):
    db_path = tmp_path / "legacy-topic.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE topic_ideas (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'draft',
            title TEXT NOT NULL,
            genre TEXT DEFAULT '',
            world_preset TEXT DEFAULT '',
            length_tier TEXT DEFAULT '',
            logline TEXT DEFAULT '',
            premise TEXT DEFAULT '',
            protagonist_hook TEXT DEFAULT '',
            core_conflict TEXT DEFAULT '',
            opening_hook TEXT DEFAULT '',
            selling_points_json TEXT DEFAULT '[]',
            long_term_potential TEXT DEFAULT '',
            risk_notes_json TEXT DEFAULT '[]',
            market_tags_json TEXT DEFAULT '[]',
            score INTEGER DEFAULT 0,
            adopted_novel_id TEXT,
            source_brief_json TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("INSERT INTO topic_ideas (id, title) VALUES ('topic-old', '旧选题')")
    conn.commit()
    conn.close()

    db = DatabaseConnection(str(db_path))
    repo = SqliteTopicIdeaRepository(db)

    loaded = repo.get_by_id("topic-old")
    assert loaded is not None
    assert loaded.development_notes == {}
    assert loaded.evaluation == {}

    loaded.development_notes = {"方向": "补列后可保存"}
    loaded.evaluation = {"score_detail": {"hook": 7}}
    repo.save(loaded)

    reloaded = repo.get_by_id("topic-old")
    assert reloaded.development_notes == {"方向": "补列后可保存"}
    assert reloaded.evaluation == {"score_detail": {"hook": 7}}


def test_database_connection_migrates_minimal_legacy_topic_ideas_table(tmp_path):
    db_path = tmp_path / "minimal-legacy-topic.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE topic_ideas (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL
        )
        """
    )
    conn.execute("INSERT INTO topic_ideas (id, title) VALUES ('topic-minimal', '极旧选题')")
    conn.commit()
    conn.close()

    db = DatabaseConnection(str(db_path))
    repo = SqliteTopicIdeaRepository(db)

    loaded = repo.get_by_id("topic-minimal")
    assert loaded is not None
    assert loaded.title == "极旧选题"
    assert loaded.selling_points == []
    assert loaded.risk_notes == []
    assert loaded.market_tags == []

    loaded.selling_points = ["强开局"]
    loaded.market_tags = ["热门榜"]
    loaded.score = 76
    repo.save(loaded)

    reloaded = repo.get_by_id("topic-minimal")
    assert reloaded.selling_points == ["强开局"]
    assert reloaded.market_tags == ["热门榜"]
    assert reloaded.score == 76


def test_sqlite_topic_idea_repository_persists_market_signals(tmp_path):
    db = DatabaseConnection(str(tmp_path / "topic-signals.db"))
    repo = SqliteTopicIdeaRepository(db)
    first = TopicMarketSignalDTO(
        id="signal-1",
        source="手动观察",
        title="债务修仙",
        genre="玄幻",
        tags=["负债", "升级"],
        summary="债务驱动升级",
        raw_text="债务修仙 | 玄幻 | 负债,升级 | 债务驱动升级",
        created_at="2026-04-29T10:00:00+00:00",
    )
    second = TopicMarketSignalDTO(
        id="signal-2",
        source="手动观察",
        summary="榜单热词：御兽学院",
        raw_text="榜单热词：御兽学院",
        created_at="2026-04-29T11:00:00+00:00",
    )

    repo.save_market_signals([first, second])

    signals = repo.list_market_signals(limit=10)
    assert [item.id for item in signals] == ["signal-2", "signal-1"]
    assert signals[1].title == "债务修仙"
    assert signals[1].tags == ["负债", "升级"]
    assert signals[0].summary == "榜单热词：御兽学院"


def test_sqlite_topic_idea_repository_deduplicates_market_signals_by_source_title_or_summary(tmp_path):
    db = DatabaseConnection(str(tmp_path / "topic-signals-dedup.db"))
    repo = SqliteTopicIdeaRepository(db)

    repo.save_market_signals(
        [
            TopicMarketSignalDTO(
                id="signal-title-1",
                source="起点-小说榜",
                title="债务修仙",
                summary="债务驱动升级",
                created_at="2026-04-29T10:00:00+00:00",
            ),
            TopicMarketSignalDTO(
                id="signal-summary-1",
                source="手动观察",
                summary="榜单热词：御兽学院",
                created_at="2026-04-29T11:00:00+00:00",
            ),
        ]
    )
    repo.save_market_signals(
        [
            TopicMarketSignalDTO(
                id="signal-title-2",
                source="起点-小说榜",
                title="债务修仙",
                summary="同标题重复不应入库",
                created_at="2026-04-29T12:00:00+00:00",
            ),
            TopicMarketSignalDTO(
                id="signal-summary-2",
                source="手动观察",
                summary="榜单热词：御兽学院",
                created_at="2026-04-29T13:00:00+00:00",
            ),
            TopicMarketSignalDTO(
                id="signal-other-source",
                source="七猫-小说榜",
                title="债务修仙",
                summary="不同来源同标题允许入库",
                created_at="2026-04-29T14:00:00+00:00",
            ),
        ]
    )

    signals = repo.list_market_signals(limit=10)
    assert [item.id for item in signals] == [
        "signal-other-source",
        "signal-summary-1",
        "signal-title-1",
    ]


def test_sqlite_topic_idea_repository_persists_market_signal_settings(tmp_path):
    db = DatabaseConnection(str(tmp_path / "topic-signal-settings.db"))
    repo = SqliteTopicIdeaRepository(db)

    settings = repo.get_market_signal_settings()
    assert settings.enabled is False
    assert settings.interval_minutes == 180

    updated = repo.save_market_signal_settings(
        settings.__class__(
            enabled=True,
            interval_minutes=90,
            limit_per_source=6,
            lookback_days=21,
            source_weights={"qidian_rank": 1.3},
            selected_source_keys=["qidian_rank", "kuaikan_comic"],
            last_status="success",
            last_run_at="2026-04-29T12:00:00+00:00",
        )
    )

    reloaded = repo.get_market_signal_settings()
    assert updated.enabled is True
    assert reloaded.interval_minutes == 90
    assert reloaded.lookback_days == 21
    assert reloaded.selected_source_keys == ["qidian_rank", "kuaikan_comic"]
    assert reloaded.source_weights == {"qidian_rank": 1.3}


def test_sqlite_topic_idea_repository_persists_market_signal_credentials(tmp_path):
    db = DatabaseConnection(str(tmp_path / "topic-signal-credentials.db"))
    repo = SqliteTopicIdeaRepository(db)

    repo.save_market_signal_credentials(
        TopicMarketSignalSourceCredentialDTO(
            source_key="qidian_rank",
            api_key="key-123",
            cookie="session=abc",
            endpoint_url="https://example.com/qidian/api/rank",
            headers={"X-Platform": "qidian"},
            updated_at="2026-04-29T12:00:00+00:00",
        )
    )

    reloaded = SqliteTopicIdeaRepository(DatabaseConnection(str(tmp_path / "topic-signal-credentials.db")))
    credentials = reloaded.list_market_signal_credentials()

    assert len(credentials) == 1
    assert credentials[0].source_key == "qidian_rank"
    assert credentials[0].api_key == "key-123"
    assert credentials[0].cookie == "session=abc"
    assert credentials[0].endpoint_url == "https://example.com/qidian/api/rank"
    assert credentials[0].headers == {"X-Platform": "qidian"}


def test_sqlite_topic_idea_repository_persists_market_signal_source_health(tmp_path):
    db_path = tmp_path / "topic-signal-health.db"
    repo = SqliteTopicIdeaRepository(DatabaseConnection(str(db_path)))

    repo.save_market_signal_source_health(
        TopicMarketSignalSourceHealthDTO(
            source_key="qidian_rank",
            source_name="起点-小说榜",
            status="success",
            last_run_at="2026-04-29T12:00:00+00:00",
            last_success_at="2026-04-29T12:00:00+00:00",
            last_count=5,
            last_error="",
        )
    )
    repo.save_market_signal_source_health(
        TopicMarketSignalSourceHealthDTO(
            source_key="qimao_rank",
            source_name="七猫-小说榜",
            status="error",
            last_run_at="2026-04-29T12:05:00+00:00",
            last_count=0,
            last_error="No signals collected",
        )
    )

    reloaded = SqliteTopicIdeaRepository(DatabaseConnection(str(db_path)))
    health = reloaded.list_market_signal_source_health()

    assert [item.source_key for item in health] == ["qidian_rank", "qimao_rank"]
    assert health[0].status == "success"
    assert health[0].last_success_at == "2026-04-29T12:00:00+00:00"
    assert health[0].last_count == 5
    assert health[1].status == "error"
    assert health[1].last_error == "No signals collected"
