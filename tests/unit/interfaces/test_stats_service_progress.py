from datetime import datetime, timedelta

from interfaces.api.stats.services.stats_service import StatsService


class _ProgressRepo:
    def __init__(self, records):
        self.records = records

    def get_chapter_progress_records(self, slug: str):
        assert slug == "novel-1"
        return self.records

    def count_words(self, text: str) -> int:
        return len([ch for ch in text if ch.strip()])


class _NoProgressRepo:
    def count_words(self, text: str) -> int:
        return len(text)


def test_writing_progress_aggregates_chapter_records_by_day():
    today = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    old_day = today - timedelta(days=40)
    service = StatsService(
        _ProgressRepo(
            [
                {"content": "一二三", "written_at": today.isoformat()},
                {"content": "四五", "written_at": today.timestamp()},
                {"content": "六七八九", "written_at": yesterday},
                {"content": "过期内容", "written_at": old_day.isoformat()},
                {"content": "", "written_at": today.isoformat()},
            ]
        )
    )

    progress = service.get_writing_progress("novel-1", days=30)

    assert [item.date.date() for item in progress] == [yesterday.date(), today.date()]
    assert progress[0].words_written == 4
    assert progress[0].chapters_completed == 1
    assert progress[1].words_written == 5
    assert progress[1].chapters_completed == 2


def test_writing_progress_returns_empty_when_repository_has_no_progress_source():
    service = StatsService(_NoProgressRepo())

    assert service.get_writing_progress("novel-1", days=30) == []
