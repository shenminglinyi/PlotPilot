import logging
import os
from domain.ai.services.llm_service import LLMService, GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from domain.novel.value_objects.chapter_state import ChapterState
from application.ai.chapter_state_llm_contract import (
    chapter_state_payload_to_domain,
    parse_chapter_state_llm_response,
)
from infrastructure.ai.prompt_keys import CHAPTER_STATE_EXTRACTION
from infrastructure.ai.prompt_utils import render_required_prompt

logger = logging.getLogger(__name__)


class StateExtractionError(RuntimeError):
    """章节状态提取失败；禁止用空状态伪装成功。"""


class StateExtractor:
    """状态提取应用服务

    使用 LLM 从章节内容中提取结构化信息
    """

    def __init__(self, llm_service: LLMService):
        self.llm_service = llm_service

    async def extract_chapter_state(self, content: str) -> ChapterState:
        """从章节内容中提取状态

        Args:
            content: 章节内容

        Returns:
            提取的章节状态
        """
        logger.info(f"StateExtractor.extract_chapter_state: content_length={len(content)}")

        prompt = self._build_extraction_prompt(content)

        # 配置 LLM
        config = GenerationConfig(
            model=os.getenv("WRITING_MODEL", ""),
            max_tokens=4096,
            temperature=0.3
        )

        # 调用 LLM 生成
        result = await self.llm_service.generate(prompt=prompt, config=config)
        raw_response = result.content
        logger.debug(f"StateExtractor LLM raw response (first 500 chars): {raw_response[:500]}")

        payload, errors = parse_chapter_state_llm_response(raw_response)
        if payload is None:
            message = "; ".join(errors) if errors else "unknown"
            logger.error("StateExtractor: LLM 输出未通过契约校验: %s", message)
            raise StateExtractionError(f"章节状态 LLM 输出未通过契约校验: {message}")
        chapter_state = chapter_state_payload_to_domain(payload)
        logger.info(
            f"StateExtractor result: "
            f"new_characters={len(chapter_state.new_characters)}, "
            f"character_actions={len(chapter_state.character_actions)}, "
            f"relationship_changes={len(chapter_state.relationship_changes)}, "
            f"foreshadowing_planted={len(chapter_state.foreshadowing_planted)}, "
            f"foreshadowing_resolved={len(chapter_state.foreshadowing_resolved)}, "
            f"events={len(chapter_state.events)}"
        )
        return chapter_state

    def _build_extraction_prompt(self, content: str) -> Prompt:
        """构建提取提示词

        Args:
            content: 章节内容

        Returns:
            CPMS 渲染后的 Prompt
        """
        return render_required_prompt(CHAPTER_STATE_EXTRACTION, {"content": content})
