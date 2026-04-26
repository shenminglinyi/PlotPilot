"""读者模拟 Agent 服务 — 模拟三类读者视角评估章节质量

核心流程：
1. 加载章节正文 + 上下文（前一章摘要、大纲）
2. 构建包含三个读者人设的 Prompt
3. 调用 LLM 获取结构化 JSON 反馈
4. 解析并转为 DTO 返回

三类读者人设：
- 硬核粉 (hardcore): 深度追更、关注伏笔/世界观一致性、不容忍逻辑漏洞
- 休闲读者 (casual): 碎片时间阅读、追求爽感和节奏、耐心有限
- 挑刺党 (nitpicker): 关注文笔/表达、指出陈词滥调、对重复描写敏感
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Optional

from application.ai.structured_json_pipeline import (
    parse_and_repair_json,
    sanitize_llm_output,
    validate_json_schema,
)
from application.reader.schema import (
    ReaderSimulationLlmPayload,
    SingleReaderFeedbackPayload,
)
from application.reader.dtos.reader_feedback_dto import (
    ChapterReaderReportDTO,
    ReaderDimensionScoresDTO,
    ReaderFeedbackDTO,
    PERSONA_LABELS,
)
from domain.novel.repositories.chapter_repository import ChapterRepository
from domain.novel.value_objects.novel_id import NovelId

logger = logging.getLogger(__name__)

_CHAPTER_EXCERPT_MAX_CHARS = 6000
_DEFAULT_MAX_TOKENS = 4096
_DEFAULT_TEMPERATURE = 0.4


def _excerpt(text: str, max_chars: int = _CHAPTER_EXCERPT_MAX_CHARS) -> str:
    """截断过长正文，保留头尾。"""
    stripped = (text or "").strip()
    if len(stripped) <= max_chars:
        return stripped
    half = max_chars // 2
    return stripped[:half] + "\n…（正文过长，已截取首尾）…\n" + stripped[-half:]


class ReaderSimulationService:
    """读者模拟 Agent 服务"""

    def __init__(
        self,
        chapter_repository: ChapterRepository,
        llm_client,
        knowledge_repository=None,
    ) -> None:
        self._chapter_repo = chapter_repository
        self._llm_client = llm_client
        self._knowledge_repo = knowledge_repository

    async def simulate(
        self,
        novel_id: str,
        chapter_number: int,
    ) -> ChapterReaderReportDTO:
        """对指定章节运行三类读者模拟。

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号

        Returns:
            ChapterReaderReportDTO 包含三个读者视角的反馈
        """
        novel_id_vo = NovelId(value=novel_id)
        chapters = self._chapter_repo.list_by_novel(novel_id_vo)
        current = next((c for c in chapters if c.number == chapter_number), None)
        if current is None:
            return self._empty_report(novel_id, chapter_number, "章节不存在")

        content = (current.content or "").strip()
        if not content:
            return self._empty_report(novel_id, chapter_number, "章节内容为空")

        # 收集上下文
        prev_chapter = next((c for c in chapters if c.number == chapter_number - 1), None)
        next_chapter = next((c for c in chapters if c.number == chapter_number + 1), None)

        # 尝试获取章节摘要
        prev_summary = ""
        if self._knowledge_repo and prev_chapter:
            try:
                knowledge = self._knowledge_repo.get_by_novel_id(novel_id)
                if knowledge:
                    ch_sum = knowledge.get_chapter(chapter_number - 1)
                    if ch_sum:
                        prev_summary = ch_sum.summary or ""
            except Exception:
                pass

        context = self._build_context(
            current_content=content,
            current_outline=current.outline or "",
            current_title=current.title or f"第{chapter_number}章",
            chapter_number=chapter_number,
            prev_summary=prev_summary,
            prev_content=_excerpt(prev_chapter.content, 2000) if prev_chapter else "",
            next_exists=next_chapter is not None,
            tension_score=current.tension_score,
        )

        prompt = self._build_prompt(context)

        # LLM 调用隔离：网络错误/超时/认证失败等均转为降级报告，
        # 让上层 API 明确感知 LLM 失败而非被通用 500 掩盖。
        try:
            response = await self._llm_client.generate(prompt)
        except Exception as e:
            logger.error(
                "读者模拟 LLM 调用失败 novel=%s ch=%d: %s",
                novel_id, chapter_number, e,
            )
            return self._empty_report(
                novel_id, chapter_number,
                f"LLM 调用失败: {type(e).__name__}: {e}",
            )

        report = self._parse_response(novel_id, chapter_number, response)
        return report

    def _build_context(
        self,
        current_content: str,
        current_outline: str,
        current_title: str,
        chapter_number: int,
        prev_summary: str,
        prev_content: str,
        next_exists: bool,
        tension_score: float,
    ) -> Dict[str, str]:
        """组装供 prompt 使用的上下文数据。"""
        parts = {
            "chapter_title": current_title,
            "chapter_number": str(chapter_number),
            "chapter_content": _excerpt(current_content),
            "chapter_outline": current_outline,
            "tension_score": f"{tension_score:.0f}",
            "has_next": "是" if next_exists else "否（本章是最新章）",
        }
        if prev_summary:
            parts["prev_summary"] = prev_summary
        elif prev_content:
            parts["prev_summary"] = prev_content
        return parts

    def _build_prompt(self, ctx: Dict[str, str]) -> str:
        prev_block = ""
        if ctx.get("prev_summary"):
            prev_block = f"\n上一章摘要/片段:\n{ctx['prev_summary']}\n"

        outline_block = ""
        if ctx.get("chapter_outline"):
            outline_block = f"\n本章大纲:\n{ctx['chapter_outline']}\n"

        return f"""你是一位专业的小说质量分析师，需要模拟三种不同类型的读者来评估章节质量。

