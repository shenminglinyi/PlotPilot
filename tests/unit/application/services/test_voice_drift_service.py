"""VoiceDriftService 单元测试"""
from unittest.mock import MagicMock
from application.analyst.services.voice_drift_service import VoiceDriftService, DRIFT_ALERT_CONSECUTIVE


def _make_service(scores=None, fingerprint=None):
    score_repo = MagicMock()
    score_repo.list_by_novel.return_value = scores or []
    score_repo.upsert.return_value = "score-1"

    fp_repo = MagicMock()
    fp_repo.get_by_novel.return_value = fingerprint

    return VoiceDriftService(score_repo, fp_repo)


# ------ 指标计算 ------

def test_compute_metrics_empty_text():
    m = VoiceDriftService._compute_metrics("")
    assert m["adjective_density"] == 0.0
    assert m["avg_sentence_length"] == 0.0
    assert m["sentence_count"] == 0


def test_compute_metrics_counts_sentences():
    text = "他很美丽。她很温柔。那真的很好。"
    m = VoiceDriftService._compute_metrics(text)
    assert m["sentence_count"] == 3
    assert m["avg_sentence_length"] > 0


# ------ 相似度计算 ------

def test_cosine_similarity_identical_returns_one():
    metrics = {"adjective_density": 0.05, "avg_sentence_length": 20.0}
    fp = {"adjective_density": 0.05, "avg_sentence_length": 20.0}
    assert VoiceDriftService._cosine_similarity(metrics, fp) == 1.0


def test_cosine_similarity_zero_baseline():
    metrics = {"adjective_density": 0.0, "avg_sentence_length": 0.0}
    fp = {"adjective_density": 0.0, "avg_sentence_length": 0.0}
    assert VoiceDriftService._cosine_similarity(metrics, fp) == 1.0


# ------ 漂移告警 ------

def test_no_alert_when_insufficient_history():
    svc = _make_service(scores=[{"similarity_score": 0.5}] * 3)
    assert not svc._check_drift_alert("novel-1")


def test_alert_when_consecutive_low_scores():
    low = [{"similarity_score": 0.5}] * DRIFT_ALERT_CONSECUTIVE
    svc = _make_service(scores=low)
    assert svc._check_drift_alert("novel-1")


def test_no_alert_when_one_high_score():
    mixed = [{"similarity_score": 0.5}] * (DRIFT_ALERT_CONSECUTIVE - 1)
    mixed.append({"similarity_score": 0.9})
    svc = _make_service(scores=mixed)
    assert not svc._check_drift_alert("novel-1")


# ------ score_chapter 集成 ------

def test_score_chapter_without_fingerprint_returns_none_similarity():
    svc = _make_service(fingerprint=None)
    result = svc.score_chapter("novel-1", 1, "他很美丽。她很温柔。")
    assert result["similarity_score"] is None


def test_score_chapter_with_fingerprint_returns_float():
    fingerprint = {
        "adjective_density": 0.05,
        "avg_sentence_length": 20.0,
        "sample_count": 10,
    }
    svc = _make_service(fingerprint=fingerprint)
    result = svc.score_chapter("novel-1", 1, "他很美丽。她很温柔。这真的很好。")
    assert isinstance(result["similarity_score"], float)
    assert 0.0 <= result["similarity_score"] <= 1.0


def test_score_chapter_persists_score():
    fingerprint = {
        "adjective_density": 0.05,
        "avg_sentence_length": 20.0,
        "sample_count": 10,
    }
    svc = _make_service(fingerprint=fingerprint)
    svc.score_chapter("novel-1", 3, "她很可爱。他很聪明。")
    svc.score_repo.upsert.assert_called_once()
    call_kwargs = svc.score_repo.upsert.call_args
    assert call_kwargs.kwargs["chapter_number"] == 3
