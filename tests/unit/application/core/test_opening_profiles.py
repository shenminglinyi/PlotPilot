import pytest

from application.core.taxonomy.opening_profiles import (
    OpeningProfileError,
    get_opening_profile_bundle_cached,
    resolve_opening_profile,
    split_genre_label,
)


def test_split_genre_label_accepts_market_separators():
    assert split_genre_label("都市 / 都市异能") == ("都市", "都市异能")
    assert split_genre_label("都市-都市异能") == ("都市", "都市异能")
    assert split_genre_label("都市异能") == ("都市异能", "")


def test_resolve_secondary_profile_from_config_asset():
    profile = resolve_opening_profile("都市 / 都市异能")

    assert profile is not None
    assert profile.genre_major == "都市"
    assert profile.genre_theme == "都市异能"
    assert profile.source_level == "secondary"
    variables = profile.as_variables()
    assert variables["genre_opening_profile"]["opening_mechanism"]
    assert variables["genre_reader_contract"]["reader_promise"]
    assert variables["genre_rhythm_constraints"]["payoff_interval"]


def test_resolve_secondary_alias_without_major_when_unique():
    profile = resolve_opening_profile("都市异能")

    assert profile is not None
    assert profile.genre_major == "都市"
    assert profile.genre_theme == "都市异能"
    assert profile.source_level == "secondary_alias"


def test_resolve_primary_alias_from_config_without_code_fallback():
    profile = resolve_opening_profile("修仙 / 悬疑")

    assert profile is not None
    assert profile.genre_major == "仙侠"
    assert profile.source_level == "primary_default"


def test_missing_profile_blocks_in_strict_mode():
    with pytest.raises(OpeningProfileError, match="类型开篇画像缺失"):
        resolve_opening_profile("不存在分类 / 不存在二级")


def test_opening_profile_bundle_covers_collected_secondary_categories():
    bundle = get_opening_profile_bundle_cached()
    profiles = bundle["profiles"]
    secondary_count = sum(len(items) for items in profiles.values())

    assert len(bundle["primary_defaults"]) >= 15
    assert secondary_count >= 82
    assert bundle["resolution_policy"]["missing_profile"] == "block_generation"
