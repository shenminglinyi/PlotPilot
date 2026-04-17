from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from domain.novel.entities.novel import AutopilotStatus, Novel, NovelStage
from domain.novel.value_objects.novel_id import NovelId
from interfaces.api.v1.engine import autopilot_routes


class _FakeNovelRepo:
    def __init__(self, novel):
        self.novel = novel
        self.saved = []

    def get_by_id(self, _novel_id):
        return self.novel

    def save(self, novel):
        self.saved.append((novel.autopilot_status, novel.current_stage))


class _FakeChapterRepo:
    def __init__(self, chapters):
        self._chapters = chapters

    def list_by_novel(self, _novel_id):
        return list(self._chapters)


def _build_client(monkeypatch, novel, chapters, has_current_act_chapters=True):
    monkeypatch.setattr(
        autopilot_routes,
        "get_novel_repository",
        lambda: _FakeNovelRepo(novel),
    )
    monkeypatch.setattr(
        autopilot_routes,
        "get_chapter_repository",
        lambda: _FakeChapterRepo(chapters),
    )
    monkeypatch.setattr(
        autopilot_routes,
        "_has_chapter_nodes_under_current_act",
        lambda *_args, **_kwargs: has_current_act_chapters,
    )

    app = FastAPI()
    app.include_router(autopilot_routes.router, prefix="/api/v1")
    return TestClient(app)


def test_start_autopilot_recovers_incomplete_completed_novel(monkeypatch):
    novel = Novel(
        id=NovelId("test-novel"),
        title="Test Novel",
        author="Tester",
        target_chapters=3,
        autopilot_status=AutopilotStatus.STOPPED,
        current_stage=NovelStage.COMPLETED,
        current_act=0,
    )
    chapters = [SimpleNamespace(status=SimpleNamespace(value="completed"))]
    client = _build_client(monkeypatch, novel, chapters, has_current_act_chapters=True)

    response = client.post("/api/v1/autopilot/test-novel/start", json={"max_auto_chapters": 5})

    assert response.status_code == 200
    assert response.json()["current_stage"] == "writing"
    assert novel.autopilot_status == AutopilotStatus.RUNNING
    assert novel.current_stage == NovelStage.WRITING


def test_start_autopilot_rejects_truly_completed_novel(monkeypatch):
    novel = Novel(
        id=NovelId("done-novel"),
        title="Done Novel",
        author="Tester",
        target_chapters=3,
        autopilot_status=AutopilotStatus.STOPPED,
        current_stage=NovelStage.COMPLETED,
        current_act=0,
    )
    chapters = [
        SimpleNamespace(status=SimpleNamespace(value="completed")),
        SimpleNamespace(status=SimpleNamespace(value="completed")),
        SimpleNamespace(status=SimpleNamespace(value="completed")),
    ]
    client = _build_client(monkeypatch, novel, chapters, has_current_act_chapters=True)

    response = client.post("/api/v1/autopilot/done-novel/start", json={"max_auto_chapters": 5})

    assert response.status_code == 400
    assert "已完成" in response.json()["detail"]
    assert novel.autopilot_status == AutopilotStatus.STOPPED
    assert novel.current_stage == NovelStage.COMPLETED
