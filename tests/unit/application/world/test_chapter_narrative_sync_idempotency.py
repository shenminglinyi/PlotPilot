from domain.novel.entities.foreshadowing_registry import ForeshadowingRegistry

from application.world.services.chapter_narrative_sync import (
    persist_bundle_triples_and_foreshadows,
    persist_causal_edges,
    persist_character_end_states,
    persist_character_mutations,
    update_narrative_debts,
)
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_narrative_event_repository import (
    SqliteNarrativeEventRepository,
)


class _KnowledgeRepo:
    def __init__(self):
        self.rows = {}

    def save_triple(self, novel_id, row):
        self.rows[row["id"]] = dict(row, novel_id=novel_id)


class _TripleRepo:
    def __init__(self):
        self._kr = _KnowledgeRepo()


class _ForeshadowRepo:
    def __init__(self):
        self.registry = None

    def get_by_novel_id(self, novel_id):
        if self.registry is None:
            self.registry = ForeshadowingRegistry(id=f"fr-{novel_id.value}", novel_id=novel_id)
        return self.registry

    def save(self, registry):
        self.registry = registry


class _CausalRepo:
    def __init__(self):
        self.edges = {}

    def save(self, edge):
        self.edges[edge.id] = edge

    def get_unresolved(self, novel_id):
        return [edge for edge in self.edges.values() if edge.novel_id == novel_id and not edge.is_resolved]

    def get_by_novel(self, novel_id):
        return [edge for edge in self.edges.values() if edge.novel_id == novel_id]

    def resolve(self, edge_id, chapter):
        self.edges[edge_id] = self.edges[edge_id].resolve(chapter)


class _CharacterStateRepo:
    def __init__(self):
        self.states = {}

    def get(self, character_id, novel_id):
        return self.states.get((novel_id, character_id))

    def save(self, state):
        self.states[(state.novel_id, state.character_id)] = state


class _DebtRepo:
    def __init__(self):
        self.debts = {}

    def save(self, debt):
        self.debts[debt.id] = debt

    def get_by_type(self, novel_id, debt_type):
        return [
            debt
            for debt in self.debts.values()
            if debt.novel_id == novel_id and debt.debt_type == debt_type and not debt.resolved_chapter
        ]

    def resolve(self, debt_id, chapter):
        self.debts[debt_id] = self.debts[debt_id].resolve(chapter)

    def mark_overdue_batch(self, novel_id, chapter_number):
        return 0


def test_chapter_narrative_artifacts_are_idempotent_across_audit_retries():
    bundle = {
        "relation_triples": [{"data": {"subject": "林澈", "predicate": "持有", "object": "铜铃"}, "status": "pending"}],
        "foreshadow_hints": [{"data": {"description": "铜铃将在雨夜响起", "suggested_resolve_offset": 3, "importance": "high"}}],
        "causal_edges": [{"data": {"source_event": "铜铃丢失", "target_event": "林澈追查真相", "causal_type": "motivates", "strength": 0.8}}],
        "character_mutations": [{"data": {"character_name": "林澈", "mutation_type": "motivation", "source_event": "铜铃丢失", "impact_or_description": "追查真相", "sensitivity_tags_or_priority": 8}}],
        "character_states": [{"character_name": "林澈", "mental_state": "警觉"}],
    }
    triple_repo = _TripleRepo()
    foreshadow_repo = _ForeshadowRepo()
    causal_repo = _CausalRepo()
    state_repo = _CharacterStateRepo()
    debt_repo = _DebtRepo()

    for _ in range(2):
        persist_bundle_triples_and_foreshadows("novel-1", 4, bundle, triple_repo, foreshadow_repo)
        persist_causal_edges("novel-1", 4, bundle, causal_repo)
        persist_character_mutations("novel-1", 4, bundle, state_repo)
        persist_character_end_states("novel-1", 4, bundle, state_repo)
        update_narrative_debts("novel-1", 4, bundle, debt_repo, causal_repo)

    assert len(triple_repo._kr.rows) == 1
    assert len(foreshadow_repo.registry.foreshadowings) == 1
    assert len(causal_repo.edges) == 1
    assert len(debt_repo.debts) == 2
    state = state_repo.states[("novel-1", "林澈")]
    assert len(state.motivations) == 1
    assert len(state.emotional_arc) == 1


def test_narrative_event_upsert_uses_stable_event_id(tmp_path):
    db = DatabaseConnection(str(tmp_path / "events.db"))
    db.execute("INSERT INTO novels (id, title, slug) VALUES ('novel-1', 'Novel', 'novel-1')")
    repo = SqliteNarrativeEventRepository(db)

    for _ in range(2):
        repo.upsert_event(
            event_id="event-stable",
            novel_id="novel-1",
            chapter_number=2,
            event_summary="林澈: 铜铃响了",
            mutations=[],
            tags=["对话:林澈"],
        )

    rows = db.fetch_all("SELECT * FROM narrative_events WHERE novel_id = ?", ("novel-1",))
    assert len(rows) == 1
    assert rows[0]["event_id"] == "event-stable"
