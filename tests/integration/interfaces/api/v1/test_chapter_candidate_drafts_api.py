from fastapi.testclient import TestClient
import uuid

from interfaces.api.dependencies import get_chapter_aftermath_pipeline
from interfaces.main import app


class _FakePipeline:
    def __init__(self):
        self.calls = []

    async def run_after_chapter_saved(self, novel_id: str, chapter_number: int, content: str):
        self.calls.append(
            {
                "novel_id": novel_id,
                "chapter_number": chapter_number,
                "content": content,
            }
        )
        return {
            "drift_alert": False,
            "similarity_score": None,
        }


class TestChapterCandidateDraftsAPI:
    def setup_method(self):
        self.pipeline = _FakePipeline()
        app.dependency_overrides[get_chapter_aftermath_pipeline] = lambda: self.pipeline
        self.client = TestClient(app)

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_create_list_and_accept_candidate_draft(self):
        novel_id = f"test-novel-candidate-api-{uuid.uuid4().hex[:8]}"
        create_novel = self.client.post(
            "/api/v1/novels",
            json={
                "novel_id": novel_id,
                "title": "候选稿 API 测试",
                "author": "测试作者",
                "target_chapters": 12,
                "premise": "测试 premise",
            },
        )
        assert create_novel.status_code == 201

        create_draft = self.client.post(
            f"/api/v1/novels/{novel_id}/chapters/5/candidate-drafts",
            json={
                "source": "kimi",
                "title": "第5章候选",
                "content": "这是通过 Kimi 生成的候选正文。",
                "rationale": "更克制",
                "metadata": {"provider": "kimi"},
            },
        )
        assert create_draft.status_code == 201
        draft = create_draft.json()
        assert draft["status"] == "draft"
        draft_id = draft["id"]

        list_drafts = self.client.get(
            f"/api/v1/novels/{novel_id}/chapters/5/candidate-drafts"
        )
        assert list_drafts.status_code == 200
        assert len(list_drafts.json()) == 1

        accept = self.client.post(
            f"/api/v1/novels/{novel_id}/chapters/5/candidate-drafts/{draft_id}/accept"
        )
        assert accept.status_code == 200
        accepted = accept.json()
        assert accepted["draft"]["status"] == "accepted"
        assert accepted["chapter"]["content"] == "这是通过 Kimi 生成的候选正文。"
        assert accepted["snapshot_id"]

        chapter = self.client.get(f"/api/v1/novels/{novel_id}/chapters/5")
        assert chapter.status_code == 200
        assert chapter.json()["content"] == "这是通过 Kimi 生成的候选正文。"

        assert self.pipeline.calls == [
            {
                "novel_id": novel_id,
                "chapter_number": 5,
                "content": "这是通过 Kimi 生成的候选正文。",
            }
        ]

    def test_list_candidate_drafts_can_filter_by_branch_name(self):
        novel_id = f"test-novel-candidate-branch-{uuid.uuid4().hex[:8]}"
        create_novel = self.client.post(
            "/api/v1/novels",
            json={
                "novel_id": novel_id,
                "title": "候选稿分支测试",
                "author": "测试作者",
                "target_chapters": 12,
                "premise": "测试 premise",
            },
        )
        assert create_novel.status_code == 201

        for branch_name, title in [("main", "主线稿"), ("branch-alt", "分支稿")]:
            create_draft = self.client.post(
                f"/api/v1/novels/{novel_id}/chapters/5/candidate-drafts",
                json={
                    "source": "kimi",
                    "title": title,
                    "content": f"{title}正文",
                    "branch_name": branch_name,
                },
            )
            assert create_draft.status_code == 201

        list_drafts = self.client.get(
            f"/api/v1/novels/{novel_id}/chapters/5/candidate-drafts",
            params={"branch_name": "branch-alt"},
        )
        assert list_drafts.status_code == 200
        assert len(list_drafts.json()) == 1
        assert list_drafts.json()[0]["branch_name"] == "branch-alt"
        assert list_drafts.json()[0]["title"] == "分支稿"
