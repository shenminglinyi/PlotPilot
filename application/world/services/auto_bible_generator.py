"""自动 Bible 生成器 - 从小说标题生成完整的人物、地点、风格设定和世界观"""
import logging
import json
import uuid
import re
from typing import Dict, Any, AsyncIterator, List
from datetime import datetime
from domain.ai.services.llm_service import LLMService, GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from application.world.services.bible_service import BibleService
from application.world.services.worldbuilding_service import WorldbuildingService
from domain.bible.triple import Triple, SourceType
from infrastructure.persistence.database.triple_repository import TripleRepository
from domain.shared.exceptions import EntityNotFoundError
from application.ai.trace_context import ensure_trace
from infrastructure.ai.prompt_keys import (
    BIBLE_ALL, BIBLE_WORLDBUILDING, BIBLE_CHARACTERS, BIBLE_LOCATIONS,
    BIBLE_STYLE_CONVENTION,
)

logger = logging.getLogger(__name__)


# ============================================================================
# 流式 JSON 数组增量解析器
# ============================================================================

def _try_extract_next_item(buf: str, array_key: str):
    """从流式 buffer 中尝试提取 JSON 数组中下一个完整对象。

    策略：在 buf 中查找 array_key 对应数组区域的第一个完整 JSON 对象
    （通过花括号深度匹配），提取并从 buf 中移除。

    Args:
        buf: 当前累积的 LLM 输出文本
        array_key: JSON 数组的键名（如 "characters" 或 "locations"）

    Returns:
        (parsed_dict, remaining_buf) 如果找到完整对象
        None 如果尚未收到完整对象
    """
    # 找到数组开始标记  "key": [
    # 宽松匹配：允许空格、换行
    pattern = rf'"{array_key}"\s*:\s*\['
    m = re.search(pattern, buf)
    if m is None:
        return None

    arr_start = m.end()  # [ 之后的偏移

    # 在数组区域内寻找第一个完整 JSON 对象
    depth = 0
    in_string = False
    escape_next = False
    obj_start = None

    i = arr_start
    while i < len(buf):
        ch = buf[i]

        if escape_next:
            escape_next = False
            i += 1
            continue

        if ch == '\\' and in_string:
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

        if ch == '{':
            if depth == 0:
                obj_start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and obj_start is not None:
                # 找到完整对象
                obj_str = buf[obj_start:i + 1]
                try:
                    parsed = json.loads(obj_str)
                    # 从 buf 中移除已解析的对象（保留数组前缀和前导逗号/空格）
                    # 找到对象后的逗号或空白
                    rest_start = i + 1
                    # 跳过逗号和空白
                    while rest_start < len(buf) and buf[rest_start] in ' ,\n\r\t':
                        rest_start += 1
                    # 保留数组前缀 + 剩余未解析内容
                    remaining = f'{{"{array_key}": [' + buf[rest_start:]
                    return parsed, remaining
                except json.JSONDecodeError:
                    # 对象看起来完整但解析失败，跳过
                    obj_start = None

        i += 1

    return None


# ============================================================================
# JSON 输出稳定性增强 - Prompt 常量
# ============================================================================
USER_PROMPT_SUFFIX = "\n\n直接输出 JSON（不要包在代码块里），格式：\n"

# ============================================================================
# CPMS prompt 加载
# ============================================================================


class BiblePromptTemplateUnavailable(RuntimeError):
    """Bible 生成所需 CPMS 节点缺失或不可渲染。"""


