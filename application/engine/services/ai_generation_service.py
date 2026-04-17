"""AI 生成应用服务"""
import logging
from typing import Optional
from domain.ai.services.llm_service import LLMService, GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from domain.novel.repositories.novel_repository import NovelRepository
from domain.bible.repositories.bible_repository import BibleRepository
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.entities.novel import Novel
from domain.bible.entities.bible import Bible
from domain.shared.exceptions import EntityNotFoundError

logger = logging.getLogger(__name__)


class AIGenerationService:
    """AI 生成服务

    协调 LLM、Novel 和 Bible 领域服务，实现 AI 内容生成功能。
    """

    def __init__(
        self,
        llm_service: LLMService,
        novel_repository: NovelRepository,
        bible_repository: BibleRepository
    ):
        """初始化服务

        Args:
            llm_service: LLM 服务
            novel_repository: Novel 仓储（同步设计，应用层负责协调）
            bible_repository: Bible 仓储（同步设计，应用层负责协调）

        Note:
            仓储使用同步接口是设计决策，应用层服务负责异步协调。
            这样可以保持领域层简单，避免异步复杂性传播到领域模型。
        """
        self.llm_service = llm_service
        self.novel_repository = novel_repository
        self.bible_repository = bible_repository

    async def generate_chapter(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str
    ) -> str:
        """生成章节内容

        Args:
            novel_id: 小说 ID
            chapter_number: 章节编号
            outline: 章节大纲

        Returns:
            生成的章节内容

        Raises:
            EntityNotFoundError: 如果小说不存在
            ValueError: 如果输入参数无效
            RuntimeError: 如果 LLM 生成失败
        """
        # 验证输入
        if not outline or not outline.strip():
            raise ValueError("Outline cannot be empty")

        # 1. 获取小说
        novel = self.novel_repository.get_by_id(NovelId(novel_id))
        if novel is None:
            raise EntityNotFoundError("Novel", novel_id)

        # 2. 获取 Bible（可选）
        bible = self.bible_repository.get_by_novel_id(NovelId(novel_id))

        # 3. 构建提示词
        prompt = self._build_chapter_prompt(novel, bible, chapter_number, outline)

        # 4. 调用 LLM
        try:
            config = GenerationConfig()
            result = await self.llm_service.generate(prompt, config)
            logger.info(f"Successfully generated chapter {chapter_number} for novel {novel_id}")
            return result.content
        except Exception as e:
            logger.error(f"LLM generation failed for novel {novel_id}, chapter {chapter_number}: {str(e)}")
            raise RuntimeError(f"Failed to generate chapter: {str(e)}") from e

    def _build_chapter_prompt(
        self,
        novel: Novel,
        bible: Optional[Bible],
        chapter_number: int,
        outline: str
    ) -> Prompt:
        """构建章节生成提示词

        Args:
            novel: 小说实体
            bible: Bible 实体（可选）
            chapter_number: 章节编号
            outline: 章节大纲

        Returns:
            Prompt 对象
        """
        system_message = f"你是一位专业的小说作家，正在创作《{novel.title}》。"

        # 添加人物信息
        if bible and bible.characters:
            char_info = "\n".join([
                f"- {char.name}: {char.description}"
                for char in bible.characters
            ])
            system_message += f"\n\n主要人物：\n{char_info}"

        # 添加世界设定
        if bible and bible.world_settings:
            setting_info = "\n".join([
                f"- {setting.name}: {setting.description}"
                for setting in bible.world_settings
            ])
            system_message += f"\n\n世界设定：\n{setting_info}"

        user_message = f"请根据以下大纲创作第{chapter_number}章：\n\n{outline}"

        return Prompt(system=system_message, user=user_message)
