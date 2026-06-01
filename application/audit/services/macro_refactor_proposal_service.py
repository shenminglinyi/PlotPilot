"""Macro Refactor Proposal Service - 使用 LLM 生成重构建议"""
import logging
import os
from typing import Dict, Any
from application.audit.dtos.macro_refactor_dto import RefactorProposalRequest, RefactorProposal
from application.ai.llm_json_extract import parse_llm_json_to_dict
from domain.ai.services.llm_service import LLMService, GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from infrastructure.ai.prompt_utils import PromptTemplateUnavailable

logger = logging.getLogger(__name__)


class MacroRefactorProposalError(RuntimeError):
    """宏观重构提案生成失败。"""


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
            result = await self.llm_service.generate(prompt, config)

            # 解析 JSON 响应
            data, errors = parse_llm_json_to_dict(result.content)

            if errors or not data:
                raise MacroRefactorProposalError(f"LLM 重构提案响应无法解析: {errors}")

            # 构建提案对象
            return RefactorProposal(
                natural_language_suggestion=data.get("natural_language_suggestion", ""),
                suggested_mutations=data.get("suggested_mutations", []),
                suggested_tags=data.get("suggested_tags", []),
                reasoning=data.get("reasoning", "")
            )

        except PromptTemplateUnavailable:
            raise
        except Exception as e:
            logger.error(f"Error generating proposal: {e}", exc_info=True)
            if isinstance(e, MacroRefactorProposalError):
                raise
            raise MacroRefactorProposalError("LLM 重构提案生成失败，流程已阻塞") from e

    def _build_prompt(self, request: RefactorProposalRequest) -> Prompt:
        """构建 LLM prompt（CPMS 统一入口）"""
        from infrastructure.ai.prompt_keys import REFACTOR_PROPOSAL_MACRO
        from infrastructure.ai.prompt_utils import render_required_prompt

        variables = {
            "event_data": request.current_event_summary,
            "intent": request.author_intent or "",
        }

        return render_required_prompt(REFACTOR_PROPOSAL_MACRO, variables)
