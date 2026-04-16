"""向导 Step 4：基于 Bible 与小说元数据，由 LLM 推演三条主线候选。"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from domain.ai.services.llm_service import GenerationConfig, LLMService
from domain.ai.value_objects.prompt import Prompt
from application.world.services.bible_service import BibleService
from application.core.services.novel_service import NovelService
from application.ai.knowledge_llm_contract import parse_json_from_response

logger = logging.getLogger(__name__)

SETUP_TASK_MARKER = "setup_main_plot_options_v1"


class SetupMainPlotSuggestionService:
    def __init__(
        self,
        llm_service: LLMService,
        bible_service: BibleService,
        novel_service: NovelService,
    ):
        self._llm = llm_service
        self._bible_service = bible_service
        self._novel_service = novel_service

    def _build_context(self, novel_id: str) -> Dict[str, Any]:
        novel = self._novel_service.get_novel(novel_id)
        bible_dto = self._bible_service.get_bible_by_novel(novel_id)

        premise = ""
        title = ""
        target_chapters = 100
        if novel:
            premise = (novel.premise or "").strip()
            title = (novel.title or "").strip()
            target_chapters = int(novel.target_chapters or 100)

        protagonist: Optional[Dict[str, str]] = None
        other_chars: List[Dict[str, str]] = []
        locations: List[Dict[str, str]] = []
        world_lines: List[str] = []
        style_hint = ""

        if bible_dto:
            chars = bible_dto.characters or []
            prot_idx: Optional[int] = None
            for i, c in enumerate(chars):
                role = (getattr(c, "role", None) or "").strip()
                if "主角" in role or role.lower() in (
                    "protagonist",
                    "main",
                    "mc",
                    "主人公",
                ):
                    prot_idx = i
                    break
            if prot_idx is None and chars:
                prot_idx = 0
            if prot_idx is not None and chars:
                c = chars[prot_idx]
                protagonist = {
                    "name": (c.name or "").strip(),
                    "role": (getattr(c, "role", None) or "").strip(),
                    "description": (c.description or "")[:800],
                }
                for j, ch in enumerate(chars):
                    if j == prot_idx:
                        continue
                    other_chars.append(
                        {
                            "name": (ch.name or "").strip(),
                            "role": (getattr(ch, "role", None) or "").strip(),
                            "description": (ch.description or "")[:800],
                        }
                    )

            for loc in (bible_dto.locations or [])[:8]:
                locations.append(
                    {
                        "name": (loc.name or "").strip(),
                        "type": (getattr(loc, "location_type", None) or getattr(loc, "type", None) or "").strip(),
                        "description": (loc.description or "")[:400],
                    }
                )

            for ws in bible_dto.world_settings or []:
                n = (ws.name or "").strip()
                d = (ws.description or "").strip()
                if n or d:
                    world_lines.append(f"{n}: {d}"[:500])

            notes = bible_dto.style_notes or []
            if notes:
                style_hint = "；".join(
                    (f"{n.category}: {n.content}"[:200] for n in notes[:5] if n.content)
                )

        return {
            "novel_title": title,
            "premise": premise,
            "target_chapters": target_chapters,
            "protagonist": protagonist,
            "other_characters": other_chars[:6],
            "locations": locations,
            "worldview_summary": world_lines[:24],
            "style_hint": style_hint[:1200],
        }

    @staticmethod
    def _parse_plot_json(raw: str) -> List[Dict[str, Any]]:
        data = parse_json_from_response(raw)
        opts = data.get("plot_options")
        if not isinstance(opts, list):
            raise ValueError("plot_options must be a list")
        return opts

    @staticmethod
    def _normalize_options(raw_list: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        for i, item in enumerate(raw_list[:5]):
            if not isinstance(item, dict):
                continue
            oid = str(item.get("id") or f"option_{chr(ord('a') + i)}")
            out.append(
                {
                    "id": oid,
                    "type": str(item.get("type") or "")[:120],
                    "title": str(item.get("title") or f"主线方案 {i + 1}")[:200],
                    "logline": str(item.get("logline") or "")[:2000],
                    "core_conflict": str(item.get("core_conflict") or "")[:2000],
                    "starting_hook": str(item.get("starting_hook") or "")[:2000],
                }
            )
        return out

    def _fallback_options(self, ctx: Dict[str, Any]) -> List[Dict[str, str]]:
        name = (ctx.get("protagonist") or {}).get("name") or "主角"
        return [
            {
                "id": "option_a_survival",
                "type": "底层逆袭 / 生存狂飙",
                "title": "绝境中的第一枪",
                "logline": f"{name}在危机中被迫出手，卷入一场远超自身层级的对抗。",
                "core_conflict": f"{name}（资源与信息劣势）对抗试图碾压个体的结构性力量",
                "starting_hook": "一次失败的交易/任务，带回的不是解药，而是通缉与追杀。",
            },
            {
                "id": "option_b_conspiracy",
                "type": "自上而下的阴谋",
                "title": "表象之下的齿轮",
                "logline": f"{name}偶然窥见规则背后的操纵者，每一步调查都在缩小生存空间。",
                "core_conflict": f"{name}对真相的渴求 vs 维持秩序的秘密同盟",
                "starting_hook": "一份被刻意抹去的记录，让主角意识到自己活在剧本里。",
            },
            {
                "id": "option_c_anomaly",
                "type": "异类 / 变数觉醒",
                "title": "规则的裂缝",
                "logline": f"{name}身上出现违背世界常识的特质，成为各方势力争夺或清除的目标。",
                "core_conflict": f"{name}的「异常」与既有权力/知识体系的零和博弈",
                "starting_hook": "觉醒瞬间：一次濒死体验后，世界在主角眼中换了一套语法。",
            },
        ]

    async def suggest_options(self, novel_id: str) -> List[Dict[str, str]]:
        ctx = self._build_context(novel_id)
        user_blob = json.dumps(ctx, ensure_ascii=False, indent=2)

        system_prompt = """你是一位拥有十年经验的华语网络小说白金级编辑。作者已完成世界观与人物等静态设定，你需要推演 3 个截然不同、但都具有强商业张力与可读性的主线故事轴（Main Plot Options）。