=== 三种读者人设 ===

1. **硬核粉 (hardcore)**
   - 从第一章追到现在的深度读者
   - 关注伏笔回收、世界观一致性、角色成长合理性
   - 不容忍逻辑漏洞和人设崩塌
   - 对「填坑」和「前后呼应」特别敏感
   - 语气：认真、细致、偶尔兴奋

2. **休闲读者 (casual)**
   - 碎片时间阅读，可能跳着看
   - 追求「爽感」和情节推进速度
   - 耐心有限——3段无高潮就想划走
   - 对信息密度过高、铺垫过长容易疲倦
   - 语气：随意、直接、"看得爽就行"

3. **挑刺党 (nitpicker)**
   - 文笔鉴赏家，关注遣词造句质量
   - 对陈词滥调（"不由自主"、"嘴角上扬"）过敏
   - 指出重复描写、水字数、逻辑硬伤
   - 会对比同类作品打分
   - 语气：犀利、挑剔、有理有据

=== 待评估章节 ===

标题: {ctx['chapter_title']}（第{ctx['chapter_number']}章）
系统张力评分: {ctx['tension_score']}/100
是否有下一章: {ctx['has_next']}
{prev_block}{outline_block}
正文:
{ctx['chapter_content']}

=== 评估要求 ===

请从三个读者视角分别评分并给出反馈。

**四个维度** (每项 0-100):
- **suspense_retention** (悬疑保持度): 读完本章后是否想知道"接下来会怎样"
- **thrill_score** (爽感评分): 本章是否提供了令人满足的情绪高潮、反转或爽点
- **churn_risk** (劝退风险): 读者在本章后放弃此书的概率（0=绝不弃书, 100=必弃）
- **emotional_resonance** (情感共鸣度): 本章是否触动了读者情感

另外给出：
- **overall_readability** (综合可读性 0-100)
- **chapter_hook_strength** (章末钩子强度: weak/medium/strong)
- **pacing_verdict** (节奏总评，一句话)

