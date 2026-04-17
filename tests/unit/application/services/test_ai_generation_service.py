"""AIGenerationService 单元测试"""
import pytest
from unittest.mock import Mock, AsyncMock
from domain.novel.entities.novel import Novel, NovelStage
from domain.novel.value_objects.novel_id import NovelId
from domain.bible.entities.bible import Bible
from domain.bible.entities.character import Character
from domain.bible.entities.world_setting import WorldSetting
from domain.bible.value_objects.character_id import CharacterId
from domain.ai.services.llm_service import GenerationResult, GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage
from domain.shared.exceptions import EntityNotFoundError
from application.services.ai_generation_service import AIGenerationService


class TestAIGenerationService:
    """AIGenerationService 单元测试"""

    @pytest.fixture
    def mock_llm_service(self):
        """创建 mock LLM 服务"""
        return Mock()

    @pytest.fixture
    def mock_novel_repository(self):
        """创建 mock Novel 仓储"""
        return Mock()

    @pytest.fixture
    def mock_bible_repository(self):
        """创建 mock Bible 仓储"""
        return Mock()

    @pytest.fixture
    def service(self, mock_llm_service, mock_novel_repository, mock_bible_repository):
        """创建服务实例"""
        return AIGenerationService(
            llm_service=mock_llm_service,
            novel_repository=mock_novel_repository,
            bible_repository=mock_bible_repository
        )

    @pytest.fixture
    def sample_novel(self):
        """创建示例小说"""
        return Novel(
            id=NovelId("test-novel"),
            title="测试小说",
            author="测试作者",
            target_chapters=10,
            stage=NovelStage.WRITING
        )

    @pytest.fixture
    def sample_bible(self):
        """创建示例 Bible"""
        bible = Bible(id="bible-1", novel_id=NovelId("test-novel"))

        # 添加人物
        character = Character(
            id=CharacterId("char-1"),
            name="张三",
            description="主角，勇敢的战士"
        )
        bible.add_character(character)

        # 添加世界设定
        setting = WorldSetting(
            id="setting-1",
            name="魔法学院",
            description="培养魔法师的地方",
            setting_type="location"
        )
        bible.add_world_setting(setting)

        return bible

    @pytest.mark.asyncio
    async def test_generate_chapter_success(
        self,
        service,
        mock_llm_service,
        mock_novel_repository,
        mock_bible_repository,
        sample_novel
    ):
        """测试成功生成章节"""
        # 准备 mock 数据
        mock_novel_repository.get_by_id.return_value = sample_novel
        mock_bible_repository.get_by_novel_id.return_value = None

        # Mock LLM 返回
        mock_result = GenerationResult(
            content="这是生成的章节内容...",
            token_usage=TokenUsage(input_tokens=100, output_tokens=200)
        )
        mock_llm_service.generate = AsyncMock(return_value=mock_result)

        # 执行
        content = await service.generate_chapter(
            novel_id="test-novel",
            chapter_number=1,
            outline="主角开始冒险"
        )

        # 验证
        assert content == "这是生成的章节内容..."
        mock_novel_repository.get_by_id.assert_called_once_with(NovelId("test-novel"))
        mock_bible_repository.get_by_novel_id.assert_called_once_with(NovelId("test-novel"))
        mock_llm_service.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_chapter_with_bible(
        self,
        service,
        mock_llm_service,
        mock_novel_repository,
        mock_bible_repository,
        sample_novel,
        sample_bible
    ):
        """测试使用 Bible 生成章节"""
        # 准备 mock 数据
        mock_novel_repository.get_by_id.return_value = sample_novel
        mock_bible_repository.get_by_novel_id.return_value = sample_bible

        # Mock LLM 返回
        mock_result = GenerationResult(
            content="包含人物和世界设定的章节内容...",
            token_usage=TokenUsage(input_tokens=150, output_tokens=300)
        )
        mock_llm_service.generate = AsyncMock(return_value=mock_result)

        # 执行
        content = await service.generate_chapter(
            novel_id="test-novel",
            chapter_number=2,
            outline="主角遇到张三"
        )

        # 验证
        assert content == "包含人物和世界设定的章节内容..."

        # 验证 LLM 调用的 prompt 包含 Bible 信息
        call_args = mock_llm_service.generate.call_args
        prompt = call_args[0][0]
        assert isinstance(prompt, Prompt)
        assert "张三" in prompt.system
        assert "主角，勇敢的战士" in prompt.system
        assert "魔法学院" in prompt.system
        assert "培养魔法师的地方" in prompt.system
        assert "主角遇到张三" in prompt.user

    @pytest.mark.asyncio
    async def test_generate_chapter_without_bible(
        self,
        service,
        mock_llm_service,
        mock_novel_repository,
        mock_bible_repository,
        sample_novel
    ):
        """测试没有 Bible 时生成章节"""
        # 准备 mock 数据
        mock_novel_repository.get_by_id.return_value = sample_novel
        mock_bible_repository.get_by_novel_id.return_value = None

        # Mock LLM 返回
        mock_result = GenerationResult(
            content="没有 Bible 的章节内容...",
            token_usage=TokenUsage(input_tokens=80, output_tokens=150)
        )
        mock_llm_service.generate = AsyncMock(return_value=mock_result)

        # 执行
        content = await service.generate_chapter(
            novel_id="test-novel",
            chapter_number=3,
            outline="简单的情节"
        )

        # 验证
        assert content == "没有 Bible 的章节内容..."

        # 验证 prompt 不包含 Bible 信息
        call_args = mock_llm_service.generate.call_args
        prompt = call_args[0][0]
        assert isinstance(prompt, Prompt)
        assert "主要人物" not in prompt.system
        assert "世界设定" not in prompt.system
        assert "测试小说" in prompt.system

    @pytest.mark.asyncio
    async def test_generate_chapter_novel_not_found(
        self,
        service,
        mock_novel_repository,
        mock_bible_repository
    ):
        """测试小说不存在时抛出异常"""
        # 准备 mock 数据
        mock_novel_repository.get_by_id.return_value = None

        # 执行并验证
        with pytest.raises(EntityNotFoundError) as exc_info:
            await service.generate_chapter(
                novel_id="nonexistent",
                chapter_number=1,
                outline="测试大纲"
            )

        # 验证异常信息
        assert exc_info.value.entity_type == "Novel"
        assert exc_info.value.entity_id == "nonexistent"

        # 验证没有调用 Bible 仓储和 LLM
        mock_bible_repository.get_by_novel_id.assert_not_called()

    def test_build_chapter_prompt(self, service, sample_novel, sample_bible):
        """测试构建章节提示词"""
        # 执行
        prompt = service._build_chapter_prompt(
            novel=sample_novel,
            bible=sample_bible,
            chapter_number=5,
            outline="测试大纲内容"
        )

        # 验证
        assert isinstance(prompt, Prompt)

        # 验证 system message
        assert "测试小说" in prompt.system
        assert "专业的小说作家" in prompt.system
        assert "张三" in prompt.system
        assert "主角，勇敢的战士" in prompt.system
        assert "魔法学院" in prompt.system
        assert "培养魔法师的地方" in prompt.system

        # 验证 user message
        assert "第5章" in prompt.user
        assert "测试大纲内容" in prompt.user

    @pytest.mark.asyncio
    async def test_generate_chapter_empty_outline(
        self,
        service,
        mock_novel_repository
    ):
        """测试空大纲时抛出异常"""
        # 测试空字符串
        with pytest.raises(ValueError, match="Outline cannot be empty"):
            await service.generate_chapter(
                novel_id="test-novel",
                chapter_number=1,
                outline=""
            )

        # 测试只有空格
        with pytest.raises(ValueError, match="Outline cannot be empty"):
            await service.generate_chapter(
                novel_id="test-novel",
                chapter_number=1,
                outline="   "
            )

        # 验证没有调用仓储
        mock_novel_repository.get_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_chapter_llm_error(
        self,
        service,
        mock_llm_service,
        mock_novel_repository,
        mock_bible_repository,
        sample_novel
    ):
        """测试 LLM 调用失败时的异常处理"""
        # 准备 mock 数据
        mock_novel_repository.get_by_id.return_value = sample_novel
        mock_bible_repository.get_by_novel_id.return_value = None

        # Mock LLM 抛出异常
        mock_llm_service.generate = AsyncMock(side_effect=Exception("LLM service unavailable"))

        # 执行并验证
        with pytest.raises(RuntimeError, match="Failed to generate chapter"):
            await service.generate_chapter(
                novel_id="test-novel",
                chapter_number=1,
                outline="测试大纲"
            )

        # 验证调用了仓储
        mock_novel_repository.get_by_id.assert_called_once()
        mock_bible_repository.get_by_novel_id.assert_called_once()

