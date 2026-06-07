from interfaces.api.urls import bible_generation_status_url


def test_bible_generation_status_url_uses_api_prefix():
    assert (
        bible_generation_status_url("novel-1")
        == "/api/v1/bible/novels/novel-1/bible/status"
    )
