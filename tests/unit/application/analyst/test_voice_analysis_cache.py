import pytest

from application.analyst.services.llm_voice_analysis_service import LLMVoiceAnalysisService
from application.analyst.services.voice_analysis_settings import VoiceAnalysisRuntimeSettings
from application.analyst.services.voice_drift_service import VoiceDriftService


def _settings(
    *,
    style_ttl: float = 100.0,
    style_max_size: int = 2,
    baseline_ttl: float = 100.0,
    baseline_max_size: int = 2,
) -> VoiceAnalysisRuntimeSettings:
    return VoiceAnalysisRuntimeSettings(
        style_cache_ttl_seconds=style_ttl,
        style_cache_max_size=style_max_size,
        baseline_cache_ttl_seconds=baseline_ttl,
        baseline_cache_max_size=baseline_max_size,
    )


def test_llm_voice_style_cache_evicts_lru_entry():
    service = LLMVoiceAnalysisService(object(), runtime_settings=_settings(style_max_size=2))

    service._remember_style("n1:1", {"pacing": 0.1})
    service._remember_style("n1:2", {"pacing": 0.2})
    assert service._get_cached_style("n1:1") == {"pacing": 0.1}
    service._remember_style("n1:3", {"pacing": 0.3})

    assert list(service._cache) == ["n1:1", "n1:3"]
    assert "n1:2" not in service._cache_loaded_at


def test_llm_voice_style_cache_expires(monkeypatch):
    service = LLMVoiceAnalysisService(object(), runtime_settings=_settings(style_ttl=1.0))
    now = 10.0
    monkeypatch.setattr(
        "application.analyst.services.llm_voice_analysis_service.time.monotonic",
        lambda: now,
    )

    service._remember_style("n1:1", {"pacing": 0.1})
    assert service._get_cached_style("n1:1") == {"pacing": 0.1}

    now = 11.1
    assert service._get_cached_style("n1:1") is None
    assert service._cache == {}
    assert service._cache_loaded_at == {}


def test_llm_voice_style_cache_can_be_disabled():
    service = LLMVoiceAnalysisService(object(), runtime_settings=_settings(style_ttl=0.0))

    service._remember_style("n1:1", {"pacing": 0.1})

    assert service._get_cached_style("n1:1") is None
    assert service._cache == {}
    assert service._cache_loaded_at == {}


class _ScoreRepo:
    def list_by_novel(self, novel_id: str, limit=None):
        return [
            {"adjective_density": 0.1, "avg_sentence_length": 20},
            {"adjective_density": 0.2, "avg_sentence_length": 25},
            {"adjective_density": 0.3, "avg_sentence_length": 30},
            {"adjective_density": 0.4, "avg_sentence_length": 35},
            {"adjective_density": 0.5, "avg_sentence_length": 40},
        ]


class _FingerprintRepo:
    pass


class _BaselineService:
    def _compute_simple_baseline(self, style_vectors):
        return {"baseline": {"description_depth": len(style_vectors)}, "tolerance": {}}


def test_voice_drift_baseline_cache_reuses_loaded_baseline(monkeypatch):
    service = VoiceDriftService(
        _ScoreRepo(),
        _FingerprintRepo(),
        llm_voice_service=_BaselineService(),
        use_llm_mode=True,
        runtime_settings=_settings(),
    )
    calls = 0

    def list_by_novel(novel_id: str, limit=None):
        nonlocal calls
        calls += 1
        return _ScoreRepo().list_by_novel(novel_id, limit)

    monkeypatch.setattr(service.score_repo, "list_by_novel", list_by_novel)

    first = service._get_or_init_baseline("n1")
    second = service._get_or_init_baseline("n1")

    assert first is second
    assert calls == 1


def test_voice_drift_baseline_cache_evicts_lru_entry():
    service = VoiceDriftService(
        _ScoreRepo(),
        _FingerprintRepo(),
        runtime_settings=_settings(baseline_max_size=2),
    )

    service._remember_baseline("n1", {"baseline": 1})
    service._remember_baseline("n2", {"baseline": 2})
    assert service._get_cached_baseline("n1") == {"baseline": 1}
    service._remember_baseline("n3", {"baseline": 3})

    assert list(service._baseline_cache) == ["n1", "n3"]
    assert "n2" not in service._baseline_cache_loaded_at


@pytest.mark.parametrize("ttl,max_size", [(0.0, 2), (100.0, 0)])
def test_voice_drift_baseline_cache_can_be_disabled(ttl, max_size):
    service = VoiceDriftService(
        _ScoreRepo(),
        _FingerprintRepo(),
        runtime_settings=_settings(baseline_ttl=ttl, baseline_max_size=max_size),
    )

    service._remember_baseline("n1", {"baseline": 1})

    assert service._get_cached_baseline("n1") is None
    assert service._baseline_cache == {}
    assert service._baseline_cache_loaded_at == {}
