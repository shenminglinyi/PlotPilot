"""Writer Block API 集成测试"""
import pytest
from fastapi.testclient import TestClient
from interfaces.main import app


class TestWriterBlockAPI:
    """Writer Block API 集成测试套件"""

    @pytest.fixture
    def client(self):
        """创建测试客户端"""
        return TestClient(app)

    @pytest.fixture
    def client_with_fake_analyzer(self):
        """校验类测试专用：override 掉 LLM 依赖（否则未配置时依赖层先 503，
        校验逻辑到不了），用一个假 analyzer 让路由本体逻辑照常执行。"""
        from interfaces.api.dependencies import get_tension_analyzer

        class _FakeAnalyzer:
            def analyze(self, *args, **kwargs):
                return {"tension_level": "low", "diagnosis": "x", "missing_elements": [], "suggestions": ["引入"]}

        app.dependency_overrides[get_tension_analyzer] = lambda: _FakeAnalyzer()
        try:
            yield TestClient(app)
        finally:
            app.dependency_overrides.pop(get_tension_analyzer, None)

    @pytest.fixture
    def setup_test_data(self):
        """设置测试数据"""
        from infrastructure.persistence.database.connection import get_database
        from infrastructure.persistence.database.sqlite_narrative_event_repository import SqliteNarrativeEventRepository

        db = get_database()
        repo = SqliteNarrativeEventRepository(db)

        # 创建测试小说和事件
        novel_id = "test-novel-writer-block"

        # 清理旧数据
        db.execute("DELETE FROM narrative_events WHERE novel_id = ?", (novel_id,))
        db.execute("DELETE FROM novels WHERE id = ?", (novel_id,))
        db.get_connection().commit()

        # 创建测试小说
        db.execute(
            "INSERT INTO novels (id, title, slug, target_chapters) VALUES (?, ?, ?, ?)",
            (novel_id, "Test Novel", "test-novel-writer-block", 10)
        )
        db.get_connection().commit()

        # 添加低张力事件（无冲突标签）
        repo.append_event(
            novel_id=novel_id,
            chapter_number=1,
            event_summary="主角在家吃早餐",
            mutations=[],
            tags=["日常", "情绪:平静"]
        )
        repo.append_event(
            novel_id=novel_id,
            chapter_number=2,
            event_summary="主角去上班",
            mutations=[],
            tags=["日常"]
        )

        # 添加高张力事件（有冲突标签）
        repo.append_event(
            novel_id=novel_id,
            chapter_number=3,
            event_summary="主角与敌人激烈战斗",
            mutations=[],
            tags=["冲突:对抗", "冲突:生死", "情绪:愤怒", "情绪:恐惧"]
        )

        yield novel_id

        # 清理测试数据
        db.execute("DELETE FROM narrative_events WHERE novel_id = ?", (novel_id,))
        db.execute("DELETE FROM novels WHERE id = ?", (novel_id,))
        db.get_connection().commit()

    @pytest.mark.asyncio
    async def test_tension_slingshot_low_tension(self, client, setup_test_data):
        """测试：分析低张力章节"""
        novel_id = setup_test_data

        # 构建请求
        request_data = {
            "novel_id": novel_id,
            "chapter_number": 2
        }

        # 发送请求
        response = client.post(
            f"/api/v1/novels/{novel_id}/writer-block/tension-slingshot",
            json=request_data
        )

        # 验证响应：未配置 LLM 时必须明确 503（回归：不再静默走 MockProvider 假成功）
        assert response.status_code == 503
        body = response.json()
        assert "配置" in body["detail"]

    @pytest.mark.asyncio
    async def test_tension_slingshot_with_stuck_reason(self, client, setup_test_data):
        """测试：提供卡文原因时的分析"""
        novel_id = setup_test_data

        # 构建请求（包含卡文原因）
        request_data = {
            "novel_id": novel_id,
            "chapter_number": 2,
            "stuck_reason": "不知道如何推进情节"
        }

        # 发送请求
        response = client.post(
            f"/api/v1/novels/{novel_id}/writer-block/tension-slingshot",
            json=request_data
        )

        # 验证响应：未配置 LLM 时必须明确 503（回归：不再走 MockProvider 假成功）
        assert response.status_code == 503
        body = response.json()
        assert "配置" in body["detail"]

    @pytest.mark.asyncio
    async def test_tension_slingshot_high_tension(self, client, setup_test_data):
        """测试：分析高张力章节"""
        novel_id = setup_test_data

        # 构建请求
        request_data = {
            "novel_id": novel_id,
            "chapter_number": 3
        }

        # 发送请求
        response = client.post(
            f"/api/v1/novels/{novel_id}/writer-block/tension-slingshot",
            json=request_data
        )

        # 验证响应：未配置 LLM 时必须明确 503（回归：不再走 MockProvider 假成功）
        assert response.status_code == 503
        body = response.json()
        assert "配置" in body["detail"]

    def test_tension_slingshot_validation_novel_id_mismatch(self, client_with_fake_analyzer):
        """测试：验证 novel_id 不匹配时返回错误"""
        # 路径中的 novel_id 与请求体中的不匹配
        request_data = {
            "novel_id": "different-novel-id",
            "chapter_number": 1
        }

        response = client_with_fake_analyzer.post(
            "/api/v1/novels/test-novel/writer-block/tension-slingshot",
            json=request_data
        )

        # 应该返回 400 错误
        assert response.status_code == 400
        assert "does not match" in response.json()["detail"]

    def test_tension_slingshot_validation_missing_fields(self, client_with_fake_analyzer):
        """测试：验证缺少必需字段时返回错误"""
        novel_id = "test-novel"

        # 缺少 chapter_number 字段
        invalid_request = {
            "novel_id": novel_id
            # 缺少 chapter_number
        }

        response = client_with_fake_analyzer.post(
            f"/api/v1/novels/{novel_id}/writer-block/tension-slingshot",
            json=invalid_request
        )

        # 应该返回 422 验证错误
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_tension_slingshot_empty_events(self, client):
        """测试：处理无事件的小说"""
        from infrastructure.persistence.database.connection import get_database

        db = get_database()
        novel_id = "test-novel-empty"

        # 清理并创建空小说
        db.execute("DELETE FROM narrative_events WHERE novel_id = ?", (novel_id,))
        db.execute("DELETE FROM novels WHERE id = ?", (novel_id,))
        db.get_connection().commit()

        db.execute(
            "INSERT INTO novels (id, title, slug, target_chapters) VALUES (?, ?, ?, ?)",
            (novel_id, "Empty Novel", "test-novel-empty", 10)
        )
        db.get_connection().commit()

        # 构建请求
        request_data = {
            "novel_id": novel_id,
            "chapter_number": 1
        }

        # 发送请求
        response = client.post(
            f"/api/v1/novels/{novel_id}/writer-block/tension-slingshot",
            json=request_data
        )

        # 验证响应：未配置 LLM 时必须明确 503 报错（回归：不再静默走 MockProvider 假成功）
        assert response.status_code == 503
        body = response.json()
        assert "detail" in body
        assert "配置" in body["detail"]

        # 清理
        db.execute("DELETE FROM novels WHERE id = ?", (novel_id,))
        db.get_connection().commit()

    @pytest.mark.asyncio
    async def test_tension_slingshot_suggestions_are_actionable(self, client, setup_test_data):
        """测试：建议是可操作的（包含动作动词）"""
        novel_id = setup_test_data

        # 构建请求
        request_data = {
            "novel_id": novel_id,
            "chapter_number": 2
        }

        # 发送请求
        response = client.post(
            f"/api/v1/novels/{novel_id}/writer-block/tension-slingshot",
            json=request_data
        )

        # 验证响应：未配置 LLM 时必须明确 503 报错（回归：不再静默走 MockProvider 假成功）
        assert response.status_code == 503
        body = response.json()
        assert "detail" in body
        assert "配置" in body["detail"]
