"""张力分析器服务"""
import json
import os
from typing import Dict, List
from application.workbench.dtos.writer_block_dto import TensionSlingshotRequest, TensionDiagnosis
from domain.novel.repositories.narrative_event_repository import NarrativeEventRepository


class TensionAnalyzer:
    """张力分析器，分析卡文原因并生成破局建议"""

    def __init__(self, event_repository: NarrativeEventRepository, llm_client):
        """初始化张力分析器

        Args:
            event_repository: 叙事事件仓储
            llm_client: LLM 客户端
        """
        self.event_repository = event_repository
        self.llm_client = llm_client

    async def analyze_tension(self, request: TensionSlingshotRequest) -> TensionDiagnosis:
        """分析张力并生成建议

        Args:
            request: 张力弹弓请求

        Returns:
            张力诊断结果
        """
        # 1. 获取目标章节及前后章节的事件
        events = self.event_repository.list_up_to_chapter(
            request.novel_id,
            request.chapter_number
        )

        # 2. 统计分析
        stats = self._analyze_statistics(events, request.chapter_number)

        # 3. 构建 LLM prompt
        prompt = self._build_prompt(events, stats, request)

        # 4. 调用 LLM
        response = await self.llm_client.generate(prompt, model=os.getenv("SYSTEM_MODEL", ""))

        # 5. 解析响应
        diagnosis = self._parse_response(response)

        return diagnosis

    def _analyze_statistics(self, events: List[dict], target_chapter: int) -> Dict:
        """统计分析事件数据

        Args:
            events: 事件列表
            target_chapter: 目标章节号

        Returns:
            统计数据字典
        """
        # 筛选目标章节及前后章节
        target_events = [e for e in events if e["chapter_number"] == target_chapter]
        prev_events = [e for e in events if e["chapter_number"] == target_chapter - 1]
        next_events = [e for e in events if e["chapter_number"] == target_chapter + 1]

        # 统计冲突标签
        conflict_tags = []
        emotion_tags = []
        for event in target_events:
            tags = event.get("tags", [])
            conflict_tags.extend([t for t in tags if t.startswith("冲突:")])
            emotion_tags.extend([t for t in tags if t.startswith("情绪:")])

        # 计算事件密度
        chapter_count = len(set(e["chapter_number"] for e in events))
        event_density = len(events) / chapter_count if chapter_count > 0 else 0

        return {
            "target_event_count": len(target_events),
            "prev_event_count": len(prev_events),
            "conflict_count": len(conflict_tags),
            "emotion_diversity": len(set(emotion_tags)),
            "event_density": event_density,
            "conflict_tags": conflict_tags,
            "emotion_tags": emotion_tags
        }

    def _build_prompt(
        self,
        events: List[dict],
        stats: Dict,
        request: TensionSlingshotRequest
    ) -> str:
        """构建 LLM prompt

        Args:
            events: 事件列表
            stats: 统计数据
            request: 请求对象

        Returns:
            prompt 字符串
        """
        # 构建事件摘要
        event_summaries = []
        for event in events:
            tags_str = ", ".join(event.get("tags", []))
            event_summaries.append(
                f"第{event['chapter_number']}章: {event['event_summary']} (标签: {tags_str})"
            )

        events_text = "\n".join(event_summaries) if event_summaries else "暂无事件数据"

        # 构建统计信息
        stats_text = f"""
统计数据:
- 目标章节事件数: {stats['target_event_count']}
- 冲突标签数: {stats['conflict_count']}
- 情绪多样性: {stats['emotion_diversity']}
- 事件密度: {stats['event_density']:.2f}
- 冲突类型: {', '.join(stats['conflict_tags']) if stats['conflict_tags'] else '无'}
- 情绪类型: {', '.join(stats['emotion_tags']) if stats['emotion_tags'] else '无'}
"""

        # 构建作者自述部分
        stuck_reason_text = ""
        if request.stuck_reason:
            stuck_reason_text = f"\n作者自述的卡文原因: {request.stuck_reason}\n"

        prompt = f"""你是小说创作顾问，专门帮助作者突破卡文。

当前小说ID: {request.novel_id}
卡文章节: 第{request.chapter_number}章
{stuck_reason_text}
事件列表:
{events_text}

{stats_text}

请分析当前章节的张力水平，诊断卡文原因，并提供具体可操作的建议。

要求:
1. 诊断要结合统计数据和事件内容
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
        """解析 LLM 响应

        Args:
            response: LLM 响应字符串

        Returns:
            TensionDiagnosis 对象
        """
        try:
            # 尝试解析 JSON
            data = json.loads(response)
            return TensionDiagnosis(
                diagnosis=data["diagnosis"],
                tension_level=data["tension_level"],
                missing_elements=data["missing_elements"],
                suggestions=data["suggestions"]
            )
        except (json.JSONDecodeError, KeyError) as e:
            # 如果解析失败，返回默认结果
            return TensionDiagnosis(
                diagnosis=f"解析响应失败: {str(e)}",
                tension_level="low",
                missing_elements=["parse_error"],
                suggestions=["请检查 LLM 响应格式"]
            )