def _with_cpms_variable_defaults(node_key: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    """Merge prompt-node declared defaults before rendering.

    Defaults live in CPMS package metadata (package.yaml). Call sites only pass
    runtime facts; optional empty values remain owned by the prompt contract.
    """
    from infrastructure.ai.prompt_registry import get_prompt_registry

    merged = dict(variables or {})
    node = get_prompt_registry().get_node(node_key)
    if node is None:
        return merged
    for spec in getattr(node, "variables", None) or []:
        if not isinstance(spec, dict):
            continue
        name = str(spec.get("name") or "").strip()
        if not name or name in merged or "default" not in spec:
            continue
        merged[name] = spec.get("default")
    return merged


def _render_required_bible_prompt(node_key: str, variables: Dict[str, Any]) -> Prompt:
    """只从 CPMS 渲染 Bible prompt；缺失时阻塞，禁止硬编码提示词降级。"""
    try:
        from application.ai_invocation.prompt_variables import aliases_with_dotted_variables
        from infrastructure.ai.prompt_registry import get_prompt_registry

        render_variables = _with_cpms_variable_defaults(node_key, variables or {})
        prompt = get_prompt_registry().render_to_prompt(
            node_key,
            aliases_with_dotted_variables(render_variables),
        )
    except Exception as exc:
        raise BiblePromptTemplateUnavailable(
            f"CPMS PromptRegistry 不可用，已阻塞 Bible 生成: {node_key}"
        ) from exc

    if not prompt or not prompt.system or not prompt.user:
        raise BiblePromptTemplateUnavailable(
            f"CPMS prompt node unavailable or incomplete: {node_key}"
        )
    return prompt


def parse_json_from_response(rsp: str):
    """从LLM响应中解析JSON。

    🔥 已废弃：此函数是旧版简易解析器。请使用 llm_json_extract.parse_llm_json_to_dict()。
    保留此函数仅为 auto_bible_generator 内部向后兼容。
    """
    from application.ai.llm_json_extract import parse_llm_json_to_dict as _unified_parse
    data, errs = _unified_parse(rsp)
    if data is not None:
        return data
    raise json.JSONDecodeError(errs[0] if errs else "parse failed", rsp, 0)


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


def _extract_outer_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1:
        return text
    if end != -1 and end > start:
        return text[start : end + 1]
    return text[start:]


# 常见的 LLM 输出中混入的非标准引号映射
_FIXABLE_QUOTES: Dict[int, str] = {
    0x201C: '"',   # " (左双引号)
    0x201D: '"',   # " (右双引号)
    0x2018: "'",   # ' (左单引号)
    0x2019: "'",   # ' (右单引号)
    0x201E: '"',   # " (双低-9引号)
    0x201F: '"',   # " (双高反转-9引号)
    0x2033: '"',   # ″ (双二分引号)
    0x2036: '"',   # ‶ (反转双三引号)
    0x275D: '"',   # ❝ (粗左双引号)
    0x275E: '"',   # ❞ (粗右双引号)
    0xFF02: '"',   # ＂ (全角双引号)
    0x02BA: "'",   # ʺ (修饰字母单引号)
    0x0060: "'",   # ` (反引号 – 仅在字符串内部替换)
}


def _normalize_quotes_in_json(text: str) -> str:
    """将 JSON 字符串值中的中文/非标准引号替换为 ASCII 引号。

    策略：仅在字符串值内部（两个 ASCII 双引号之间）进行替换，
    避免误伤 JSON 结构本身的括号。
    """
    result = []
    in_string = False
    escape = False

    for ch in text:
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
            cp = ord(ch)
            if cp in _FIXABLE_QUOTES:
                result.append(_FIXABLE_QUOTES[cp])
                continue
        result.append(ch)

    return "".join(result)


def _repair_json_string(text: str) -> str:
    text = text.strip()
    if not text:
        return text

    # 阶段 0：直接解析（最快路径）
    try:
        json.loads(text)
        return text
    except (json.JSONDecodeError, ValueError):
        pass

    # 阶段 1：标准化非 ASCII 引号后重试
    normalized = _normalize_quotes_in_json(text)
    if normalized != text:
        try:
            json.loads(normalized)
            return normalized
        except (json.JSONDecodeError, ValueError):
            pass
        text = normalized  # 后续修复基于标准化后的文本

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


def _parse_llm_json_to_dict(raw: str) -> Dict[str, Any]:
    """解析 LLM JSON 输出（委托统一管线）。

    🔥 之前自造了 parse_json_from_response + _repair_json_string，只覆盖 3-4 种情况，
    DeepSeek 的中文引号、思考链等处理不了。现在统一用 llm_json_extract 管线。
    """
    from application.ai.llm_json_extract import parse_llm_json_to_dict as _unified_parse
    data, errs = _unified_parse(raw)
    if data is not None:
        return data
    raise json.JSONDecodeError(errs[0] if errs else "parse failed", raw, 0)


def _infer_character_importance(char_data: Dict[str, Any]) -> str:
    """与前端人物关系图 importance 一致：primary / secondary / minor。"""
    role = str(char_data.get("role") or "").strip()
    desc_head = str(char_data.get("description") or "")[:160]
    blob = f"{role}{desc_head}"
    if "主角" in blob:
        return "primary"
    if any(k in blob for k in ("导师", "师父", "宿敌", "反派", "对手", "核心", "幕后")):
        return "secondary"
    return "minor"


def _map_location_kind(raw_type: str) -> str:
    """与 KnowledgeTriple.location_type 枚举对齐。"""
    t = str(raw_type or "")
    if "城" in t:
        return "city"
    if any(k in t for k in ("区域", "域", "境", "荒", "谷", "原", "山脉")):
        return "region"
    if any(k in t for k in ("建筑", "楼", "殿", "阁", "府", "宫", "塔")):
        return "building"
    if any(k in t for k in ("势力", "宗", "门", "派", "盟", "族")):
        return "faction"
    if any(k in t for k in ("特殊", "秘境", "领域", "遗迹", "墟")):
        return "realm"
    return "region"


def _default_location_importance(_loc_data: Dict[str, Any]) -> str:
    return "normal"


class AutoBibleGenerator:
    """自动 Bible 生成器

    根据小说标题，使用 LLM 生成：
    - 3-5 个主要人物（主角、配角、对手、导师等）
    - 2-3 个重要地点
    - 文风公约
    - 世界观（5维度框架）
    """

    def __init__(self, llm_service: LLMService, bible_service: BibleService, worldbuilding_service: WorldbuildingService = None, triple_repository: TripleRepository = None):
        self.llm_service = llm_service
        self.bible_service = bible_service
        self.worldbuilding_service = worldbuilding_service
        self.triple_repository = triple_repository

    def _prepare_locations_for_save(self, novel_id: str, locations: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
        """规范化地点列表，确保父节点优先、缺失父节点降级为根节点。"""
        prepared: list[Dict[str, Any]] = []
        seen_ids: set[str] = set()
        raw_to_final: dict[str, str] = {}

        for idx, loc_data in enumerate(locations or []):
            raw_id = loc_data.get("id")
            normalized_raw_id = (
                str(raw_id).strip()
                if isinstance(raw_id, str) and str(raw_id).strip()
                else ""
            )
            location_id = normalized_raw_id or f"{novel_id}-loc-{idx+1}"
            if location_id in seen_ids:
                logger.info("Location ID %s already exists in generated payload, generating fallback ID", location_id)
                location_id = f"{novel_id}-loc-{idx+1}-{len(seen_ids)}"
            seen_ids.add(location_id)
            if normalized_raw_id and normalized_raw_id not in raw_to_final:
                raw_to_final[normalized_raw_id] = location_id

            prepared.append(
                {
                    "location_id": location_id,
                    "name": loc_data["name"],
                    "description": loc_data["description"],
                    "location_type": loc_data.get("type", "场景"),
                    "connections": loc_data.get("connections", []),
                    "raw_parent_id": loc_data.get("parent_id"),
                }
            )

        valid_ids = {item["location_id"] for item in prepared}
        for item in prepared:
            p_raw = item.pop("raw_parent_id", None)
            parent_id = (
                str(p_raw).strip()
                if isinstance(p_raw, str) and str(p_raw).strip()
                else None
            )
            if parent_id:
                parent_id = raw_to_final.get(parent_id, parent_id)
            if parent_id and parent_id not in valid_ids:
                logger.warning(
                    "Generated location %s references missing parent_id=%s, degrading to root node",
                    item["location_id"],
                    parent_id,
                )
                parent_id = None
            item["parent_id"] = parent_id

        ordered: list[Dict[str, Any]] = []
        remaining = prepared[:]
        saved_ids: set[str] = set()
        while remaining:
            progressed = False
            next_remaining: list[Dict[str, Any]] = []
            for item in remaining:
                parent_id = item["parent_id"]
                if parent_id is None or parent_id in saved_ids:
                    ordered.append(item)
                    saved_ids.add(item["location_id"])
                    progressed = True
                else:
                    next_remaining.append(item)

            if not progressed:
                for item in next_remaining:
                    logger.warning(
                        "Location %s still has unresolved parent %s after ordering, degrading to root node",
                        item["location_id"],
                        item["parent_id"],
                    )
                    item["parent_id"] = None
                    ordered.append(item)
                    saved_ids.add(item["location_id"])
                break

            remaining = next_remaining

        return ordered

    async def generate_and_save(
        self,
        novel_id: str,
        premise: str,
        target_chapters: int,
        stage: str = "all"
    ) -> Dict[str, Any]:
        """生成并保存 Bible（支持分阶段）

        Args:
            novel_id: 小说 ID
            premise: 故事梗概/创意
            target_chapters: 目标章节数
            stage: 生成阶段 (all/worldbuilding/characters/locations)

        Returns:
            生成的 Bible 数据
        """
        logger.info(f"Generating Bible for novel: {premise[:50]}... (stage: {stage})")

        ensure_trace(novel_id=novel_id, stage="world.bible.generate", stage_label="圣经生成")

        # 1. 创建空 Bible（如果不存在）
        bible_id = f"{novel_id}-bible"
        try:
            existing_bible = self.bible_service.get_bible_by_novel(novel_id)
            if existing_bible:
                logger.info(f"Bible already exists for novel {novel_id}")
            else:
                logger.info(f"Bible not found for novel {novel_id}, creating new one")
                self.bible_service.create_bible(bible_id, novel_id)
                logger.info(f"Successfully created Bible {bible_id} for novel {novel_id}")
        except Exception as e:
            logger.error(f"Error checking/creating Bible: {e}")
            # 尝试创建
            try:
                self.bible_service.create_bible(bible_id, novel_id)
                logger.info(f"Successfully created Bible {bible_id} for novel {novel_id}")
            except Exception as create_error:
                logger.error(f"Failed to create Bible: {create_error}")
                raise

        # 2. 根据阶段生成不同内容
        if stage == "all":
            # 一次性生成所有内容（向后兼容）
            bible_data = await self._generate_bible_data(premise, target_chapters)
            await self._save_to_bible(novel_id, bible_data)
            if self.worldbuilding_service and "worldbuilding" in bible_data:
                await self._save_worldbuilding(novel_id, bible_data["worldbuilding"])

        elif stage == "worldbuilding":
            logger.debug("Stage worldbuilding - checking Bible record")
            # 确保Bible记录存在
            try:
                self.bible_service.get_bible_by_novel(novel_id)
            except EntityNotFoundError:
                bible_id = f"{novel_id}-bible"
                self.bible_service.create_bible(bible_id, novel_id)
                logger.info(f"Created Bible record: {bible_id}")

            logger.debug("Calling _generate_worldbuilding_and_style")
            # 只生成世界观和文风
            bible_data = await self._generate_worldbuilding_and_style(premise, target_chapters)
            logger.debug("_generate_worldbuilding_and_style completed, keys=%s", list(bible_data.keys()))
            logger.debug("Has 'worldbuilding' key: %s, worldbuilding_service is None: %s", 'worldbuilding' in bible_data, self.worldbuilding_service is None)
            # 保存文风
            if "style" in bible_data:
                style_id = f"{novel_id}-style-1"
                try:
                    self.bible_service.add_style_note(
                        novel_id=novel_id,
                        note_id=style_id,
                        category="文风公约",
                        content=bible_data["style"]
                    )
                    logger.info(f"Style note saved: {style_id}")
                except Exception as e:
                    if "already exists" in str(e):
                        logger.info(f"Style note {style_id} already exists, skipping")
                    else:
                        logger.error(f"Failed to save style note: {e}")
                        raise
            # 保存世界观
            if self.worldbuilding_service and "worldbuilding" in bible_data:
                await self._save_worldbuilding(novel_id, bible_data["worldbuilding"])

        elif stage == "characters":
            # 确保Bible记录存在
            try:
                self.bible_service.get_bible_by_novel(novel_id)
            except EntityNotFoundError:
                bible_id = f"{novel_id}-bible"
                self.bible_service.create_bible(bible_id, novel_id)
                logger.info(f"Created Bible record: {bible_id}")

            # 基于已有世界观生成人物
            existing_worldbuilding = self._load_worldbuilding(novel_id)
            bible_data = await self._generate_characters(premise, target_chapters, existing_worldbuilding)
            chars_payload = bible_data.get("characters") or []
            if not chars_payload:
                raise ValueError(
                    "角色生成未得到任何人物：多为模型输出非 JSON、截断或解析失败。"
                    "请确认 AI 控制台模型可用并适当增大超时；也可查看服务端日志中的 LLM 原始片段。"
                )
            # 保存人物
            character_ids = []
            used_char_ids = set()  # 用于跟踪已使用的人物ID
            for idx, char_data in enumerate(bible_data.get("characters", [])):
                character_id = f"{novel_id}-char-{idx+1}"
                
                # 检查并处理重复ID
                if character_id in used_char_ids:
                    logger.info(f"Character ID {character_id} already exists, generating new ID")
                    character_id = f"{novel_id}-char-{idx+1}-{len(used_char_ids)}"
                
                used_char_ids.add(character_id)
                try:
                    self.bible_service.add_character(
                        novel_id=novel_id,
                        character_id=character_id,
                        name=char_data["name"],
                        description=f"{char_data['role']} - {char_data['description']}",
                        relationships=char_data.get("relationships", []),
                        gender=char_data.get("gender") or "",
                        age=char_data.get("age") or "",
                        appearance=char_data.get("appearance") or "",
                        personality=char_data.get("personality") or char_data.get("flaw") or "",
                        background=char_data.get("background") or char_data.get("ghost") or "",
                        core_motivation=char_data.get("core_motivation") or char_data.get("want") or "",
                        inner_lack=char_data.get("inner_lack") or char_data.get("need") or "",
                        public_profile=char_data.get("public_profile") or "",
                        hidden_profile=char_data.get("hidden_profile") or "",
                        reveal_chapter=char_data.get("reveal_chapter"),
                        mental_state=char_data.get("mental_state") or "NORMAL",
                        mental_state_reason=char_data.get("mental_state_reason") or "",
                        verbal_tic=char_data.get("verbal_tic") or "",
                        idle_behavior=char_data.get("idle_behavior") or "",
                        core_belief=char_data.get("core_belief") or "",
                        moral_taboos=char_data.get("moral_taboos") or [],
                        voice_profile=char_data.get("voice_profile") or {},
                        active_wounds=char_data.get("active_wounds") or [],
                    )
                    character_ids.append((character_id, char_data))
                    logger.info(f"Character saved: {character_id}")
                except Exception as e:
                    if "already exists" in str(e):
                        logger.info(f"Character {character_id} already exists, skipping")
                    else:
                        logger.error(f"Failed to save character: {e}")
                        raise

            # 从人物关系生成三元组
            if self.triple_repository:
                await self._generate_character_triples(novel_id, character_ids)

        elif stage == "locations":
            # 确保Bible记录存在
            try:
                self.bible_service.get_bible_by_novel(novel_id)
            except EntityNotFoundError:
                bible_id = f"{novel_id}-bible"
                self.bible_service.create_bible(bible_id, novel_id)
                logger.info(f"Created Bible record: {bible_id}")

            # 基于已有世界观和人物生成地点
            existing_worldbuilding = self._load_worldbuilding(novel_id)
            existing_characters = self._load_characters(novel_id)
            bible_data = await self._generate_locations(premise, target_chapters, existing_worldbuilding, existing_characters)
            locs_payload = bible_data.get("locations") or []
            if not locs_payload:
                raise ValueError(
                    "地点生成未得到任何地点：多为模型输出非 JSON、截断或解析失败。"
                    "请确认 AI 控制台模型可用并适当增大超时；也可查看服务端日志中的 LLM 原始片段。"
                )
            # 保存地点
            location_ids = []
            for loc_data in self._prepare_locations_for_save(novel_id, bible_data.get("locations", [])):
                try:
                    self.bible_service.add_location(
                        novel_id=novel_id,
                        location_id=loc_data["location_id"],
                        name=loc_data["name"],
                        description=loc_data["description"],
                        location_type=loc_data["location_type"],
                        connections=loc_data["connections"],
                        parent_id=loc_data["parent_id"],
                    )
                    location_ids.append((loc_data["location_id"], loc_data))
                    logger.info(f"Location saved: {loc_data['location_id']}")
                except Exception as e:
                    if "already exists" in str(e):
                        logger.info(f"Location {loc_data['location_id']} already exists, skipping")
                    else:
                        logger.error(f"Failed to save location: {e}")
                        raise

            # 从地点连接生成三元组
            if self.triple_repository:
                await self._generate_location_triples(novel_id, location_ids)

        else:
            raise ValueError(f"Unknown stage: {stage}")

        logger.info(f"Bible generation completed for {novel_id} (stage: {stage})")
        return bible_data

    async def _generate_bible_data(self, premise: str, target_chapters: int) -> Dict[str, Any]:
        """使用 LLM 生成 Bible 数据和世界观"""

        prompt = _render_required_bible_prompt(
            BIBLE_ALL,
            {
                "premise": premise,
                "genre": "",
                "target_chapters": target_chapters,
            },
        )

        bible_data = await self._call_llm_and_parse_with_retry(prompt.system, prompt.user)
        if bible_data:
            return bible_data

        logger.error("Failed to generate Bible data, falling back to default structure")
        return {
                "characters": [
                    {
                        "name": "主角",
                        "role": "主角",
                        "description": "待补充"
                    }
                ],
                "locations": [
                    {
                        "id": "loc-default-1",
                        "name": "主要场景",
                        "type": "城市",
                        "description": "待补充",
                        "parent_id": None,
                    }
                ],
                "style": "第三人称有限视角，轻松幽默"
            }

    async def _save_to_bible(self, novel_id: str, bible_data: Dict[str, Any]) -> None:
        """保存到 Bible"""

        # 先确保 Bible 记录存在
        try:
            from domain.novel.value_objects.novel_id import NovelId
            existing_bible = self.bible_service.bible_repository.get_by_novel_id(NovelId(novel_id))
            if existing_bible is None:
                # 创建 Bible 记录
                bible_id = f"bible-{novel_id}"
                self.bible_service.create_bible(bible_id=bible_id, novel_id=novel_id)
                logger.info(f"Created Bible record for novel {novel_id}")
        except Exception as e:
            logger.error(f"Failed to ensure Bible exists: {e}")
            return

        # 添加人物
        used_character_ids = set()  # 用于跟踪已使用的人物ID
        for idx, char_data in enumerate(bible_data.get("characters", [])):
            character_id = f"{novel_id}-char-{idx+1}"
            
            # 检查并处理重复ID
            if character_id in used_character_ids:
                logger.info(f"Character ID {character_id} already exists, generating new ID")
                character_id = f"{novel_id}-char-{idx+1}-{len(used_character_ids)}"
            
            used_character_ids.add(character_id)
            try:
                self.bible_service.add_character(
                    novel_id=novel_id,
                    character_id=character_id,
                    name=char_data["name"],
                    description=f"{char_data['role']} - {char_data['description']}"
                )
                logger.info(f"Character saved: {character_id}")
            except Exception as e:
                if "already exists" in str(e):
                    logger.info(f"Character {character_id} already exists, skipping")
                else:
                    logger.error(f"Failed to save character: {e}")
                    raise

        # 添加地点
        for loc_data in self._prepare_locations_for_save(novel_id, bible_data.get("locations", [])):
            try:
                self.bible_service.add_location(
                    novel_id=novel_id,
                    location_id=loc_data["location_id"],
                    name=loc_data["name"],
                    description=loc_data["description"],
                    location_type=loc_data["location_type"],
                    parent_id=loc_data["parent_id"],
                )
                logger.info(f"Location saved: {loc_data['location_id']}")
            except Exception as e:
                if "already exists" in str(e):
                    logger.info(f"Location {loc_data['location_id']} already exists, skipping")
                else:
                    logger.error(f"Failed to save location: {e}")
                    raise

        # 添加风格笔记
        style = bible_data.get("style", "")
        if style:
            style_id = f"{novel_id}-style-1"
            try:
                self.bible_service.add_style_note(
                    novel_id=novel_id,
                    note_id=style_id,
                    category="文风公约",
                    content=style
                )
                logger.info(f"Style note saved: {style_id}")
            except Exception as e:
                # 如果已存在则更新
                if "already exists" in str(e):
                    logger.info(f"Style note {style_id} already exists, skipping")
                else:
                    logger.error(f"Failed to save style note: {e}")
                    raise

    async def _save_worldbuilding(self, novel_id: str, worldbuilding_data: Dict[str, Any]) -> None:
        """保存世界观到 Worldbuilding V2 主文档。"""
        from application.world.worldbuilding_schema import validate_complete_dimension_fields

        logger.debug("_save_worldbuilding called")

        normalized_wb: Dict[str, Dict[str, str]] = {}
        for dim_key, dim_data in (worldbuilding_data or {}).items():
            if isinstance(dim_data, dict):
                normalized = validate_complete_dimension_fields(dim_key, dim_data)
                if normalized:
                    normalized_wb[dim_key] = normalized

        # 1. 保存到Worldbuilding表（用于后续生成人物和地点时读取）
        if self.worldbuilding_service:
            try:
                logger.debug("Calling worldbuilding_service.update_worldbuilding")
                self.worldbuilding_service.update_worldbuilding(
                    novel_id=novel_id,
                    core_rules=normalized_wb.get("core_rules"),
                    geography=normalized_wb.get("geography"),
                    society=normalized_wb.get("society"),
                    culture=normalized_wb.get("culture"),
                    daily_life=normalized_wb.get("daily_life")
                )
                logger.debug("Worldbuilding saved to Worldbuilding table")
                logger.info(f"Worldbuilding saved for {novel_id}")
            except Exception as e:
                logger.error("Failed to save worldbuilding: %s", e)

        # Worldbuilding V2 is the single source of truth for the five-dimension
        # world model. Bible.world_settings remains available for loose,
        # encyclopedia-like rules, but new wizard worldbuilding no longer writes
        # there.

    def _load_worldbuilding(self, novel_id: str) -> Dict[str, Any]:
        """加载已有世界观：V2 优先，旧数据在 loader 边界兼容。"""
        from application.world.services.narrative_contract_loader import load_merged_worldbuilding_slices

        bible = None
        try:
            bible = self.bible_service.get_bible_by_novel(novel_id)
        except Exception:
            bible = None

        wb_entity = None
        if self.worldbuilding_service:
            try:
                wb_entity = self.worldbuilding_service.get_worldbuilding(novel_id)
            except Exception:
                wb_entity = None

        return load_merged_worldbuilding_slices(bible=bible, worldbuilding=wb_entity)

    def _load_characters(self, novel_id: str) -> list:
        """加载已有人物"""
        try:
            bible = self.bible_service.get_bible_by_novel(novel_id)
            if bible is None:
                return []
            return [
                {
                    "name": c.name,
                    "description": c.description,
                    "gender": getattr(c, "gender", "") or "",
                    "age": getattr(c, "age", "") or "",
                    "appearance": getattr(c, "appearance", "") or "",
                    "personality": getattr(c, "personality", "") or "",
                    "background": getattr(c, "background", "") or "",
                    "core_motivation": getattr(c, "core_motivation", "") or "",
                    "inner_lack": getattr(c, "inner_lack", "") or "",
                    "public_profile": getattr(c, "public_profile", "") or "",
                    "hidden_profile": getattr(c, "hidden_profile", "") or "",
                    "mental_state": getattr(c, "mental_state", "") or "",
                    "mental_state_reason": getattr(c, "mental_state_reason", "") or "",
                    "core_belief": getattr(c, "core_belief", "") or "",
                    "relationships": list(getattr(c, "relationships", None) or []),
                    "active_wounds": list(getattr(c, "active_wounds", None) or []),
                }
                for c in bible.characters
            ]
        except Exception:
            return []

    async def _generate_worldbuilding_and_style(self, premise: str, target_chapters: int) -> Dict[str, Any]:
        """只生成世界观和文风（一次性生成全部5维度，向后兼容非SSE场景）"""
        prompt = _render_required_bible_prompt(
            BIBLE_WORLDBUILDING,
            {
                "premise": premise,
                "novel_title": "",
                "genre_major": "",
                "genre_theme": "",
                "genre_label": "",
                "world_preset": "",
                "target_chapters": target_chapters,
                "target_words_per_chapter": 0,
                "special_requirements": "",
                "worldbuilding_full": "",
                "core_rules": "",
                "geography": "",
                "society": "",
                "culture": "",
                "daily_life": "",
                "fields_desc": self._build_worldbuilding_json_schema_desc(),
                "novel_setup": f"故事创意：{premise}\n目标章节数：{target_chapters}",
                "genre_opening_profile": {},
                "genre_reader_contract": {},
                "genre_rhythm_constraints": {},
            },
        )

        data = await self._call_llm_and_parse_with_retry(prompt.system, prompt.user)
        worldbuilding = data.get("worldbuilding") if isinstance(data.get("worldbuilding"), dict) else {}
        if "worldbuilding_full" not in data:
            from application.world.services.narrative_contract_text import build_worldbuilding_prompt_fields

            data["worldbuilding_full"] = build_worldbuilding_prompt_fields(
                worldbuilding_slices=worldbuilding,
            ).get("worldbuilding_full", "")
        return data

    def _build_worldbuilding_json_schema_desc(self) -> str:
        """五维完整字段模板（单次流式输出用）。"""
        from application.world.worldbuilding_schema import build_fields_desc_for_prompt

        return build_fields_desc_for_prompt()

    def _build_worldbuilding_json_schema_desc_for(self, dimension_keys: list[str]) -> str:
        """指定维度字段模板（用于补齐缺失维度）。"""
        from application.world.worldbuilding_schema import build_fields_desc_for_prompt

        return build_fields_desc_for_prompt(dimension_keys)

    def _worldbuilding_dimension_prompt(
        self,
        *,
        dim_key: str,
        premise: str,
        target_chapters: int,
        accumulated: Dict[str, Dict[str, str]],
        attempt: int,
        missing_fields: set[str] | None = None,
    ) -> Prompt:
        """Render the CPMS worldbuilding prompt for one schema dimension."""
        fields_desc = self._build_worldbuilding_json_schema_desc_for([dim_key])
        prior_worldbuilding = json.dumps(accumulated, ensure_ascii=False, indent=2)[:8000]
        missing_text = "、".join(sorted(missing_fields or [])) or "无"
        profile = {
            "current_dimension": dim_key,
            "attempt": attempt,
            "missing_fields": sorted(missing_fields or []),
            "completed_worldbuilding": accumulated,
        }
        return _render_required_bible_prompt(
            BIBLE_WORLDBUILDING,
            {
                "premise": premise,
                "novel_title": "",
                "genre_major": "",
                "genre_theme": "",
                "genre_label": "",
                "world_preset": "",
                "target_chapters": target_chapters,
                "target_words_per_chapter": 0,
                "fields_desc": fields_desc,
                "genre_opening_profile": profile,
                "genre_reader_contract": {},
                "genre_rhythm_constraints": {},
                "special_requirements": (
                    f"本次只生成 `{dim_key}` 这一个世界观维度；"
                    "该维度必须是 JSON object，不得写成字符串；"
                    f"必须包含 fields_desc 列出的所有子字段。缺失字段：{missing_text}。"
                    f"已完成维度上下文：{prior_worldbuilding or '无'}"
                ),
            },
        )

    def _complete_worldbuilding_dimension(
        self,
        dim_key: str,
        content: Dict[str, Any],
    ) -> Dict[str, str]:
        from application.world.worldbuilding_schema import validate_complete_dimension_fields

        return validate_complete_dimension_fields(dim_key, content or {})

    async def _stream_worldbuilding_full(
        self,
        premise: str,
        target_chapters: int,
    ) -> AsyncIterator[Dict[str, Any]]:
        """逐维度流式生成完整五维世界观。

        每个维度单独调用 LLM，降低大 JSON 流式输出时漏字段/截断的概率。
        后续维度会收到已完成维度作为上下文，以保持设定之间的联动。

        Yields:
            {"type": "chunk", "text": str}
            {"type": "field", "key", "field", "value"}
            {"type": "dimension", "key": str, "content": dict}
            {"type": "done", "worldbuilding": dict}
        """
        from application.world.services.worldbuilding_stream_parser import (
            WorldbuildingStreamIncrementalParser,
        )
        from application.world.worldbuilding_merge import WORLD_BUILDING_DIMENSION_KEYS
        from application.world.worldbuilding_schema import schema_field_keys

        dimension_keys = tuple(WORLD_BUILDING_DIMENSION_KEYS)
        config = GenerationConfig(max_tokens=4096, temperature=0.55)
        accumulated: Dict[str, Dict[str, str]] = {}
        max_attempts = 2

        for dim_key in dimension_keys:
            completed: Dict[str, str] = {}
            missing = set(schema_field_keys(dim_key))

            for attempt in range(1, max_attempts + 1):
                dim_emitted = False
                parser = WorldbuildingStreamIncrementalParser()
                prompt = self._worldbuilding_dimension_prompt(
                    dim_key=dim_key,
                    premise=premise,
                    target_chapters=target_chapters,
                    accumulated=accumulated,
                    attempt=attempt,
                    missing_fields=missing,
                )

                try:
                    async for chunk in self.llm_service.stream_generate(prompt, config):
                        yield {"type": "chunk", "text": chunk}
                        for ev in parser.feed(chunk):
                            ev_type = ev.get("type")
                            event_dim = ev.get("key")
                            if ev_type:
                                logger.info(
                                    "Worldbuilding parser event: type=%s dim=%s field=%s value_len=%s",
                                    ev_type,
                                    event_dim,
                                    ev.get("field"),
                                    len(str(ev.get("value") or "")),
                                )
                            if event_dim != dim_key:
                                continue
                            if ev_type == "dimension_start":
                                yield ev
                            elif ev_type == "field":
                                fk, fv = ev.get("field"), ev.get("value")
                                if fk and fv:
                                    accumulated.setdefault(dim_key, {})[fk] = fv
                                yield ev
                            elif ev_type == "dimension":
                                dim_data = self._complete_worldbuilding_dimension(
                                    dim_key,
                                    ev.get("content") or {},
                                )
                                if dim_data:
                                    accumulated[dim_key] = dim_data
                                    completed = dim_data
                                    dim_emitted = True
                                    missing = set()
                                yield {"type": "dimension", "key": dim_key, "content": dim_data}

                    full_wb = parser.parse_full_worldbuilding(
                        sanitize=_sanitize_llm_json_output,
                        repair=_repair_json_string,
                    )
                    dim_data = self._complete_worldbuilding_dimension(
                        dim_key,
                        full_wb.get(dim_key) or accumulated.get(dim_key, {}),
                    )
                    if dim_data:
                        accumulated[dim_key] = dim_data
                        completed = dim_data
                        missing = set()
                        if not dim_emitted:
                            yield {"type": "dimension", "key": dim_key, "content": dim_data}
                        break

                    missing = schema_field_keys(dim_key) - set(accumulated.get(dim_key, {}))
                    logger.warning(
                        "Worldbuilding dimension incomplete after split generation: dim=%s attempt=%s missing=%s",
                        dim_key,
                        attempt,
                        sorted(missing),
                    )
                except Exception as e:
                    logger.error(
                        "Stream worldbuilding dimension failed: dim=%s attempt=%s error=%s",
                        dim_key,
                        attempt,
                        e,
                    )

            if not completed:
                raise RuntimeError(
                    f"世界观维度 {dim_key} 未按契约生成完整字段，缺失：{', '.join(sorted(missing)) or '字段长度不足'}"
                )

        yield {"type": "done", "worldbuilding": accumulated}

    # ── 文风公约（世界观由 _stream_worldbuilding_full 分维度流式生成）────────

    async def _generate_style(self, premise: str, target_chapters: int) -> str:
        """Generate style convention via CPMS."""
        chunks: list[str] = []
        async for item in self._stream_style(premise, target_chapters):
            if item.get("type") == "chunk":
                chunks.append(str(item.get("text") or ""))
            elif item.get("type") == "done":
                return str(item.get("style") or "").strip()
        return "".join(chunks).strip()

    async def _stream_style(
        self,
        premise: str,
        target_chapters: int,
    ) -> AsyncIterator[Dict[str, str]]:
        """Stream style convention tokens and return the final text."""
        from infrastructure.ai.prompt_keys import BIBLE_STYLE_CONVENTION
        from infrastructure.ai.prompt_registry import get_prompt_registry

        variables = {
            "premise": premise,
            "target_chapters": str(target_chapters),
        }

        registry = get_prompt_registry()
        prompt = registry.render_to_prompt(BIBLE_STYLE_CONVENTION, variables)

        if not prompt:
            raise BiblePromptTemplateUnavailable(
                f"CPMS prompt node unavailable or incomplete: {BIBLE_STYLE_CONVENTION}"
            )

        config = GenerationConfig(max_tokens=1024, temperature=0.7)
        chunks: list[str] = []
        async for chunk in self.llm_service.stream_generate(prompt, config):
            if not chunk:
                continue
            chunks.append(chunk)
            yield {"type": "chunk", "text": chunk}
        yield {"type": "done", "style": "".join(chunks).strip()}

    # 维度定义：key → (label, field_definitions)
    async def _generate_characters(self, premise: str, target_chapters: int, worldbuilding: Dict[str, Any]) -> Dict[str, Any]:
        """基于世界观生成人物"""
        from application.world.services.narrative_contract_text import build_worldbuilding_prompt_fields

        wb_fields = build_worldbuilding_prompt_fields(worldbuilding_slices=worldbuilding)

        prompt = _render_required_bible_prompt(
            BIBLE_CHARACTERS,
            {
                **wb_fields,
                "novel.premise": premise,
                "premise": premise,
                "target_chapters": target_chapters,
                "worldbuilding.content": worldbuilding or {},
                "worldbuilding.style": "",
                "style_guide": "",
                "existing_characters": "",
            },
        )

        return await self._call_llm_and_parse_with_retry(prompt.system, prompt.user)

    # ── 流式人物生成 ──

    async def _stream_generate_characters(
        self,
        premise: str,
        target_chapters: int,
        worldbuilding: Dict[str, Any],
    ) -> AsyncIterator[Dict[str, Any]]:
        """流式生成人物：LLM 逐 token 输出，增量解析 JSON 数组，
        每解析完一个角色对象立即 yield 给调用方。

        Yields:
            {"type": "character", "index": int, "content": dict}
            {"type": "chunk", "text": str}   — 原始 token（可选，用于调试/进度）
            {"type": "done", "count": int}   — 全部完成
        """
        from application.world.services.narrative_contract_text import build_worldbuilding_prompt_fields

        wb_fields = build_worldbuilding_prompt_fields(worldbuilding_slices=worldbuilding)
        prompt = _render_required_bible_prompt(
            BIBLE_CHARACTERS,
            {
                **wb_fields,
                "novel.premise": premise,
                "premise": premise,
                "target_chapters": target_chapters,
                "worldbuilding.content": worldbuilding or {},
                "worldbuilding.style": "",
                "style_guide": "",
                "existing_characters": "",
            },
        )
        config = GenerationConfig(max_tokens=4096, temperature=0.7)

        buf = ""
        char_index = 0
        try:
            async for chunk in self.llm_service.stream_generate(prompt, config):
                buf += chunk
                # yield 原始 chunk（前端可用于打字效果/进度）
                yield {"type": "chunk", "text": chunk}
                # 尝试增量解析已完成的角色对象
                while True:
                    parsed = _try_extract_next_item(buf, "characters")
                    if parsed is None:
                        break
                    char_data, buf = parsed
                    yield {"type": "character", "index": char_index, "content": char_data}
                    char_index += 1

        except Exception as e:
            logger.error("Stream generate characters failed: %s", e)
            # 流式失败后降级：尝试一次性解析已收集的完整 buffer
            if buf.strip():
                try:
                    full = _sanitize_llm_json_output(buf)
                    result = _parse_llm_json_to_dict(full) if full else {}
                    for ch in result.get("characters", []):
                        yield {"type": "character", "index": char_index, "content": ch}
                        char_index += 1
                except Exception:
                    pass

        yield {"type": "done", "count": char_index}

    async def _generate_locations(self, premise: str, target_chapters: int, worldbuilding: Dict[str, Any], characters: list) -> Dict[str, Any]:
        """基于世界观和人物生成地点"""
        prompt = _render_required_bible_prompt(
            BIBLE_LOCATIONS,
            {
                "novel.premise": premise,
                "worldbuilding.content": worldbuilding or {},
                "characters.list": characters or [],
            },
        )

        return await self._call_llm_and_parse_with_retry(prompt.system, prompt.user)

    # ── 流式地点生成 ──

    async def _stream_generate_locations(
        self,
        premise: str,
        target_chapters: int,
        worldbuilding: Dict[str, Any],
        characters: list,
    ) -> AsyncIterator[Dict[str, Any]]:
        """流式生成地点：LLM 逐 token 输出，增量解析 JSON 数组，
        每解析完一个地点对象立即 yield 给调用方。

        Yields: 同 _stream_generate_characters，type 为 location
        """
        prompt = _render_required_bible_prompt(
            BIBLE_LOCATIONS,
            {
                "novel.premise": premise,
                "worldbuilding.content": worldbuilding or {},
                "characters.list": characters or [],
            },
        )
        config = GenerationConfig(max_tokens=4096, temperature=0.7)

        buf = ""
        loc_index = 0
        try:
            async for chunk in self.llm_service.stream_generate(prompt, config):
                buf += chunk
                yield {"type": "chunk", "text": chunk}
                while True:
                    parsed = _try_extract_next_item(buf, "locations")
                    if parsed is None:
                        break
                    loc_data, buf = parsed
                    yield {"type": "location", "index": loc_index, "content": loc_data}
                    loc_index += 1

        except Exception as e:
            logger.error("Stream generate locations failed: %s", e)
            if buf.strip():
                try:
                    full = _sanitize_llm_json_output(buf)
                    result = _parse_llm_json_to_dict(full) if full else {}
                    for loc in result.get("locations", []):
                        yield {"type": "location", "index": loc_index, "content": loc}
                        loc_index += 1
                except Exception:
                    pass

        yield {"type": "done", "count": loc_index}

    def _summarize_worldbuilding(self, wb: Dict[str, Any]) -> str:
        """总结世界观为文本"""
        if not wb:
            return "无"

        parts = []
        for key, value in wb.items():
            if isinstance(value, dict):
                items = ", ".join([f"{k}: {v}" for k, v in value.items() if v])
                parts.append(f"{key}: {items}")
        return "\n".join(parts)

    async def _call_llm_and_parse(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        raise_on_unrecoverable: bool = False,
    ) -> Dict[str, Any]:
        """调用 LLM 并解析 JSON（含自动修复）"""
        prompt = Prompt(system=system_prompt, user=user_prompt)
        config = GenerationConfig(max_tokens=4096, temperature=0.7)
        result = await self.llm_service.generate(prompt, config)

        content = ""
        try:
            content = _sanitize_llm_json_output(result.content)
            # 第一轮：直接解析
            return _parse_llm_json_to_dict(content)
        except json.JSONDecodeError as e:
            logger.warning(f"Direct JSON parse failed, attempting repair: {e}")
            logger.debug(f"Content length: {len(content)}")
            logger.debug(f"Raw content (first 1000 chars): {content[:1000]}")

            # 第二轮：使用修复引擎（处理截断、中文引号、未闭合括号等）
            try:
                repaired = _repair_json_string(content)
                return _parse_llm_json_to_dict(repaired)
            except json.JSONDecodeError as e2:
                logger.error(f"Content length: {len(content)}")
                logger.error(f"Failed to parse JSON (even after repair): {e2}")
                logger.error(f"Raw content (first 1000 chars): {content[:1000]}")
                logger.error(f"Raw content (last 500 chars): {content[-500:]}")
                if raise_on_unrecoverable:
                    raise  # 向上抛出，让重试逻辑处理
                return {}

    async def _call_llm_and_parse_with_retry(
        self,
        system_prompt: str,
        user_prompt: str,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """带重试的 LLM 调用；总尝试次数不超过 LLM_MAX_TOTAL_ATTEMPTS。

        注意：当所有重试均失败时抛出 ValueError 而非返回空字典，
        以避免调用方将空结果当作有效数据继续处理。
        """
        from application.ai.llm_retry_policy import LLM_MAX_TOTAL_ATTEMPTS

        last_error = None
        attempts = min(max_retries, LLM_MAX_TOTAL_ATTEMPTS)

        for attempt in range(attempts):
            try:
                if attempt == 0:
                    # 第一次尝试，使用标准prompt
                    return await self._call_llm_and_parse(
                        system_prompt,
                        user_prompt,
                        raise_on_unrecoverable=True,
                    )
                else:
                    # 重试时加强调prompt
                    retry_reminder = "\n\n【重要提醒】上次JSON解析失败，请严格遵守JSON输出规则！只输出纯JSON，不要任何其他文字！"
                    logger.warning("JSON解析重试 %d/%d，添加强调提示", attempt, attempts)
                    return await self._call_llm_and_parse(
                        system_prompt + retry_reminder,
                        user_prompt,
                        raise_on_unrecoverable=True,
                    )
            except json.JSONDecodeError as e:
                last_error = e
                logger.warning("JSON解析失败，重试 %d/%d", attempt + 1, attempts)
            except Exception as e:
                last_error = e
                logger.warning("LLM调用异常，重试 %d/%d: %s", attempt + 1, attempts, e)

        # 所有重试均失败 → 抛出异常而非返回空字典
        error_msg = f"Bible LLM 生成在 {attempts} 次尝试后仍然失败（JSON 解析错误）"
        if last_error:
            error_msg += f": {last_error}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    async def _generate_character_triples(self, novel_id: str, character_ids: list):
        """从人物关系生成三元组"""
        logger.info(f"Generating character relationship triples for {novel_id}")

        # 创建人物名称到ID的映射
        name_to_id = {char_data["name"]: char_id for char_id, char_data in character_ids}
        id_to_char = {cid: data for cid, data in character_ids}

        for char_id, char_data in character_ids:
            relationships = char_data.get("relationships", [])
            if not relationships:
                continue

            for rel in relationships:
                # 支持两种格式：字符串或对象
                if isinstance(rel, str):
                    # 旧格式：字符串描述，尝试解析
                    target_name = None
                    predicate = "关系"
                    description = rel

                    # 简单的名称匹配
                    for other_id, other_data in character_ids:
                        if other_id != char_id and other_data["name"] in rel:
                            target_name = other_data["name"]
                            break

                    # 提取关系类型
                    if "师徒" in rel or "师从" in rel:
                        predicate = "师徒关系"
                    elif "朋友" in rel or "好友" in rel:
                        predicate = "朋友"
                    elif "敌对" in rel or "对手" in rel:
                        predicate = "敌对"
                    elif "家人" in rel or "亲属" in rel:
                        predicate = "家人"
                    elif "同事" in rel or "同僚" in rel:
                        predicate = "同事"
                else:
                    # 新格式：对象 {target, relation, description}
                    target_name = rel.get("target")
                    predicate = rel.get("relation", "关系")
                    description = rel.get("description", "")

                # 查找目标人物ID
                target_char_id = name_to_id.get(target_name)

                # 如果找到了目标人物，创建三元组
                if target_char_id:
                    target_char = id_to_char.get(target_char_id, {})
                    subj_imp = _infer_character_importance(char_data)
                    obj_imp = _infer_character_importance(target_char)
                    triple = Triple(
                        id=f"triple-{uuid.uuid4().hex[:8]}",
                        novel_id=novel_id,
                        subject_type="character",
                        subject_id=char_id,
                        predicate=predicate,
                        object_type="character",
                        object_id=target_char_id,
                        confidence=0.9,
                        source_type=SourceType.BIBLE_GENERATED,
                        description=description,
                        attributes={
                            "subject_label": char_data["name"],
                            "object_label": target_name,
                            "subject_importance": subj_imp,
                            "object_importance": obj_imp,
                        },
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    try:
                        await self.triple_repository.save(triple)
                        logger.info(f"Created triple: {char_data['name']} -{predicate}-> {target_name}")
                    except Exception as e:
                        logger.error(f"Failed to save triple: {e}")

    async def _generate_location_triples(self, novel_id: str, location_ids: list):
        """从地点连接生成三元组"""
        logger.info(f"Generating location connection triples for {novel_id}")

        # 创建地点名称到ID的映射
        name_to_id = {loc_data["name"]: loc_id for loc_id, loc_data in location_ids}
        id_to_loc = {lid: data for lid, data in location_ids}

        for loc_id, loc_data in location_ids:
            connections = loc_data.get("connections", [])
            if not connections:
                continue

            for conn in connections:
                # 支持两种格式：字符串或对象
                if isinstance(conn, str):
                    # 旧格式：字符串描述，尝试解析
                    target_name = None
                    predicate = "连接"
                    description = conn

                    # 简单的名称匹配
                    for other_id, other_data in location_ids:
                        if other_id != loc_id and other_data["name"] in conn:
                            target_name = other_data["name"]
                            break

                    # 提取连接类型
                    if "包含" in conn or "内部" in conn:
                        predicate = "包含"
                    elif "相邻" in conn or "毗邻" in conn:
                        predicate = "相邻"
                    elif "通往" in conn or "通向" in conn:
                        predicate = "通往"
                    elif "位于" in conn:
                        predicate = "位于"
                else:
                    # 新格式：对象 {target, relation, description}
                    target_name = conn.get("target")
                    predicate = conn.get("relation", "连接")
                    description = conn.get("description", "")

                pred_norm = (predicate or "").strip()
                if pred_norm == "位于":
                    continue

                # 查找目标地点ID
                target_loc_id = name_to_id.get(target_name)

                # 如果找到了目标地点，创建三元组
                if target_loc_id:
                    target_loc = id_to_loc.get(target_loc_id, {})
                    subj_lt = _map_location_kind(loc_data.get("type", ""))
                    obj_lt = _map_location_kind(target_loc.get("type", ""))
                    subj_imp = _default_location_importance(loc_data)
                    obj_imp = _default_location_importance(target_loc)
                    triple = Triple(
                        id=f"triple-{uuid.uuid4().hex[:8]}",
                        novel_id=novel_id,
                        subject_type="location",
                        subject_id=loc_id,
                        predicate=predicate,
                        object_type="location",
                        object_id=target_loc_id,
                        confidence=0.9,
                        source_type=SourceType.BIBLE_GENERATED,
                        description=description,
                        attributes={
                            "subject_label": loc_data["name"],
                            "object_label": target_name,
                            "subject_importance": subj_imp,
                            "subject_location_type": subj_lt,
                            "object_importance": obj_imp,
                            "object_location_type": obj_lt,
                        },
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    try:
                        await self.triple_repository.save(triple)
                        logger.info(f"Created triple: {loc_data['name']} -{predicate}-> {target_name}")
                    except Exception as e:
                        logger.error(f"Failed to save triple: {e}")
