"""张力分析器服务"""
from __future__ import annotations

from typing import Dict, List, Optional

from application.ai.trace_context import ensure_trace
from application.ai.structured_json_pipeline import (
    parse_and_repair_json,
    sanitize_llm_output,
)
from application.workbench.dtos.writer_block_dto import TensionDiagnosis, TensionSlingshotRequest
from domain.novel.repositories.chapter_repository import ChapterRepository
from domain.novel.repositories.narrative_event_repository import NarrativeEventRepository
from domain.novel.repositories.plot_arc_repository import PlotArcRepository
from domain.novel.value_objects.novel_id import NovelId
from infrastructure.ai.prompt_contracts.tension_analysis_diagnosis import (
    TENSION_ANALYSIS_DIAGNOSIS_CONTRACT,
)
from infrastructure.ai.prompt_gateway import PromptGatewayValidationError, get_prompt_gateway

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
        ensure_trace(novel_id=request.novel_id, stage="analyst.tension.score", stage_label="张力评分")
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

        stuck_reason_text = request.stuck_reason.strip() if request.stuck_reason else "未提供"

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

        rendered = get_prompt_gateway().render(
            TENSION_ANALYSIS_DIAGNOSIS_CONTRACT,
            {
                "novel_id": request.novel_id,
                "chapter_number": request.chapter_number,
                "stuck_reason_text": stuck_reason_text,
                "events_text": events_text,
                "repository_context": repository_context.strip(),
                "stats_text": stats_text.strip(),
            },
        )
        return rendered.as_text()

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

        try:
            payload = get_prompt_gateway().validate_output(
                TENSION_ANALYSIS_DIAGNOSIS_CONTRACT,
                data,
            )
        except PromptGatewayValidationError as exc:
            return TensionDiagnosis(
                diagnosis=f"JSON 结构校验失败: {exc}",
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
