"""Unit tests for voice fingerprint service."""
import pytest
from unittest.mock import Mock

from application.analyst.services.voice_fingerprint_service import VoiceFingerprintService


class TestVoiceFingerprintService:
    """Test suite for VoiceFingerprintService."""

    @pytest.fixture
    def mock_fingerprint_repo(self):
        """Mock fingerprint repository."""
        return Mock()

    @pytest.fixture
    def mock_sample_repo(self):
        """Mock sample repository."""
        return Mock()

    @pytest.fixture
    def service(self, mock_fingerprint_repo, mock_sample_repo):
        """Create service instance."""
        return VoiceFingerprintService(mock_fingerprint_repo, mock_sample_repo)

    def test_compute_fingerprint_calculates_metrics(self, service):
        """Test that compute_fingerprint calculates all metrics correctly."""
        samples = [
            {"content": "这是一个美丽的春天。"},
            {"content": "天气很温柔！阳光明亮？"},
        ]

        result = service.compute_fingerprint(samples)

        assert "adjective_density" in result
        assert "avg_sentence_length" in result
        assert "sentence_count" in result
        assert result["adjective_density"] > 0
        assert result["avg_sentence_length"] > 0
        assert result["sentence_count"] == 3

    def test_compute_fingerprint_empty_samples(self, service):
        """Test that empty samples return zero values."""
        result = service.compute_fingerprint([])

        assert result["adjective_density"] == 0.0
        assert result["avg_sentence_length"] == 0.0
        assert result["sentence_count"] == 0

    def test_maybe_recompute_triggers_at_threshold(
        self, service, mock_sample_repo, mock_fingerprint_repo
    ):
        """Test that recompute triggers when sample count reaches threshold."""
        novel_id = "novel-123"
        samples = [{"content": f"样本{i}。"} for i in range(10)]
        mock_sample_repo.get_by_novel.return_value = samples

        result = service.maybe_recompute(novel_id)

        assert result is True
        mock_sample_repo.get_by_novel.assert_called_once_with(novel_id, None)
        mock_fingerprint_repo.upsert.assert_called_once()

        # Verify upsert was called with correct structure
        call_args = mock_fingerprint_repo.upsert.call_args
        assert call_args[0][0] == novel_id
        assert "metrics" in call_args[0][1]
        assert "sample_count" in call_args[0][1]
        assert call_args[0][1]["sample_count"] == 10

    def test_maybe_recompute_skips_below_threshold(
        self, service, mock_sample_repo, mock_fingerprint_repo
    ):
        """Test that recompute does not trigger below threshold."""
        novel_id = "novel-123"
        samples = [{"content": f"样本{i}。"} for i in range(5)]
        mock_sample_repo.get_by_novel.return_value = samples

        result = service.maybe_recompute(novel_id)

        assert result is False
        mock_sample_repo.get_by_novel.assert_called_once_with(novel_id, None)
        mock_fingerprint_repo.upsert.assert_not_called()

    def test_maybe_recompute_with_pov_character(
        self, service, mock_sample_repo, mock_fingerprint_repo
    ):
        """Test recompute with POV character ID."""
        novel_id = "novel-123"
        pov_character_id = "char-456"
        samples = [{"content": f"样本{i}。"} for i in range(10)]
        mock_sample_repo.get_by_novel.return_value = samples

        result = service.maybe_recompute(novel_id, pov_character_id)

        assert result is True
        mock_sample_repo.get_by_novel.assert_called_once_with(
            novel_id, pov_character_id
        )
        mock_fingerprint_repo.upsert.assert_called_once()
        call_args = mock_fingerprint_repo.upsert.call_args
        assert call_args[0][2] == pov_character_id

    def test_maybe_recompute_only_at_multiples_of_threshold(
        self, service, mock_sample_repo, mock_fingerprint_repo
    ):
        """Test that recompute only triggers at exact multiples of threshold."""
        novel_id = "novel-123"

        # Test at 15 samples (not a multiple of 10)
        samples = [{"content": f"样本{i}。"} for i in range(15)]
        mock_sample_repo.get_by_novel.return_value = samples

        result = service.maybe_recompute(novel_id)

        assert result is False
        mock_fingerprint_repo.upsert.assert_not_called()

        # Test at 20 samples (multiple of 10)
        samples = [{"content": f"样本{i}。"} for i in range(20)]
        mock_sample_repo.get_by_novel.return_value = samples

        result = service.maybe_recompute(novel_id)

        assert result is True
        mock_fingerprint_repo.upsert.assert_called_once()
