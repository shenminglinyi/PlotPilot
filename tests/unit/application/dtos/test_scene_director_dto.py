import pytest
from pydantic import ValidationError

from application.dtos.scene_director_dto import (
    SceneDirectorAnalysis,
    SceneDirectorAnalyzeRequest,
    SceneDirectorAnalyzeResponse,
    ContextRetrieveRequest,
    coerce_scene_director,
    validate_outline_not_empty,
)


def test_coerce_scene_director_none():
    assert coerce_scene_director(None) is None


def test_coerce_scene_director_passes_dict_through():
    d = {"characters": ["a"], "locations": []}
    assert coerce_scene_director(d) is d


def test_coerce_scene_director_from_analysis():
    m = SceneDirectorAnalysis(characters=["李明"], pov="李明")
    out = coerce_scene_director(m)
    assert out["characters"] == ["李明"]
    assert out["pov"] == "李明"


def test_coerce_scene_director_response_subclass():
    r = SceneDirectorAnalyzeResponse(characters=["a"])
    out = coerce_scene_director(r)
    assert out["characters"] == ["a"]


def test_coerce_scene_director_rejects_bad_type():
    with pytest.raises(TypeError):
        coerce_scene_director("invalid")  # type: ignore[arg-type]


def test_validate_outline_not_empty_rejects_empty_string():
    """Test that validate_outline_not_empty rejects empty strings."""
    with pytest.raises(ValueError, match="outline cannot be empty or whitespace only"):
        validate_outline_not_empty("")


def test_validate_outline_not_empty_rejects_whitespace():
    """Test that validate_outline_not_empty rejects whitespace-only strings."""
    with pytest.raises(ValueError, match="outline cannot be empty or whitespace only"):
        validate_outline_not_empty("   \n\t  ")


def test_validate_outline_not_empty_accepts_valid_outline():
    """Test that validate_outline_not_empty accepts valid outlines."""
    result = validate_outline_not_empty("valid outline")
    assert result == "valid outline"


def test_scene_director_analysis_accepts_valid_payload():
    m = SceneDirectorAnalysis(
        characters=["李明"],
        locations=["废弃工厂"],
        action_types=["combat"],
        trigger_keywords=["武器"],
        emotional_state="tense",
        pov="李明",
    )
    assert m.pov == "李明"


def test_scene_director_analysis_has_default_values():
    """Test that SceneDirectorAnalysis provides sensible defaults."""
    m = SceneDirectorAnalysis()
    assert m.characters == []
    assert m.locations == []
    assert m.action_types == []
    assert m.trigger_keywords == []
    assert m.emotional_state == ""
    assert m.pov is None


def test_scene_director_analyze_response_inherits_from_analysis():
    """Test that SceneDirectorAnalyzeResponse inherits from SceneDirectorAnalysis."""
    response = SceneDirectorAnalyzeResponse(
        characters=["李明"],
        locations=["废弃工厂"],
        action_types=["combat"],
        trigger_keywords=["武器"],
        emotional_state="tense",
        pov="李明",
    )
    assert isinstance(response, SceneDirectorAnalysis)
    assert response.pov == "李明"
    assert response.characters == ["李明"]


def test_scene_director_analyze_response_has_default_values():
    """Test that SceneDirectorAnalyzeResponse inherits default values."""
    response = SceneDirectorAnalyzeResponse()
    assert response.characters == []
    assert response.locations == []
    assert response.action_types == []
    assert response.trigger_keywords == []
    assert response.emotional_state == ""
    assert response.pov is None


def test_outline_request_rejects_empty_outline():
    with pytest.raises(ValidationError):
        SceneDirectorAnalyzeRequest(chapter_number=1, outline="   ")


def test_outline_request_rejects_zero_chapter_number():
    """Test that chapter_number must be >= 1."""
    with pytest.raises(ValidationError):
        SceneDirectorAnalyzeRequest(chapter_number=0, outline="valid outline")


def test_outline_request_rejects_negative_chapter_number():
    """Test that chapter_number must be positive."""
    with pytest.raises(ValidationError):
        SceneDirectorAnalyzeRequest(chapter_number=-1, outline="valid outline")


def test_outline_request_accepts_valid_chapter_number():
    """Test that chapter_number >= 1 is accepted."""
    req = SceneDirectorAnalyzeRequest(chapter_number=1, outline="valid outline")
    assert req.chapter_number == 1

    req = SceneDirectorAnalyzeRequest(chapter_number=100, outline="valid outline")
    assert req.chapter_number == 100


def test_context_retrieve_request_rejects_empty_outline():
    """Test that ContextRetrieveRequest rejects empty outline."""
    with pytest.raises(ValidationError):
        ContextRetrieveRequest(chapter_number=1, outline="   ")


def test_context_retrieve_request_uses_shared_validator():
    """Test that ContextRetrieveRequest uses the shared outline validator."""
    # Valid outline should work
    req = ContextRetrieveRequest(chapter_number=1, outline="valid outline")
    assert req.outline == "valid outline"

    # Invalid outline should fail
    with pytest.raises(ValidationError):
        ContextRetrieveRequest(chapter_number=1, outline="")

