"""独立多维张力分析服务。

将张力评分从 llm_chapter_extract_bundle() 的多任务 JSON 提取中拆出，
使用专门的多维 prompt（情节/情绪/节奏）进行精准分析。
"""
from __future__ import annotations

import logging

from domain.ai.services.llm_service import LLMService
from domain.novel.value_objects.tension_dimensions import TensionDimensions
from application.ai.tension_scoring_contract import (
    TensionScoringLlmPayload,
    tension_scoring_payload_to_domain,
    tension_scoring_response_format,
)
from application.ai.structured_json_pipeline import structured_json_generate
from infrastructure.ai.generation_profiles import generation_config_from_profile
from infrastructure.ai.prompt_contract import PromptContract
from infrastructure.ai.prompt_gateway import PromptGatewayError, get_prompt_gateway
from infrastructure.ai.prompt_keys import TENSION_SCORING

logger = logging.getLogger(__name__)

# 章节正文最大长度（与 llm_chapter_extract_bundle 保持一致）
_MAX_CONTENT_LENGTH = 24000

_TENSION_SCORING_CONTRACT = PromptContract(
    node_key=TENSION_SCORING,
    version="1.0.0",
    output_schema=TensionScoringLlmPayload,
    generation_profile="tension_scoring",
)


class TensionScoringService:
    """独立多维张力分析服务。

    对章节正文进行三维度（情节张力、情绪张力、节奏张力）评分，
    并通过加权公式计算综合张力分。
    """

    def __init__(self, llm_service: LLMService) -> None:
        self._llm = llm_service

    async def score_chapter(
        self,
        chapter_content: str,
        chapter_number: int,
        prev_chapter_tension: float = 50.0,
    ) -> TensionDimensions:
        """分析章节的多维张力。

        Args:
            chapter_content: 章节正文
            chapter_number: 章节号
            prev_chapter_tension: 前章综合张力（0-100），用于提供上下文基准

        Returns:
            TensionDimensions 多维张力结果
        """
        body = chapter_content.strip()
        if not body:
            return TensionDimensions.unevaluated()
        if len(body) > _MAX_CONTENT_LENGTH:
            body = body[:_MAX_CONTENT_LENGTH] + "\n\n…（正文过长已截断）"

        try:
            prompt = get_prompt_gateway().render(
                _TENSION_SCORING_CONTRACT,
                {
                    "content": body,
                    "prev_tension": f"{prev_chapter_tension:.0f}",
                },
            ).prompt
        except PromptGatewayError as exc:
            logger.warning("张力评分提示词渲染失败: %s", exc)
            return TensionDimensions.unevaluated()
        config = generation_config_from_profile(
            "tension_scoring",
            response_format=tension_scoring_response_format(),
        )

        try:
            payload = await structured_json_generate(
                llm=self._llm,
                prompt=prompt,
                config=config,
                schema_model=TensionScoringLlmPayload,
            )
        except Exception as e:
            logger.warning("张力评分管线异常: %s", e)
            payload = None

        if payload is None:
            return TensionDimensions.unevaluated()

        dims = tension_scoring_payload_to_domain(payload)
        logger.debug(
            "张力评分完成: plot=%.0f emotional=%.0f pacing=%.0f composite=%.1f",
            dims.plot_tension,
            dims.emotional_tension,
            dims.pacing_tension,
            dims.composite_score,
        )
        return dims
