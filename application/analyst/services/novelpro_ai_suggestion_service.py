"""NovelPro form-field suggestion service powered by the active PP AI."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from domain.ai.services.llm_service import GenerationConfig, LLMService
from domain.ai.value_objects.prompt import Prompt


SUGGESTION_TYPE_LABELS = {
    "voice_anchor": "角色口吻/OOC 锚点",
    "voice_sample": "作者样本对",
    "relationship_event": "关系变化事件",
    "outline_node": "大纲节点状态",
    "power_rules": "战力规则",
    "power_profile": "角色战力档案",
    "power_event": "战斗/升级事件",
}


class NovelProAISuggestionService:
    """Generate editable suggestions for manual NovelPro forms."""

    def __init__(
        self,
        *,
        llm_service: LLMService,
        knowledge_service,
        bible_service,
        continuity_service,
        power_system_service,
    ) -> None:
        self.llm_service = llm_service
        self.knowledge_service = knowledge_service
        self.bible_service = bible_service
        self.continuity_service = continuity_service
        self.power_system_service = power_system_service

    async def suggest_fields(
        self,
        *,
        novel_id: str,
        suggestion_type: str,
        fields: List[str],
        chapter_number: Optional[int] = None,
        target: Optional[Dict[str, Any]] = None,
        current_values: Optional[Dict[str, Any]] = None,
        instruction: str = "",
    ) -> Dict[str, Any]:
        fields = [str(field).strip() for field in fields if str(field).strip()]
        if not fields:
            raise ValueError("fields is required")

        prompt = Prompt(
            system=(
                "你是 PlotPilot NovelPro 内部填表助手。"
                "你只为作者生成可编辑建议，不要自动保存，不要写正文。"
                "必须输出 JSON，不要 Markdown。"
            ),
            user=self._build_user_prompt(
                novel_id=novel_id,
                suggestion_type=suggestion_type,
                fields=fields,
                chapter_number=chapter_number,
                target=target or {},
                current_values=current_values or {},
                instruction=instruction,
            ),
        )
        result = await self.llm_service.generate(
            prompt,
            GenerationConfig(max_tokens=1600, temperature=0.35),
        )
        parsed = self._parse_json_object(result.content)
        suggested_fields = parsed.get("fields", parsed)
        if not isinstance(suggested_fields, dict):
            suggested_fields = {}
        clean_fields = {
            field: self._coerce_field_value(suggested_fields.get(field, ""))
            for field in fields
            if suggested_fields.get(field) is not None
        }
        return {
            "suggestion_type": suggestion_type,
            "fields": clean_fields,
            "rationale": str(parsed.get("rationale") or "").strip(),
        }

    def _build_user_prompt(
        self,
        *,
        novel_id: str,
        suggestion_type: str,
        fields: List[str],
        chapter_number: Optional[int],
        target: Dict[str, Any],
        current_values: Dict[str, Any],
        instruction: str,
    ) -> str:
        context = self._build_context(novel_id, chapter_number)
        return "\n".join(
            [
                f"小说 ID：{novel_id}",
                f"建议类型：{SUGGESTION_TYPE_LABELS.get(suggestion_type, suggestion_type)}",
                f"关注章节：{chapter_number or '最新章节'}",
                "",
                "【作品上下文】",
                context,
                "",
                "【目标对象】",
                json.dumps(target, ensure_ascii=False, indent=2),
                "",
                "【当前表单值】",
                json.dumps(current_values, ensure_ascii=False, indent=2),
                "",
                "【需要生成的字段】",
                ", ".join(fields),
                "",
                "【额外要求】",
                instruction.strip() or "根据初始设定、长期记忆、连续性提醒和战力规范给出稳妥建议。",
                "",
                "【输出 JSON 格式】",
                json.dumps(
                    {
                        "fields": {field: "这里填建议值" for field in fields},
                        "rationale": "一句话说明为什么这样建议",
                    },
                    ensure_ascii=False,
                ),
            ]
        )

    def _build_context(self, novel_id: str, chapter_number: Optional[int]) -> str:
        chunks: List[str] = []
        knowledge = self._safe_call(lambda: self.knowledge_service.get_knowledge(novel_id))
        if knowledge:
            premise = str(getattr(knowledge, "premise_lock", "") or "").strip()
            if premise:
                chunks.append(f"全书基调：{premise}")
            facts = getattr(knowledge, "facts", []) or []
            if facts:
                chunks.append("长期事实：")
                for fact in facts[:12]:
                    chunks.append(
                        f"- {getattr(fact, 'subject', '')} / {getattr(fact, 'predicate', '')} / {getattr(fact, 'object', '')}"
                    )
            chapters = sorted(getattr(knowledge, "chapters", []) or [], key=lambda item: item.chapter_id)
            if chapters:
                selected = [item for item in chapters if item.chapter_id == chapter_number] or chapters[-3:]
                chunks.append("章节记忆：")
                for chapter in selected:
                    summary = str(getattr(chapter, "summary", "") or "").strip()
                    key_events = str(getattr(chapter, "key_events", "") or "").strip()
                    chunks.append(f"- 第{chapter.chapter_id}章：{summary or key_events}")

        bible = self._safe_call(lambda: self.bible_service.get_bible_by_novel(novel_id))
        if bible:
            for attr, label in (("theme", "主题"), ("genre", "类型"), ("worldview", "世界观")):
                value = str(getattr(bible, attr, "") or "").strip()
                if value:
                    chunks.append(f"{label}：{value[:500]}")

        continuity = self._safe_call(lambda: self.continuity_service.get_overview(novel_id, chapter_number)) or {}
        if continuity:
            dropouts = continuity.get("character_dropouts") or []
            outline = continuity.get("outline_deviation") or {}
            chunks.append(
                "连续性提醒："
                f"掉线角色 {len(dropouts)}；"
                f"大纲状态 {outline.get('status') or 'unknown'}；"
                f"原因 {'；'.join(outline.get('warning_reasons') or [])}"
            )

        power = self._safe_call(lambda: self.power_system_service.get_overview(novel_id)) or {}
        if power:
            warnings = power.get("warnings") or []
            rules = power.get("rules") or {}
            chunks.append(
                "战力约束："
                f"{str(rules.get('tier_schema') or '')[:300]}；"
                f"提醒 {'；'.join(str(item.get('title') or '') for item in warnings[:5])}"
            )

        return "\n".join(chunk for chunk in chunks if str(chunk).strip()) or "暂无结构化上下文。"

    @staticmethod
    def _safe_call(factory):
        try:
            return factory()
        except Exception:
            return None

    @staticmethod
    def _parse_json_object(text: str) -> Dict[str, Any]:
        raw = str(text or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?", "", raw).strip()
            raw = re.sub(r"```$", "", raw).strip()
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                return {}
            try:
                value = json.loads(match.group(0))
                return value if isinstance(value, dict) else {}
            except json.JSONDecodeError:
                return {}

    @staticmethod
    def _coerce_field_value(value: Any) -> Any:
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False)
        return str(value).strip()
