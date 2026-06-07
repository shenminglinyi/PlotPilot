from interfaces.api.urls import bible_generation_status_url, stats_api_url


def test_bible_generation_status_url_uses_api_prefix():
    assert (
        bible_generation_status_url("novel-1")
        == "/api/v1/bible/novels/novel-1/bible/status"
    )


def test_stats_api_url_uses_stats_prefix():
    assert stats_api_url("global") == "/api/stats/global"
    assert stats_api_url("/book/demo/progress?days=7") == (
        "/api/stats/book/demo/progress?days=7"
    )
