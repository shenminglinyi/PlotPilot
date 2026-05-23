from __future__ import annotations

from dataclasses import dataclass, field

from application.memory.services.character_projection_service import CharacterProjectionService
from application.memory.services.legacy_memory_importer import LegacyMemoryImporter
from application.memory.services.narrative_memory_service import NarrativeMemoryService
from domain.novel.value_objects.character_state import CharacterState, EmotionalArcNode, Motivation, Scar
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_character_state_repository import SqliteCharacterStateRepository
from infrastructure.persistence.database.sqlite_memory_repository import SqliteNarrativeMemoryRepository


@dataclass
class _CID:
    value: str


@dataclass
class _Char:
    id: str
    name: str
    novel_id: str = "n1"
    description: str = ""
    core_belief: str = ""
    moral_taboos: list[str] = field(default_factory=list)
    voice_profile: dict = field(default_factory=dict)
    public_profile: str = ""
    hidden_profile: str = ""
    active_wounds: list[dict] = field(default_factory=list)
    mental_state: str = ""
    mental_state_reason: str = ""
    verbal_tic: str = ""
    idle_behavior: str = ""

    @property
    def character_id(self):
        return _CID(self.id)


class _UnifiedCharacterRepo:
    def __init__(self, chars):
        self.chars = {c.id: c for c in chars}

    def get(self, character_id):
        return self.chars.get(character_id.value)


def _memory_service(tmp_path):
    db = DatabaseConnection(str(tmp_path / "memory.db"))
    return db, NarrativeMemoryService(SqliteNarrativeMemoryRepository(db))


def test_memory_atom_repository_is_idempotent_and_status_mutates(tmp_path):
    _db, svc = _memory_service(tmp_path)

    first = svc.remember(
        "n1", "c1", "state", {"summary": "动摇"}, source="chapter_extract",
        chapter_number=8, text_span="动摇", status="candidate",
    )
    second = svc.remember(
        "n1", "c1", "state", {"summary": "动摇加深"}, source="chapter_extract",
        chapter_number=8, text_span="动摇", status="candidate",
    )

    assert first.id == second.id
    atoms = svc.atoms_for_entity("n1", "c1")
    assert len(atoms) == 1
    assert atoms[0]["payload"]["summary"] == "动摇加深"

    updated = svc.update_status("n1", first.id, "confirmed", action="confirm")
    assert updated is not None
    assert updated.status == "confirmed"


def test_legacy_importer_converts_character_state(tmp_path):
    _db, svc = _memory_service(tmp_path)
    state = CharacterState(character_id="c1", novel_id="n1", current_state_summary="冷硬紧绷", last_updated_chapter=8)
    state.add_scar(Scar(source_event="同门质问誓言", source_chapter=8, impact="对宗门信任动摇", sensitivity_tags=["宗门"]))
    state.add_motivation(Motivation(description="查明宗门命令是否公正", source_event="同门之死", source_chapter=8, priority=8))
    state.add_emotional_arc_node(EmotionalArcNode(chapter=8, emotion="冷硬紧绷", trigger="处决同门", intensity=7))

    LegacyMemoryImporter(svc).import_character_state("n1", "c1", state, name="谷梁卿羽")

    atoms = svc.atoms_for_entity("n1", "c1")
    assert {a["memory_type"] for a in atoms} >= {"scar", "motivation", "emotion", "state"}
    assert all(a["status"] == "confirmed" for a in atoms)


def test_character_projection_reduces_legacy_state_and_compiles_locks(tmp_path):
    db, svc = _memory_service(tmp_path)
    db.execute(
        "INSERT INTO novels (id, title, slug) VALUES (?, ?, ?)",
        ("n1", "测试小说", "n1"),
    )
    db.get_connection().commit()
    state_repo = SqliteCharacterStateRepository(db)
    state = CharacterState(character_id="c1", novel_id="n1", current_state_summary="冷硬紧绷", last_updated_chapter=8)
    state.add_motivation(Motivation(description="查明宗门命令是否公正", source_event="同门之死", source_chapter=8, priority=8))
    state_repo.save(state)

    projection = CharacterProjectionService(
        memory_service=svc,
        unified_character_repository=_UnifiedCharacterRepo([
            _Char(
                "c1",
                "谷梁卿羽",
                core_belief="律法必须公正执行",
                moral_taboos=["绝不对已投降者下杀手"],
                voice_profile={"style": "冷峻简洁"},
            )
        ]),
        character_state_repository=state_repo,
    ).get_projection("n1", "c1")

    assert projection["current_state"]["summary"] == "冷硬紧绷"
    assert projection["active_motivations"][0]["description"] == "查明宗门命令是否公正"
    assert "核心信念" in projection["context_locks"]["t0"]
    assert "冷硬紧绷" in projection["context_locks"]["t1"]
