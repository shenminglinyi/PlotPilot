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
import json
import logging
import os

from domain.novel.entities.chapter import Chapter
from domain.novel.repositories.chapter_repository import ChapterRepository
from domain.cast.repositories.cast_repository import CastRepository
from domain.novel.repositories.timeline_repository import TimelineRepository
from domain.novel.repositories.storyline_repository import StorylineRepository
from domain.novel.repositories.foreshadowing_repository import ForeshadowingRepository
from application.ai.llm_json_extract import parse_llm_json_to_dict
from domain.ai.services.llm_service import LLMService, GenerationConfig
from domain.ai.value_objects.prompt import Prompt

if TYPE_CHECKING:
    from infrastructure.ai.chromadb_vector_store import ChromaDBVectorStore

logger = logging.getLogger(__name__)


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

    _DEFAULT_MAX_TOKENS = 2048
    _DEFAULT_TEMPERATURE = 0.3

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

    async def review_chapter(self, novel_id: str, chapter_number: int) -> ChapterReviewResult:
        """审稿章节"""
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

            prompt_text = self._build_character_consistency_prompt(
                character_name=char_name,
                character_profile=character.to_dict(),
                chapter_content=chapter.content
            )

            prompt = Prompt(system="你是小说审稿助手，专门检查人物一致性。", user=prompt_text)
            config = GenerationConfig(
                model=self.model,
                max_tokens=self._DEFAULT_MAX_TOKENS,
                temperature=self._DEFAULT_TEMPERATURE
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
            prompt_text = self._build_timeline_consistency_prompt(
                current_events=current_events,
                previous_events=previous_events[-5:],  # 只检查最近5个事件
                chapter_content=chapter.content
            )

            prompt = Prompt(system="你是小说审稿助手，专门检查时间线一致性。", user=prompt_text)
            config = GenerationConfig(
                model=self.model,
                max_tokens=self._DEFAULT_MAX_TOKENS,
                temperature=self._DEFAULT_TEMPERATURE
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
        prompt_text = self._build_storyline_consistency_prompt(
            active_storylines=active_storylines,
            chapter_content=chapter.content
        )

        prompt = Prompt(system="你是小说审稿助手，专门检查故事线连贯性。", user=prompt_text)
        config = GenerationConfig(
            model=self.model,
            max_tokens=self._DEFAULT_MAX_TOKENS,
            temperature=self._DEFAULT_TEMPERATURE
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
            prompt_text = self._build_foreshadowing_usage_prompt(
                foreshadowings=relevant_foreshadowings,
                chapter_content=chapter.content
            )

            prompt = Prompt(system="你是小说审稿助手，专门检查伏笔使用。", user=prompt_text)
            config = GenerationConfig(
                model=self.model,
                max_tokens=self._DEFAULT_MAX_TOKENS,
                temperature=self._DEFAULT_TEMPERATURE
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
            prompt_text = self._build_improvement_suggestions_prompt(chapter, issues)

            prompt = Prompt(system="你是小说审稿助手，专门提供改进建议。", user=prompt_text)
            config = GenerationConfig(
                model=self.model,
                max_tokens=self._DEFAULT_MAX_TOKENS,
                temperature=self._DEFAULT_TEMPERATURE
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

    def _build_character_consistency_prompt(
        self,
        character_name: str,
        character_profile: Dict[str, Any],
        chapter_content: str
    ) -> str:
        """构建人物一致性检查提示词"""
        return f"""请检查以下章节内容中人物"{character_name}"的表现是否与人物设定一致。

人物设定：
{json.dumps(character_profile, ensure_ascii=False, indent=2)}

章节内容：
{chapter_content}

请以 JSON 格式返回检查结果：
{{
  "inconsistencies": [
    {{
      "severity": "critical/warning/suggestion",
      "description": "不一致的具体描述",
      "suggestion": "修改建议"
    }}
  ]
}}

如果没有发现不一致，返回空数组。"""

    def _build_timeline_consistency_prompt(
        self,
        current_events: List[Any],
        previous_events: List[Any],
        chapter_content: str
    ) -> str:
        """构建时间线一致性检查提示词"""
        current_events_str = "\n".join([f"- {e.description} ({e.time_type})" for e in current_events])
        previous_events_str = "\n".join([f"- {e.description} ({e.time_type})" for e in previous_events])

        return f"""请检查以下章节的时间线是否与之前的事件一致。

当前章节事件：
{current_events_str}

前置事件：
{previous_events_str}

章节内容：
{chapter_content[:1000]}...

请以 JSON 格式返回检查结果：
{{
  "conflicts": [
    {{
      "severity": "critical/warning",
      "description": "时间线冲突的具体描述",
      "suggestion": "修改建议"
    }}
  ]
}}

如果没有发现冲突，返回空数组。"""

    def _build_storyline_consistency_prompt(
        self,
        active_storylines: List[Any],
        chapter_content: str
    ) -> str:
        """构建故事线连贯性检查提示词"""
        storylines_str = "\n".join([
            f"- {s.name} ({s.storyline_type}): {s.progress_summary or '无进展摘要'}"
            for s in active_storylines
        ])

        return f"""请检查以下章节内容是否推进了活跃的故事线，或者是否存在故事线断裂。

活跃故事线：
{storylines_str}

章节内容：
{chapter_content[:1000]}...

请以 JSON 格式返回检查结果：
{{
  "gaps": [
    {{
      "severity": "warning/suggestion",
      "description": "故事线断裂或未推进的描述",
      "suggestion": "改进建议"
    }}
  ]
}}

如果故事线连贯，返回空数组。"""

    def _build_foreshadowing_usage_prompt(
        self,
        foreshadowings: List[Any],
        chapter_content: str
    ) -> str:
        """构建伏笔使用检查提示词"""
        foreshadowings_str = "\n".join([
            f"- {f.get('metadata', {}).get('description', 'No description')}"
            for f in foreshadowings
        ])

        return f"""请检查以下章节内容是否错过了使用相关伏笔的机会。

相关伏笔：
{foreshadowings_str}

章节内容：
{chapter_content[:1000]}...

请以 JSON 格式返回检查结果：
{{
  "missed_opportunities": [
    {{
      "description": "错过的伏笔使用机会",
      "suggestion": "如何使用该伏笔的建议"
    }}
  ]
}}

如果没有错过机会，返回空数组。"""

    def _build_improvement_suggestions_prompt(
        self,
        chapter: Chapter,
        issues: List[ConsistencyIssue]
    ) -> str:
        """构建改进建议提示词"""
        issues_str = "\n".join([
            f"- [{i.severity}] {i.issue_type}: {i.description}"
            for i in issues
        ])

        return f"""基于以下检测到的问题，请提供3-5条具体的改进建议。

章节号：{chapter.chapter_number}
章节标题：{chapter.title}

检测到的问题：
{issues_str}

请以 JSON 格式返回：
{{
  "suggestions": [
    "具体的改进建议1",
    "具体的改进建议2",
    "具体的改进建议3"
  ]
}}"""
