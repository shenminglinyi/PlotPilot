"""
章节审稿服务

负责对生成的章节内容进行一致性检查和质量审核，包括：
- 人物一致性检查（性格、外貌、能力）
- 时间线一致性检查
- 故事线连贯性检查
- 伏笔使用检查
- 改进建议生成
"""

from typing import List, Dict, Any, Optional, TYPE_CHECKING
from datetime import datetime
import logging
import os

from domain.novel.entities.chapter import Chapter
from domain.novel.repositories.chapter_repository import ChapterRepository
from domain.cast.repositories.cast_repository import CastRepository
from domain.novel.repositories.timeline_repository import TimelineRepository
from domain.novel.repositories.storyline_repository import StorylineRepository
from domain.novel.repositories.foreshadowing_repository import ForeshadowingRepository
from application.ai.llm_json_extract import parse_llm_json_to_dict
from domain.ai.services.llm_service import LLMService
from application.ai.trace_context import ensure_trace
from infrastructure.ai.generation_profiles import generation_config_from_profile
from infrastructure.ai.prompt_contract import PromptContract
from infrastructure.ai.prompt_gateway import get_prompt_gateway

if TYPE_CHECKING:
    from infrastructure.ai.chromadb_vector_store import ChromaDBVectorStore

logger = logging.getLogger(__name__)

# CPMS: 审稿提示词节点 key 映射（统一从 prompt_keys 导入）
from infrastructure.ai.prompt_keys import (
    REVIEW_CHARACTER_CONSISTENCY,
    REVIEW_TIMELINE_CONSISTENCY,
    REVIEW_STORYLINE_CONSISTENCY,
    REVIEW_FORESHADOWING_USAGE,
    REVIEW_IMPROVEMENT_SUGGESTIONS,
)

_REVIEW_PROMPT_KEYS = {
    "character": REVIEW_CHARACTER_CONSISTENCY,
    "timeline": REVIEW_TIMELINE_CONSISTENCY,
    "storyline": REVIEW_STORYLINE_CONSISTENCY,
    "foreshadowing": REVIEW_FORESHADOWING_USAGE,
    "improvement": REVIEW_IMPROVEMENT_SUGGESTIONS,
}


class ConsistencyIssue:
    """一致性问题"""

    def __init__(
        self,
        issue_type: str,  # character, timeline, storyline, foreshadowing
        severity: str,  # critical, warning, suggestion
        description: str,
        location: str,  # 问题位置描述
        suggestion: Optional[str] = None
    ):
        self.issue_type = issue_type
        self.severity = severity
        self.description = description
        self.location = location
        self.suggestion = suggestion

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issue_type": self.issue_type,
            "severity": self.severity,
            "description": self.description,
            "location": self.location,
            "suggestion": self.suggestion
        }


class ChapterReviewResult:
    """章节审稿结果"""

    def __init__(
        self,
        chapter_number: int,
        issues: List[ConsistencyIssue],
        overall_score: float,  # 0-100
        improvement_suggestions: List[str],
        reviewed_at: datetime
    ):
        self.chapter_number = chapter_number
        self.issues = issues
        self.overall_score = overall_score
        self.improvement_suggestions = improvement_suggestions
        self.reviewed_at = reviewed_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chapter_number": self.chapter_number,
            "issues": [issue.to_dict() for issue in self.issues],
            "overall_score": self.overall_score,
            "improvement_suggestions": self.improvement_suggestions,
            "reviewed_at": self.reviewed_at.isoformat()
        }


