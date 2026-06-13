from types import SimpleNamespace

from domain.novel.entities.novel import AutopilotStatus, NovelStage
from interfaces.api.v1.engine import autopilot_routes


class _Repo:
    def __init__(self):
        self.patches = []

    def patch(self, novel_id, **fields):
        self.patches.append((novel_id.value, fields))


def test_resume_persist_keeps_explicit_next_stage(monkeypatch):
    repo = _Repo()

    monkeypatch.setattr(
        autopilot_routes,
        "_persist_autopilot_running_sync",
        lambda *args, **kwargs: {"decision": SimpleNamespace(next_stage="paused_for_review"), "run_epoch": 7},
    )
    monkeypatch.setattr(autopilot_routes, "get_novel_repository", lambda: repo)

    result = autopilot_routes._persist_autopilot_resume_sync(
        "novel-1",
        next_stage=NovelStage.ACT_PLANNING.value,
        current_act=0,
        max_auto_chapters=9999,
        target_chapters=150,
        target_words_per_chapter=2000,
    )

    assert result["run_epoch"] == 7
    assert len(repo.patches) == 1
    novel_id, fields = repo.patches[0]
    assert novel_id == "novel-1"
    assert fields["autopilot_status"] == AutopilotStatus.RUNNING
    assert fields["current_stage"] == NovelStage.ACT_PLANNING
    assert fields["current_act"] == 0
    assert fields["last_stable_stage"] == "act_planning"
