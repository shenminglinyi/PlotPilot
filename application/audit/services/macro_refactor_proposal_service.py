"""Macro Refactor Proposal Service - 使用 LLM 生成重构建议"""
import logging
import os
from typing import Dict, Any
from application.audit.dtos.macro_refactor_dto import RefactorProposalRequest, RefactorProposal
from application.ai.llm_json_extract import parse_llm_json_to_dict
from application.ai.trace_context import ensure_trace
from domain.ai.services.llm_service import LLMService, GenerationConfig
from domain.ai.value_objects.prompt import Prompt

logger = logging.getLogger(__name__)


class MacroRefactorProposalService:
    """宏观重构提案服务 - 使用 LLM 生成修复建议"""

    def __init__(self, llm_service: LLMService):
        """初始化服务

        Args:
            llm_service: LLM 服务实例
        """
        self.llm_service = llm_service

    async def generate_proposal(self, request: RefactorProposalRequest) -> RefactorProposal:
        """生成重构提案

        Args:
            request: 提案请求

        Returns:
            RefactorProposal: 重构提案
        """
        try:
            # 构建 LLM prompt
            prompt = self._build_prompt(request)

            config = GenerationConfig(
                model=os.getenv("SYSTEM_MODEL", ""),
                max_tokens=2048,
                temperature=0.7
            )

            # 调用 LLM
            ensure_trace(novel_id="", stage="audit.macro.refactor", stage_label="宏观重构")
            result = await self.llm_service.generate(prompt, config)

            # 解析 JSON 响应
            data, errors = parse_llm_json_to_dict(result.content)

            if errors or not data:
                logger.warning(f"Failed to parse LLM response: {errors}")
                return self._create_fallback_proposal()

            # 构建提案对象
            return RefactorProposal(
                natural_language_suggestion=data.get("natural_language_suggestion", ""),
                suggested_mutations=data.get("suggested_mutations", []),
                suggested_tags=data.get("suggested_tags", []),
                reasoning=data.get("reasoning", "")
            )

        except Exception as e:
            logger.error(f"Error generating proposal: {e}", exc_info=True)
            return self._create_fallback_proposal()

    def _build_prompt(self, request: RefactorProposalRequest) -> Prompt:
        """构建 LLM prompt（CPMS 统一入口）"""
        from infrastructure.ai.prompt_keys import REFACTOR_PROPOSAL_MACRO
        from infrastructure.ai.prompt_registry import get_prompt_registry

        variables = {
            "event_data": request.current_event_summary,
            "intent": request.author_intent or "",
        }

        registry = get_prompt_registry()
        prompt = registry.render_to_prompt(REFACTOR_PROPOSAL_MACRO, variables)
        if prompt:
            return prompt

        # 降级：直接拼接
        from infrastructure.ai.prompt_utils import get_prompt_system
        system = get_prompt_system(REFACTOR_PROPOSAL_MACRO)
        user = f"请分析以下事件并提供修复建议：\n\n**作者意图：**\n{request.author_intent}\n\n**当前事件摘要：**\n{request.current_event_summary}\n\n**当前标签：**\n{', '.join(request.current_tags)}\n\n**事件 ID：**\n{request.event_id}\n\n请提供修复建议（JSON 格式）："
        return Prompt(system=system, user=user)

    def _create_fallback_proposal(self) -> RefactorProposal:
        """创建降级提案（当 LLM 失败时）

        Returns:
            RefactorProposal: 降级提案
        """
        return RefactorProposal(
            natural_language_suggestion="无法生成具体建议，请手动检查事件标签和内容",
            suggested_mutations=[],
            suggested_tags=[],
            reasoning="LLM 服务暂时不可用或响应格式错误"
        )