请以 JSON 格式返回:
{{
    "feedbacks": [
        {{
            "persona": "hardcore",
            "scores": {{
                "suspense_retention": 75,
                "thrill_score": 60,
                "churn_risk": 15,
                "emotional_resonance": 70
            }},
            "one_line_verdict": "一句话总评（带该读者的口吻）",
            "highlights": ["亮点1", "亮点2"],
            "pain_points": ["痛点1"],
            "suggestions": ["建议1"]
        }},
        {{
            "persona": "casual",
            "scores": {{ ... }},
            "one_line_verdict": "...",
            "highlights": [...],
            "pain_points": [...],
            "suggestions": [...]
        }},
        {{
            "persona": "nitpicker",
            "scores": {{ ... }},
            "one_line_verdict": "...",
            "highlights": [...],
            "pain_points": [...],
            "suggestions": [...]
        }}
    ],
    "overall_readability": 72,
    "chapter_hook_strength": "strong",
    "pacing_verdict": "节奏总评一句话"
}}"""

    def _parse_response(
        self,
        novel_id: str,
        chapter_number: int,
        response: str,
    ) -> ChapterReaderReportDTO:
        """解析 LLM 响应为 DTO。"""
        cleaned = sanitize_llm_output(response)
        data, parse_errors = parse_and_repair_json(cleaned)

        if data is None:
            logger.warning(
                "读者模拟 JSON 解析失败 novel=%s ch=%d: %s",
                novel_id, chapter_number, "; ".join(parse_errors[:4]),
            )
            return self._empty_report(
                novel_id, chapter_number,
                "LLM 返回无法解析: " + "; ".join(parse_errors[:2]),
            )

        payload, schema_errors = validate_json_schema(
            data, ReaderSimulationLlmPayload,
        )

        if payload is None:
            logger.warning(
                "读者模拟 Schema 校验失败 novel=%s ch=%d: %s",
                novel_id, chapter_number, "; ".join(schema_errors[:4]),
            )
            return self._empty_report(
                novel_id, chapter_number,
                "JSON 结构校验失败: " + "; ".join(schema_errors[:2]),
            )

        # 空响应保护：LLM 可能返回空对象、空字符串或拒答，
        # 这种情况下 payload.feedbacks 为空但 schema 能过（所有字段都有默认值）。
        # 此时应判定为降级而非假成功，避免 API 层返回空报告却宣称成功。
        if not payload.feedbacks:
            logger.warning(
                "读者模拟 LLM 返回空 feedbacks novel=%s ch=%d（可能是密钥缺失/模型拒答）",
                novel_id, chapter_number,
            )
            preview = (response or "").strip()[:200] or "(空响应)"
            return self._empty_report(
                novel_id, chapter_number,
                f"LLM 返回无有效读者反馈（响应预览: {preview}）",
            )

        feedbacks = []
        for fb in payload.feedbacks:
            feedbacks.append(ReaderFeedbackDTO(
                persona=fb.persona,
                persona_label=PERSONA_LABELS.get(fb.persona, fb.persona),
                scores=ReaderDimensionScoresDTO(
                    suspense_retention=fb.scores.suspense_retention,
                    thrill_score=fb.scores.thrill_score,
                    churn_risk=fb.scores.churn_risk,
                    emotional_resonance=fb.scores.emotional_resonance,
                ),
                one_line_verdict=fb.one_line_verdict,
                highlights=list(fb.highlights),
                pain_points=list(fb.pain_points),
                suggestions=list(fb.suggestions),
            ))

        # 确保三个人设都有（缺失时填默认）
        existing_personas = {f.persona for f in feedbacks}
        for persona_key in ("hardcore", "casual", "nitpicker"):
            if persona_key not in existing_personas:
                feedbacks.append(ReaderFeedbackDTO(
                    persona=persona_key,
                    persona_label=PERSONA_LABELS.get(persona_key, persona_key),
                    scores=ReaderDimensionScoresDTO(),
                    one_line_verdict="（该读者视角的反馈未能生成）",
                ))

        return ChapterReaderReportDTO(
            novel_id=novel_id,
            chapter_number=chapter_number,
            feedbacks=feedbacks,
            overall_readability=payload.overall_readability,
            chapter_hook_strength=payload.chapter_hook_strength,
            pacing_verdict=payload.pacing_verdict,
            analyzed_at=datetime.utcnow(),
        )

    @staticmethod
    def _empty_report(
        novel_id: str,
        chapter_number: int,
        reason: str,
    ) -> ChapterReaderReportDTO:
        """生成空报告（用于异常/降级分支）。

        所有降级分支（章节不存在、LLM 失败、JSON 解析失败、Schema 校验失败）
        均走此入口，标记 is_fallback=True 让 API 层能精准识别并拒绝持久化
        假数据。
        """
        feedbacks = []
        for persona_key in ("hardcore", "casual", "nitpicker"):
            feedbacks.append(ReaderFeedbackDTO(
                persona=persona_key,
                persona_label=PERSONA_LABELS.get(persona_key, persona_key),
                scores=ReaderDimensionScoresDTO(),
                one_line_verdict=reason,
            ))
        return ChapterReaderReportDTO(
            novel_id=novel_id,
            chapter_number=chapter_number,
            feedbacks=feedbacks,
            pacing_verdict=reason,
            analyzed_at=datetime.utcnow(),
            is_fallback=True,
            error_message=reason,
        )