推演原则：
1. 切入点差异化：
   - 选项 A：自下而上的爆发（复仇、生存危机、底层逆袭、资源争夺战）。
   - 选项 B：自上而下的阴谋（卷入高层博弈、发现世界运转的虚假或黑箱规则）。
   - 选项 C：异类/变数觉醒（主角具备颠覆当前世界规则的异常属性或认知）。
2. 张力前置：每个方案必须写清核心冲突（谁对抗谁、赌注/代价是什么）。
3. 结合输入中的世界观、主角与地点，避免空泛套路句，要有具体钩子。

JSON Schema：
{
  "plot_options": [
    {
      "id": "option_a_xxx",
      "type": "简短类型标签",
      "title": "标题（8-16字为宜）",
      "logline": "一句话故事梗概",
      "core_conflict": "核心冲突（谁 vs 谁，代价）",
      "starting_hook": "开篇钩子场景或事件"
    }
  ]
}
必须恰好包含 3 个元素，顺序对应 A/B/C 三类切入点。

请按照以下json格式进行输出，可以被Python json.loads函数解析。只给出JSON，不作解释，不作答：
```json
{
  "plot_options": []
}
```"""

        user_prompt = f"""{SETUP_TASK_MARKER}

以下为小说设定简报（JSON）：
{user_blob}

请输出仅包含 plot_options 数组的 JSON 对象。"""

        prompt = Prompt(system=system_prompt, user=user_prompt)
        config = GenerationConfig(max_tokens=2048, temperature=0.85)

        try:
            result = await self._llm.generate(prompt, config)
            raw_list = self._parse_plot_json(result.content)
            normalized = self._normalize_options(raw_list)
            if len(normalized) >= 3:
                return normalized[:3]
            if len(normalized) > 0:
                # 不足 3 条时用本地模板补足
                fb = self._fallback_options(ctx)
                merged = normalized + [x for x in fb if x["id"] not in {n["id"] for n in normalized}]
                return merged[:3]
        except Exception as e:
            logger.warning("Main plot suggestion LLM parse failed: %s", e)

        return self._fallback_options(ctx)
