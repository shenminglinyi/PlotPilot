"""AI 持续规划服务

整合宏观规划、幕级规划、AI 续规划为统一的服务
"""

import json
import uuid
import logging
import re
from typing import Dict, List, Optional
from datetime import datetime
from json_repair import repair_json

from domain.structure.story_node import StoryNode, NodeType, PlanningStatus, PlanningSource
from domain.structure.chapter_element import ChapterElement, ElementType, RelationType, Importance
from domain.novel.entities.chapter import Chapter, ChapterStatus
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.chapter_id import ChapterId
from domain.novel.repositories.chapter_repository import ChapterRepository
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
from infrastructure.persistence.database.chapter_element_repository import ChapterElementRepository
from domain.ai.services.llm_service import LLMService, GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from application.audit.services.macro_merge_engine import MacroMergeEngine, MergePlan, MergeConflictException

logger = logging.getLogger(__name__)
_macro_plan_progress_store: Dict[str, Dict] = {}
_macro_plan_result_store: Dict[str, Dict] = {}


# ======================================================================
#  结构计算引擎 (Structure Calculator)
#  -------------------------------
#  唯一真相源：根据 target_chapters 计算出合理的部/卷/幕/章分布。
#  所有路径（极速模式 / 精密模式 / fallback / 动态幕生成）都必须通过本引擎
#  获取结构参数，禁止任何地方再硬编码 "3幕" 或 "5章"。
# ======================================================================