class ChapterReviewService:
    """章节审稿服务"""

    def __init__(
        self,
        chapter_repo: ChapterRepository,
        cast_repo: CastRepository,
        timeline_repo: TimelineRepository,
        storyline_repo: StorylineRepository,
        foreshadowing_repo: ForeshadowingRepository,
        vector_store: "ChromaDBVectorStore",
        llm_service: LLMService,
        model: str = ""
    ):
        self.chapter_repo = chapter_repo
        self.cast_repo = cast_repo
        self.timeline_repo = timeline_repo
        self.storyline_repo = storyline_repo
        self.foreshadowing_repo = foreshadowing_repo
        self.vector_store = vector_store
        self.llm_service = llm_service
        self.model = model or os.getenv("SYSTEM_MODEL", "")

    @staticmethod
    def _render_review_prompt(review_type: str, variables: Dict[str, Any]):
        """通过 PromptGateway 渲染审稿提示词。"""
        node_key = _REVIEW_PROMPT_KEYS.get(review_type, "")
        if not node_key:
            raise ValueError(f"未知审稿类型: {review_type}")
        return get_prompt_gateway().render(
            PromptContract(node_key=node_key, generation_profile="review_json"),
            variables,
        ).prompt

    async def review_chapter(self, novel_id: str, chapter_number: int) -> ChapterReviewResult:
        """审稿章节"""
        ensure_trace(novel_id=novel_id, stage="audit.chapter.review", stage_label="章节审稿")
        chapter = self.chapter_repo.get_by_number(novel_id, chapter_number)
        if not chapter:
            raise ValueError(f"Chapter {chapter_number} not found")

        if not chapter.content:
            raise ValueError(f"Chapter {chapter_number} has no content to review")

        issues: List[ConsistencyIssue] = []

        # 1. 人物一致性检查
        character_issues = await self._check_character_consistency(novel_id, chapter)
        issues.extend(character_issues)

        # 2. 时间线一致性检查
        timeline_issues = await self._check_timeline_consistency(novel_id, chapter)
        issues.extend(timeline_issues)

        # 3. 故事线连贯性检查
        storyline_issues = await self._check_storyline_consistency(novel_id, chapter)
        issues.extend(storyline_issues)

        # 4. 伏笔使用检查
        foreshadowing_issues = await self._check_foreshadowing_usage(novel_id, chapter)
        issues.extend(foreshadowing_issues)

        # 5. 生成改进建议
        improvement_suggestions = await self._generate_improvement_suggestions(chapter, issues)

        # 6. 计算总体评分
        overall_score = self._calculate_overall_score(issues)

        return ChapterReviewResult(
            chapter_number=chapter_number,
            issues=issues,
            overall_score=overall_score,
            improvement_suggestions=improvement_suggestions,
            reviewed_at=datetime.now()
        )

    async def _check_character_consistency(
        self,
        novel_id: str,
        chapter: Chapter
    ) -> List[ConsistencyIssue]:
        """检查人物一致性"""
        issues = []

        # 获取人物设定
        cast = self.cast_repo.get_by_novel_id(novel_id)
        if not cast:
            return issues

        # 提取章节中出现的人物
        characters_in_chapter = self._extract_characters_from_content(chapter.content)

        # 使用 LLM 检查人物一致性
        for char_name in characters_in_chapter:
            character = next((c for c in cast.characters if c.name == char_name), None)
            if not character:
                continue

            prompt = self._render_review_prompt(
                "character",
                {
                    "character_name": char_name,
                    "character_profile": character.to_dict(),
                    "chapter_content": chapter.content,
                },
            )
            config = generation_config_from_profile(
                "review_json",
                model=self.model,
            )

            result = await self.llm_service.generate(prompt, config)
            data, errs = parse_llm_json_to_dict(result.content)

            if data:
                inconsistencies = data.get("inconsistencies", [])
                for inconsistency in inconsistencies:
                    issues.append(ConsistencyIssue(
                        issue_type="character",
                        severity=inconsistency.get("severity", "warning"),
                        description=inconsistency.get("description", ""),
                        location=f"Chapter {chapter.chapter_number}",
                        suggestion=inconsistency.get("suggestion")
                    ))
            else:
                logger.warning(f"Character consistency check JSON parse failed: {errs}")

        return issues

    async def _check_timeline_consistency(
        self,
        novel_id: str,
        chapter: Chapter
    ) -> List[ConsistencyIssue]:
        """检查时间线一致性"""
        issues = []

        # 获取时间线
        timeline_registry = self.timeline_repo.get_by_novel_id(novel_id)
        if not timeline_registry:
            return issues

        # 获取当前章节的时间线事件
        current_events = [e for e in timeline_registry.events if e.chapter_number == chapter.chapter_number]

        # 获取前置章节的时间线事件
        previous_events = [e for e in timeline_registry.events if e.chapter_number < chapter.chapter_number]

        # 使用 LLM 检查时间线冲突
        if current_events and previous_events:
            current_events_str = "\n".join(
                f"- {e.description} ({e.time_type})" for e in current_events
            )
            previous_events_str = "\n".join(
                f"- {e.description} ({e.time_type})" for e in previous_events[-5:]
            )
            prompt = self._render_review_prompt(
                "timeline",
                {
                    "current_events": current_events_str,
                    "previous_events": previous_events_str,
                    "chapter_content": chapter.content[:1000],
                },
            )
            config = generation_config_from_profile(
                "review_json",
                model=self.model,
            )

            result = await self.llm_service.generate(prompt, config)
            data, errs = parse_llm_json_to_dict(result.content)

            if data:
                conflicts = data.get("conflicts", [])
                for conflict in conflicts:
                    issues.append(ConsistencyIssue(
                        issue_type="timeline",
                        severity=conflict.get("severity", "warning"),
                        description=conflict.get("description", ""),
                        location=f"Chapter {chapter.chapter_number}",
                        suggestion=conflict.get("suggestion")
                    ))
            else:
                logger.warning(f"Timeline consistency check JSON parse failed: {errs}")

        return issues

    async def _check_storyline_consistency(
        self,
        novel_id: str,
        chapter: Chapter
    ) -> List[ConsistencyIssue]:
        """检查故事线连贯性"""
        issues = []

        # 获取活跃的故事线
        active_storylines = self.storyline_repo.get_active_storylines(novel_id)

        if not active_storylines:
            return issues

        # 使用 LLM 检查故事线连贯性
        storylines_str = "\n".join(
            f"- {s.name} ({s.storyline_type}): {s.progress_summary or '无进展摘要'}"
            for s in active_storylines
        )
        prompt = self._render_review_prompt(
            "storyline",
            {
                "active_storylines": storylines_str,
                "chapter_content": chapter.content[:1000],
            },
        )
        config = generation_config_from_profile(
            "review_json",
            model=self.model,
        )

        result = await self.llm_service.generate(prompt, config)
        data, errs = parse_llm_json_to_dict(result.content)

        if data:
            gaps = data.get("gaps", [])
            for gap in gaps:
                issues.append(ConsistencyIssue(
                    issue_type="storyline",
                    severity=gap.get("severity", "suggestion"),
                    description=gap.get("description", ""),
                    location=f"Chapter {chapter.chapter_number}",
                    suggestion=gap.get("suggestion")
                ))
        else:
            logger.warning(f"Storyline consistency check JSON parse failed: {errs}")

        return issues

    async def _check_foreshadowing_usage(
        self,
        novel_id: str,
        chapter: Chapter
    ) -> List[ConsistencyIssue]:
        """检查伏笔使用"""
        issues = []

        # 获取未回收的伏笔
        unrevealed_foreshadowings = self.foreshadowing_repo.get_unrevealed(novel_id)

        if not unrevealed_foreshadowings:
            return issues

        # 使用向量检索找到相关伏笔
        relevant_foreshadowings = self.vector_store.search(
            query_text=chapter.content[:500],  # 使用章节开头作为查询
            top_k=5
        )

        # 使用 LLM 检查伏笔是否被合理使用
        if relevant_foreshadowings:
            foreshadowings_str = "\n".join(
                f"- {f.get('metadata', {}).get('description', '无描述')}"
                for f in relevant_foreshadowings
            )
            prompt = self._render_review_prompt(
                "foreshadowing",
                {
                    "foreshadowings": foreshadowings_str,
                    "chapter_content": chapter.content[:1000],
                },
            )
            config = generation_config_from_profile(
                "review_json",
                model=self.model,
            )

            result = await self.llm_service.generate(prompt, config)
            data, errs = parse_llm_json_to_dict(result.content)

            if data:
                missed_opportunities = data.get("missed_opportunities", [])
                for opportunity in missed_opportunities:
                    issues.append(ConsistencyIssue(
                        issue_type="foreshadowing",
                        severity="suggestion",
                        description=opportunity.get("description", ""),
                        location=f"Chapter {chapter.chapter_number}",
                        suggestion=opportunity.get("suggestion")
                    ))
            else:
                logger.warning(f"Foreshadowing usage check JSON parse failed: {errs}")

        return issues

    async def _generate_improvement_suggestions(
        self,
        chapter: Chapter,
        issues: List[ConsistencyIssue]
    ) -> List[str]:
        """生成改进建议"""
        suggestions = []

        # 根据问题类型分组
        critical_issues = [i for i in issues if i.severity == "critical"]
        warnings = [i for i in issues if i.severity == "warning"]

        if critical_issues:
            suggestions.append(f"发现 {len(critical_issues)} 个严重问题，建议优先修复")

        if warnings:
            suggestions.append(f"发现 {len(warnings)} 个警告，建议检查并改进")

        # 使用 LLM 生成综合改进建议
        if issues:
            issues_str = "\n".join(
                f"- [{i.severity}] {i.issue_type}: {i.description}"
                for i in issues
            )
            prompt = self._render_review_prompt(
                "improvement",
                {
                    "chapter_number": chapter.chapter_number,
                    "chapter_title": chapter.title,
                    "issues_list": issues_str,
                },
            )
            config = generation_config_from_profile(
                "review_json",
                model=self.model,
            )

            result = await self.llm_service.generate(prompt, config)
            data, errs = parse_llm_json_to_dict(result.content)

            if data:
                llm_suggestions = data.get("suggestions", [])
                suggestions.extend(llm_suggestions)
            else:
                logger.warning(f"Improvement suggestions JSON parse failed: {errs}")

        return suggestions

    def _calculate_overall_score(self, issues: List[ConsistencyIssue]) -> float:
        """计算总体评分"""
        base_score = 100.0

        for issue in issues:
            if issue.severity == "critical":
                base_score -= 15
            elif issue.severity == "warning":
                base_score -= 5
            elif issue.severity == "suggestion":
                base_score -= 2

        return max(0.0, base_score)

    def _extract_characters_from_content(self, content: str) -> List[str]:
        """从内容中提取人物名称（简化实现）"""
        # TODO: 使用 NER 或 LLM 提取人物名称
        # 这里先返回空列表，实际应该使用场记分析服务
        return []
