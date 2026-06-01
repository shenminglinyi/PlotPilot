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
        # 准备 mock 数据
        bible = Bible(id="bible-1", novel_id=NovelId("novel-1"))
        mock_repository.get_by_novel_id.return_value = bible

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

        # 验证调用了 save
        mock_repository.save.assert_called_once()

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

    def test_update_character_voice_anchors_uses_repository_capability(self):
        """仓储支持行级更新时，优先使用专用能力并返回更新后的角色。"""

        class AnchorRepository:
            def __init__(self):
                self.bible = Bible(id="bible-1", novel_id=NovelId("novel-1"))
                self.bible.add_character(Character(
                    id=CharacterId("char-1"),
                    name="主角",
                    description="描述",
                ))
                self.updated = None

            def update_character_anchors(self, novel_id, character_id, *, mental_state, verbal_tic, idle_behavior):
                self.updated = {
                    "novel_id": novel_id,
                    "character_id": character_id,
                    "mental_state": mental_state,
                    "verbal_tic": verbal_tic,
                    "idle_behavior": idle_behavior,
                }
                character = self.bible.get_character(CharacterId(character_id))
                character.mental_state = mental_state
                character.verbal_tic = verbal_tic
                character.idle_behavior = idle_behavior

            def get_by_novel_id(self, novel_id):
                assert novel_id == NovelId("novel-1")
                return self.bible

        repo = AnchorRepository()
        dto = BibleService(repo).update_character_voice_anchors(
            "novel-1",
            "char-1",
            mental_state="紧张",
            verbal_tic="且慢",
            idle_behavior="捻袖口",
        )

        assert repo.updated == {
            "novel_id": "novel-1",
            "character_id": "char-1",
            "mental_state": "紧张",
            "verbal_tic": "且慢",
            "idle_behavior": "捻袖口",
        }
        assert dto.mental_state == "紧张"
        assert dto.verbal_tic == "且慢"
        assert dto.idle_behavior == "捻袖口"

    def test_update_character_voice_anchors_falls_back_to_read_modify_save(self):
        """通用 Bible 仓储没有行级更新能力时，使用聚合读改写保存。"""

        class ReadWriteRepository:
            def __init__(self):
                self.bible = Bible(id="bible-1", novel_id=NovelId("novel-1"))
                self.bible.add_character(Character(
                    id=CharacterId("char-1"),
                    name="配角",
                    description="描述",
                    mental_state="NORMAL",
                ))
                self.saved_bible = None

            def get_by_novel_id(self, novel_id):
                assert novel_id == NovelId("novel-1")
                return self.bible

            def save(self, bible):
                self.saved_bible = bible

        repo = ReadWriteRepository()
        dto = BibleService(repo).update_character_voice_anchors(
            "novel-1",
            "char-1",
            mental_state="",
            verbal_tic="听我说",
            idle_behavior="敲桌面",
        )

        character = repo.bible.get_character(CharacterId("char-1"))
        assert repo.saved_bible is repo.bible
        assert character.mental_state == "NORMAL"
        assert character.verbal_tic == "听我说"
        assert character.idle_behavior == "敲桌面"
        assert dto.mental_state == "NORMAL"
        assert dto.verbal_tic == "听我说"
        assert dto.idle_behavior == "敲桌面"

    def test_update_character_voice_anchors_fallback_requires_existing_bible(self):
        """读改写路径上 Bible 不存在时返回明确领域错误。"""

        class ReadWriteRepository:
            def get_by_novel_id(self, novel_id):
                return None

            def save(self, bible):
                raise AssertionError("Bible 不存在时不应保存")

        with pytest.raises(EntityNotFoundError, match="Bible"):
            BibleService(ReadWriteRepository()).update_character_voice_anchors(
                "missing-novel",
                "char-1",
                mental_state="NORMAL",
                verbal_tic="",
                idle_behavior="",
            )

    def test_update_character_voice_anchors_fallback_requires_existing_character(self):
        """读改写路径上角色不存在时返回明确领域错误。"""

        class ReadWriteRepository:
            def __init__(self):
                self.bible = Bible(id="bible-1", novel_id=NovelId("novel-1"))

            def get_by_novel_id(self, novel_id):
                return self.bible

            def save(self, bible):
                raise AssertionError("角色不存在时不应保存")

        with pytest.raises(EntityNotFoundError, match="Character"):
            BibleService(ReadWriteRepository()).update_character_voice_anchors(
                "novel-1",
                "missing-char",
                mental_state="NORMAL",
                verbal_tic="",
                idle_behavior="",
            )
