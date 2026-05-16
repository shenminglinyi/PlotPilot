"""Bible API 集成测试（Bible / Novel 均使用临时 SQLite，与生产链路一致）。"""
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_novel_repository import SqliteNovelRepository
from infrastructure.persistence.database.sqlite_chapter_repository import SqliteChapterRepository
from infrastructure.persistence.database.sqlite_bible_repository import SqliteBibleRepository
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
from application.services.novel_service import NovelService
from application.services.bible_service import BibleService
from interfaces.api.dependencies import get_novel_service, get_bible_service
from interfaces.main import app

_test_novel_service = None
_test_bible_service = None
_test_db: Optional[DatabaseConnection] = None


def get_test_novel_service():
    return _test_novel_service


def get_test_bible_service():
    return _test_bible_service


@pytest.fixture(autouse=True)
def setup_test_env(tmp_path):
    global _test_novel_service, _test_bible_service, _test_db

    db_path = str(tmp_path / "plotpilot.db")
    _test_db = DatabaseConnection(db_path)
    novel_repo = SqliteNovelRepository(_test_db)
    chapter_repo = SqliteChapterRepository(_test_db)
    bible_repo = SqliteBibleRepository(_test_db)
    story_repo = StoryNodeRepository(db_path)

    _test_novel_service = NovelService(novel_repo, chapter_repo, story_repo)
    _test_bible_service = BibleService(bible_repo)

    app.dependency_overrides[get_novel_service] = get_test_novel_service
    app.dependency_overrides[get_bible_service] = get_test_bible_service

    yield

    app.dependency_overrides.clear()
    _test_novel_service = None
    _test_bible_service = None
    if _test_db:
        _test_db.close()
        _test_db = None


client = TestClient(app)


@pytest.fixture
def test_novel():
    """创建测试小说"""
    response = client.post(
        "/api/v1/novels/",
        json={
            "novel_id": "test-novel-bible",
            "title": "测试小说",
            "author": "测试作者",
            "target_chapters": 10,
        },
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def test_bible(test_novel):
    """创建测试 Bible"""
    response = client.post(
        "/api/v1/bible/novels/test-novel-bible/bible",
        json={"bible_id": "bible-1", "novel_id": "test-novel-bible"},
    )
    assert response.status_code == 201
    return response.json()


class TestGetBible:
    """测试获取 Bible 端点"""

    def test_get_bible_success(self, test_bible):
        """测试成功获取 Bible"""
        response = client.get("/api/v1/bible/novels/test-novel-bible/bible")
        assert response.status_code == 200
        data = response.json()
        assert data["novel_id"] == "test-novel-bible"
        assert "characters" in data
        assert "world_settings" in data
        assert isinstance(data["characters"], list)
        assert isinstance(data["world_settings"], list)

    def test_get_bible_not_found(self, test_novel):
        """测试获取不存在的 Bible"""
        response = client.get("/api/v1/bible/novels/test-novel-bible/bible")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_bible_wrong_novel(self):
        """测试从不存在的小说获取 Bible"""
        response = client.get("/api/v1/bible/novels/wrong-novel-id/bible")
        assert response.status_code == 404


class TestListCharacters:
    """测试列出人物端点"""

    def test_list_characters_empty(self, test_bible):
        """测试列出空人物列表"""
        response = client.get("/api/v1/bible/novels/test-novel-bible/bible/characters")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_list_characters_with_data(self, test_bible):
        """测试列出有数据的人物列表"""
        client.post(
            "/api/v1/bible/novels/test-novel-bible/bible/characters",
            json={"character_id": "char-1", "name": "张三", "description": "主角"},
        )
        client.post(
            "/api/v1/bible/novels/test-novel-bible/bible/characters",
            json={"character_id": "char-2", "name": "李四", "description": "配角"},
        )

        response = client.get("/api/v1/bible/novels/test-novel-bible/bible/characters")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["name"] == "张三"
        assert data[1]["name"] == "李四"

    def test_list_characters_bible_not_found(self, test_novel):
        """测试从不存在的 Bible 列出人物"""
        response = client.get("/api/v1/bible/novels/test-novel-bible/bible/characters")
        assert response.status_code == 404


class TestAddCharacter:
    """测试添加人物端点"""

    def test_add_character_success(self, test_bible):
        """测试成功添加人物"""
        response = client.post(
            "/api/v1/bible/novels/test-novel-bible/bible/characters",
            json={
                "character_id": "char-1",
                "name": "张三",
                "description": "主角，勇敢善良",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["novel_id"] == "test-novel-bible"
        assert len(data["characters"]) == 1
        assert data["characters"][0]["name"] == "张三"
        assert data["characters"][0]["description"] == "主角，勇敢善良"

    def test_add_character_bible_not_found(self, test_novel):
        """测试向不存在的 Bible 添加人物"""
        response = client.post(
            "/api/v1/bible/novels/test-novel-bible/bible/characters",
            json={"character_id": "char-1", "name": "张三", "description": "主角"},
        )
        assert response.status_code == 404

    def test_add_character_invalid_request(self, test_bible):
        """测试无效的添加人物请求"""
        response = client.post(
            "/api/v1/bible/novels/test-novel-bible/bible/characters",
            json={"character_id": "char-1"},
        )
        assert response.status_code == 422

    def test_add_multiple_characters(self, test_bible):
        """测试添加多个人物"""
        response1 = client.post(
            "/api/v1/bible/novels/test-novel-bible/bible/characters",
            json={"character_id": "char-1", "name": "张三", "description": "主角"},
        )
        assert response1.status_code == 200
        assert len(response1.json()["characters"]) == 1

        response2 = client.post(
            "/api/v1/bible/novels/test-novel-bible/bible/characters",
            json={"character_id": "char-2", "name": "李四", "description": "配角"},
        )
        assert response2.status_code == 200
        data = response2.json()
        assert len(data["characters"]) == 2

        char_names = [c["name"] for c in data["characters"]]
        assert "张三" in char_names
        assert "李四" in char_names
