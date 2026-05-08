"""BibleService 单元测试"""
import pytest
from unittest.mock import Mock
from domain.bible.entities.bible import Bible
from domain.bible.entities.character import Character
from domain.bible.entities.world_setting import WorldSetting
from domain.bible.value_objects.character_id import CharacterId
from domain.novel.value_objects.novel_id import NovelId
from domain.shared.exceptions import EntityNotFoundError
from application.services.bible_service import BibleService


class TestBibleService:
    """BibleService 单元测试"""

    @pytest.fixture
    def mock_repository(self):
        """创建 mock 仓储"""
        return Mock()

    @pytest.fixture
    def service(self, mock_repository):
        """创建服务实例"""
        return BibleService(mock_repository)

    def test_create_bible(self, service, mock_repository):
        """测试创建 Bible"""
        bible_dto = service.create_bible(
            bible_id="bible-1",
            novel_id="novel-1"
        )

        assert bible_dto.id == "bible-1"
        assert bible_dto.novel_id == "novel-1"
        assert len(bible_dto.characters) == 0
        assert len(bible_dto.world_settings) == 0

        # 验证调用了 save
        mock_repository.save.assert_called_once()

    def test_add_character(self, service, mock_repository):
        """测试添加人物"""
        # 准备 mock 数据：第一次返回空 Bible，第二次返回含角色的 Bible（模拟增量写入后）
        bible_empty = Bible(id="bible-1", novel_id=NovelId("novel-1"))
        bible_with_char = Bible(id="bible-1", novel_id=NovelId("novel-1"))
        bible_with_char.add_character(
            Character(id=CharacterId("char-1"), name="主角", description="主角描述")
        )
        mock_repository.get_by_novel_id.side_effect = [bible_empty, bible_with_char]

        bible_dto = service.add_character(
            novel_id="novel-1",
            character_id="char-1",
            name="主角",
            description="主角描述"
        )

        assert bible_dto.id == "bible-1"
        assert len(bible_dto.characters) == 1
        assert bible_dto.characters[0].id == "char-1"
        assert bible_dto.characters[0].name == "主角"

        # 验证调用了增量写入
        mock_repository.add_character_incremental.assert_called_once()

    def test_add_character_bible_not_found(self, service, mock_repository):
        """测试向不存在的 Bible 添加人物"""
        mock_repository.get_by_novel_id.return_value = None

        with pytest.raises(EntityNotFoundError, match="Bible"):
            service.add_character(
                novel_id="nonexistent",
                character_id="char-1",
                name="主角",
                description="主角描述"
            )

    def test_add_world_setting(self, service, mock_repository):
        """测试添加世界设定"""
        # 准备 mock 数据
        bible = Bible(id="bible-1", novel_id=NovelId("novel-1"))
        mock_repository.get_by_novel_id.return_value = bible

        bible_dto = service.add_world_setting(
            novel_id="novel-1",
            setting_id="setting-1",
            name="魔法系统",
            description="魔法系统描述",
            setting_type="rule"
        )

        assert bible_dto.id == "bible-1"
        assert len(bible_dto.world_settings) == 1
        assert bible_dto.world_settings[0].id == "setting-1"
        assert bible_dto.world_settings[0].name == "魔法系统"
        assert bible_dto.world_settings[0].setting_type == "rule"

        # 验证调用了 save
        mock_repository.save.assert_called_once()

    def test_add_world_setting_bible_not_found(self, service, mock_repository):
        """测试向不存在的 Bible 添加世界设定"""
        mock_repository.get_by_novel_id.return_value = None

        with pytest.raises(EntityNotFoundError, match="Bible"):
            service.add_world_setting(
                novel_id="nonexistent",
                setting_id="setting-1",
                name="魔法系统",
                description="魔法系统描述",
                setting_type="rule"
            )

    def test_get_bible_by_novel(self, service, mock_repository):
        """测试根据小说 ID 获取 Bible"""
        # 准备 mock 数据
        bible = Bible(id="bible-1", novel_id=NovelId("novel-1"))
        mock_repository.get_by_novel_id.return_value = bible

        bible_dto = service.get_bible_by_novel("novel-1")

        assert bible_dto is not None
        assert bible_dto.id == "bible-1"
        assert bible_dto.novel_id == "novel-1"

        mock_repository.get_by_novel_id.assert_called_once_with(NovelId("novel-1"))

    def test_get_bible_by_novel_not_found(self, service, mock_repository):
        """测试获取不存在的 Bible"""
        mock_repository.get_by_novel_id.return_value = None

        bible_dto = service.get_bible_by_novel("nonexistent")

        assert bible_dto is None
