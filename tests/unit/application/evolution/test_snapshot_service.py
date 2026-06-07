from application.evolution.services.snapshot_service import EvolutionSnapshotService
from domain.evolution.models import ChapterEvolutionSnapshot, EvolutionAction, EvolutionState


class Repo:
    def __init__(self, existing=None, previous=None):
        self.existing = existing
        self.previous = previous
        self.saved = None
        self.stale_from = None

    def get_latest_active_before(self, novel_id, branch_id, chapter_number):
        return self.previous

    def get_by_chapter(self, novel_id, branch_id, chapter_number):
        return self.existing

    def mark_stale_from(self, novel_id, branch_id, chapter_number):
        self.stale_from = chapter_number
        return 1

    def save(self, snapshot):
        self.saved = snapshot


class Extractor:
    def extract(self, novel_id, chapter_number, content, evidence=None):
        return [
            EvolutionAction(
                action_id="a1",
                type="SET_CHARACTER_STATUS",
                payload={"character_id": "char-001", "status": "alive"},
            )
        ]


def test_snapshot_service_replays_legacy_overrides():
    existing = ChapterEvolutionSnapshot(
        snapshot_id="old",
        novel_id="n1",
        branch_id="main",
        chapter_number=2,
        human_override_patches=[
            {"op": "replace", "path": "/characters/char-001/status", "value": "ambiguous"}
        ],
    )
    repo = Repo(existing=existing)

    snapshot = EvolutionSnapshotService(repo, Extractor()).build_after_chapter_saved(
        "n1", 2, "正文"
    )

    assert repo.stale_from == 2
    assert snapshot.status == "active"
    assert snapshot.ending_state.characters["char-001"]["status"] == "ambiguous"
    assert snapshot.human_override_patches == existing.human_override_patches


def test_snapshot_service_blocks_on_patch_conflict():
    existing = ChapterEvolutionSnapshot(
        snapshot_id="old",
        novel_id="n1",
        branch_id="main",
        chapter_number=2,
        human_override_patches=[
            {"op": "replace", "path": "/characters/missing/status", "value": "dead"}
        ],
    )
    repo = Repo(existing=existing)

    snapshot = EvolutionSnapshotService(repo, Extractor()).build_after_chapter_saved(
        "n1", 2, "正文"
    )

    assert snapshot.status == "blocked"
    assert snapshot.conflicts[0]["conflict_type"] == "PATCH_CONFLICT"
