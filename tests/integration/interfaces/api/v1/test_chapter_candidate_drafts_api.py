from fastapi.testclient import TestClient
import uuid

from domain.ai.services.llm_service import GenerationResult
from domain.ai.value_objects.token_usage import TokenUsage
from interfaces.api.dependencies import (
    get_chapter_aftermath_pipeline,
    get_analysis_llm_service,
    get_llm_provider_factory,
    get_llm_service,
    get_writing_llm_service,
)
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


class _FakeLLMService:
    def __init__(self, content: str):
        self.content = content
        self.calls = []

    async def generate(self, prompt, config):
        self.calls.append({"prompt": prompt, "config": config})
        return GenerationResult(
            content=self.content,
            token_usage=TokenUsage(input_tokens=10, output_tokens=10),
        )

    async def stream_generate(self, prompt, config):
        yield self.content


class _FakeLLMFactory:
    def __init__(self):
        self.requested_profiles = []
        self.writer_service = _FakeLLMService("写作模型 profile 生成的候选正文")
        self.supervisor_service = _FakeLLMService("监督模型检查：建议采纳前补一条关系事件。")

    def create_by_profile_id(self, profile_id: str):
        self.requested_profiles.append(profile_id)
        if profile_id == "supervisor-profile":
            return self.supervisor_service
        return self.writer_service


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

    def test_branch_merge_memory_diff_and_external_task_ledger(self):
        novel_id = f"test-novel-candidate-tools-{uuid.uuid4().hex[:8]}"
        create_novel = self.client.post(
            "/api/v1/novels",
            json={
                "novel_id": novel_id,
                "title": "候选稿工具测试",
                "author": "测试作者",
                "target_chapters": 12,
                "premise": "测试 premise",
            },
        )
        assert create_novel.status_code == 201

        create_draft = self.client.post(
            f"/api/v1/novels/{novel_id}/chapters/5/candidate-drafts",
            json={
                "source": "external-model",
                "title": "分支实验稿",
                "content": "甲和乙关系升温，并埋下一个秘密伏笔。",
                "branch_name": "branch-alt",
                "metadata": {"external_model": "kimi"},
            },
        )
        assert create_draft.status_code == 201
        source_draft = create_draft.json()

        compare = self.client.get(
            f"/api/v1/novels/{novel_id}/chapters/5/candidate-drafts/{source_draft['id']}/compare"
        )
        assert compare.status_code == 200
        assert compare.json()["draft"]["id"] == source_draft["id"]
        assert compare.json()["paragraphs"]

        task = self.client.post(
            f"/api/v1/novels/{novel_id}/external-model-tasks",
            json={
                "id": "task-1",
                "chapter_number": 5,
                "model": "kimi",
                "prompt": "写第5章",
                "candidate_draft_id": source_draft["id"],
                "response_preview": "甲和乙关系升温",
                "status": "imported",
            },
        )
        assert task.status_code == 201
        assert task.json()["id"] == "task-1"

        tasks = self.client.get(
            f"/api/v1/novels/{novel_id}/external-model-tasks",
            params={"chapter_number": 5},
        )
        assert tasks.status_code == 200
        assert len(tasks.json()) == 1

        diff = self.client.get(
            f"/api/v1/novels/{novel_id}/chapters/5/candidate-drafts/branch-memory-diff",
            params={"source_branch": "branch-alt", "target_branch": "main"},
        )
        assert diff.status_code == 200
        assert diff.json()["source_draft_count"] == 1
        assert any(item["label"] == "外部模型稿" for item in diff.json()["memory_impacts"])

        merge = self.client.post(
            f"/api/v1/novels/{novel_id}/chapters/5/candidate-drafts/merge-branch",
            json={"source_branch": "branch-alt", "target_branch": "main"},
        )
        assert merge.status_code == 201
        assert merge.json()["source"] == "branch-merge"
        assert merge.json()["branch_name"] == "main"

        accept = self.client.post(
            f"/api/v1/novels/{novel_id}/chapters/5/candidate-drafts/{source_draft['id']}/accept"
        )
        assert accept.status_code == 200

        accepted_tasks = self.client.get(
            f"/api/v1/novels/{novel_id}/external-model-tasks",
            params={"chapter_number": 5},
        )
        assert accepted_tasks.status_code == 200
        assert accepted_tasks.json()[0]["status"] == "accepted"

    def test_generate_candidate_draft_uses_requested_llm_profile(self):
        novel_id = f"test-novel-direct-model-{uuid.uuid4().hex[:8]}"
        create_novel = self.client.post(
            "/api/v1/novels",
            json={
                "novel_id": novel_id,
                "title": "直连模型测试",
                "author": "测试作者",
                "target_chapters": 12,
                "premise": "测试 premise",
            },
        )
        assert create_novel.status_code == 201

        active_service = _FakeLLMService("全局激活模型正文")
        factory = _FakeLLMFactory()
        app.dependency_overrides[get_llm_service] = lambda: active_service
        app.dependency_overrides[get_llm_provider_factory] = lambda: factory

        response = self.client.post(
            f"/api/v1/novels/{novel_id}/candidate-drafts/generate",
            json={
                "chapter_number": 3,
                "outline": "第三章主角破局。",
                "current_content": "旧稿",
                "branch_name": "main",
                "model_label": "Kimi",
                "llm_profile_id": "writer-profile",
            },
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["draft"]["content"] == "写作模型 profile 生成的候选正文"
        assert payload["draft"]["metadata"]["llm_profile_id"] == "writer-profile"
        assert payload["task"]["model"] == "Kimi"
        assert factory.requested_profiles == ["writer-profile"]

    def test_generate_editorial_polish_candidate_uses_review_actions(self):
        novel_id = f"test-novel-editorial-polish-{uuid.uuid4().hex[:8]}"
        create_novel = self.client.post(
            "/api/v1/novels",
            json={
                "novel_id": novel_id,
                "title": "主编审稿精修测试",
                "author": "测试作者",
                "target_chapters": 12,
                "premise": "测试 premise",
            },
        )
        assert create_novel.status_code == 201

        writing_service = _FakeLLMService("按主编审稿精修后的候选正文")
        app.dependency_overrides[get_writing_llm_service] = lambda: writing_service

        response = self.client.post(
            f"/api/v1/novels/{novel_id}/candidate-drafts/editorial-polish",
            json={
                "chapter_number": 2,
                "outline": "第二章主角继续调查灰卡。",
                "current_content": "旧正文里许照突然出现，黑线发现过程偏散。",
                "branch_name": "editorial",
                "target_word_count": 2500,
                "editorial_review": {
                    "summary": "可优化后使用",
                    "verdict": "可优化后使用",
                    "scores": {
                        "opening": 90,
                        "conflict": 92,
                        "character": 88,
                        "dialogue": 90,
                        "hook": 95,
                        "pacing": 87,
                    },
                    "strengths": ["物证层层递进", "对白潜台词丰富"],
                    "problems": ["许照出场缺少铺垫", "开头一两段偏散文化"],
                    "actions": ["许照出场前增加极简暗示", "压紧前300字"],
                },
            },
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["draft"]["source"] == "editorial-polish"
        assert payload["draft"]["content"] == "按主编审稿精修后的候选正文"
        assert payload["draft"]["branch_name"] == "editorial"
        assert payload["draft"]["metadata"]["editorial_review"]["verdict"] == "可优化后使用"
        assert payload["task"]["execution_mode"] == "editorial_polish_api"
        assert "许照出场缺少铺垫" in writing_service.calls[0]["prompt"].user
        assert "许照出场前增加极简暗示" in writing_service.calls[0]["prompt"].user
        assert "旧正文里许照突然出现" in writing_service.calls[0]["prompt"].user
        assert "目标字数：约 2500 字" in writing_service.calls[0]["prompt"].user
        assert writing_service.calls[0]["config"].max_tokens <= 4096

    def test_create_web_writing_prompt_records_copy_paste_task(self):
        novel_id = f"test-novel-web-writing-{uuid.uuid4().hex[:8]}"
        create_novel = self.client.post(
            "/api/v1/novels",
            json={
                "novel_id": novel_id,
                "title": "Web 写作测试",
                "author": "测试作者",
                "target_chapters": 12,
                "premise": "测试 premise",
            },
        )
        assert create_novel.status_code == 201

        response = self.client.post(
            f"/api/v1/novels/{novel_id}/candidate-drafts/web-writing-prompt",
            json={
                "chapter_number": 6,
                "outline": "第六章，主角在灯塔里发现旧记录。",
                "current_content": "上一版正文开头偏慢。",
                "model_label": "ChatGPT Web",
                "task_prompt": "生成一版 2500 字左右的商业悬疑正文。",
            },
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["task"]["model"] == "ChatGPT Web"
        assert payload["task"]["status"] == "prompted"
        assert payload["task"]["execution_mode"] == "web_copy_paste"
        assert payload["prompt"] == payload["task"]["prompt"]
        assert "第六章，主角在灯塔里发现旧记录" in payload["prompt"]
        assert "上一版正文开头偏慢" in payload["prompt"]
        assert "只输出完整章节正文" in payload["prompt"]

    def test_supervisor_review_uses_requested_llm_profile_and_records_task(self):
        novel_id = f"test-novel-supervisor-review-{uuid.uuid4().hex[:8]}"
        create_novel = self.client.post(
            "/api/v1/novels",
            json={
                "novel_id": novel_id,
                "title": "监督模型测试",
                "author": "测试作者",
                "target_chapters": 12,
                "premise": "测试 premise",
            },
        )
        assert create_novel.status_code == 201

        create_draft = self.client.post(
            f"/api/v1/novels/{novel_id}/chapters/4/candidate-drafts",
            json={
                "source": "direct-model",
                "title": "第4章候选",
                "content": "甲突然击败高阶敌人，但没有付出代价。",
                "branch_name": "main",
            },
        )
        assert create_draft.status_code == 201
        draft = create_draft.json()

        factory = _FakeLLMFactory()
        app.dependency_overrides[get_llm_provider_factory] = lambda: factory

        response = self.client.post(
            f"/api/v1/novels/{novel_id}/chapters/4/candidate-drafts/{draft['id']}/supervisor-review",
            json={
                "model_label": "GPT 审稿",
                "llm_profile_id": "supervisor-profile",
                "focus": "检查记忆、连续性、战力崩坏和采纳建议。",
            },
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["review"] == "监督模型检查：建议采纳前补一条关系事件。"
        assert payload["task"]["candidate_draft_id"] == draft["id"]
        assert payload["task"]["status"] == "reviewed"
        assert payload["task"]["execution_mode"] == "supervisor_api"
        assert factory.requested_profiles == ["supervisor-profile"]
        assert "甲突然击败高阶敌人" in factory.supervisor_service.calls[0]["prompt"].user

    def test_supervisor_review_defaults_to_analysis_llm_when_no_profile_requested(self):
        novel_id = f"test-novel-supervisor-default-{uuid.uuid4().hex[:8]}"
        create_novel = self.client.post(
            "/api/v1/novels",
            json={
                "novel_id": novel_id,
                "title": "默认审稿模型测试",
                "author": "测试作者",
                "target_chapters": 12,
                "premise": "测试 premise",
            },
        )
        assert create_novel.status_code == 201

        create_draft = self.client.post(
            f"/api/v1/novels/{novel_id}/chapters/4/candidate-drafts",
            json={
                "source": "direct-model",
                "title": "第4章候选",
                "content": "甲突然击败高阶敌人，但没有付出代价。",
                "branch_name": "main",
            },
        )
        assert create_draft.status_code == 201
        draft = create_draft.json()

        active_service = _FakeLLMService("当前激活 Kimi 检查结果")
        analysis_service = _FakeLLMService("DS 分析模型检查结果")
        app.dependency_overrides[get_llm_service] = lambda: active_service
        app.dependency_overrides[get_analysis_llm_service] = lambda: analysis_service

        response = self.client.post(
            f"/api/v1/novels/{novel_id}/chapters/4/candidate-drafts/{draft['id']}/supervisor-review",
            json={
                "model_label": "PP 当前 AI",
                "focus": "检查记忆、连续性、战力崩坏和采纳建议。",
            },
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["review"] == "DS 分析模型检查结果"
        assert len(analysis_service.calls) == 1
        assert active_service.calls == []
        assert "AI味" in analysis_service.calls[0]["prompt"].user
        assert "对白直白" in analysis_service.calls[0]["prompt"].user
