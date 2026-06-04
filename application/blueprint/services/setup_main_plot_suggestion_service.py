"""向导 Step 4：基于 Bible 与小说元数据，由 LLM 推演三条主线候选。"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, AsyncIterator, Dict, List, Mapping, Optional, Tuple

from domain.ai.services.llm_service import GenerationConfig, LLMService
from domain.ai.value_objects.prompt import Prompt
from application.world.services.bible_service import BibleService
from application.core.services.novel_service import NovelService
from application.blueprint.services.setup_context_builder import SetupContextBuilder
from application.ai_invocation.prompt_variables import aliases_with_dotted_variables
from application.ai.knowledge_llm_contract import parse_json_from_response

logger = logging.getLogger(__name__)

SETUP_TASK_MARKER = "setup_main_plot_options_v1"


class MainPlotSuggestionContractError(RuntimeError):
    """主线候选输出不满足合同。"""


def normalize_main_plot_options(raw: str, ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """将模型输出规范化为可落库的主线候选。"""
    try:
        raw_list = SetupMainPlotSuggestionService._parse_plot_json(raw)
        normalized = SetupMainPlotSuggestionService._normalize_options(raw_list)
        normalized = SetupMainPlotSuggestionService._complete_option_architecture(ctx, normalized)
        if len(normalized) >= 3:
            return normalized[:3]
    except Exception as e:
        logger.warning("Main plot suggestion parse failed: %s", e)
        raise MainPlotSuggestionContractError("主线候选 JSON 解析失败或结构不符合合同") from e

    raise MainPlotSuggestionContractError("主线候选数量不足：需要至少 3 条有效方案")


def _try_extract_next_plot_option(buf: str) -> Optional[Tuple[Dict[str, Any], str]]:
    """从流式 JSON buffer 中提取 plot_options 数组里的下一个完整对象。"""
    m = re.search(r'"plot_options"\s*:\s*\[', buf)
    if m is None:
        return None
    arr_start = m.end()
    depth = 0
    in_string = False
    escape_next = False
    obj_start: Optional[int] = None

    i = arr_start
    while i < len(buf):
        ch = buf[i]
        if escape_next:
            escape_next = False
            i += 1
            continue
        if ch == "\\" and in_string:
            escape_next = True
            i += 1
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            i += 1
            continue
        if in_string:
            i += 1
            continue
        if ch == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and obj_start is not None:
                obj_str = buf[obj_start:i + 1]
                try:
                    parsed = json.loads(obj_str)
                except json.JSONDecodeError:
                    return None
                rest_start = i + 1
                while rest_start < len(buf) and buf[rest_start] in " ,\n\r\t":
                    rest_start += 1
                remaining = '{"plot_options": [' + buf[rest_start:]
                return parsed, remaining
        i += 1
    return None


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
        self._context_builder = SetupContextBuilder(
            bible_service=bible_service,
            novel_service=novel_service,
        )

    def build_context(self, novel_id: str) -> Dict[str, Any]:
        """公开的向导上下文构建入口，供 AI Invocation 路由复用。"""
        return self._context_builder.build_context(novel_id)

    def _build_context(self, novel_id: str) -> Dict[str, Any]:
        return self._context_builder.build_context(novel_id)

    @staticmethod
    def _parse_plot_json(raw: str) -> List[Dict[str, Any]]:
        data = parse_json_from_response(raw)
        opts = data.get("plot_options")
        if not isinstance(opts, list):
            raise ValueError("plot_options must be a list")
        return opts

    @staticmethod
    def _normalize_options(raw_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for i, item in enumerate(raw_list[:5]):
            if not isinstance(item, dict):
                continue
            raw_sublines = item.get("sublines") or item.get("supporting_storylines") or []
            sublines: List[Dict[str, Any]] = []
            if isinstance(raw_sublines, list):
                for j, raw_sub in enumerate(raw_sublines[:4]):
                    if not isinstance(raw_sub, dict):
                        continue
                    merge_chapter = raw_sub.get("merge_chapter") or raw_sub.get("target_chapter")
                    try:
                        merge_chapter_int = int(merge_chapter) if merge_chapter is not None else 0
                    except (TypeError, ValueError):
                        merge_chapter_int = 0
                    role = str(raw_sub.get("role") or "sub").strip().lower()
                    if role not in ("sub", "dark"):
                        role = "sub"
                    sublines.append({
                        "id": str(raw_sub.get("id") or f"subline_{j + 1}")[:80],
                        "name": str(raw_sub.get("name") or raw_sub.get("title") or f"支线 {j + 1}")[:160],
                        "role": role,
                        "purpose": str(raw_sub.get("purpose") or "")[:800],
                        "description": str(raw_sub.get("description") or "")[:1200],
                        "merge_chapter": max(0, merge_chapter_int),
                        "guard": str(raw_sub.get("guard") or raw_sub.get("forbidden_drift") or "")[:800],
                    })
            oid = str(item.get("id") or f"option_{chr(ord('a') + i)}")
            out.append(
                {
                    "id": oid,
                    "type": str(item.get("type") or "")[:120],
                    "title": str(item.get("title") or f"主线方案 {i + 1}")[:200],
                    "logline": str(item.get("logline") or "")[:2000],
                    "core_conflict": str(item.get("core_conflict") or "")[:2000],
                    "starting_hook": str(item.get("starting_hook") or "")[:2000],
                    "main_axis": str(item.get("main_axis") or item.get("axis") or "")[:2000],
                    "opening_pressure": str(item.get("opening_pressure") or "")[:1200],
                    "forbidden_drift": str(item.get("forbidden_drift") or "")[:1200],
                    "sublines": sublines,
                }
            )
        return out

    @staticmethod
    def _complete_option_architecture(
        ctx: Dict[str, Any],
        options: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        target_chapters = int(ctx.get("target_chapters") or 100)
        axis = ctx.get("fusion_axis") or {}
        core_promise = str(axis.get("core_promise") or "").strip()
        central_conflict = str(axis.get("central_conflict") or "").strip()
        false_mystery = str(axis.get("false_mystery") or "").strip()
        true_mystery = str(axis.get("true_mystery") or "").strip()
        forbidden_competitors = [
            str(x).strip()
            for x in (axis.get("forbidden_mainline_competitors") or [])
            if str(x).strip()
        ]
        taboos = [
            str(x).strip()
            for x in (axis.get("taboos") or [])
            if str(x).strip()
        ]
        mode_titles = {
            "survival": "生存求证线",
            "conspiracy": "黑箱揭露线",
            "anomaly": "规则变数线",
        }
        completed: List[Dict[str, Any]] = []
        for idx, item in enumerate(options):
            mode = "survival" if idx == 0 else "conspiracy" if idx == 1 else "anomaly"
            if not item.get("main_axis"):
                if core_promise or central_conflict:
                    parts = [
                        f"{mode_titles[mode]}必须服务融合题材主轴锁。",
                    ]
                    if core_promise:
                        parts.append(f"核心承诺：{core_promise}")
                    if central_conflict:
                        parts.append(f"中心冲突：{central_conflict}")
                    item["main_axis"] = " ".join(parts)
                else:
                    item["main_axis"] = (
                        f"第一主线围绕「{item.get('core_conflict') or item.get('logline') or '核心冲突'}」持续推进，"
                        "所有支线都必须回到这个承诺。"
                    )
            if not item.get("opening_pressure"):
                hook = str(item.get("starting_hook") or "").strip()
                if hook:
                    item["opening_pressure"] = (
                        "前三章必须把开篇钩子外化为现实压力、限时风险、外部追捕、资源损失或关系代价："
                        + hook[:500]
                    )
                else:
                    item["opening_pressure"] = "前三章必须出现外部压力、限时损失或不可回避的现实行动，不能只解释设定。"
            if not item.get("forbidden_drift"):
                drift_rules = []
                if forbidden_competitors:
                    drift_rules.append(
                        "不得抬成第一主线：" + "；".join(forbidden_competitors)
                    )
                if taboos:
                    drift_rules.append("融合禁忌：" + "；".join(taboos[:2]))
                if false_mystery and true_mystery:
                    drift_rules.append(
                        f"表层谜团「{false_mystery}」只能误导或铺证，必须回收至真实谜团「{true_mystery}」。"
                    )
                if drift_rules:
                    item["forbidden_drift"] = " ".join(drift_rules)
                else:
                    item["forbidden_drift"] = "不得让新谜团、新支线或回忆说明连续抢走主角的现实行动目标。"
            if not item.get("sublines"):
                if core_promise or false_mystery or true_mystery:
                    subline_by_mode = {
                        "survival": {
                            "id": "subline_evidence_cost",
                            "name": "证据与代价线",
                            "role": "sub",
                            "purpose": "持续把主角的现实行动转化为证据、代价、通缉、关系裂痕或资源损失。",
                            "description": core_promise or central_conflict,
                            "merge_chapter": max(6, int(target_chapters * 0.22)),
                            "guard": "不能变成单纯跑图、打怪或收集设定。支线每次推进都要回到主轴锁。",
                        },
                        "conspiracy": {
                            "id": "subline_black_box_chain",
                            "name": "黑箱证据链",
                            "role": "sub",
                            "purpose": "把高层信息差、伪证和被抹除记录收束成可验证证据链。",
                            "description": true_mystery or central_conflict or core_promise,
                            "merge_chapter": max(8, int(target_chapters * 0.3)),
                            "guard": "不能让主角长期只替强势阵营执行任务，调查必须反向咬住主轴。",
                        },
                        "anomaly": {
                            "id": "subline_false_mystery",
                            "name": "表层谜团误导线",
                            "role": "dark",
                            "purpose": "把异常、误判或错误答案作为误导，反衬并保护真正第一主线的后续反转。",
                            "description": false_mystery or core_promise or central_conflict,
                            "merge_chapter": max(8, int(target_chapters * 0.26)),
                            "guard": "表层谜团不能成为第一主线或最终解释，必须回流到主轴锁。",
                        },
                    }
                    item["sublines"] = [subline_by_mode[mode]]
                else:
                    item["sublines"] = [{
                        "id": "subline_cost_chain",
                        "name": "代价回收线",
                        "role": "sub",
                        "purpose": "让主角每次推进主线都付出可见代价，并在中段汇流回核心冲突。",
                        "description": "围绕证据、关系、资源或身份风险展开，服务主线而不另开新书。",
                        "merge_chapter": max(5, int(target_chapters * 0.25)),
                        "guard": "不能连续抢走主线目标。",
                    }]
            completed.append(item)
        return completed

    def _build_prompt_and_config(self, novel_id: str) -> Tuple[Dict[str, Any], Prompt, GenerationConfig]:
        ctx = self._build_context(novel_id)
        from infrastructure.ai.prompt_keys import PLANNING_MAIN_PLOT_OPTION
        from infrastructure.ai.prompt_registry import get_prompt_registry

        theme_metadata = ctx.get("theme_metadata") if isinstance(ctx.get("theme_metadata"), dict) else {}
        genre_label = str(theme_metadata.get("genre_label") or "")
        genre_parts = [part.strip() for part in genre_label.split("/") if part.strip()]
        alias_map = {
            "novel.title": str(ctx.get("novel_title") or ""),
            "novel.premise": str(ctx.get("premise") or ""),
            "novel.genre_major": genre_parts[0] if genre_parts else "",
            "novel.genre_theme": " / ".join(genre_parts[1:]) if len(genre_parts) > 1 else "",
            "novel.genre_label": genre_label,
            "novel.world_preset": str(theme_metadata.get("world_preset") or ""),
            "novel.target_chapters": int(ctx.get("target_chapters") or 0),
            "novel.target_words_per_chapter": int(ctx.get("target_words_per_chapter") or 0),
            "plot.fusion_contract": str(ctx.get("fusion_contract") or ""),
            "characters.protagonist": ctx.get("protagonist") or {},
            "characters.list": ctx.get("characters") or ctx.get("other_characters") or [],
            "locations.list": ctx.get("locations") or [],
            "worldbuilding.style": str(ctx.get("style_hint") or ""),
            "worldbuilding.content": ctx.get("worldbuilding") or {
                key: ctx.get(key) or {}
                for key in ("core_rules", "geography", "society", "culture", "daily_life")
                if ctx.get(key)
            },
        }
        variables = aliases_with_dotted_variables(alias_map)

        registry = get_prompt_registry()
        prompt = registry.render_to_prompt(PLANNING_MAIN_PLOT_OPTION, variables)

        if not prompt:
            raise RuntimeError(f"CPMS prompt node unavailable: {PLANNING_MAIN_PLOT_OPTION}")

        config = GenerationConfig(max_tokens=8192, temperature=0.85)
        return ctx, prompt, config

    def parse_suggested_options(
        self,
        raw: str,
        *,
        ctx: Optional[Dict[str, Any]] = None,
        novel_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """把模型输出解析为三条主线候选；不满足合同时抛错阻塞。"""
        context = ctx or (self._build_context(novel_id) if novel_id else {})
        return normalize_main_plot_options(raw, context)

    async def suggest_options(self, novel_id: str) -> List[Dict[str, Any]]:
        ctx, prompt, config = self._build_prompt_and_config(novel_id)
        try:
            result = await self._llm.generate(prompt, config)
            return self.parse_suggested_options(result.content, ctx=ctx)
        except Exception as e:
            logger.warning("Main plot suggestion LLM parse failed: %s", e)
            raise MainPlotSuggestionContractError("主线候选生成失败：请检查模型输出或 CPMS 模板") from e

    async def stream_suggest_options(self, novel_id: str) -> AsyncIterator[Dict[str, Any]]:
        """流式推演主线候选：chunk 透传 + option 增量解析；不合同时返回错误事件。"""
        ctx, prompt, config = self._build_prompt_and_config(novel_id)
        buf = ""
        full_buf = ""
        parsed_options: List[Dict[str, Any]] = []
        emitted_ids: set[str] = set()
        try:
            async for chunk in self._llm.stream_generate(prompt, config):
                if not chunk:
                    continue
                buf += chunk
                full_buf += chunk
                yield {"type": "chunk", "text": chunk}
                while True:
                    extracted = _try_extract_next_plot_option(buf)
                    if extracted is None:
                        break
                    raw_item, buf = extracted
                    norm = self._normalize_options([raw_item])
                    norm = self._complete_option_architecture(ctx, norm)
                    if not norm:
                        continue
                    item = norm[0]
                    if item["id"] in emitted_ids:
                        continue
                    emitted_ids.add(item["id"])
                    parsed_options.append(item)
                    yield {"type": "option", "option": item, "index": len(parsed_options) - 1}

            if len(parsed_options) < 3:
                try:
                    raw_list = self._parse_plot_json(full_buf)
                    for item in self._complete_option_architecture(ctx, self._normalize_options(raw_list)):
                        if item["id"] in emitted_ids:
                            continue
                        emitted_ids.add(item["id"])
                        parsed_options.append(item)
                        yield {"type": "option", "option": item, "index": len(parsed_options) - 1}
                except Exception:
                    pass

            if len(parsed_options) < 3:
                raise MainPlotSuggestionContractError("主线候选数量不足：需要至少 3 条有效方案")

            yield {"type": "done", "plot_options": parsed_options[:3]}
        except Exception as e:
            logger.warning("Main plot suggestion stream failed: %s", e)
            yield {"type": "error", "message": "主线候选生成失败：请检查模型输出或 CPMS 模板", "detail": str(e)}
