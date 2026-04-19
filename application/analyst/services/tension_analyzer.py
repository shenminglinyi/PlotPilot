"""张力分析器服务"""
from __future__ import annotations

from typing import Dict, List, Optional

from application.ai.structured_json_pipeline import (
    parse_and_repair_json,
    sanitize_llm_output,
    validate_json_schema,
)
from application.analyst.tension.schema import TensionDiagnosisLlmPayload
from application.workbench.dtos.writer_block_dto import TensionDiagnosis, TensionSlingshotRequest
from domain.novel.repositories.chapter_repository import ChapterRepository
from domain.novel.repositories.narrative_event_repository import NarrativeEventRepository
from domain.novel.repositories.plot_arc_repository import PlotArcRepository
from domain.novel.value_objects.novel_id import NovelId

_CHAPTER_EXCERPT_MAX_CHARS = 3500


def _excerpt_chapter_text(text: str, max_chars: int = _CHAPTER_EXCERPT_MAX_CHARS) -> str:
    """截断过长正文，保留头尾以便 prompt 可控。"""
    stripped = (text or "").strip()
    if len(stripped) <= max_chars:
        return stripped
    half = max_chars // 2
    return stripped[:half] + "\n…\n" + stripped[-half:]


class TensionAnalyzer:
    """张力分析器，分析卡文原因并生成破局建议。"""

    def __init__(
        self,
        event_repository: NarrativeEventRepository,
        llm_client,
        chapter_repository: Optional[ChapterRepository] = None,
        plot_arc_repository: Optional[PlotArcRepository] = None,
    ) -> None:
        self._event_repository = event_repository
        self._llm_client = llm_client
        self._chapter_repository = chapter_repository
        self._plot_arc_repository = plot_arc_repository

    async def analyze_tension(self, request: TensionSlingshotRequest) -> TensionDiagnosis:
        events = self._event_repository.list_up_to_chapter(
            request.novel_id,
            request.chapter_number,
        )
        stats = self._analyze_statistics(events, request.chapter_number)
        extra_context = self._build_repository_context(request)
        prompt = self._build_prompt(events, stats, request, extra_context)
        response = await self._llm_client.generate(prompt)
        return self._parse_response(response)

    def _build_repository_context(self, request: TensionSlingshotRequest) -> str:
        """从章节正文与剧情弧补充可核验的上下文（仓储缺失时自动跳过）。"""
        blocks: List[str] = []
        novel_id_vo = NovelId(value=request.novel_id)

        if self._chapter_repository is not None:
            chapters = self._chapter_repository.list_by_novel(novel_id_vo)
            current = next(
                (c for c in chapters if c.number == request.chapter_number),
                None,
            )
            if current is not None:
                excerpt = _excerpt_chapter_text(current.content)
                if excerpt:
                    blocks.append(
                        f"当前章正文摘录（可能截断）:\n{excerpt}"
                    )
                blocks.append(
                    "库内章节张力字段（0–100，仅作参考）: "
                    f"tension_score={current.tension_score:.0f}, "
                    f"plot_tension={current.plot_tension:.0f}, "
                    f"emotional_tension={current.emotional_tension:.0f}, "
                    f"pacing_tension={current.pacing_tension:.0f}"
                )
            else:
                blocks.append(
                    f"库中未找到第 {request.chapter_number} 章实体，暂无正文/张力字段。"
                )

        if self._plot_arc_repository is not None:
            arc = self._plot_arc_repository.get_by_novel_id(novel_id_vo)
            if arc is not None:
                expected = arc.get_expected_tension(request.chapter_number)
                line = (
                    f"情节弧（slug={arc.slug}）按锚点插值的期望张力档位: "
                    f"{expected.name}（数值 {expected.value}，1=LOW … 4=PEAK）"
                )
                nxt = arc.get_next_plot_point(request.chapter_number)
                if nxt is not None:
                    desc = (nxt.description or "").strip()
                    if len(desc) > 220:
                        desc = desc[:220] + "…"
                    line += f"；下一剧情点: 第{nxt.chapter_number}章 — {desc}"
                blocks.append(line)
            else:
                blocks.append("库中暂无该小说的剧情弧记录。")

        return "\n\n".join(blocks) if blocks else ""

    def _analyze_statistics(self, events: List[dict], target_chapter: int) -> Dict:
        target_events = [e for e in events if e["chapter_number"] == target_chapter]
        prev_events = [e for e in events if e["chapter_number"] == target_chapter - 1]
        next_events = [e for e in events if e["chapter_number"] == target_chapter + 1]

        conflict_tags: List[str] = []
        emotion_tags: List[str] = []
        for event in target_events:
            tags = event.get("tags", [])
            conflict_tags.extend(t for t in tags if isinstance(t, str) and t.startswith("冲突:"))
            emotion_tags.extend(t for t in tags if isinstance(t, str) and t.startswith("情绪:"))

        chapters_with_data = {e["chapter_number"] for e in events}
        chapter_count = len(chapters_with_data)
        event_density = len(events) / chapter_count if chapter_count > 0 else 0.0

        return {
            "target_event_count": len(target_events),
            "prev_event_count": len(prev_events),
            "next_event_count": len(next_events),
            "conflict_count": len(conflict_tags),
            "emotion_diversity": len(set(emotion_tags)),
            "event_density": event_density,
            "chapters_with_narrative_count": chapter_count,
            "conflict_tags": conflict_tags,
            "emotion_tags": emotion_tags,
        }

    def _build_prompt(
        self,
        events: List[dict],
        stats: Dict,
        request: TensionSlingshotRequest,
        repository_context: str,
    ) -> str:
        event_summaries: List[str] = []
        for event in events:
            tags = event.get("tags", []) or []
            tags_str = ", ".join(str(t) for t in tags)
            event_summaries.append(
                f"第{event['chapter_number']}章: {event['event_summary']} (标签: {tags_str})"
            )

        events_text = "\n".join(event_summaries) if event_summaries else "暂无事件数据"

        repo_block = ""
        if repository_context.strip():
            repo_block = f"\n补充上下文（仓储）:\n{repository_context.strip()}\n"

        stuck_reason_text = ""
        if request.stuck_reason:
            stuck_reason_text = f"\n作者自述的卡文原因: {request.stuck_reason}\n"

        density_note = (
            "事件密度 = 已加载叙事事件总数 / 其中出现过的不同章节数；"
            "分母不是全书总章数。"
        )

        stats_text = f"""
统计数据:
- 目标章节事件数: {stats['target_event_count']}
- 上一章事件数: {stats['prev_event_count']}
- 下一章事件数: {stats['next_event_count']}
- 冲突标签数: {stats['conflict_count']}
- 情绪多样性（目标章不重复情绪标签数）: {stats['emotion_diversity']}
- 有叙事数据的章节数: {stats['chapters_with_narrative_count']}
- 事件密度: {stats['event_density']:.2f}（{density_note}）
- 冲突类型: {', '.join(stats['conflict_tags']) if stats['conflict_tags'] else '无'}
- 情绪类型: {', '.join(stats['emotion_tags']) if stats['emotion_tags'] else '无'}
"""

        prompt = f"""你是小说创作顾问，专门帮助作者突破卡文。

当前小说ID: {request.novel_id}
卡文章节: 第{request.chapter_number}章
{stuck_reason_text}
事件列表:
{events_text}
{repo_block}
{stats_text}

请分析当前章节的张力水平，诊断卡文原因，并提供具体可操作的建议。

要求:
1. 诊断要结合统计数据、事件内容与补充上下文（若有）
2. 张力水平分为: low（低）、medium（中）、high（高）
3. 缺失元素可能包括: conflict（冲突）、stakes（利害关系）、action（行动）、consequence（后果）、rising_tension（递增张力）、external_conflict（外部冲突）、internal_conflict（内心冲突）等
4. 建议必须是动作导向的，使用"引入"、"增加"、"设置"、"让"等动词开头
5. 建议要具体，不要泛泛而谈

请以 JSON 格式返回结果:
{{
    "diagnosis": "诊断结果（2-3句话）",
    "tension_level": "low/medium/high",
    "missing_elements": ["缺失元素1", "缺失元素2"],
    "suggestions": ["具体建议1", "具体建议2", "具体建议3"]
}}
"""

        return prompt

    def _parse_response(self, response: str) -> TensionDiagnosis:
        cleaned = sanitize_llm_output(response)
        data, parse_errors = parse_and_repair_json(cleaned)
        if data is None:
            return TensionDiagnosis(
                diagnosis="无法解析 LLM 返回的 JSON: " + "; ".join(parse_errors[:4]),
                tension_level="low",
                missing_elements=["parse_error"],
                suggestions=["请稍后重试，或检查模型输出是否被截断"],
            )

        payload, schema_errors = validate_json_schema(data, TensionDiagnosisLlmPayload)
        if payload is None:
            return TensionDiagnosis(
                diagnosis="JSON 结构校验失败: " + "; ".join(schema_errors[:6]),
                tension_level="low",
                missing_elements=["schema_error"],
                suggestions=["请稍后重试"],
            )

        return TensionDiagnosis(
            diagnosis=payload.diagnosis,
            tension_level=payload.tension_level,
            missing_elements=list(payload.missing_elements),
            suggestions=list(payload.suggestions),
        )
