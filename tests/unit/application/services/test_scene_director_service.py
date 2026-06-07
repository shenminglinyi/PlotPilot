"""SceneDirectorService 单元测试"""
import pytest
from unittest.mock import AsyncMock, Mock

from application.dtos.scene_director_dto import SceneDirectorAnalysis
from application.services.scene_director_service import SceneDirectorService
from domain.ai.services.llm_service import GenerationConfig, GenerationResult
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage


@pytest.mark.asyncio
async def test_analyze_outline_parses_json():
    llm = Mock()
    llm.generate = AsyncMock(
        return_value=GenerationResult(
            content='{"characters":["A"],"locations":[],"action_types":[],"trigger_keywords":[],"emotional_state":"calm","pov":"A"}',
            token_usage=TokenUsage(input_tokens=1, output_tokens=1),
        )
    )
    svc = SceneDirectorService(llm_service=llm)
    result = await svc.analyze(chapter_number=1, outline="A walks")
    assert isinstance(result, SceneDirectorAnalysis)
    assert result.characters == ["A"]
    assert result.locations == []
    assert result.action_types == []
    assert result.trigger_keywords == []
    assert result.emotional_state == "calm"
    assert result.pov == "A"
    llm.generate.assert_called_once()


@pytest.mark.asyncio
async def test_analyze_uses_injected_model():
    llm = Mock()
    llm.generate = AsyncMock(
        return_value=GenerationResult(
            content='{"characters":[]}',
            token_usage=TokenUsage(input_tokens=1, output_tokens=1),
        )
    )
    svc = SceneDirectorService(llm_service=llm, model="system-test-model")

    await svc.analyze(chapter_number=1, outline="A walks")

    config = llm.generate.call_args[0][1]
    assert isinstance(config, GenerationConfig)
    assert config.model == "system-test-model"


@pytest.mark.asyncio
async def test_analyze_returns_empty_on_invalid_json():
    """Test that invalid JSON returns empty SceneDirectorAnalysis."""
    llm = Mock()
    llm.generate = AsyncMock(
        return_value=GenerationResult(
            content='{"invalid json',
            token_usage=TokenUsage(input_tokens=1, output_tokens=1),
        )
    )
    svc = SceneDirectorService(llm_service=llm)
    result = await svc.analyze(chapter_number=1, outline="A walks")
    assert isinstance(result, SceneDirectorAnalysis)
    assert result.characters == []
    assert result.locations == []
    assert result.action_types == []
    assert result.trigger_keywords == []
    assert result.emotional_state == ""
    assert result.pov is None


@pytest.mark.asyncio
async def test_analyze_returns_empty_on_non_dict_json():
    """Test that non-dict JSON (e.g., array) returns empty SceneDirectorAnalysis."""
    llm = Mock()
    llm.generate = AsyncMock(
        return_value=GenerationResult(
            content='["not", "a", "dict"]',
            token_usage=TokenUsage(input_tokens=1, output_tokens=1),
        )
    )
    svc = SceneDirectorService(llm_service=llm)
    result = await svc.analyze(chapter_number=1, outline="A walks")
    assert isinstance(result, SceneDirectorAnalysis)
    assert result.characters == []


@pytest.mark.asyncio
async def test_analyze_handles_missing_fields():
    """Test that missing fields are handled gracefully."""
    llm = Mock()
    llm.generate = AsyncMock(
        return_value=GenerationResult(
            content='{"characters":["A"]}',
            token_usage=TokenUsage(input_tokens=1, output_tokens=1),
        )
    )
    svc = SceneDirectorService(llm_service=llm)
    result = await svc.analyze(chapter_number=1, outline="A walks")
    assert result.characters == ["A"]
    assert result.locations == []
    assert result.action_types == []
    assert result.trigger_keywords == []
    assert result.emotional_state == ""
    assert result.pov is None


@pytest.mark.asyncio
async def test_analyze_handles_partial_fields():
    """Test that partial/incomplete fields are handled gracefully."""
    llm = Mock()
    llm.generate = AsyncMock(
        return_value=GenerationResult(
            content='{"characters":["A","B"],"locations":["room"],"emotional_state":"tense"}',
            token_usage=TokenUsage(input_tokens=1, output_tokens=1),
        )
    )
    svc = SceneDirectorService(llm_service=llm)
    result = await svc.analyze(chapter_number=1, outline="A and B in room")
    assert result.characters == ["A", "B"]
    assert result.locations == ["room"]
    assert result.action_types == []
    assert result.trigger_keywords == []
    assert result.emotional_state == "tense"
    assert result.pov is None


def test_coerce_with_non_list_values():
    """Test _coerce handles non-list values by converting to single-item list."""
    llm = Mock()
    svc = SceneDirectorService(llm_service=llm)
    data = {
        "characters": "single_char",
        "locations": ["loc1", "loc2"],
        "action_types": None,
        "trigger_keywords": ["kw1"],
        "emotional_state": "calm",
        "pov": "single_char",
    }
    result = svc._coerce(data)
    assert result.characters == ["single_char"]
    assert result.locations == ["loc1", "loc2"]
    assert result.action_types == []
    assert result.trigger_keywords == ["kw1"]
    assert result.emotional_state == "calm"
    assert result.pov == "single_char"


def test_coerce_with_null_values_in_list():
    """Test _coerce filters out None values from lists."""
    llm = Mock()
    svc = SceneDirectorService(llm_service=llm)
    data = {
        "characters": ["A", None, "B"],
        "locations": [None, "room"],
        "action_types": [],
        "trigger_keywords": ["kw1", None, "kw2"],
        "emotional_state": "calm",
        "pov": None,
    }
    result = svc._coerce(data)
    assert result.characters == ["A", "B"]
    assert result.locations == ["room"]
    assert result.action_types == []
    assert result.trigger_keywords == ["kw1", "kw2"]
    assert result.pov is None


