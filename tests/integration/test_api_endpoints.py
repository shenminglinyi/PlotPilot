"""API 集成测试

测试所有 API 端点的集成功能。
"""
from fastapi.testclient import TestClient
from interfaces.main import app
import tempfile
import shutil
from pathlib import Path
import pytest


client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch, tmp_path):
    """设置测试环境"""
    # 使用临时目录作为输出目录
    test_output = tmp_path / "output"
    test_output.mkdir()
    monkeypatch.setenv("OUTPUT_DIR", str(test_output))
    yield
    # 清理
    if test_output.exists():
        shutil.rmtree(test_output)


def test_root_endpoint(monkeypatch):
    """测试根路径（无前端构建时返回 JSON 欢迎信息）"""
    import interfaces.main as main_mod

    monkeypatch.setattr(main_mod, "_FRONTEND_DIR", Path("/__plotpilot_test_no_frontend__"))
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["message"] == "PlotPilot API"


def test_health_check():
    """测试健康检查"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_create_and_get_novel():
    """测试创建和获取小说"""
    # 创建小说
    response = client.post("/api/v1/novels/", json={
        "novel_id": "test-novel-1",
        "title": "测试小说",
        "author": "测试作者",
        "target_chapters": 10
    })
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "测试小说"
    assert data["author"] == "测试作者"
    assert data["target_chapters"] == 10

    # 获取小说
    response = client.get("/api/v1/novels/test-novel-1")
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "测试小说"
    assert data["id"] == "test-novel-1"


def test_list_novels():
    """测试列出所有小说"""
    # 创建几个小说
    client.post("/api/v1/novels/", json={
        "novel_id": "test-novel-2",
        "title": "测试小说2",
        "author": "作者2",
        "target_chapters": 5
    })

    # 列出所有小说
    response = client.get("/api/v1/novels/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1


def test_update_novel_stage():
    """测试更新小说阶段"""
    # 创建小说
    client.post("/api/v1/novels/", json={
        "novel_id": "test-novel-3",
        "title": "测试小说3",
        "author": "作者3",
        "target_chapters": 5
    })

    # 更新阶段
    response = client.put("/api/v1/novels/test-novel-3/stage", json={
        "stage": "writing"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["stage"] == "writing"


def test_delete_novel():
    """测试删除小说"""
    # 创建小说
    client.post("/api/v1/novels/", json={
        "novel_id": "test-novel-4",
        "title": "测试小说4",
        "author": "作者4",
        "target_chapters": 5
    })

    # 删除小说
    response = client.delete("/api/v1/novels/test-novel-4")
    assert response.status_code == 204

    # 验证已删除
    response = client.get("/api/v1/novels/test-novel-4")
    assert response.status_code == 404


def test_chapter_operations():
    """测试章节操作"""
    # 先创建小说
    client.post("/api/v1/novels/", json={
        "novel_id": "test-novel-5",
        "title": "测试小说5",
        "author": "作者5",
        "target_chapters": 5
    })

    # 获取章节列表（应该为空）
    response = client.get("/api/v1/novels/test-novel-5/chapters")
    assert response.status_code == 200
    assert len(response.json()) == 0


def test_bible_operations():
    """测试 Bible 操作"""
    # 创建小说
    client.post("/api/v1/novels/", json={
        "novel_id": "test-novel-6",
        "title": "测试小说6",
        "author": "作者6",
        "target_chapters": 5
    })

    # 创建 Bible
    response = client.post("/api/v1/bible/novels/test-novel-6/bible", json={
        "bible_id": "bible-1",
        "novel_id": "test-novel-6"
    })
    assert response.status_code == 201
    data = response.json()
    assert data["novel_id"] == "test-novel-6"

    # 添加人物
    response = client.post("/api/v1/bible/novels/test-novel-6/bible/characters", json={
        "character_id": "char-1",
        "name": "主角",
        "description": "主角描述"
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data["characters"]) == 1
    assert data["characters"][0]["name"] == "主角"

    # 添加世界设定
    response = client.post("/api/v1/bible/novels/test-novel-6/bible/world-settings", json={
        "setting_id": "setting-1",
        "name": "魔法系统",
        "description": "魔法系统描述",
        "setting_type": "rule"
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data["world_settings"]) == 1

    # 获取 Bible
    response = client.get("/api/v1/bible/novels/test-novel-6/bible")
    assert response.status_code == 200
    data = response.json()
    assert len(data["characters"]) == 1
    assert len(data["world_settings"]) == 1


def test_404_errors():
    """测试 404 错误"""
    # 不存在的小说
    response = client.get("/api/v1/novels/nonexistent")
    assert response.status_code == 404

    # 不存在的章节
    response = client.get("/api/v1/chapters/nonexistent")
    assert response.status_code == 404

    # 不存在的 Bible
    response = client.get("/api/v1/bible/novels/nonexistent/bible")
    assert response.status_code == 404


def test_novel_statistics():
    """测试小说统计信息"""
    # 创建小说
    client.post("/api/v1/novels/", json={
        "novel_id": "test-novel-7",
        "title": "测试小说7",
        "author": "作者7",
        "target_chapters": 10
    })

    # 获取统计信息
    response = client.get("/api/v1/novels/test-novel-7/statistics")
    assert response.status_code == 200
    data = response.json()
    assert "total_chapters" in data
    assert "total_words" in data
    assert "completed_chapters" in data
    assert "stage" in data
