"""Bible Extended Fields API 集成测试"""
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
    response = client.post("/api/v1/novels/", json={
        "novel_id": "test-novel-bible-ext",
        "title": "测试小说",
        "author": "测试作者",
        "target_chapters": 10
    })
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def test_bible(test_novel):
    """创建测试 Bible"""
    response = client.post("/api/v1/bible/novels/test-novel-bible-ext/bible", json={
        "bible_id": "bible-1",
        "novel_id": "test-novel-bible-ext"
    })
    assert response.status_code == 201
    return response.json()


class TestAddLocation:
    """测试添加地点端点"""

    def test_add_location_success(self, test_bible):
        """测试成功添加地点"""
        response = client.post(
            "/api/v1/bible/novels/test-novel-bible-ext/bible/locations",
            json={
                "location_id": "loc-1",
                "name": "皇宫",
                "description": "金碧辉煌的皇宫",
                "location_type": "building"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["locations"]) == 1
        assert data["locations"][0]["name"] == "皇宫"
        assert data["locations"][0]["location_type"] == "building"

    def test_add_multiple_locations(self, test_bible):
        """测试添加多个地点"""
        # 添加第一个地点
        client.post(
            "/api/v1/bible/novels/test-novel-bible-ext/bible/locations",
            json={
                "location_id": "loc-1",
                "name": "皇宫",
                "description": "金碧辉煌的皇宫",
                "location_type": "building"
            }
        )

        # 添加第二个地点
        response = client.post(
            "/api/v1/bible/novels/test-novel-bible-ext/bible/locations",
            json={
                "location_id": "loc-2",
                "name": "森林",
                "description": "神秘的森林",
                "location_type": "natural"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["locations"]) == 2

    def test_add_location_bible_not_found(self, test_novel):
        """测试 Bible 不存在"""
        response = client.post(
            "/api/v1/bible/novels/nonexistent-novel/bible/locations",
            json={
                "location_id": "loc-1",
                "name": "皇宫",
                "description": "金碧辉煌的皇宫",
                "location_type": "building"
            }
        )
        assert response.status_code == 404


class TestAddTimelineNote:
    """测试添加时间线笔记端点"""

    def test_add_timeline_note_success(self, test_bible):
        """测试成功添加时间线笔记"""
        response = client.post(
            "/api/v1/bible/novels/test-novel-bible-ext/bible/timeline-notes",
            json={
                "note_id": "timeline-1",
                "event": "主角出生",
                "time_point": "序章",
                "description": "在一个风雨交加的夜晚"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["timeline_notes"]) == 1
        assert data["timeline_notes"][0]["event"] == "主角出生"
        assert data["timeline_notes"][0]["time_point"] == "序章"

    def test_add_multiple_timeline_notes(self, test_bible):
        """测试添加多个时间线笔记"""
        # 添加第一个笔记
        client.post(
            "/api/v1/bible/novels/test-novel-bible-ext/bible/timeline-notes",
            json={
                "note_id": "timeline-1",
                "event": "主角出生",
                "time_point": "序章",
                "description": "在一个风雨交加的夜晚"
            }
        )

        # 添加第二个笔记
        response = client.post(
            "/api/v1/bible/novels/test-novel-bible-ext/bible/timeline-notes",
            json={
                "note_id": "timeline-2",
                "event": "主角觉醒",
                "time_point": "第一章",
                "description": "发现自己的特殊能力"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["timeline_notes"]) == 2


class TestAddStyleNote:
    """测试添加风格笔记端点"""

    def test_add_style_note_success(self, test_bible):
        """测试成功添加风格笔记"""
        response = client.post(
            "/api/v1/bible/novels/test-novel-bible-ext/bible/style-notes",
            json={
                "note_id": "style-1",
                "category": "tone",
                "content": "整体风格偏向轻松幽默"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["style_notes"]) == 1
        assert data["style_notes"][0]["category"] == "tone"
        assert data["style_notes"][0]["content"] == "整体风格偏向轻松幽默"

    def test_add_multiple_style_notes(self, test_bible):
        """测试添加多个风格笔记"""
        # 添加第一个笔记
        client.post(
            "/api/v1/bible/novels/test-novel-bible-ext/bible/style-notes",
            json={
                "note_id": "style-1",
                "category": "tone",
                "content": "整体风格偏向轻松幽默"
            }
        )

        # 添加第二个笔记
        response = client.post(
            "/api/v1/bible/novels/test-novel-bible-ext/bible/style-notes",
            json={
                "note_id": "style-2",
                "category": "pacing",
                "content": "节奏要快，避免拖沓"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["style_notes"]) == 2


class TestGetBibleWithExtendedFields:
    """测试获取包含扩展字段的 Bible"""

    def test_get_bible_with_all_fields(self, test_bible):
        """测试获取包含所有字段的 Bible"""
        # 添加各种数据
        client.post(
            "/api/v1/bible/novels/test-novel-bible-ext/bible/locations",
            json={
                "location_id": "loc-1",
                "name": "皇宫",
                "description": "金碧辉煌的皇宫",
                "location_type": "building"
            }
        )
        client.post(
            "/api/v1/bible/novels/test-novel-bible-ext/bible/timeline-notes",
            json={
                "note_id": "timeline-1",
                "event": "主角出生",
                "time_point": "序章",
                "description": "在一个风雨交加的夜晚"
            }
        )
        client.post(
            "/api/v1/bible/novels/test-novel-bible-ext/bible/style-notes",
            json={
                "note_id": "style-1",
                "category": "tone",
                "content": "整体风格偏向轻松幽默"
            }
        )

        # 获取 Bible
        response = client.get("/api/v1/bible/novels/test-novel-bible-ext/bible")
        assert response.status_code == 200
        data = response.json()

        # 验证所有字段都存在
        assert "locations" in data
        assert "timeline_notes" in data
        assert "style_notes" in data
        assert len(data["locations"]) == 1
        assert len(data["timeline_notes"]) == 1
        assert len(data["style_notes"]) == 1


class TestBulkUpdateBible:
    """测试批量更新 Bible 端点"""

    def test_bulk_update_success(self, test_bible):
        """测试成功批量更新 Bible"""
        response = client.put(
            "/api/v1/bible/novels/test-novel-bible-ext/bible",
            json={
                "characters": [
                    {
                        "id": "char-1",
                        "name": "张三",
                        "description": "主角",
                        "relationships": []
                    },
                    {
                        "id": "char-2",
                        "name": "李四",
                        "description": "配角",
                        "relationships": ["char-1"]
                    }
                ],
                "world_settings": [
                    {
                        "id": "setting-1",
                        "name": "魔法系统",
                        "description": "基于元素的魔法",
                        "setting_type": "rule"
                    }
                ],
                "locations": [
                    {
                        "id": "loc-1",
                        "name": "皇宫",
                        "description": "金碧辉煌的皇宫",
                        "location_type": "building"
                    }
                ],
                "timeline_notes": [
                    {
                        "id": "timeline-1",
                        "event": "主角出生",
                        "time_point": "序章",
                        "description": "在一个风雨交加的夜晚"
                    }
                ],
                "style_notes": [
                    {
                        "id": "style-1",
                        "category": "tone",
                        "content": "整体风格偏向轻松幽默"
                    }
                ]
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["characters"]) == 2
        assert len(data["world_settings"]) == 1
        assert len(data["locations"]) == 1
        assert len(data["timeline_notes"]) == 1
        assert len(data["style_notes"]) == 1
        assert data["characters"][0]["name"] == "张三"
        assert data["characters"][1]["name"] == "李四"

    def test_bulk_update_partial(self, test_bible):
        """测试部分字段批量更新"""
        response = client.put(
            "/api/v1/bible/novels/test-novel-bible-ext/bible",
            json={
                "characters": [
                    {
                        "id": "char-1",
                        "name": "张三",
                        "description": "主角",
                        "relationships": []
                    }
                ],
                "world_settings": [],
                "locations": [],
                "timeline_notes": [],
                "style_notes": []
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["characters"]) == 1
        assert len(data["world_settings"]) == 0
        assert len(data["locations"]) == 0
        assert len(data["timeline_notes"]) == 0
        assert len(data["style_notes"]) == 0

    def test_bulk_update_replaces_existing(self, test_bible):
        """测试批量更新会替换现有数据"""
        # 先添加一些数据
        client.post(
            "/api/v1/bible/novels/test-novel-bible-ext/bible/characters",
            json={
                "character_id": "old-char",
                "name": "旧人物",
                "description": "将被替换"
            }
        )

        # 批量更新，应该替换掉旧数据
        response = client.put(
            "/api/v1/bible/novels/test-novel-bible-ext/bible",
            json={
                "characters": [
                    {
                        "id": "new-char",
                        "name": "新人物",
                        "description": "新的人物",
                        "relationships": []
                    }
                ],
                "world_settings": [],
                "locations": [],
                "timeline_notes": [],
                "style_notes": []
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["characters"]) == 1
        assert data["characters"][0]["id"] == "new-char"
        assert data["characters"][0]["name"] == "新人物"

    def test_bulk_update_bible_not_found(self, test_novel):
        """测试更新不存在的 Bible"""
        response = client.put(
            "/api/v1/bible/novels/test-novel-bible-ext/bible",
            json={
                "characters": [],
                "world_settings": [],
                "locations": [],
                "timeline_notes": [],
                "style_notes": []
            }
        )
        assert response.status_code == 404

    def test_bulk_update_invalid_data(self, test_bible):
        """测试无效数据"""
        response = client.put(
            "/api/v1/bible/novels/test-novel-bible-ext/bible",
            json={
                "characters": [
                    {
                        "id": "char-1",
                        # 缺少必需字段
                    }
                ],
                "world_settings": [],
                "locations": [],
                "timeline_notes": [],
                "style_notes": []
            }
        )
        assert response.status_code == 422  # Validation error