def test_coerce_with_empty_string_pov():
    """Test _coerce converts empty string pov to None."""
    llm = Mock()
    svc = SceneDirectorService(llm_service=llm)
    data = {
        "characters": [],
        "locations": [],
        "action_types": [],
        "trigger_keywords": [],
        "emotional_state": "",
        "pov": "   ",
    }
    result = svc._coerce(data)
    assert result.pov is None


def test_coerce_with_empty_string_emotional_state():
    """Test _coerce handles empty emotional_state consistently."""
    llm = Mock()
    svc = SceneDirectorService(llm_service=llm)
    data = {
        "characters": [],
        "locations": [],
        "action_types": [],
        "trigger_keywords": [],
        "emotional_state": "   ",
        "pov": None,
    }
    result = svc._coerce(data)
    assert result.emotional_state == ""


def test_coerce_with_none_emotional_state():
    """Test _coerce converts None emotional_state to empty string."""
    llm = Mock()
    svc = SceneDirectorService(llm_service=llm)
    data = {
        "characters": [],
        "locations": [],
        "action_types": [],
        "trigger_keywords": [],
        "emotional_state": None,
        "pov": None,
    }
    result = svc._coerce(data)
    assert result.emotional_state == ""


def test_coerce_raises_on_non_dict():
    """Test _coerce raises TypeError when data is not a dict."""
    llm = Mock()
    svc = SceneDirectorService(llm_service=llm)
    with pytest.raises(TypeError, match="Expected dict"):
        svc._coerce(["not", "a", "dict"])


def test_coerce_raises_on_string():
    """Test _coerce raises TypeError when data is a string."""
    llm = Mock()
    svc = SceneDirectorService(llm_service=llm)
    with pytest.raises(TypeError, match="Expected dict"):
        svc._coerce("not a dict")


def test_coerce_raises_on_none():
    """Test _coerce raises TypeError when data is None."""
    llm = Mock()
    svc = SceneDirectorService(llm_service=llm)
    with pytest.raises(TypeError, match="Expected dict"):
        svc._coerce(None)


@pytest.mark.asyncio
async def test_analyze_includes_performance_notes():
    """Test that performance_notes field is parsed when present in LLM response."""
    llm = Mock()
    llm.generate = AsyncMock(
        return_value=GenerationResult(
            content='{"characters":["A"],"locations":[],"action_types":[],"trigger_keywords":[],"emotional_state":"tense","pov":"A","performance_notes":["eyes flicker","clenches fist"]}',
            token_usage=TokenUsage(input_tokens=1, output_tokens=1),
        )
    )
    svc = SceneDirectorService(llm_service=llm)
    result = await svc.analyze(chapter_number=1, outline="A walks nervously")
    assert isinstance(result, SceneDirectorAnalysis)
    assert result.performance_notes == ["eyes flicker", "clenches fist"]


@pytest.mark.asyncio
async def test_analyze_handles_missing_performance_notes():
    """Test that missing performance_notes field defaults to None for backward compatibility."""
    llm = Mock()
    llm.generate = AsyncMock(
        return_value=GenerationResult(
            content='{"characters":["A"],"locations":[],"action_types":[],"trigger_keywords":[],"emotional_state":"calm","pov":"A"}',
            token_usage=TokenUsage(input_tokens=1, output_tokens=1),
        )
    )
    svc = SceneDirectorService(llm_service=llm)
    result = await svc.analyze(chapter_number=1, outline="A walks")
    assert result.performance_notes is None


def test_performance_notes_is_list_of_strings():
    """Test that performance_notes is correctly parsed as a list of strings."""
    llm = Mock()
    svc = SceneDirectorService(llm_service=llm)
    data = {
        "characters": ["A"],
        "locations": [],
        "action_types": [],
        "trigger_keywords": [],
        "emotional_state": "nervous",
        "pov": "A",
        "performance_notes": ["glances around", "fidgets with hands", "voice trembles"],
    }
    result = svc._coerce(data)
    assert isinstance(result.performance_notes, list)
    assert all(isinstance(note, str) for note in result.performance_notes)
    assert result.performance_notes == ["glances around", "fidgets with hands", "voice trembles"]


@pytest.mark.asyncio
async def test_analyze_parses_action_transition_graph():
    payload = (
        '{"characters":["艾伦"],"locations":[],"action_types":[],"trigger_keywords":[],"emotional_state":"tense","pov":"艾伦",'
        '"atg":{"nodes":[{"location_id":"府邸_走廊","initial_props":["火把"],"is_entry_point":true}],'
        '"transitions":[{"source_location":"府邸_走廊","target_location":"府邸_房间","required_action":"推门","trigger_characters":["艾伦"]}],'
        '"visit_sequence":["府邸_走廊","府邸_房间"]}}'
    )
    llm = Mock()
    llm.generate = AsyncMock(
        return_value=GenerationResult(
            content=payload,
            token_usage=TokenUsage(input_tokens=1, output_tokens=1),
        )
    )
    svc = SceneDirectorService(llm_service=llm)
    result = await svc.analyze(chapter_number=1, outline="大纲")
    assert result.action_transition_graph is not None
    assert result.action_transition_graph.visit_sequence == ["府邸_走廊", "府邸_房间"]
    dom = result.action_transition_graph.to_domain()
    assert dom.get_transition_path("府邸_走廊", "府邸_房间") is not None

