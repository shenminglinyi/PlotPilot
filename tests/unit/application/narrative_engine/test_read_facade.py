"""NarrativeEngineReadFacade dependency boundary tests."""
from types import SimpleNamespace

import pytest

from application.narrative_engine.read_facade import NarrativeEngineReadFacade


class _QueryService:
    def get_workbench_context(self, novel_id):
        return SimpleNamespace(
            to_dict=lambda: {
                "storylines": [{"id": "main"}],
                "plot_arc": {"phase": "opening"},
                "confluence_points": [],
                "chronicles": {"rows": [], "max_chapter_in_book": 1, "note": ""},
                "chapters_digest": [],
                "foreshadow_ledger": [1, 2],
            }
        )


class _EvolutionRepo:
    def get_latest_active(self, novel_id, stream):
        return None

    def count_by_status(self, novel_id, stream):
        return {"active": 1, "stale": 2, "blocked": 3}


class _BibleService:
    def get_bible_by_novel(self, novel_id):
        return SimpleNamespace(
            characters=[
                SimpleNamespace(
                    id="c1",
                    name="林照",
                    mental_state="ALERT",
                    verbal_tic="且慢",
                    idle_behavior="按剑",
                )
            ]
        )


class _SandboxDialogueService:
    def get_dialogue_whitelist(self, novel_id):
        return SimpleNamespace(
            total_count=2,
            dialogues=[
                SimpleNamespace(speaker="林照"),
                SimpleNamespace(speaker="旁人"),
            ],
        )


def test_story_evolution_read_model_uses_injected_dependencies():
    facade = NarrativeEngineReadFacade(
        query_service=_QueryService(),
        story_phase_resolver=lambda novel_id: {"phase": "opening"},
        evolution_repository_factory=lambda: _EvolutionRepo(),
        context_presenter_factory=lambda: SimpleNamespace(present=lambda state, max_lines: "summary"),
    )

    result = facade.get_story_evolution_read_model("novel-1")

    assert result["novel_id"] == "novel-1"
    assert result["life_cycle"] == {"phase": "opening"}
    assert result["subtext_surface"]["foreshadow_ledger_count"] == 2
    assert result["evolution_surface"]["counts"] == {"active": 1, "stale": 2, "blocked": 3}


def test_persona_voice_read_model_uses_injected_services():
    facade = NarrativeEngineReadFacade(
        bible_service=_BibleService(),
        sandbox_dialogue_service=_SandboxDialogueService(),
    )

    result = facade.get_persona_voice_read_model("novel-1", "c1")

    assert result["character_name"] == "林照"
    assert result["voice_anchor"]["verbal_tic"] == "且慢"
    assert result["dialogue_corpus"] == {"total_lines": 2, "lines_as_speaker": 1}


def test_persona_voice_requires_injected_services():
    facade = NarrativeEngineReadFacade()

    with pytest.raises(RuntimeError):
        facade.get_persona_voice_read_model("novel-1", "c1")