def calculate_structure_params(target_chapters: int) -> Dict:
    """根据目标总章节数，计算最优的结构参数。

    这是整个规划系统的「唯一真相源」(Single Source of Truth)。
    任何需要知道"该有几幕"、"每幕该几章"的地方都应调用此函数。

    设计原则（基于叙事工程学 + 网文商业实践）：
    - 一幕 = 一个完整的叙事弧线（激励事件 → 发展 → 高潮 → 降级），至少 5 章
    - 一卷 = 一个大的故事单元（通常 3-8 幕）
    - 一部 = 一个大阶段（起源 / 发展 / 决战）
    - 每幕章数随总篇幅增长：短篇每幕薄，长篇每幕厚（更复杂的情节需要更多篇幅展开）

    Args:
        target_chapters: 目标总章节数

    Returns:
        {
            "parts": int,              # 部数
            "volumes_per_part": int,   # 每部卷数
            "acts_per_volume": int,    # 每卷幕数
            "chapters_per_act": int,   # 每幕建议章数
            "total_acts": int,         # 总幕数
            "reasoning": str,           # 计算理由（用于日志）
        }
    """
    t = max(target_chapters, 10)

    if t <= 30:
        # 短篇：1部1卷3幕，每幕约10章（三幕剧刚好是一个完整故事）
        parts, vpp, apv = 1, 1, 3
        cpa = max(t // 3, 5)
        reason = f"短篇({t}章)：1部×1卷×3幕，每幕{cpa}章，经典三幕剧"
    elif t <= 80:
        # 中短篇：1部2-3卷，每卷3-4幕
        parts, vpp = 1, 2
        apv = 4 if t > 50 else 3
        total_acts = vpp * apv
        cpa = max(t // total_acts, 5)
        reason = f"中短篇({t}章)：{parts}部×{vpp}卷×{apv}幕={total_acts}幕，每幕{cpa}章"
    elif t <= 200:
        # 中篇：2-3部，每部2-3卷，每卷4-5幕
        parts = 2 if t <= 120 else 3
        vpp = 3 if t <= 150 else 3
        apv = 5 if t > 100 else 4
        total_acts = parts * vpp * apv
        cpa = max(t // total_acts, 6)
        reason = f"中篇({t}章)：{parts}部×{vpp}卷×{apv}幕≈{total_acts}幕，每幕{cpa}章"
    elif t <= 500:
        # 长篇：3-4部，每部3-4卷，每卷5-7幕
        parts = 3 if t <= 300 else 4
        vpp = 3 if t <= 350 else 4
        apv = 6 if t > 300 else 5
        total_acts = parts * vpp * apv
        cpa = max(t // total_acts, 8)
        reason = f"长篇({t}章)：{parts}部×{vpp}卷×{apv}幕≈{total_acts}幕，每幕{cpa}章"
    else:
        # 超长篇(500+)：4-6部，每部4-6卷，每卷6-10幕
        # 超长篇的幕只规划框架，具体幕在写作时动态生成
        # 这里给出的是"每卷建议幕数"的上限参考值
        if t <= 800:
            parts, vpp, apv = 4, 4, 7
        elif t <= 1500:
            parts, vpp, apv = 5, 5, 8
        else:
            parts, vpp, apv = 6, 6, 10
        total_acts = parts * vpp * apv
        cpa = max(t // total_acts, 10)
        reason = f"超长篇({t}章)：{parts}部×{vpp}卷×{apv}幕≈{total_acts}幕，每幕{cpa}章（动态扩展）"

    return {
        "parts": parts,
        "volumes_per_part": vpp,
        "acts_per_volume": apv,
        "chapters_per_act": cpa,
        "total_acts": parts * vpp * apv,
        "reasoning": reason,
    }


def _sanitize_llm_json_output(raw: str) -> str:
    content = (raw or "").strip()
    content = re.sub(r"\x1b\[[0-9;]*m", "", content)
    content = re.sub(r"<think\|?>.*?</think\|?>", "", content, flags=re.DOTALL)
    content = re.sub(r"<thinking>.*?</thinking>", "", content, flags=re.DOTALL)
    if "```json" in content:
        content = content.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in content:
        content = content.split("```", 1)[1].split("```", 1)[0]
    return content.strip()


def _extract_outer_json_value(text: str) -> str:
    obj_start = text.find("{")
    arr_start = text.find("[")
    if obj_start != -1:
        start = obj_start
    elif arr_start != -1:
        start = arr_start
    else:
        return text

    root_char = text[start]
    root_close = "}" if root_char == "{" else "]"
    depth = 0
    in_string = False
    escape = False

    for idx in range(start, len(text)):
        ch = text[idx]
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == root_char:
            depth += 1
            continue
        if ch == root_close:
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return text[start:]


def _repair_json_string(text: str) -> str:
    text = text.strip()
    if not text:
        return text

    try:
        json.loads(text)
        return text
    except (json.JSONDecodeError, ValueError):
        pass

    def _close_json(s: str) -> str:
        s = s.strip()
        if not s:
            return "{}"

        in_string = False
        escape = False
        stack = []
        result = []

        for ch in s:
            if escape:
                result.append(ch)
                escape = False
                continue
            if ch == "\\" and in_string:
                result.append(ch)
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                result.append(ch)
                continue
            if in_string:
                result.append(ch)
                continue
            if ch == "{":
                stack.append("}")
                result.append(ch)
                continue
            if ch == "[":
                stack.append("]")
                result.append(ch)
                continue
            if ch in "}]":
                if stack and stack[-1] == ch:
                    stack.pop()
                result.append(ch)
                continue
            result.append(ch)

        if in_string:
            result.append('"')

        repaired = "".join(result).rstrip()
        while repaired.endswith(","):
            repaired = repaired[:-1].rstrip()
        while stack:
            while repaired.endswith(","):
                repaired = repaired[:-1].rstrip()
            repaired += stack.pop()
        return repaired

    candidate = text
    retries = 15
    while retries > 0 and candidate:
        repaired = _close_json(candidate)
        try:
            json.loads(repaired)
            return repaired
        except json.JSONDecodeError:
            last_comma = candidate.rfind(",")
            if last_comma == -1:
                break
            candidate = candidate[:last_comma]
        retries -= 1
    return _close_json(text)


# 导出 MergeConflictException 供路由层使用
__all__ = ['ContinuousPlanningService', 'MergeConflictException']


def get_macro_plan_progress(novel_id: str) -> Dict:
    return _macro_plan_progress_store.get(novel_id, {
        "status": "idle",
        "current": 0,
        "total": 0,
        "percent": 0,
        "message": "",
    }).copy()


def get_macro_plan_result(novel_id: str) -> Dict:
    return _macro_plan_result_store.get(novel_id, {
        "ready": False,
        "result": None,
        "error": None,
    }).copy()


class ContinuousPlanningService:
    """AI 持续规划服务

    统一的规划服务，包含：
    1. 宏观规划：生成部-卷-幕结构框架
    2. 幕级规划：为指定幕生成章节规划
    3. AI 续规划：自动判断何时创建新幕
    """

    def __init__(
        self,
        story_node_repo: StoryNodeRepository,
        chapter_element_repo: ChapterElementRepository,
        llm_service: LLMService,
        bible_service=None,
        chapter_repository: Optional[ChapterRepository] = None,
    ):
        self.story_node_repo = story_node_repo
        self.chapter_element_repo = chapter_element_repo
        self.llm_service = llm_service
        self.bible_service = bible_service
        self.chapter_repository = chapter_repository

    # ==================== 宏观规划 ====================

    async def generate_macro_plan(
        self,
        novel_id: str,
        target_chapters: int,
        structure_preference: Optional[Dict[str, int]] = None,
    ) -> Dict:
        """生成宏观规划"""
        import time
        start_time = time.time()

        logger.info(f"Generating macro plan for novel {novel_id}")
        self._update_macro_progress(novel_id, status="running", current=0, total=0, message="正在准备结构规划")

        # 获取 Bible 信息
        bible_context = self._get_bible_context(novel_id)

        try:
            if structure_preference is None:
                # 构建提示词
                prompt = self._build_macro_planning_prompt(
                    bible_context=bible_context,
                    target_chapters=target_chapters,
                    structure_preference=structure_preference
                )

                # 调用 LLM 生成规划
                config = GenerationConfig(max_tokens=4096, temperature=0.7)
                response = await self.llm_service.generate(prompt, config)
                structure = self._parse_llm_response(response)
            else:
                structure = await self._generate_precise_macro_plan(
                    novel_id=novel_id,
                    bible_context=bible_context,
                    target_chapters=target_chapters,
                    structure_preference=structure_preference,
                )

            # 评估规划质量
            elapsed_time = time.time() - start_time
            quality_metrics = self._evaluate_macro_plan_quality(
                structure=structure,
                bible_context=bible_context,
                target_chapters=target_chapters,
                structure_preference=structure_preference
            )

            logger.info(f"[MacroPlanQuality] novel={novel_id}, time={elapsed_time:.2f}s, metrics={quality_metrics}")
            self._update_macro_progress(
                novel_id,
                status="completed",
                current=self._get_total_volumes(structure_preference),
                total=self._get_total_volumes(structure_preference),
                message="结构规划生成完成",
            )

            return {
                "success": True,
                "structure": structure.get("parts", []),
                "quality_metrics": quality_metrics,
                "generation_time": elapsed_time
            }
        except Exception:
            self._update_macro_progress(
                novel_id,
                status="failed",
                message="结构规划生成失败",
            )
            raise

    async def _generate_precise_macro_plan(
        self,
        novel_id: str,
        bible_context: Dict,
        target_chapters: int,
        structure_preference: Dict[str, int]
    ) -> Dict:
        """精密模式：系统先搭固定骨架，整版生成后再定向补全缺失字段。"""
        skeleton = self._build_precise_structure_skeleton(target_chapters, structure_preference)
        total_volumes = self._get_total_volumes(structure_preference)
        self._update_macro_progress(
            novel_id,
            status="running",
            current=0,
            total=total_volumes,
            message="正在生成整版叙事骨架",
        )

        prompt = self._build_precise_macro_prompt(
            bible_context=bible_context,
            target_chapters=target_chapters,
            structure_preference=structure_preference,
            skeleton=skeleton,
        )
        config = GenerationConfig(
            max_tokens=self._calculate_precise_max_tokens(structure_preference),
            temperature=0.7,
        )
        response = await self.llm_service.generate(prompt, config)
        updates = self._parse_llm_response(response)
        self._merge_precise_structure_updates(
            skeleton=skeleton,
            updates=updates,
            target_chapters=target_chapters,
            rebalance=False,
        )
        self._update_macro_progress(
            novel_id,
            status="running",
            current=max(total_volumes - 1, 0),
            total=total_volumes,
            message="正在检查并补全缺失字段",
        )

        incomplete_acts = self._find_incomplete_precise_acts(skeleton)
        if incomplete_acts:
            repair_prompt = self._build_precise_repair_prompt(
                bible_context=bible_context,
                target_chapters=target_chapters,
                structure_preference=structure_preference,
                incomplete_acts=incomplete_acts,
            )
            repair_config = GenerationConfig(
                max_tokens=self._calculate_precise_repair_max_tokens(incomplete_acts),
                temperature=0.5,
            )
            repair_response = await self.llm_service.generate(repair_prompt, repair_config)
            repair_updates = self._parse_llm_response(repair_response)
            self._merge_precise_structure_updates(
                skeleton=skeleton,
                updates=repair_updates,
                target_chapters=target_chapters,
                rebalance=False,
            )

        all_acts = [
            act
            for part in skeleton.get("parts", [])
            for volume in part.get("volumes", [])
            for act in volume.get("acts", [])
        ]
        self._rebalance_act_chapters(all_acts, target_chapters)
        return skeleton

    def _build_precise_structure_skeleton(
        self,
        target_chapters: int,
        structure_preference: Dict[str, int]
    ) -> Dict:
        """按用户指定网格构造固定骨架，节点数量不交给 AI 决定。"""
        parts = structure_preference.get("parts", 3)
        volumes_per_part = structure_preference.get("volumes_per_part", 3)
        acts_per_volume = structure_preference.get("acts_per_volume", 3)
        total_acts = max(parts * volumes_per_part * acts_per_volume, 1)
        avg_chapters_per_act = max(target_chapters // total_acts, 1)

        structure = {"parts": []}
        for part_index in range(1, parts + 1):
            part_node = {
                "node_id": f"P{part_index}",
                "title": f"第{part_index}部",
                "description": "",
                "volumes": [],
            }
            for volume_index in range(1, volumes_per_part + 1):
                volume_node = {
                    "node_id": f"V{part_index}_{volume_index}",
                    "title": f"第{volume_index}卷",
                    "description": "",
                    "acts": [],
                }
                for act_index in range(1, acts_per_volume + 1):
                    volume_node["acts"].append({
                        "node_id": f"A{part_index}_{volume_index}_{act_index}",
                        "title": f"第{act_index}幕",
                        "description": "",
                        "estimated_chapters": avg_chapters_per_act,
                        "narrative_goal": "",
                        "plot_points": [],
                        "key_characters": [],
                        "key_locations": [],
                        "emotional_arc": "",
                        "setup_for": [],
                        "payoff_from": [],
                    })
                part_node["volumes"].append(volume_node)
            structure["parts"].append(part_node)
        return structure

    def _merge_precise_structure_updates(
        self,
        skeleton: Dict,
        updates: Dict,
        target_chapters: int,
        rebalance: bool = True,
    ) -> Dict:
        """将 AI 返回的内容更新合并回固定骨架。"""
        node_index: Dict[str, Dict] = {}
        acts: List[Dict] = []

        for part in skeleton.get("parts", []):
            node_index[part["node_id"]] = part
            for volume in part.get("volumes", []):
                node_index[volume["node_id"]] = volume
                for act in volume.get("acts", []):
                    node_index[act["node_id"]] = act
                    acts.append(act)

        for update in updates.get("node_updates", []):
            if not isinstance(update, dict):
                continue
            node_id = str(update.get("node_id") or "").strip()
            if not node_id or node_id not in node_index:
                continue
            self._apply_precise_node_update(node_index[node_id], update)

        if rebalance:
            self._rebalance_act_chapters(acts, target_chapters)
        return skeleton

    def _apply_precise_node_update(self, node: Dict, update: Dict) -> None:
        title = str(update.get("title") or "").strip()
        description = str(update.get("description") or "").strip()
        if title:
            node["title"] = title
        if description:
            node["description"] = description

        if "estimated_chapters" in node:
            estimated = update.get("estimated_chapters")
            try:
                node["estimated_chapters"] = max(int(estimated), 0)
            except (TypeError, ValueError):
                pass
            for field in (
                "narrative_goal",
                "emotional_arc",
            ):
                value = str(update.get(field) or "").strip()
                if value:
                    node[field] = value
            for field in (
                "plot_points",
                "key_characters",
                "key_locations",
                "setup_for",
                "payoff_from",
            ):
                value = update.get(field)
                if isinstance(value, list):
                    node[field] = [str(item).strip() for item in value if str(item).strip()]

    def _rebalance_act_chapters(self, acts: List[Dict], target_chapters: int) -> None:
        """将各幕 estimated_chapters 归一到目标总章数。"""
        if not acts:
            return

        min_each = 1 if target_chapters >= len(acts) else 0
        remaining = max(target_chapters - min_each * len(acts), 0)

        weights = []
        for act in acts:
            try:
                value = int(act.get("estimated_chapters", 0) or 0)
            except (TypeError, ValueError):
                value = 0
            weights.append(max(value, 1))

        total_weight = sum(weights) or len(acts)
        scaled = [weight * remaining / total_weight for weight in weights]
        allocations = [int(value) for value in scaled]
        leftover = remaining - sum(allocations)
        remainders = sorted(
            enumerate(scaled),
            key=lambda item: item[1] - int(item[1]),
            reverse=True,
        )
        for index, _ in remainders[:leftover]:
            allocations[index] += 1

        for act, extra in zip(acts, allocations):
            act["estimated_chapters"] = min_each + extra

    def _calculate_precise_max_tokens(self, structure_preference: Dict[str, int]) -> int:
        total_volumes = self._get_total_volumes(structure_preference)
        total_acts = max(
            structure_preference.get("parts", 0)
            * structure_preference.get("volumes_per_part", 0)
            * structure_preference.get("acts_per_volume", 0),
            1,
        )
        return min(12_000, max(3_072, 2_048 + total_volumes * 400 + total_acts * 120))

    def _calculate_precise_repair_max_tokens(self, incomplete_acts: List[Dict]) -> int:
        return min(6_000, max(1_536, 768 + len(incomplete_acts) * 320))

    def _find_incomplete_precise_acts(self, skeleton: Dict) -> List[Dict]:
        required_text_fields = ("narrative_goal", "emotional_arc")
        required_list_fields = ("plot_points", "key_characters", "key_locations")
        incomplete = []
        for part in skeleton.get("parts", []):
            for volume in part.get("volumes", []):
                for act in volume.get("acts", []):
                    missing_fields = [
                        field for field in required_text_fields
                        if not str(act.get(field) or "").strip()
                    ]
                    missing_fields.extend(
                        field for field in required_list_fields
                        if not isinstance(act.get(field), list) or not act.get(field)
                    )
                    if missing_fields:
                        incomplete.append({
                            "node_id": act["node_id"],
                            "title": act.get("title", ""),
                            "description": act.get("description", ""),
                            "missing_fields": missing_fields,
                        })
        return incomplete

    def _get_total_volumes(self, structure_preference: Optional[Dict[str, int]]) -> int:
        if not structure_preference:
            return 0
        return max(
            structure_preference.get("parts", 0) * structure_preference.get("volumes_per_part", 0),
            0,
        )

    def _update_macro_progress(
        self,
        novel_id: str,
        *,
        status: str,
        current: Optional[int] = None,
        total: Optional[int] = None,
        message: Optional[str] = None,
    ) -> None:
        progress = _macro_plan_progress_store.get(novel_id, {
            "status": "idle",
            "current": 0,
            "total": 0,
            "percent": 0,
            "message": "",
        }).copy()
        progress["status"] = status
        if current is not None:
            progress["current"] = current
        if total is not None:
            progress["total"] = total
        total_value = progress.get("total", 0) or 0
        current_value = progress.get("current", 0) or 0
        progress["percent"] = round(current_value / total_value * 100, 1) if total_value else 0
        if message is not None:
            progress["message"] = message
        _macro_plan_progress_store[novel_id] = progress

    def initialize_macro_plan_task(self, novel_id: str) -> None:
        _macro_plan_result_store[novel_id] = {
            "ready": False,
            "result": None,
            "error": None,
        }
        self._update_macro_progress(
            novel_id,
            status="running",
            current=0,
            total=0,
            message="正在准备结构规划",
        )

    def store_macro_plan_result(self, novel_id: str, result: Dict) -> None:
        _macro_plan_result_store[novel_id] = {
            "ready": True,
            "result": result,
            "error": None,
        }

    def store_macro_plan_error(self, novel_id: str, error: str) -> None:
        _macro_plan_result_store[novel_id] = {
            "ready": False,
            "result": None,
            "error": error,
        }

    def _evaluate_macro_plan_quality(
        self,
        structure: Dict,
        bible_context: Dict,
        target_chapters: int,
        structure_preference: Dict[str, int]
    ) -> Dict:
        """评估宏观规划质量

        用于持续优化提示词效果，记录关键指标：
        - 结构完整性：部/卷/幕数量是否符合预期
        - 世界观融合度：Bible 元素在结构中的出现比例
        - 冲突密度：每幕是否有明确的冲突描述
        - 标题质量：标题长度、词汇多样性等
        """
        parts = structure.get("parts", [])

        # 基础统计
        part_count = len(parts)
        volume_count = sum(len(p.get("volumes", [])) for p in parts)
        act_count = sum(
            len(v.get("acts", []))
            for p in parts
            for v in p.get("volumes", [])
        )

        # 检查结构偏好匹配度
        expected_parts = structure_preference.get("parts") if structure_preference else None
        structure_match = {
            "parts_match": expected_parts is None or part_count == expected_parts,
            "expected_parts": expected_parts,
            "actual_parts": part_count
        }

        # 收集所有幕
        all_acts = []
        for p in parts:
            for v in p.get("volumes", []):
                all_acts.extend(v.get("acts", []))

        # 评估冲突密度
        acts_with_conflict = sum(
            1 for a in all_acts
            if a.get("core_conflict") and len(a.get("core_conflict", "")) > 10
        )
        conflict_density = acts_with_conflict / len(all_acts) if all_acts else 0

        # 评估世界观融合度
        bible_chars = {c.get("name", "").lower() for c in bible_context.get("characters", [])}
        bible_locations = {l.get("name", "").lower() for l in bible_context.get("locations", [])}

        char_mentions = 0
        location_mentions = 0
        for act in all_acts:
            desc = act.get("description", "").lower()
            title = act.get("title", "").lower()
            text = desc + " " + title

            for char in bible_chars:
                if char and char in text:
                    char_mentions += 1
                    break

            for loc in bible_locations:
                if loc and loc in text:
                    location_mentions += 1
                    break

        world_fusion = {
            "character_coverage": char_mentions / len(all_acts) if all_acts else 0,
            "location_coverage": location_mentions / len(all_acts) if all_acts else 0
        }

        # 评估标题质量
        titles = [a.get("title", "") for a in all_acts]
        avg_title_length = sum(len(t) for t in titles) / len(titles) if titles else 0

        # 检查标题是否包含动词（简单启发式）
        action_words = ["战", "杀", "破", "夺", "逃", "追", "救", "毁", "变", "觉醒", "背叛", "降临", "崛起", "坠落", "燃烧", "冻结", "撕裂", "缝合"]
        titles_with_action = sum(1 for t in titles if any(w in t for w in action_words))
        title_action_ratio = titles_with_action / len(titles) if titles else 0

        # 检查是否有情绪反转字段（新提示词特性）
        acts_with_emotion = sum(1 for a in all_acts if a.get("emotional_turn"))
        emotion_field_ratio = acts_with_emotion / len(all_acts) if all_acts else 0

        return {
            "structure_stats": {
                "parts": part_count,
                "volumes": volume_count,
                "acts": act_count
            },
            "structure_match": structure_match,
            "conflict_density": round(conflict_density, 2),
            "world_fusion": {
                "character_coverage": round(world_fusion["character_coverage"], 2),
                "location_coverage": round(world_fusion["location_coverage"], 2)
            },
            "title_quality": {
                "avg_length": round(avg_title_length, 1),
                "action_word_ratio": round(title_action_ratio, 2)
            },
            "prompt_version_features": {
                "emotional_turn_field": round(emotion_field_ratio, 2),
                "key_characters_field": round(sum(1 for a in all_acts if a.get("key_characters")) / len(all_acts), 2) if all_acts else 0
            }
        }

    async def confirm_macro_plan(self, novel_id: str, structure: List[Dict]) -> Dict:
        """确认宏观规划（旧版本，不安全，保留用于向后兼容）

        ⚠️ 警告：此方法不检查已有数据，可能导致僵尸节点或数据丢失
        推荐使用 confirm_macro_plan_safe() 方法
        """
        logger.warning(f"Using unsafe confirm_macro_plan for novel {novel_id}")
        logger.info(f"Confirming macro plan for novel {novel_id}")

        created_nodes = []
        order_index = 0
        part_number = 0
        volume_number = 0
        act_number = 0

        for part_data in structure:
            part_number += 1
            part_data["number"] = part_number
            part_node = self._create_node_from_data(
                novel_id, None, NodeType.PART, part_data, order_index
            )
            created_nodes.append(part_node)
            order_index += 1

            for volume_data in part_data.get("volumes", []):
                volume_number += 1
                volume_data["number"] = volume_number
                volume_node = self._create_node_from_data(
                    novel_id, part_node.id, NodeType.VOLUME, volume_data, order_index
                )
                created_nodes.append(volume_node)
                order_index += 1

                for act_data in volume_data.get("acts", []):
                    act_number += 1
                    act_data["number"] = act_number
                    act_node = self._create_node_from_data(
                        novel_id, volume_node.id, NodeType.ACT, act_data, order_index
                    )
                    created_nodes.append(act_node)
                    order_index += 1

        await self.story_node_repo.save_batch(created_nodes)

        return {
            "success": True,
            "created_nodes": len(created_nodes),
            "message": f"已创建 {len(created_nodes)} 个结构节点"
        }

    async def confirm_macro_plan_safe(self, novel_id: str, structure: List[Dict]) -> Dict:
        """安全的宏观规划确认（带血缘继承的智能合并）

        核心机制：
        1. 自底向上标记承载者（有正文的节点）
        2. 三路比对（create/update/delete）
        3. 冲突检测（红色阻断）
        4. 原子性事务执行

        Args:
            novel_id: 小说 ID
            structure: 新的宏观结构（部-卷-幕）

        Returns:
            合并结果，包含 summary（GREEN/YELLOW/RED 状态）

        Raises:
            MergeConflictException: 当新结构试图删除包含正文的节点时
        """
        logger.info(f"[SafeMerge] Starting safe macro plan confirmation for novel {novel_id}")

        # 阶段 1：深度扫描 - 获取旧结构
        old_nodes_entities = await self.story_node_repo.get_by_novel(novel_id)
        logger.info(f"[SafeMerge] Found {len(old_nodes_entities)} existing nodes")

        # 标准化旧节点：Entity → Dict（Enum 序列化）
        old_nodes = [
            {
                "id": node.id,
                "novel_id": node.novel_id,
                "parent_id": node.parent_id,
                "node_type": node.node_type.value,  # NodeType.CHAPTER → 'CHAPTER'
                "number": node.number,
                "title": node.title,
                "description": node.description,
                "order_index": node.order_index,
            }
            for node in old_nodes_entities
        ]

        # 标准化新节点：扁平化嵌套结构 → 平面列表
        new_nodes = self._flatten_structure_to_nodes(novel_id, structure)
        logger.info(f"[SafeMerge] Generated {len(new_nodes)} new nodes")

        # 阶段 2：匹配与继承 - 执行比对
        engine = MacroMergeEngine(old_nodes, new_nodes)
        plan = engine.execute_diff()
        logger.info(f"[SafeMerge] Merge plan: creates={len(plan.creates)}, updates={len(plan.updates)}, deletes={len(plan.deletes)}, conflicts={len(plan.conflicts)}")

        # 阶段 3：冲突检测 - 红色阻断
        if plan.has_fatal_conflict:
            logger.error(f"[SafeMerge] Fatal conflicts detected: {plan.conflicts}")
            raise MergeConflictException(
                message="重构导致部分已有正文的章节孤立",
                conflicts=plan.conflicts
            )

        # 阶段 4：执行合并 - 原子性事务
        logger.info(f"[SafeMerge] Applying merge plan...")
        await self.story_node_repo.apply_merge_plan(
            creates=plan.creates,
            updates=plan.updates,
            deletes=plan.deletes
        )

        logger.info(f"[SafeMerge] Merge completed successfully: {plan.summary}")
        return {
            "success": True,
            "summary": plan.summary
        }

    async def _count_macro_structure_nodes(self, novel_id: str) -> int:
        """部 / 卷 / 幕节点数量（用于落库后展示规模）。"""
        nodes = await self.story_node_repo.get_by_novel(novel_id)
        return sum(
            1
            for n in nodes
            if n.node_type in (NodeType.PART, NodeType.VOLUME, NodeType.ACT)
        )

    async def persist_macro_structure_with_fallback(
        self,
        novel_id: str,
        structure: List[Dict],
    ) -> Dict:
        """先安全合并，失败则回退为一次性写入（与全托管守护进程行为一致）。"""
        try:
            await self.confirm_macro_plan_safe(novel_id=novel_id, structure=structure)
            count = await self._count_macro_structure_nodes(novel_id)
            return {
                "success": True,
                "created_nodes": count,
                "message": f"已同步 {count} 个结构节点",
            }
        except Exception as e:
            logger.warning(
                f"[{novel_id}] confirm_macro_plan_safe 失败，回退 confirm_macro_plan：{e}"
            )
            return await self.confirm_macro_plan(novel_id=novel_id, structure=structure)

    def build_minimal_macro_structure(
        self,
        target_chapters: int,
        *,
        placeholder_description: str = (
            "系统生成的占位结构（可在审阅后于结构树中调整）"
        ),
    ) -> List[Dict]:
        """LLM 无有效输出时的最小部–卷–幕骨架（左侧规划与全托管共用）。

        不再硬编码 3 幕！改用 calculate_structure_params 动态计算。
        """
        target = max(int(target_chapters or 30), 1)
        params = calculate_structure_params(target)
        parts_count = params["parts"]
        volumes_per_part = params["volumes_per_part"]
        acts_per_volume = params["acts_per_volume"]
        chapters_per_act = params["chapters_per_act"]

        logger.info(
            f"[MinimalFallback] target={target} → "
            f"{parts_count}部×{volumes_per_part}卷×{acts_per_volume}幕, "
            f"每幕{chapters_per_act}章 ({params['reasoning']})"
        )

        structure = []
        for p in range(1, parts_count + 1):
            part_node = {
                "title": f"第{p}部",
                "description": placeholder_description,
                "volumes": [],
            }
            for v in range(1, volumes_per_part + 1):
                volume_node = {
                    "title": f"第{v}卷",
                    "description": "",
                    "acts": [],
                }
                for a in range(1, acts_per_volume + 1):
                    global_act = (p - 1) * volumes_per_part * acts_per_volume + (v - 1) * acts_per_volume + a
                    act_titles = ["开端 · 世界建立", "发展 · 冲突升级", "转折 · 陷入深渊",
                                   "高潮 · 终极对决", "收尾 · 新世界", "过渡 · 力量积蓄",
                                   "阴谋 · 暗流涌动", "觉醒 · 真相大白", "抉择 · 牺牲与重生",
                                   "终局 · 一切归零"]
                    title_prefix = act_titles[a - 1] if a <= len(act_titles) else f"第{a}幕"
                    volume_node["acts"].append({
                        "title": f"第{a}幕 · {title_prefix}",
                        "description": f"第{p}部-第{v}卷-第{a}幕叙事单元",
                        "suggested_chapter_count": chapters_per_act,
                    })
                part_node["volumes"].append(volume_node)
            structure.append(part_node)
        return structure

    async def apply_macro_plan_from_llm_result(
        self,
        llm_result: Dict,
        novel_id: str,
        target_chapters: int,
        *,
        minimal_fallback_on_empty: bool = True,
    ) -> Dict:
        """在 `generate_macro_plan` 之后统一落库：有效结构则写入，否则可选占位骨架。

        供 POST /novels/{id}/plan 与全托管守护进程共用，避免两处逻辑分叉。
        """
        struct = llm_result.get("structure") if isinstance(llm_result, dict) else None
        if llm_result.get("success") and isinstance(struct, list) and len(struct) > 0:
            confirm = await self.persist_macro_structure_with_fallback(
                novel_id, struct
            )
            return {
                "success": True,
                "created_nodes": confirm["created_nodes"],
                "used_minimal_fallback": False,
                "message": confirm.get("message", ""),
            }

        if not minimal_fallback_on_empty:
            raise ValueError(
                "宏观规划未返回有效结构（success 或 structure 无效）"
            )

        logger.warning(
            "宏观规划未返回有效结构（success=%r），使用最小占位结构 novel_id=%s",
            llm_result.get("success") if isinstance(llm_result, dict) else None,
            novel_id,
        )
        minimal = self.build_minimal_macro_structure(target_chapters)
        confirm = await self.persist_macro_structure_with_fallback(
            novel_id, minimal
        )
        return {
            "success": True,
            "created_nodes": confirm["created_nodes"],
            "used_minimal_fallback": True,
            "message": confirm.get("message", ""),
        }

    # ==================== 幕级规划 ====================

    async def plan_act_chapters(
        self, act_id: str, custom_chapter_count: Optional[int] = None
    ) -> Dict:
        """为指定幕生成章节规划"""
        logger.info(f"Planning chapters for act {act_id}")

        act_node = await self.story_node_repo.get_by_id(act_id)
        if not act_node:
            raise ValueError(f"幕节点不存在: {act_id}")

        bible_context = self._get_bible_context(act_node.novel_id)
        previous_summary = await self._get_previous_acts_summary(act_node)
        # 使用结构计算引擎的推荐值作为 fallback（替代硬编码的 5）
        _default_cpa = calculate_structure_params(100)["chapters_per_act"]
        chapter_count = custom_chapter_count or act_node.suggested_chapter_count or _default_cpa
        if not custom_chapter_count and not act_node.suggested_chapter_count:
            logger.info(
                f"[ActPlanning] act={act_id} 无自定义章数且无 suggested_chapter_count，"
                f"使用引擎推荐值 {_default_cpa}"
            )

        prompt = self._build_act_planning_prompt(
            act_node, bible_context, previous_summary, chapter_count
        )

        try:
            response = await self.llm_service.generate(
                prompt, GenerationConfig(max_tokens=4096, temperature=0.7)
            )
        except Exception as e:
            logger.warning(f"幕级规划 LLM 调用失败 act={act_id}: {e}")
            return {"success": False, "act_id": act_id, "chapters": [], "error": str(e)}

        try:
            plan = self._parse_llm_response(response)
        except Exception as e:
            logger.warning(f"幕级规划 JSON 解析失败 act={act_id}: {e}")
            return {"success": False, "act_id": act_id, "chapters": [], "parse_error": str(e)}

        if not isinstance(plan, dict):
            logger.warning(f"幕级规划解析结果非对象 act={act_id}: {type(plan)}")
            return {"success": False, "act_id": act_id, "chapters": []}

        chapters = plan.get("chapters", [])
        if not isinstance(chapters, list):
            chapters = []

        return {
            "success": True,
            "act_id": act_id,
            "chapters": chapters,
        }

    async def _remove_chapter_children_of_act(self, act_id: str) -> None:
        """同一幕再次确认规划时，先删掉本幕下已有章节节点及对应正文行、元素关联，避免重复堆积。"""
        children = self.story_node_repo.get_children_sync(act_id)
        chapter_nodes = [n for n in children if n.node_type == NodeType.CHAPTER]
        for n in chapter_nodes:
            await self.chapter_element_repo.delete_by_chapter(n.id)
            if self.chapter_repository:
                self.chapter_repository.delete(ChapterId(n.id))
            await self.story_node_repo.delete(n.id)

    async def confirm_act_planning(self, act_id: str, chapters: List[Dict]) -> Dict:
        """确认幕级规划：写入 story_nodes + chapters 表（供工作台侧栏列表），并关联 Bible 元素。"""
        logger.info(f"Confirming act planning for act {act_id}")

        act_node = await self.story_node_repo.get_by_id(act_id)
        if not act_node:
            raise ValueError(f"幕节点不存在: {act_id}")

        await self._remove_chapter_children_of_act(act_id)

        novel_id_vo = NovelId(act_node.novel_id)
        existing_book = []
        if self.chapter_repository:
            existing_book = self.chapter_repository.list_by_novel(novel_id_vo)
        max_num = max((c.number for c in existing_book), default=0)
        next_global_number = max_num + 1

        created_chapters: List[StoryNode] = []
        created_elements: List[ChapterElement] = []

        for idx, raw in enumerate(chapters):
            row = self._normalize_act_chapter_row(raw, act_local_index=idx + 1)
            global_number = next_global_number + idx
            # 与 novel_service.add_chapter / 前端树选择一致：id 以 chapter-{全局章号} 结尾
            story_chapter_id = f"chapter-{act_node.novel_id}-chapter-{global_number}"

            chapter_node = StoryNode(
                id=story_chapter_id,
                novel_id=act_node.novel_id,
                parent_id=act_id,
                node_type=NodeType.CHAPTER,
                number=global_number,
                title=row["title"],
                order_index=act_node.order_index + 1 + idx,
                planning_status=PlanningStatus.CONFIRMED,
                planning_source=PlanningSource.AI_ACT,
                outline=row.get("outline"),
                pov_character_id=row.get("pov_character_id"),
            )
            created_chapters.append(chapter_node)

            elements_dict = self._merged_elements_dict(row)
            elements = self._create_elements_from_data(story_chapter_id, elements_dict)
            created_elements.extend(elements)

            if self.chapter_repository:
                book_ch = Chapter(
                    id=story_chapter_id,
                    novel_id=novel_id_vo,
                    number=global_number,
                    title=row["title"],
                    content="",
                    status=ChapterStatus.DRAFT,
                )
                self.chapter_repository.save(book_ch)

        await self.story_node_repo.save_batch(created_chapters)
        await self.chapter_element_repo.save_batch(created_elements)

        act_children = self.story_node_repo.get_children_sync(act_id)
        chapter_nodes = [n for n in act_children if n.node_type == NodeType.CHAPTER]
        if chapter_nodes:
            nums = [n.number for n in chapter_nodes]
            act_node.chapter_start = min(nums)
            act_node.chapter_end = max(nums)
        else:
            act_node.chapter_start = None
            act_node.chapter_end = None
        act_node.chapter_count = len(chapter_nodes)
        await self.story_node_repo.update(act_node)

        return {
            "success": True,
            "created_chapters": len(created_chapters),
            "created_elements": len(created_elements),
            "message": f"已写入 {len(created_chapters)} 个章节（本幕旧规划已替换）",
        }

    # ==================== AI 续规划 ====================

    async def continue_planning(self, novel_id: str, current_chapter_number: int) -> Dict:
        """AI 续规划"""
        logger.info(f"Continue planning for novel {novel_id}, chapter {current_chapter_number}")

        current_act = await self._find_act_for_chapter(novel_id, current_chapter_number)
        if not current_act:
            return {"success": False, "message": "未找到当前章节所属的幕"}

        chapters_written = await self._count_written_chapters_in_act(current_act.id)
        chapters_planned = await self._count_planned_chapters_in_act(current_act.id)

        should_end = chapters_written >= chapters_planned

        if should_end:
            next_act = await self._get_next_act(current_act)

            if next_act:
                return {
                    "success": True,
                    "act_completed": True,
                    "has_next_act": True,
                    "current_act": current_act.to_dict(),
                    "next_act": next_act.to_dict(),
                    "message": f"第 {current_act.number} 幕已完成，可以开始第 {next_act.number} 幕"
                }
            else:
                return {
                    "success": True,
                    "act_completed": True,
                    "has_next_act": False,
                    "current_act": current_act.to_dict(),
                    "suggest_create_next": True,
                    "message": f"第 {current_act.number} 幕已完成，是否需要 AI 生成下一幕？"
                }
        else:
            return {
                "success": True,
                "act_completed": False,
                "current_act": current_act.to_dict(),
                "progress": f"{chapters_written}/{chapters_planned}",
                "message": f"继续第 {current_act.number} 幕"
            }

    async def create_next_act_auto(self, novel_id: str, current_act_id: str) -> Dict:
        """自动创建下一幕"""
        logger.info(f"Creating next act after {current_act_id}")

        current_act = await self.story_node_repo.get_by_id(current_act_id)
        if not current_act:
            raise ValueError(f"当前幕不存在: {current_act_id}")

        bible_context = self._get_bible_context(novel_id)
        next_act_info = await self._generate_next_act_info(novel_id, current_act, bible_context)

        next_act = self._create_node_from_data(
            novel_id,
            current_act.parent_id,
            NodeType.ACT,
            {
                "number": current_act.number + 1,
                "title": next_act_info["title"],
                "description": next_act_info["description"],
                "suggested_chapter_count": next_act_info.get("suggested_chapter_count", 5),
                "key_events": next_act_info.get("key_events", []),
                "narrative_arc": next_act_info.get("narrative_arc"),
                "conflicts": next_act_info.get("conflicts", []),
            },
            current_act.order_index + 1
        )

        await self.story_node_repo.save(next_act)

        return {
            "success": True,
            "next_act": next_act.to_dict(),
            "message": f"已创建第 {next_act.number} 幕，请为其规划章节"
        }

    # ==================== 辅助方法 ====================

    def _get_bible_context(self, novel_id: str) -> Dict:
        """获取 Bible 上下文"""
        if not self.bible_service:
            return {}

        bible = self.bible_service.get_bible_by_novel(novel_id)
        if not bible:
            return {}

        return {
            "characters": [{"id": c.id, "name": c.name, "description": c.description}
                           for c in bible.characters],
            "world_settings": [{"id": w.id, "name": w.name, "description": w.description}
                               for w in bible.world_settings],
            "locations": [{"id": l.id, "name": l.name, "description": l.description}
                          for l in bible.locations],
            "timeline_notes": [{"id": t.id, "event": t.event, "description": t.description}
                               for t in bible.timeline_notes],
        }

    def _create_node_from_data(
        self, novel_id: str, parent_id: Optional[str], node_type: NodeType,
        data: Dict, order_index: int
    ) -> StoryNode:
        """从数据创建节点"""
        return StoryNode(
            id=f"{node_type.value}-{uuid.uuid4().hex[:8]}",
            novel_id=novel_id,
            parent_id=parent_id,
            node_type=node_type,
            number=data["number"],
            title=data["title"],
            description=data.get("description"),
            order_index=order_index,
            planning_status=PlanningStatus.CONFIRMED,
            planning_source=PlanningSource.AI_MACRO,
            suggested_chapter_count=data.get("suggested_chapter_count"),
            themes=data.get("themes", []),
            key_events=data.get("key_events", []) if node_type == NodeType.ACT else [],
            narrative_arc=data.get("narrative_arc") if node_type == NodeType.ACT else None,
            conflicts=data.get("conflicts", []) if node_type == NodeType.ACT else [],
        )

    def _flatten_structure_to_nodes(self, novel_id: str, structure: List[Dict]) -> List[Dict]:
        """将嵌套的部-卷-幕结构扁平化为节点列表（用于 MacroMergeEngine）

        Args:
            novel_id: 小说 ID
            structure: 嵌套结构 [{"title": "第一部", "volumes": [...]}]

        Returns:
            平面节点列表 [{"id": "part-xxx", "node_type": "PART", ...}]
        """
        nodes = []
        order_index = 0
        part_number = 0
        volume_number = 0
        act_number = 0

        for part_data in structure:
            part_number += 1
            part_data["number"] = part_number
            part_id = f"part-{novel_id}-{part_number}"

            nodes.append({
                "id": part_id,
                "novel_id": novel_id,
                "parent_id": None,
                "node_type": "part",
                "number": part_number,
                "title": part_data["title"],
                "description": part_data.get("description", ""),
                "order_index": order_index,
            })
            order_index += 1

            for volume_data in part_data.get("volumes", []):
                volume_number += 1
                volume_data["number"] = volume_number
                volume_id = f"volume-{novel_id}-{volume_number}"

                nodes.append({
                    "id": volume_id,
                    "novel_id": novel_id,
                    "parent_id": part_id,
                    "node_type": "volume",
                    "number": volume_number,
                    "title": volume_data["title"],
                    "description": volume_data.get("description", ""),
                    "order_index": order_index,
                })
                order_index += 1

                for act_data in volume_data.get("acts", []):
                    act_number += 1
                    act_data["number"] = act_number
                    act_id = f"act-{novel_id}-{act_number}"

                    nodes.append({
                        "id": act_id,
                        "novel_id": novel_id,
                        "parent_id": volume_id,
                        "node_type": "act",
                        "number": act_number,
                        "title": act_data["title"],
                        "description": act_data.get("description", ""),
                        "order_index": order_index,
                    })
                    order_index += 1

        return nodes

    def _normalize_act_chapter_row(self, raw: Dict, act_local_index: int) -> Dict:
        """LLM / 前端可能缺 number、title，或 number 为字符串；统一为可落库结构。"""
        title = (raw.get("title") or "").strip() or f"第{act_local_index}章"
        num = raw.get("number")
        try:
            num_int = int(num) if num is not None else act_local_index
        except (TypeError, ValueError):
            num_int = act_local_index
        outline = raw.get("outline") or raw.get("description") or ""
        if isinstance(outline, str):
            outline = outline.strip() or None
        else:
            outline = None
        return {
            **raw,
            "number": num_int,
            "title": title,
            "outline": outline,
        }

    def _merged_elements_dict(self, chapter_row: Dict) -> Dict:
        """提示词里人物/地点在 chapters[].characters；落库时期望 elements.characters 为带 id 的对象列表。"""
        merged: Dict = {}
        inner = chapter_row.get("elements")
        if isinstance(inner, dict):
            merged.update(inner)
        for key in ("characters", "locations"):
            top = chapter_row.get(key)
            if top and not merged.get(key):
                merged[key] = top
        return merged

    def _create_elements_from_data(self, chapter_id: str, elements_data: Dict) -> List[ChapterElement]:
        """从数据创建章节元素"""
        elements = []
        if not isinstance(elements_data, dict):
            return elements

        for char_data in elements_data.get("characters", []):
            if isinstance(char_data, str):
                char_data = {"id": char_data}
            if not isinstance(char_data, dict) or not char_data.get("id"):
                continue
            elements.append(ChapterElement(
                id=f"elem-{uuid.uuid4().hex[:8]}",
                chapter_id=chapter_id,
                element_type=ElementType.CHARACTER,
                element_id=str(char_data["id"]),
                relation_type=RelationType(char_data.get("relation", "appears")),
                importance=Importance(char_data.get("importance", "normal")),
            ))

        for loc_data in elements_data.get("locations", []):
            if isinstance(loc_data, str):
                loc_data = {"id": loc_data}
            if not isinstance(loc_data, dict) or not loc_data.get("id"):
                continue
            elements.append(ChapterElement(
                id=f"elem-{uuid.uuid4().hex[:8]}",
                chapter_id=chapter_id,
                element_type=ElementType.LOCATION,
                element_id=str(loc_data["id"]),
                relation_type=RelationType.SCENE,
                importance=Importance.NORMAL,
            ))

        return elements

    def _parse_llm_response(self, response) -> Dict:
        """解析 LLM 响应"""
        # 如果是 GenerationResult 对象，提取 content 属性
        if hasattr(response, 'content'):
            content = response.content
        else:
            content = response

        cleaned = _sanitize_llm_json_output(content)
        cleaned = _extract_outer_json_value(cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        try:
            repaired = repair_json(cleaned)
            return json.loads(repaired)
        except Exception:
            pass

        cleaned = _repair_json_string(cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse planning JSON: %s", e)
            logger.error("Planning content length: %d", len(cleaned))
            logger.error("Planning raw content (first 1000 chars): %s", cleaned[:1000])
            logger.error("Planning raw content (last 500 chars): %s", cleaned[-500:])
            raise

    def _calculate_chapter_distribution(self, total_chapters: int, parts: int) -> Dict[str, List[int]]:
        """计算黄金比例的章数分配

        核心算法：
        - 3部：25% - 50% - 25% (起源-深渊-决战)
        - 4部：20% - 30% - 30% - 20% (双峰中段)
        - 5部+：首尾各20%，中间平分剩余60%

        Returns:
            {
                "part_chapters": [250, 500, 250],  # 每部的章数
                "part_ratios": [0.25, 0.5, 0.25]   # 每部的占比
            }
        """
        if parts == 1:
            return {"part_chapters": [total_chapters], "part_ratios": [1.0]}

        if parts == 2:
            # 双部结构：40% - 60% (铺垫-高潮)
            p1 = int(total_chapters * 0.4)
            p2 = total_chapters - p1
            return {"part_chapters": [p1, p2], "part_ratios": [0.4, 0.6]}

        if parts == 3:
            # 经典三幕剧：25% - 50% - 25%
            p1 = int(total_chapters * 0.25)
            p3 = int(total_chapters * 0.25)
            p2 = total_chapters - p1 - p3
            return {"part_chapters": [p1, p2, p3], "part_ratios": [0.25, 0.5, 0.25]}

        if parts == 4:
            # 双峰中段：20% - 30% - 30% - 20%
            p1 = int(total_chapters * 0.2)
            p4 = int(total_chapters * 0.2)
            remaining = total_chapters - p1 - p4
            p2 = remaining // 2
            p3 = remaining - p2
            return {"part_chapters": [p1, p2, p3, p4], "part_ratios": [0.2, 0.3, 0.3, 0.2]}

        # 5部及以上：首尾各20%，中间平分60%
        first = int(total_chapters * 0.2)
        last = int(total_chapters * 0.2)
        middle_total = total_chapters - first - last
        middle_parts = parts - 2
        middle_each = middle_total // middle_parts

        part_chapters = [first]
        for i in range(middle_parts):
            if i == middle_parts - 1:
                # 最后一个中间部分吃掉余数
                part_chapters.append(middle_total - middle_each * (middle_parts - 1))
            else:
                part_chapters.append(middle_each)
        part_chapters.append(last)

        part_ratios = [c / total_chapters for c in part_chapters]
        return {"part_chapters": part_chapters, "part_ratios": part_ratios}

    def _build_quick_macro_prompt(self, bible_context: Dict, target_chapters: int) -> Prompt:
        """极速模式：破城槌提示词 V4（智能结构感知版）

        V4 变更：
        - 使用 calculate_structure_params 注入结构参数到 prompt 中
        - 不再使用硬编码的"三幕剧"暗示，改为根据目标篇幅推荐合理幕数
        - 让 LLM 在一个明确的数量框架内发挥创意
        """

        # 从结构计算引擎获取推荐参数
        params = calculate_structure_params(target_chapters)
        rec_acts_per_volume = params["acts_per_volume"]
        rec_chapters_per_act = params["chapters_per_act"]
        rec_parts = params["parts"]
        rec_volumes_per_part = params["volumes_per_part"]
        total_recommended_acts = params["total_acts"]

        logger.info(
            f"[QuickPrompt] target={target_chapters} → "
            f"推荐 {rec_parts}部×{rec_volumes_per_part}卷×{rec_acts_per_volume}幕"
            f"≈{total_recommended_acts}幕, 每幕~{rec_chapters_per_act}章"
        )

        # 根据章节数决定规划深度
        if target_chapters > 500:
            planning_depth = "framework"  # 只规划部/卷框架
            depth_instruction = f"""
【规划深度】目标章节数>500，采用渐进式规划：
- 只输出「部」和「卷」的标题与主题（不输出具体幕）
- 【强制要求】每卷必须输出 estimated_chapters（预估章数）
- 【章数约束】所有卷的 estimated_chapters 之和必须等于 {target_chapters} 章
- 每卷建议 {rec_chapters_per_act * rec_acts_per_volume}-{rec_chapters_per_act * rec_acts_per_volume * 2} 章，根据剧情需要灵活分配
- 写作时每卷将动态生成约 {rec_acts_per_volume} 幕（每幕约 {rec_chapters_per_act} 章）
- 幕节点将在写作过程中动态生成
"""
        elif target_chapters > 100:
            planning_depth = "partial"  # 规划前几部的幕
            depth_instruction = f"""
【规划深度】目标章节数>100，采用部分详细规划：
- 规划「部」和「卷」的完整结构
- 【强制要求】每卷必须输出 estimated_chapters（预估章数）
- 【章数约束】所有卷的 estimated_chapters 之和必须等于 {target_chapters} 章
- 【关键参数】建议每卷规划 {rec_acts_per_volume} 幕（每幕约 {rec_chapters_per_act} 章）
- 只为第1-2部的卷规划幕节点
- 后续部的幕节点将在写作中动态生成
"""
        else:
            planning_depth = "full"  # 完整规划
            depth_instruction = f"""
【规划深度】目标章节数<100，完整规划所有部/卷/幕
- 【强制要求】每幕必须输出 estimated_chapters（预估章数）
- 【关键参数】建议共 {rec_parts} 部，每部 {rec_volumes_per_part} 卷，每卷 {rec_acts_per_volume} 幕
- 【章数约束】所有幕的 estimated_chapters 之和必须等于 {target_chapters} 章
- 每幕建议约 {rec_chapters_per_act} 章
"""
        
        system_msg = f"""# 角色设定
你是一位狂热且极具市场敏锐度的顶级网文主编，精通"退婚流"、"克苏鲁修仙"、"赛博朋克反乌托邦"等各种爆款商业节奏。你的任务是帮作者打破"白纸恐惧"，利用他给出的世界观设定，瞬间推演填补出一个完整、宏大、且充满极端冲突的长篇叙事骨架。

{depth_instruction}

# 叙事结构理论指导
<STORY_THEORY>
你设计的结构应符合以下经典叙事原理：
1. 多幕级联结构：每一幕是一个完整的「激励事件→发展→高潮→降级」叙事弧线。
   本篇小说目标 {target_chapters} 章，建议分为约 {total_recommended_acts} 幕
   （{rec_parts} 部 × 每部约 {rec_volumes_per_part} 卷 × 每卷约 {rec_acts_per_volume} 幕），
   每幕约 {rec_chapters_per_act} 章。请严格按此数量框架规划。
2. 英雄之旅：平凡世界→冒险召唤→试炼→深渊→蜕变→归来
3. 情绪曲线：开篇抓人→中段起伏（小高潮间隔2-3幕）→终局爆发
4. 钩子密度：每部结尾必须有大悬念，每卷结尾有中等悬念，每幕结尾有小悬念
</STORY_THEORY>

# 核心推演铁律（The Icebreaker Rules V4）
<CONSTRAINTS>
1. 【结构量化】本次规划的硬性数量约束（必须遵守）：
   - 总幕数应在 {total_recommended_acts} 幕左右（±20%可接受）
   - 每卷应包含 {rec_acts_per_volume} 幕左右，不要出现某卷只有1-2幕的情况
   - 每幕约 {rec_chapters_per_act} 章（重要情节的幕可以多几章，过渡幕可以少几章）

2. 【极致冲突】每一幕必须包含：
   - 核心对抗（谁 vs 谁）
   - 赌注（失败会失去什么）
   - 转折（预期违背）

3. 【世界观融合】必须深度融合提供的设定：
   - 主要角色必须出现在关键幕中
   - 关键地点必须承担叙事功能
   - 时间线事件必须影响情节走向

4. 【商业节奏】
   - 第一部：快速抛出核心悬念，建立主角目标
   - 中间部：主角经历重大失败/觉醒
   - 最后一部：所有伏笔收束，终极对决
</CONSTRAINTS>

# 输出格式
请直接输出JSON：
{{"parts": [{{"title": "部标题", "theme": "部主题", "volumes": [...]}}]}}

每卷格式（estimated_chapters 为必填字段）：
{{"title": "卷标题", "theme": "卷主题", "estimated_chapters": 预估章数（必填整数）}}

{"如果规划深度为 full 或 partial，每卷还应包含 acts 数组，每幕也必须有 estimated_chapters：" if planning_depth != "framework" else "超长篇不输出 acts，但必须确保每卷的 estimated_chapters 之和等于目标章数。"}
{"每幕格式：" if planning_depth == "full" else ""}
{{"acts": [{{"title": "幕标题", "estimated_chapters": 预估章数（必填整数）, "description": "情节摘要"}}]}}

【章数校验】请确保：所有卷/幕的 estimated_chapters 之和 = {target_chapters}

不要添加任何解释性文字。"""

        # 构建丰富的世界观上下文
        context_parts = []

        # 世界观
        if bible_context.get("worldview"):
            context_parts.append(f"【世界观】\n{bible_context['worldview']}\n")

        # 角色（带关系和弧光）
        if bible_context.get("characters"):
            chars = bible_context['characters']
            char_lines = ["【角色设定】"]
            for c in chars[:5]:  # 限制主要角色数量
                name = c.get('name', 'Unknown')
                desc = c.get('description', '')
                role = c.get('role', '')
                arc = c.get('character_arc', '')
                char_lines.append(f"- {name} ({role}): {desc}")
                if arc:
                    char_lines.append(f"  人物弧光: {arc}")
            context_parts.append("\n".join(char_lines) + "\n")

        # 角色关系
        if bible_context.get("relationships"):
            rel_lines = ["【角色关系】"]
            for r in bible_context['relationships'][:5]:
                char1 = r.get('character1', '')
                char2 = r.get('character2', '')
                rel_type = r.get('relationship_type', '')
                rel_desc = r.get('description', '')
                rel_lines.append(f"- {char1} ↔ {char2} ({rel_type}): {rel_desc}")
            context_parts.append("\n".join(rel_lines) + "\n")

        # 地点（带叙事功能）
        if bible_context.get("locations"):
            loc_lines = ["【关键地点】"]
            for l in bible_context['locations'][:5]:
                name = l.get('name', 'Unknown')
                desc = l.get('description', '')
                significance = l.get('significance', '')
                loc_lines.append(f"- {name}: {desc}")
                if significance:
                    loc_lines.append(f"  叙事意义: {significance}")
            context_parts.append("\n".join(loc_lines) + "\n")

        # 时间线事件
        if bible_context.get("timeline_notes"):
            time_lines = ["【时间线事件】"]
            for t in bible_context['timeline_notes'][:5]:
                event = t.get('event', '')
                desc = t.get('description', '')
                impact = t.get('impact', '')
                time_lines.append(f"- {event}: {desc}")
                if impact:
                    time_lines.append(f"  情节影响: {impact}")
            context_parts.append("\n".join(time_lines) + "\n")

        if not context_parts:
            context_parts.append("【世界观与人物】\n暂无详细设定，请基于通用的商业小说套路生成结构，但仍需保持结构灵活和冲突极致。\n")

        worldview_context = "\n".join(context_parts)

        user_msg = f"""<STORY_CONTEXT>
{worldview_context}
</STORY_CONTEXT>

<TARGET_SCOPE>
目标总篇幅：精确 {target_chapters} 章
【强制约束】所有卷/幕的 estimated_chapters 之和必须等于 {target_chapters}
</TARGET_SCOPE>

请立即生成叙事骨架，严格按以下JSON格式输出：
{{
  "parts": [
    {{
      "title": "部标题（如：深渊觉醒）",
      "volumes": [
        {{
          "title": "卷标题（如：血色的黎明）",
          "acts": [
            {{
              "title": "幕标题（如：青铜门下的背叛）",
              "core_conflict": "主角 vs 反派，赌注是...",
              "emotional_turn": "从...到...",
              "description": "情节摘要...",
              "key_characters": ["角色1", "角色2"],
              "key_locations": ["地点1"]
            }}
          ]
        }}
      ]
    }}
  ]
}}"""
        return Prompt(system=system_msg, user=user_msg)

    def _build_precise_macro_prompt(
        self,
        bible_context: Dict,
        target_chapters: int,
        structure_preference: Dict,
        skeleton: Dict,
    ) -> Prompt:
        """精密模式：手术刀提示词 V2

        设计哲学：
        - 捍卫创作者的绝对主权与节奏感
        - 严格遵守用户指定的结构网格和字数节奏
        - 强调逻辑严密、中段支撑、情节容量匹配
        - 深度融合 Bible 设定进行精密推演
        - 引入叙事理论确保结构合理性
        """
        parts = structure_preference.get('parts', 3)
        volumes_per_part = structure_preference.get('volumes_per_part', 3)
        acts_per_volume = structure_preference.get('acts_per_volume', 3)
        total_acts = parts * volumes_per_part * acts_per_volume

        # 计算章数分配
        distribution = self._calculate_chapter_distribution(target_chapters, parts)
        part_chapters = distribution["part_chapters"]

        # 计算每幕平均章数
        avg_chapters_per_act = target_chapters // total_acts if total_acts > 0 else 5

        # 构建动态章节配额指示
        pacing_guide = "<PACING_GUIDE>\n"
        for i, chapters in enumerate(part_chapters, 1):
            if i == 1:
                pacing_guide += f"- 第{i}部（起源）：分配 {chapters} 章。情节要求：紧凑、抛出核心悬念、建立主角目标。\n"
            elif i == parts:
                pacing_guide += f"- 第{i}部（决战）：分配 {chapters} 章。情节要求：收束所有主线、终极对决、情绪爆发。\n"
            else:
                pacing_guide += f"- 第{i}部（发展/深渊）：分配 {chapters} 章。情节要求：容量极大、多线叙事、主角重大转变。\n"
        pacing_guide += f"</PACING_GUIDE>\n\n<ACT_PACING>\n"
        pacing_guide += f"- 总幕数：{total_acts} 幕\n"
        pacing_guide += f"- 平均每幕：约 {avg_chapters_per_act} 章\n"
        pacing_guide += f"- 节奏建议：前1/3幕数铺垫，中1/3幕数发展+小高潮，后1/3幕数爆发+收束\n"
        pacing_guide += "</ACT_PACING>"

        system_msg = f"""# 角色设定
你是一位极其理性的长篇小说结构架构师，精通经典叙事理论和现代网文节奏。作者正在进行一项严密的叙事工程，设定了精确的篇幅限制和结构分布。你的任务是像外科手术一样，在严格遵守"结构网格"和"字数节奏"的前提下，深度融合世界观设定，分配情节张力，确保中段不塌陷，高潮不疲软。

# 叙事理论框架
<STORY_THEORY>
1. 三幕剧结构映射：
   - 第1部 ≈ 第一幕（设定）：主角现状→触发事件→拒绝改变→跨越门槛
   - 中间部 ≈ 第二幕（对抗）：试炼与盟友→深入深渊→核心考验
   - 最后部 ≈ 第三幕（解决）：回归→终极对决→新世界

2. 情绪曲线设计：
   - 每部内部：起→承→转→合
   - 幕间关系：悬念→揭示→更大悬念
   - 高潮分布：每部1个大高潮，每卷1个中高潮，每2-3幕1个小高潮

3. 角色弧光整合：
   - 主角必须在结构节点处经历关键转变
   - 反派势力应随幕推进逐步显露/强化
   - 配角应在特定幕完成其叙事功能
</STORY_THEORY>

# 精密推演铁律（The Scalpel Rules V2）
<CONSTRAINTS>
1. 【结构网格绝对服从】
   必须严格输出 {parts} 部 × {volumes_per_part} 卷/部 × {acts_per_volume} 幕/卷 = {total_acts} 幕，不得多一个或少一个节点。

2. 【节奏匹配】
   系统已为你计算好每部的【预估章数配额】。你设计的情节容量必须能撑起这个章数：
   - 高章数配额（>100章/部）：必须设计【多线叙事】+【复杂长线副本】+【势力博弈】
   - 中章数配额（50-100章/部）：设计【主线+1-2条副线】+【阶段性目标】
   - 低章数配额（<50章/部）：情节必须是【单线程快速推进】+【紧凑冲突】

3. 【世界观深度融合】
   - 主要角色必须出现在具体幕中，标注其在该幕的角色功能（主角/反派/盟友/阻碍者）
   - 关键地点必须承担具体叙事功能（不仅是背景，而是冲突发生地/转折点）
   - 时间线事件必须与幕结构对齐（某幕必须解决某事件，或某事件触发某幕）
   - 角色关系必须在幕中体现（某幕聚焦某对关系的转变）

4. 【逻辑严密性】
   - 严禁机械降神：所有解决必须基于已铺垫的能力/资源
   - 因果清晰：每一幕的结果必须是下一幕的前提
   - 伏笔呼应：早期幕埋下的线索必须在后期幕回收

5. 【中段支撑】
   - 中间部分必须设计"次要反派的崛起"或"主角信念的暂时崩溃"
   - 每3-4幕必须有一个情绪转折点（希望→绝望，或反之）
   - 避免"中段塌陷"：确保中间幕的冲突强度不低于首尾

6. 【章数分配】
   - 每幕必须标注 estimated_chapters（参考平均每幕{avg_chapters_per_act}章）
   - 重要幕（转折点、高潮）可分配更多章数
   - 过渡幕可分配较少章数，但必须有冲突推进
</CONSTRAINTS>

{pacing_guide}

# 输出要求
请直接输出JSON格式，层级必须严格吻合结构网格。
每幕（Act）的输出字段必须包含：
- "title": "精准的情节标题（动词+名词，暗示冲突）"
- "estimated_chapters": 本幕预计占用的章数（整数）
- "narrative_goal": "本幕在整个故事结构中承担的叙事功能"
- "plot_points": ["情节点1", "情节点2", "情节点3"]（本幕包含的关键事件）
- "description": "严谨的剧情走向摘要（含因果逻辑）"
- "key_characters": ["角色ID"]（本幕涉及的角色，标注功能如：主角-李明）
- "key_locations": ["地点ID"]（本幕发生的关键地点，标注功能）
- "emotional_arc": "情绪曲线（如：平静→紧张→爆发）"
- "setup_for": ["后续幕ID或标题"]（本幕为哪些后续幕做铺垫）
- "payoff_from": ["前置幕ID或标题"]（本幕回收了哪些前置幕的伏笔）

不要添加任何解释性文字。"""

        # 构建丰富的世界观上下文（与极速模式一致）
        context_parts = []

        # 世界观
        if bible_context.get("worldview"):
            context_parts.append(f"【世界观】\n{bible_context['worldview']}\n")

        # 角色（带关系和弧光）
        if bible_context.get("characters"):
            chars = bible_context['characters']
            char_lines = ["【角色设定】"]
            for c in chars[:5]:
                name = c.get('name', 'Unknown')
                desc = c.get('description', '')
                role = c.get('role', '')
                arc = c.get('character_arc', '')
                char_id = c.get('id', 'N/A')
                char_lines.append(f"- {name} (ID: {char_id}) [{role}]: {desc}")
                if arc:
                    char_lines.append(f"  人物弧光: {arc}")
            context_parts.append("\n".join(char_lines) + "\n")

        # 角色关系
        if bible_context.get("relationships"):
            rel_lines = ["【角色关系】"]
            for r in bible_context['relationships'][:5]:
                char1 = r.get('character1', '')
                char2 = r.get('character2', '')
                rel_type = r.get('relationship_type', '')
                rel_desc = r.get('description', '')
                rel_lines.append(f"- {char1} ↔ {char2} ({rel_type}): {rel_desc}")
            context_parts.append("\n".join(rel_lines) + "\n")

        # 地点（带叙事功能）
        if bible_context.get("locations"):
            loc_lines = ["【关键地点】"]
            for l in bible_context['locations'][:5]:
                name = l.get('name', 'Unknown')
                desc = l.get('description', '')
                significance = l.get('significance', '')
                loc_id = l.get('id', 'N/A')
                loc_lines.append(f"- {name} (ID: {loc_id}): {desc}")
                if significance:
                    loc_lines.append(f"  叙事意义: {significance}")
            context_parts.append("\n".join(loc_lines) + "\n")

        # 时间线事件
        if bible_context.get("timeline_notes"):
            time_lines = ["【时间线事件】"]
            for t in bible_context['timeline_notes'][:5]:
                event = t.get('event', '')
                desc = t.get('description', '')
                impact = t.get('impact', '')
                time_lines.append(f"- {event}: {desc}")
                if impact:
                    time_lines.append(f"  情节影响: {impact}")
            context_parts.append("\n".join(time_lines) + "\n")

        if not context_parts:
            context_parts.append("【世界观与人物】\n暂无详细设定，请生成通用的结构框架，但仍需严格遵守结构网格。\n")

        worldview_context = "\n".join(context_parts)

        skeleton_lines = ["【固定结构骨架】"]
        for part_index, part in enumerate(skeleton.get("parts", []), 1):
            skeleton_lines.append(f'- {part["node_id"]}: 第{part_index}部')
            for volume_index, volume in enumerate(part.get("volumes", []), 1):
                skeleton_lines.append(f'  - {volume["node_id"]}: 第{part_index}部第{volume_index}卷')
                for act_index, act in enumerate(volume.get("acts", []), 1):
                    skeleton_lines.append(
                        f'    - {act["node_id"]}: 第{part_index}部第{volume_index}卷第{act_index}幕，参考 {avg_chapters_per_act} 章'
                    )

        skeleton_block = "\n".join(skeleton_lines)

        user_msg = f"""<STORY_CONTEXT>
{worldview_context}
</STORY_CONTEXT>

<STRUCTURAL_GRID>
【你必须绝对服从的物理网格】
- 目标总章数：{target_chapters} 章
- 结构分布：{parts} 部 × {volumes_per_part} 卷/部 × {acts_per_volume} 幕/卷 = {total_acts} 幕
- 平均每幕：约 {avg_chapters_per_act} 章
</STRUCTURAL_GRID>

{skeleton_block}

系统已经固定好了部/卷/幕的数量与层级，你不能新增、删除、合并、拆分任何节点。
你的任务只是为这些固定节点填写标题、描述和幕级字段。

请只输出 JSON，格式如下：
{{
  "node_updates": [
    {{
      "node_id": "P1 或 V1_1 或 A1_1_1",
      "title": "节点标题",
      "description": "节点描述",
      "estimated_chapters": 5,
      "narrative_goal": "仅 Act 必填",
      "plot_points": ["仅 Act 使用"],
      "key_characters": ["仅 Act 使用"],
      "key_locations": ["仅 Act 使用"],
      "emotional_arc": "仅 Act 使用",
      "setup_for": ["仅 Act 使用"],
      "payoff_from": ["仅 Act 使用"]
    }}
  ]
}}

要求：
1. 每个固定节点都必须返回一条 node_updates。
2. Part/Volume 只需填写 node_id、title、description。
3. Act 必须填写全部幕级字段。
4. 不要返回 parts/volumes/acts 树，不要添加解释文字。
5. 幕的 estimated_chapters 可以按剧情轻重分配，但总量应尽量接近 {target_chapters} 章。"""
        return Prompt(system=system_msg, user=user_msg)

    def _build_precise_volume_prompt(
        self,
        bible_context: Dict,
        target_chapters: int,
        structure_preference: Dict,
        skeleton: Dict,
        part_index: int,
        volume_index: int,
    ) -> Prompt:
        """按卷生成内容，缩小上下文范围以提高字段完整度。"""
        parts = structure_preference.get('parts', 3)
        volumes_per_part = structure_preference.get('volumes_per_part', 3)
        acts_per_volume = structure_preference.get('acts_per_volume', 3)
        total_acts = parts * volumes_per_part * acts_per_volume
        avg_chapters_per_act = target_chapters // total_acts if total_acts > 0 else 5

        current_part = skeleton["parts"][part_index - 1]
        current_volume = current_part["volumes"][volume_index - 1]
        act_scope = current_volume.get("acts", [])

        context_parts = []
        if bible_context.get("worldview"):
            context_parts.append(f"【世界观】\n{bible_context['worldview']}\n")
        if bible_context.get("characters"):
            char_lines = ["【角色设定】"]
            for c in bible_context["characters"][:8]:
                char_lines.append(
                    f"- {c.get('name', 'Unknown')} (ID: {c.get('id', 'N/A')}): {c.get('description', '')}"
                )
            context_parts.append("\n".join(char_lines) + "\n")
        if bible_context.get("locations"):
            loc_lines = ["【关键地点】"]
            for l in bible_context["locations"][:8]:
                loc_lines.append(
                    f"- {l.get('name', 'Unknown')} (ID: {l.get('id', 'N/A')}): {l.get('description', '')}"
                )
            context_parts.append("\n".join(loc_lines) + "\n")
        if not context_parts:
            context_parts.append("【世界观与人物】\n暂无详细设定，请给出通用但完整的单卷叙事设计。\n")

        scope_lines = [
            f"【当前生成范围】第{part_index}部 / 第{volume_index}卷",
            f'- {current_part["node_id"]}: {current_part["title"]}',
            f'- {current_volume["node_id"]}: {current_volume["title"]}',
        ]
        for act in act_scope:
            scope_lines.append(
                f'- {act["node_id"]}: {act["title"]}，需完整填写 narrative_goal / plot_points / key_characters / key_locations / emotional_arc / setup_for / payoff_from'
            )

        system_msg = """你是长篇小说结构设计师。当前任务不是规划整本书，而是只完成一个卷的详细结构设计。
你必须为当前卷内的每一幕填写完整字段，尤其不能遗漏 narrative_goal、plot_points、key_characters、key_locations、emotional_arc。
请直接输出 JSON，不要解释。"""

        user_msg = f"""<STORY_CONTEXT>
{"".join(context_parts)}
</STORY_CONTEXT>

【全书网格】
- 总章数：{target_chapters} 章
- 结构：{parts} 部 × {volumes_per_part} 卷/部 × {acts_per_volume} 幕/卷
- 平均每幕：约 {avg_chapters_per_act} 章

{chr(10).join(scope_lines)}

请仅返回当前卷相关节点的 JSON：
{{
  "node_updates": [
    {{
      "node_id": "{current_part["node_id"]} 或 {current_volume["node_id"]} 或 {act_scope[0]["node_id"] if act_scope else 'A1_1_1'}",
      "title": "节点标题",
      "description": "节点描述",
      "estimated_chapters": 5,
      "narrative_goal": "仅 Act 必填，不能为空",
      "plot_points": ["仅 Act 使用，至少 2 条"],
      "key_characters": ["仅 Act 使用，至少 1 条"],
      "key_locations": ["仅 Act 使用，至少 1 条"],
      "emotional_arc": "仅 Act 使用，不能为空",
      "setup_for": ["仅 Act 使用"],
      "payoff_from": ["仅 Act 使用"]
    }}
  ]
}}

要求：
1. 只返回当前卷涉及的 node_updates。
2. 当前卷内每个 Act 都必须返回一条更新。
3. 每个 Act 的 narrative_goal、plot_points、key_characters、key_locations、emotional_arc 都不能为空。
4. 不要新增或删除节点。"""
        return Prompt(system=system_msg, user=user_msg)

    def _build_precise_repair_prompt(
        self,
        bible_context: Dict,
        target_chapters: int,
        structure_preference: Dict,
        incomplete_acts: List[Dict],
    ) -> Prompt:
        """只为缺字段的幕生成补丁。"""
        parts = structure_preference.get('parts', 3)
        volumes_per_part = structure_preference.get('volumes_per_part', 3)
        acts_per_volume = structure_preference.get('acts_per_volume', 3)
        total_acts = max(parts * volumes_per_part * acts_per_volume, 1)
        avg_chapters_per_act = max(target_chapters // total_acts, 1)

        context_parts = []
        if bible_context.get("worldview"):
            context_parts.append(f"【世界观】\n{bible_context['worldview']}\n")
        if bible_context.get("characters"):
            char_lines = ["【角色设定】"]
            for c in bible_context["characters"][:8]:
                char_lines.append(f"- {c.get('name', 'Unknown')} (ID: {c.get('id', 'N/A')}): {c.get('description', '')}")
            context_parts.append("\n".join(char_lines) + "\n")
        if bible_context.get("locations"):
            loc_lines = ["【关键地点】"]
            for l in bible_context["locations"][:8]:
                loc_lines.append(f"- {l.get('name', 'Unknown')} (ID: {l.get('id', 'N/A')}): {l.get('description', '')}")
            context_parts.append("\n".join(loc_lines) + "\n")
        if not context_parts:
            context_parts.append("【世界观与人物】\n暂无详细设定，请补齐通用但完整的叙事字段。\n")

        act_lines = []
        for act in incomplete_acts:
            act_lines.append(
                f'- {act["node_id"]}: 标题《{act["title"]}》；简介《{act["description"]}》；缺失字段：{", ".join(act["missing_fields"])}'
            )

        system_msg = """你是小说结构补全助手。你收到的是已经生成好的幕结构，但有些关键字段为空。
你的任务是只为这些幕补齐缺失字段，不要改写已有完整字段，不要返回解释文字。"""

        user_msg = f"""<STORY_CONTEXT>
{"".join(context_parts)}
</STORY_CONTEXT>

【全书约束】
- 总章数：{target_chapters} 章
- 结构：{parts} 部 × {volumes_per_part} 卷/部 × {acts_per_volume} 幕/卷
- 平均每幕：约 {avg_chapters_per_act} 章

【待补全幕】
{chr(10).join(act_lines)}

请只输出 JSON：
{{
  "node_updates": [
    {{
      "node_id": "A1_1_1",
      "narrative_goal": "不能为空",
      "plot_points": ["至少 2 条"],
      "key_characters": ["至少 1 条"],
      "key_locations": ["至少 1 条"],
      "emotional_arc": "不能为空"
    }}
  ]
}}

要求：
1. 每个待补全幕都必须返回一条 node_updates。
2. 只返回缺失字段，不要输出 title、description、estimated_chapters，除非该幕这些字段也为空。
3. `plot_points` 至少 2 条，`key_characters` 和 `key_locations` 至少各 1 条。"""
        return Prompt(system=system_msg, user=user_msg)

    def _build_macro_planning_prompt(self, bible_context: Dict, target_chapters: int, structure_preference: Dict) -> Prompt:
        """构建宏观规划提示词（向后兼容的包装器）

        根据 structure_preference 是否为 None 来判断模式：
        - None: 极速模式（AI自主决定）
        - Dict: 精密模式（用户指定结构）
        """
        if structure_preference is None:
            # 极速模式：使用默认的3×3×3结构
            return self._build_quick_macro_prompt(bible_context, target_chapters)
        else:
            # 精密模式：使用用户指定的结构
            skeleton = self._build_precise_structure_skeleton(target_chapters, structure_preference)
            return self._build_precise_macro_prompt(
                bible_context,
                target_chapters,
                structure_preference,
                skeleton,
            )

    def _build_act_planning_prompt(self, act_node: StoryNode, bible_context: Dict, previous_summary: Optional[str], chapter_count: int) -> Prompt:
        """构建幕级规划提示词"""
        system_msg = """你是一个专业的小说章节规划助手，擅长设计章节大纲和情节安排。
你的任务是根据提供的信息生成章节规划，即使信息不完整也要生成合理的框架。
请直接输出 JSON 格式，不要询问额外信息，不要添加任何解释性文字。"""

        # 构建上下文信息
        context_parts = [f"幕信息：《{act_node.title}》"]
        if act_node.description:
            context_parts.append(f"幕简介：{act_node.description}")

        if previous_summary:
            context_parts.append(f"\n前情提要：{previous_summary}")

        # 添加 Bible 信息
        if bible_context.get("characters"):
            char_list = [f"- {c.get('name', 'Unknown')} (ID: {c.get('id', 'N/A')})" for c in bible_context["characters"][:5]]
            context_parts.append(f"\n可用人物：\n" + "\n".join(char_list))

        if bible_context.get("locations"):
            loc_list = [f"- {l.get('name', 'Unknown')} (ID: {l.get('id', 'N/A')})" for l in bible_context["locations"][:5]]
            context_parts.append(f"\n可用地点：\n" + "\n".join(loc_list))

        context = "\n".join(context_parts)

        user_msg = f"""{context}

请为这一幕规划 {chapter_count} 个章节。如果没有详细的世界观信息，请生成通用的章节框架。

要求：
1. 每个章节需要有标题和大纲
2. 如果有可用的人物和地点，尽量关联；如果没有，可以留空
3. 章节编号从 1 开始递增

请直接输出 JSON 格式，不要添加任何说明文字：
{{
  "chapters": [
    {{
      "number": 1,
      "title": "章节标题",
      "outline": "章节大纲（100-200字）",
      "characters": ["人物ID"],
      "locations": ["地点ID"]
    }}
  ]
}}"""
        return Prompt(system=system_msg, user=user_msg)

    async def _get_previous_acts_summary(self, act_node: StoryNode) -> Optional[str]:
        """获取前面幕的摘要"""
        return None

    async def _find_act_for_chapter(self, novel_id: str, chapter_number: int) -> Optional[StoryNode]:
        """查找章节所属的幕"""
        tree = self.story_node_repo.get_tree(novel_id)
        acts = [n for n in tree.nodes if n.node_type == NodeType.ACT]
        return max(acts, key=lambda x: x.number) if acts else None

    async def _count_written_chapters_in_act(self, act_id: str) -> int:
        """统计已写章节数"""
        children = self.story_node_repo.get_children(act_id, None)
        return sum(1 for n in children if n.node_type == NodeType.CHAPTER and n.word_count and n.word_count > 0)

    async def _count_planned_chapters_in_act(self, act_id: str) -> int:
        """统计已规划章节数"""
        children = self.story_node_repo.get_children(act_id, None)
        return sum(1 for n in children if n.node_type == NodeType.CHAPTER)

    async def _get_next_act(self, current_act: StoryNode) -> Optional[StoryNode]:
        """获取下一幕"""
        tree = self.story_node_repo.get_tree(current_act.novel_id)
        acts = [n for n in tree.nodes if n.node_type == NodeType.ACT and n.number == current_act.number + 1]
        return acts[0] if acts else None

    async def _generate_next_act_info(self, novel_id: str, current_act: StoryNode, bible_context: Dict) -> Dict:
        """生成下一幕信息（双轨融合版）
        
        轨道一：宏观摘要线
        - 注入前一卷/前一部的高浓缩摘要
        - 提供时空基石，防止时间线错乱
        
        轨道二：微观高亮线
        - 强制注入待回收伏笔
        - 注入角色当前状态锚点
        """
        # 使用结构计算引擎获取推荐每幕章数（替代硬编码的 5）
        # 通过 current_act 的 novel_id 查找小说目标章节数
        _default_cpa = calculate_structure_params(100)["chapters_per_act"]  # 保守默认值

        # 收集双轨上下文
        dual_track_context = await self._collect_dual_track_context(novel_id, current_act, bible_context)
        
        # 构建增强型 Prompt
        prompt = self._build_next_act_prompt_with_dual_track(current_act, dual_track_context)
        
        try:
            response = await self.llm_service.generate(prompt, GenerationConfig(max_tokens=4096, temperature=0.7))
            result = self._parse_llm_response(response)
            
            # 确保返回必要的字段
            if not isinstance(result, dict):
                result = {}
            result.setdefault("title", f"第{current_act.number + 1}幕")
            result.setdefault("description", "继续推进剧情")
            result.setdefault("suggested_chapter_count", _default_cpa)
            
            return result
        except Exception as e:
            logger.warning(f"生成下一幕信息失败: {e}")
            return {
                "title": f"第{current_act.number + 1}幕",
                "description": "描述",
                "suggested_chapter_count": _default_cpa
            }
    
    async def _collect_dual_track_context(
        self,
        novel_id: str,
        current_act: StoryNode,
        bible_context: Dict,
    ) -> Dict[str, str]:
        """收集双轨上下文
        
        Returns:
            {
                "volume_summary": "前一卷的摘要",
                "current_volume_summary": "当前卷的摘要",
                "pending_foreshadowings": "待回收伏笔列表",
                "character_states": "角色状态锚点",
            }
        """
        context = {
            "volume_summary": "",
            "current_volume_summary": "",
            "pending_foreshadowings": "",
            "character_states": "",
        }
        
        try:
            # 获取所有节点
            all_nodes = await self.story_node_repo.get_by_novel(novel_id)
            
            # 找到当前幕所属的卷
            current_volume = None
            if current_act.parent_id:
                current_volume = next(
                    (n for n in all_nodes if n.id == current_act.parent_id),
                    None
                )
            
            # 轨道一：获取卷摘要
            if current_volume:
                vol_summary = current_volume.metadata.get("summary", "") if current_volume.metadata else ""
                if vol_summary:
                    context["current_volume_summary"] = f"【当前卷进度】{current_volume.title}\n{vol_summary}"
            
            # 获取前一卷的摘要
            volume_nodes = sorted(
                [n for n in all_nodes if n.node_type.value == "volume"],
                key=lambda x: x.number
            )
            if current_volume:
                prev_volumes = [v for v in volume_nodes if v.number < (current_volume.number or 0)]
                if prev_volumes:
                    prev_vol = prev_volumes[-1]
                    prev_summary = prev_vol.metadata.get("summary", "") if prev_vol.metadata else ""
                    if prev_summary:
                        context["volume_summary"] = f"【前一卷回顾】{prev_vol.title}\n{prev_summary}"
            
            # 轨道二：获取待回收伏笔
            if hasattr(self, 'chapter_repository') and self.chapter_repository:
                try:
                    from domain.novel.repositories.foreshadowing_repository import ForeshadowingRepository
                    from domain.novel.value_objects.novel_id import NovelId
                    
                    # 尝试获取伏笔仓库（通过依赖注入或直接创建）
                    if hasattr(self.story_node_repo, 'db_path'):
                        from infrastructure.persistence.database.foreshadowing_repository import ForeshadowingRepositoryImpl
                        foreshadowing_repo = ForeshadowingRepositoryImpl(self.story_node_repo.db_path)
                        registry = foreshadowing_repo.get_by_novel_id(NovelId(novel_id))
                        
                        if registry:
                            pending = registry.get_unresolved()
                            if pending:
                                lines = ["【待回收伏笔】"]
                                for f in pending[:5]:
                                    lines.append(f"- 第{f.planted_in_chapter}章: {f.description}")
                                context["pending_foreshadowings"] = "\n".join(lines)
                except Exception as e:
                    logger.debug(f"获取伏笔信息时出错: {e}")
            
            # 轨道二：获取角色状态
            if bible_context and bible_context.get("characters"):
                char_lines = ["【角色当前状态】"]
                for char in bible_context["characters"][:3]:
                    name = char.get("name", "")
                    desc = char.get("description", "")
                    mental = char.get("mental_state", "")
                    tic = char.get("verbal_tic", "")
                    
                    char_info = f"- {name}: {desc[:50]}"
                    if mental:
                        char_info += f" [心理: {mental}]"
                    if tic:
                        char_info += f" 口头禅: {tic}"
                    char_lines.append(char_info)
                
                context["character_states"] = "\n".join(char_lines)
        
        except Exception as e:
            logger.warning(f"收集双轨上下文失败: {e}")
        
        return context
    
    def _build_next_act_prompt_with_dual_track(
        self,
        current_act: StoryNode,
        dual_track_context: Dict[str, str],
    ) -> Prompt:
        """构建双轨融合的下一幕生成 Prompt"""
        
        system = """你是一位资深的小说结构设计师，擅长在长篇叙事中推进剧情。
你的任务是为下一幕设计详细的内容规划，确保：
1. 与前文保持连贯，不出现时间线或人物状态矛盾
2. 有意识地回收或推进已有伏笔
3. 设置新的冲突和悬念

请直接输出 JSON 格式，不要添加解释性文字。"""
        
        # 组装双轨上下文
        context_parts = []
        
        if dual_track_context.get("volume_summary"):
            context_parts.append(dual_track_context["volume_summary"])
        
        if dual_track_context.get("current_volume_summary"):
            context_parts.append(dual_track_context["current_volume_summary"])
        
        if dual_track_context.get("pending_foreshadowings"):
            context_parts.append(dual_track_context["pending_foreshadowings"])
        
        if dual_track_context.get("character_states"):
            context_parts.append(dual_track_context["character_states"])
        
        context_block = "\n\n".join(context_parts) if context_parts else "暂无前文上下文"
        
        user = f"""【双轨上下文】
{context_block}

【当前幕信息】
幕标题：{current_act.title}
幕描述：{current_act.description or '无'}
幕号：第 {current_act.number} 幕

【任务】
请生成第 {current_act.number + 1} 幕的详细规划。

【输出要求】
请输出 JSON 格式：
{{
  "title": "幕标题（动词+名词，暗示冲突）",
  "description": "幕简介（100-200字，包含核心事件、冲突、转折）",
  "suggested_chapter_count": 预估章数（整数）,
  "key_events": ["事件1", "事件2"],
  "narrative_arc": "叙事弧线（如：紧张→爆发→暂缓）",
  "foreshadow_to_resolve": ["需要回收的伏笔"],
  "foreshadow_to_plant": ["需要埋下的新伏笔"]
}}"""
        
        return Prompt(system=system, user=user)
