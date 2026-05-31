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
from application.ai.knowledge_llm_contract import parse_json_from_response
from application.ai_invocation.variable_hub import materialize_setup_main_plot_context
from application.engine.theme.fusion_profile import FusionProfile, get_fusion_profile

logger = logging.getLogger(__name__)

SETUP_TASK_MARKER = "setup_main_plot_options_v1"


def normalize_main_plot_options(raw: str, ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    """将模型输出规范化为可落库的主线候选。"""
    try:
        raw_list = SetupMainPlotSuggestionService._parse_plot_json(raw)
        normalized = SetupMainPlotSuggestionService._normalize_options(raw_list)
        normalized = SetupMainPlotSuggestionService._complete_option_architecture(ctx, normalized)
        if len(normalized) >= 3:
            return normalized[:3]
        if len(normalized) > 0:
            fb = SetupMainPlotSuggestionService._fallback_options(ctx)
            merged = normalized + [x for x in fb if x["id"] not in {n["id"] for n in normalized}]
            return SetupMainPlotSuggestionService._complete_option_architecture(ctx, merged)[:3]
    except Exception as e:
        logger.warning("Main plot suggestion parse failed: %s", e)

    return SetupMainPlotSuggestionService._complete_option_architecture(
        ctx,
        SetupMainPlotSuggestionService._fallback_options(ctx),
    )


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

    def build_context(self, novel_id: str) -> Dict[str, Any]:
        """公开的向导上下文构建入口，供 AI Invocation 路由复用。"""
        return self._build_context(novel_id)

    def _build_context(self, novel_id: str) -> Dict[str, Any]:
        novel = self._novel_service.get_novel(novel_id)
        bible_dto = self._bible_service.get_bible_by_novel(novel_id)
        variable_context = self._load_variable_context(novel_id)

        premise = str(variable_context.get("premise") or "").strip()
        title = str(variable_context.get("novel_title") or "").strip()
        target_chapters = int(variable_context.get("target_chapters") or 0)
        target_words_per_chapter = int(variable_context.get("target_words_per_chapter") or 0)
        if not premise and novel:
            premise = (novel.premise or "").strip()
        if not title and novel:
            title = (novel.title or "").strip()
        if target_chapters <= 0 and novel:
            target_chapters = int(novel.target_chapters or 100)
        if target_chapters <= 0:
            target_chapters = 100
        theme_metadata = self._theme_metadata_from_novel(novel)
        theme_metadata.update(variable_context.get("theme_metadata") or {})
        fusion_profile = self._resolve_fusion_profile(theme_metadata, title, premise)
        fusion_contract = str(variable_context.get("fusion_contract") or "").strip()
        if not fusion_contract:
            fusion_contract = self._fusion_storyline_contract(fusion_profile)

        protagonist = self._coerce_dict(variable_context.get("protagonist")) or None
        other_chars = self._coerce_list(variable_context.get("other_characters"))
        locations = self._coerce_list(variable_context.get("locations"))
        worldview_summary = self._coerce_list(variable_context.get("worldview_summary"))
        world_lines: List[str] = [str(item).strip() for item in worldview_summary if str(item).strip()]
        worldbuilding_full = str(variable_context.get("worldbuilding_full") or "").strip()
        core_rules = self._coerce_dict(variable_context.get("core_rules"))
        geography = self._coerce_dict(variable_context.get("geography"))
        society = self._coerce_dict(variable_context.get("society"))
        culture = self._coerce_dict(variable_context.get("culture"))
        daily_life = self._coerce_dict(variable_context.get("daily_life"))
        style_hint = str(variable_context.get("style_hint") or "").strip()

        if bible_dto:
            chars = bible_dto.characters or []
            if protagonist is None:
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

            if not locations:
                for loc in (bible_dto.locations or [])[:8]:
                    locations.append(
                        {
                            "name": (loc.name or "").strip(),
                            "type": (getattr(loc, "location_type", None) or getattr(loc, "type", None) or "").strip(),
                            "description": (loc.description or "")[:400],
                        }
                    )

            if not world_lines:
                for ws in bible_dto.world_settings or []:
                    n = (ws.name or "").strip()
                    d = (ws.description or "").strip()
                    if n or d:
                        world_lines.append(f"{n}: {d}"[:500])

            if not style_hint:
                notes = bible_dto.style_notes or []
                if notes:
                    style_hint = "；".join(
                        (f"{n.category}: {n.content}"[:200] for n in notes[:5] if n.content)
                    )

        try:
            from infrastructure.persistence.database.connection import get_database
            from infrastructure.persistence.database.sqlite_ai_invocation_repository import SqliteVariableHubRepository

            variable_repo = SqliteVariableHubRepository(get_database())
            novel_context_key = f"novel_id:{novel_id}"
            for key, target in (
                ("novel.characters.protagonist", "protagonist"),
                ("novel.characters.list", "other_characters"),
                ("novel.locations.list", "locations"),
                ("novel.plot.fusion_contract", "fusion_contract"),
                ("novel.worldbuilding.full", "worldbuilding_full"),
                ("novel.worldbuilding.core_rules", "core_rules"),
                ("novel.worldbuilding.geography", "geography"),
                ("novel.worldbuilding.society", "society"),
                ("novel.worldbuilding.culture", "culture"),
                ("novel.worldbuilding.daily_life", "daily_life"),
                ("novel.style.guide", "style_hint"),
            ):
                value = variable_repo.get_value(key, novel_context_key)
                if value is None:
                    continue
                if target == "protagonist" and isinstance(value.value, dict) and protagonist is None:
                    protagonist = dict(value.value)
                elif target == "other_characters" and isinstance(value.value, list) and not other_chars:
                    other_chars = [dict(item) for item in value.value if isinstance(item, dict)]
                elif target == "locations" and isinstance(value.value, list) and not locations:
                    locations = [dict(item) for item in value.value if isinstance(item, dict)]
                elif target == "fusion_contract" and not fusion_contract:
                    fusion_contract = str(value.value or "").strip()
                elif target == "worldbuilding_full" and not worldbuilding_full:
                    worldbuilding_full = str(value.value or "")
                elif target == "core_rules" and isinstance(value.value, dict) and not core_rules:
                    core_rules = dict(value.value)
                elif target == "geography" and isinstance(value.value, dict) and not geography:
                    geography = dict(value.value)
                elif target == "society" and isinstance(value.value, dict) and not society:
                    society = dict(value.value)
                elif target == "culture" and isinstance(value.value, dict) and not culture:
                    culture = dict(value.value)
                elif target == "daily_life" and isinstance(value.value, dict) and not daily_life:
                    daily_life = dict(value.value)
                elif target == "style_hint" and not style_hint:
                    style_hint = str(value.value or "").strip()
        except Exception:
            pass

        if not worldbuilding_full:
            worldbuilding_full = "\n".join(world_lines)
        if not world_lines and worldbuilding_full:
            world_lines = [worldbuilding_full]
        if not style_hint and bible_dto:
            notes = bible_dto.style_notes or []
            if notes:
                style_hint = "；".join((f"{n.category}: {n.content}"[:200] for n in notes[:5] if n.content))

        return {
            "novel_title": title,
            "premise": premise,
            "target_chapters": target_chapters,
            "theme_metadata": theme_metadata,
            "fusion_axis": self._fusion_axis_payload(fusion_profile),
            "fusion_contract": fusion_contract,
            "protagonist": protagonist,
            "other_characters": other_chars[:6],
            "locations": locations,
            "worldview_summary": world_lines[:24],
            "style_hint": style_hint[:1200],
            "worldbuilding_full": worldbuilding_full,
            "core_rules": core_rules,
            "geography": geography,
            "society": society,
            "culture": culture,
            "daily_life": daily_life,
        }

    @staticmethod
    def _load_variable_context(novel_id: str) -> Dict[str, Any]:
        try:
            from infrastructure.persistence.database.connection import get_database
            from infrastructure.persistence.database.sqlite_ai_invocation_repository import SqliteVariableHubRepository

            variable_repo = SqliteVariableHubRepository(get_database())
        except Exception:
            return {}

        novel_context_key = f"novel_id:{novel_id}"
        context: Dict[str, Any] = {}
        for key, target in (
            ("novel.setup.title", "novel_title"),
            ("novel.setup.premise", "premise"),
            ("novel.setup.target_chapters", "target_chapters"),
            ("novel.setup.target_words_per_chapter", "target_words_per_chapter"),
            ("novel.setup.genre_label", "theme_metadata.genre_label"),
            ("novel.setup.world_preset", "theme_metadata.world_preset"),
            ("novel.characters.protagonist", "protagonist"),
            ("novel.characters.list", "other_characters"),
            ("novel.locations.list", "locations"),
            ("novel.plot.fusion_contract", "fusion_contract"),
            ("novel.worldbuilding.full", "worldbuilding_full"),
            ("novel.worldbuilding.core_rules", "core_rules"),
            ("novel.worldbuilding.geography", "geography"),
            ("novel.worldbuilding.society", "society"),
            ("novel.worldbuilding.culture", "culture"),
            ("novel.worldbuilding.daily_life", "daily_life"),
            ("novel.style.guide", "style_hint"),
        ):
            value = variable_repo.get_value(key, novel_context_key)
            if value is None:
                continue
            if target == "theme_metadata.genre_label":
                context.setdefault("theme_metadata", {})["genre_label"] = str(value.value or "")
            elif target == "theme_metadata.world_preset":
                context.setdefault("theme_metadata", {})["world_preset"] = str(value.value or "")
            else:
                context[target] = value.value
        return context

    @staticmethod
    def _coerce_dict(value: Any) -> Dict[str, Any]:
        return dict(value) if isinstance(value, Mapping) else {}

    @staticmethod
    def _coerce_list(value: Any) -> List[Any]:
        if isinstance(value, list):
            return list(value)
        if isinstance(value, tuple):
            return list(value)
        return []

    @staticmethod
    def _theme_metadata_from_novel(novel: Any) -> Dict[str, Any]:
        if not novel:
            return {}
        secondary = getattr(novel, "secondary_theme_keys", []) or []
        return {
            "genre_label": (getattr(novel, "genre_label", "") or getattr(novel, "locked_genre", "") or "").strip(),
            "world_preset": (getattr(novel, "world_preset", "") or getattr(novel, "locked_world_preset", "") or "").strip(),
            "primary_theme_key": (getattr(novel, "primary_theme_key", "") or "").strip(),
            "secondary_theme_keys": [str(x).strip() for x in secondary if str(x).strip()],
            "fusion_profile_key": (getattr(novel, "fusion_profile_key", "") or "").strip(),
            "market_track_label": (getattr(novel, "market_track_label", "") or "").strip(),
        }

    @staticmethod
    def _resolve_fusion_profile(
        theme_metadata: Dict[str, Any],
        title: str,
        premise: str,
    ) -> Optional[FusionProfile]:
        return get_fusion_profile(theme_metadata.get("fusion_profile_key"))

    @staticmethod
    def _fusion_axis_payload(profile: Optional[FusionProfile]) -> Dict[str, Any]:
        if profile is None:
            return {}
        axis = profile.axis_lock
        return {
            "label": profile.label,
            "core_promise": axis.core_promise,
            "central_conflict": axis.central_conflict,
            "false_mystery": axis.false_mystery,
            "true_mystery": axis.true_mystery,
            "forbidden_mainline_competitors": list(axis.forbidden_mainline_competitors),
            "taboos": list(profile.taboos),
        }

    @staticmethod
    def _fusion_storyline_contract(profile: Optional[FusionProfile]) -> str:
        if profile is None:
            return ""
        return (
            profile.to_context_text()
            + "\n\n【故事线推演硬约束】\n"
            + "1. 三条主线候选都必须围绕叙事主轴锁展开，不能把表层谜团抬成第一主线。\n"
            + "2. 每条候选都要写清：主角如果不行动，会失去什么具体东西。\n"
            + "3. 支线只能作为主线的误导、证据链、人物代价或阶段性阻碍，不能另起炉灶。\n"
            + "4. 角色功能锁优先于临时爽点，不能为了反转让角色无铺垫换阵营/换功能。"
        )

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

    @staticmethod
    def _fallback_options(ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
        name = (ctx.get("protagonist") or {}).get("name") or "主角"
        axis = ctx.get("fusion_axis") or {}
        core_promise = str(axis.get("core_promise") or "").strip()
        central_conflict = str(axis.get("central_conflict") or "").strip()
        false_mystery = str(axis.get("false_mystery") or "").strip()
        true_mystery = str(axis.get("true_mystery") or "").strip()
        axis_hint = core_promise or central_conflict
        mystery_hint = true_mystery or false_mystery or "规则背后的操纵者"
        return SetupMainPlotSuggestionService._complete_option_architecture(ctx, [
            {
                "id": "option_a_survival",
                "type": "底层逆袭 / 生存狂飙",
                "title": "绝境中的第一枪",
                "logline": f"{name}在危机中被迫出手，卷入一场远超自身层级的对抗；若不能拿到第一份证据，将失去身份、同伴或继续行动的资格。",
                "core_conflict": central_conflict or f"{name}（资源与信息劣势）对抗试图碾压个体的结构性力量",
                "starting_hook": "一次失败的交易/任务，带回的不是解药，而是通缉与追杀。",
                "main_axis": (
                    f"主线围绕主角从被动求生到主动兑现核心承诺展开：{axis_hint}"
                    if axis_hint
                    else "主线围绕主角从被动求生到主动撬动结构性力量展开。"
                ),
                "opening_pressure": "开篇必须有现实损失、追捕、债务、限时任务或关系危机。",
                "forbidden_drift": "支线不能连续抢走主角行动目标。",
                "sublines": [],
            },
            {
                "id": "option_b_conspiracy",
                "type": "自上而下的阴谋",
                "title": "表象之下的齿轮",
                "logline": f"{name}偶然窥见「{mystery_hint}」的一角，每一步调查都在缩小生存空间。",
                "core_conflict": central_conflict or f"{name}对真相的渴求 vs 维持秩序的秘密同盟",
                "starting_hook": "一份被刻意抹去的记录，让主角意识到自己活在剧本里。",
                "main_axis": (
                    f"主线围绕揭开黑箱规则并验证真实谜团推进：{true_mystery}"
                    if true_mystery
                    else "主线围绕揭开黑箱规则并付出代价推进。"
                ),
                "opening_pressure": "开篇要有证据消失、身份危险或外部势力压迫。",
                "forbidden_drift": "谜团必须服务核心黑箱，不能无限叠新谜。",
                "sublines": [],
            },
            {
                "id": "option_c_anomaly",
                "type": "异类 / 变数觉醒",
                "title": "规则的裂缝",
                "logline": f"{name}身上出现违背世界常识的特质，被误判为「{false_mystery or '灾源'}」，成为各方势力争夺或清除的目标。",
                "core_conflict": central_conflict or f"{name}的「异常」与既有权力/知识体系的零和博弈",
                "starting_hook": "觉醒瞬间：一次濒死体验后，世界在主角眼中换了一套语法。",
                "main_axis": (
                    f"主线围绕异常如何反证核心承诺推进：{core_promise}"
                    if core_promise
                    else "主线围绕异常能力如何改写旧规则推进。"
                ),
                "opening_pressure": "开篇异常必须立刻带来监视、争夺、清除或身份风险。",
                "forbidden_drift": "异常不能只当升级外挂，必须持续改变关系和世界规则。",
                "sublines": [],
            },
        ])

    def _build_prompt_and_config(self, novel_id: str) -> Tuple[Dict[str, Any], Prompt, GenerationConfig]:
        ctx = self._build_context(novel_id)
        user_blob = json.dumps(ctx, ensure_ascii=False, indent=2)
        protagonist = ctx.get("protagonist") or {}
        locations = ctx.get("locations") or []
        worldview_parts = []
        if ctx.get("fusion_contract"):
            worldview_parts.append("【融合题材主轴锁】\n" + str(ctx["fusion_contract"]))
        if ctx.get("worldbuilding_full"):
            worldview_parts.append("【世界观全文】\n" + str(ctx["worldbuilding_full"]))
        elif ctx.get("worldview_summary"):
            worldview_parts.append("【世界观摘要】\n" + "\n".join(ctx["worldview_summary"]))
        if ctx.get("style_hint"):
            worldview_parts.append("【文风公约】\n" + str(ctx["style_hint"]))

        from infrastructure.ai.prompt_keys import PLANNING_MAIN_PLOT_OPTION
        from infrastructure.ai.prompt_registry import get_prompt_registry

        context_blob = materialize_setup_main_plot_context(
            {
                "novel_title": ctx.get("novel_title"),
                "premise": ctx.get("premise"),
                "target_chapters": ctx.get("target_chapters"),
                "target_words_per_chapter": ctx.get("target_words_per_chapter"),
                "genre_label": (ctx.get("theme_metadata") or {}).get("genre_label", ""),
                "world_preset": (ctx.get("theme_metadata") or {}).get("world_preset", ""),
                "fusion_axis": ctx.get("fusion_axis"),
                "fusion_contract": ctx.get("fusion_contract"),
                "protagonist": protagonist,
                "other_characters": ctx.get("other_characters") or [],
                "locations": locations,
                "worldview_summary": ctx.get("worldview_summary") or [],
                "style_hint": ctx.get("style_hint") or "",
            }
        )
        variables = {
            "context_blob": context_blob,
            "worldview": "\n\n".join(worldview_parts) or user_blob,
            "protagonist": json.dumps(protagonist, ensure_ascii=False, indent=2),
            "locations": json.dumps(locations, ensure_ascii=False, indent=2),
            "fusion_contract": str(ctx.get("fusion_contract") or ""),
            "worldbuilding_full": str(ctx.get("worldbuilding_full") or ""),
            "core_rules": json.dumps(ctx.get("core_rules") or {}, ensure_ascii=False, indent=2),
            "geography": json.dumps(ctx.get("geography") or {}, ensure_ascii=False, indent=2),
            "society": json.dumps(ctx.get("society") or {}, ensure_ascii=False, indent=2),
            "culture": json.dumps(ctx.get("culture") or {}, ensure_ascii=False, indent=2),
            "daily_life": json.dumps(ctx.get("daily_life") or {}, ensure_ascii=False, indent=2),
        }

        registry = get_prompt_registry()
        prompt = registry.render_to_prompt(PLANNING_MAIN_PLOT_OPTION, variables)

        if not prompt:
            raise RuntimeError(f"CPMS prompt node unavailable: {PLANNING_MAIN_PLOT_OPTION}")

        config = GenerationConfig(max_tokens=2048, temperature=0.85)
        return ctx, prompt, config

    def parse_suggested_options(
        self,
        raw: str,
        *,
        ctx: Optional[Dict[str, Any]] = None,
        novel_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """把模型输出解析为三条主线候选；解析失败时回退到本地模板。"""
        context = ctx or (self._build_context(novel_id) if novel_id else {})
        return normalize_main_plot_options(raw, context)

    async def suggest_options(self, novel_id: str) -> List[Dict[str, Any]]:
        ctx, prompt, config = self._build_prompt_and_config(novel_id)
        try:
            result = await self._llm.generate(prompt, config)
            parsed = self.parse_suggested_options(result.content, ctx=ctx)
            if parsed:
                return parsed
        except Exception as e:
            logger.warning("Main plot suggestion LLM parse failed: %s", e)

        return self._complete_option_architecture(ctx, self._fallback_options(ctx))

    async def stream_suggest_options(self, novel_id: str) -> AsyncIterator[Dict[str, Any]]:
        """流式推演主线候选：chunk 透传 + option 增量解析 + done 兜底。"""
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
                for item in self._fallback_options(ctx):
                    if item["id"] in emitted_ids:
                        continue
                    parsed_options.append(item)
                    yield {"type": "option", "option": item, "index": len(parsed_options) - 1}
                    if len(parsed_options) >= 3:
                        break

            yield {"type": "done", "plot_options": parsed_options[:3]}
        except Exception as e:
            logger.warning("Main plot suggestion stream failed: %s", e)
            fallback = self._fallback_options(ctx)
            for idx, item in enumerate(fallback):
                yield {"type": "option", "option": item, "index": idx}
            yield {"type": "done", "plot_options": fallback}
