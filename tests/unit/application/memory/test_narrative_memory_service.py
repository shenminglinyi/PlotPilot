from domain.memory.entities import MemoryAtom, MemoryProjection, NarrativeEntity
from application.memory.services.narrative_memory_service import NarrativeMemoryService


class FakeMemoryRepository:
    def __init__(self):
        self.entities = {}
        self.atoms = {}
        self.projections = {}
        self.status_updates = []

    def upsert_entity(self, entity):
        self.entities[entity.id] = entity
        return entity

    def upsert_atom(self, atom):
        self.atoms[atom.id] = atom
        return atom

    def get_atoms_for_entity(self, novel_id, entity_id):
        return [
            atom
            for atom in self.atoms.values()
            if atom.novel_id == novel_id and atom.entity_id == entity_id
        ]

    def get_candidates_for_chapter(self, novel_id, chapter_number):
        return [
            atom
            for atom in self.atoms.values()
            if atom.novel_id == novel_id
            and atom.chapter_number == chapter_number
            and atom.status == "candidate"
        ]

    def update_atom_status(self, novel_id, atom_id, status, *, action, note=""):
        atom = self.atoms.get(atom_id)
        if not atom or atom.novel_id != novel_id:
            return None
        atom.status = status
        self.status_updates.append((atom_id, action, note))
        return atom

    def save_projection(self, projection):
        self.projections[(projection.novel_id, projection.entity_id, projection.projection_type)] = projection
        return projection

    def get_projection(self, novel_id, entity_id, projection_type="character"):
        return self.projections.get((novel_id, entity_id, projection_type))


def test_memory_service_facade_roundtrip_without_infrastructure_dependency():
    repo = FakeMemoryRepository()
    service = NarrativeMemoryService(repo)

    entity = service.ensure_entity("novel-1", "char-1", canonical_name="阿止")
    atom = service.remember(
        "novel-1",
        "char-1",
        "state",
        {"summary": "怀疑师父隐瞒真相"},
        chapter_number=3,
        text_span="怀疑师父",
    )
    projection = service.save_projection(
        MemoryProjection(
            novel_id="novel-1",
            entity_id="char-1",
            data={"name": "阿止"},
        )
    )

    assert isinstance(entity, NarrativeEntity)
    assert isinstance(atom, MemoryAtom)
    assert service.atoms_for_entity("novel-1", "char-1")[0]["payload"]["summary"] == "怀疑师父隐瞒真相"
    assert service.candidates_for_chapter("novel-1", 3)[0]["id"] == atom.id
    assert service.update_status("novel-1", atom.id, "confirmed", action="confirm", note="ok").status == "confirmed"
    assert service.get_projection("novel-1", "char-1") == projection
