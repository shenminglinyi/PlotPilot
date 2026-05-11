"""章节保存后：LLM 生成章末总结 → 节拍沿用既有规划 → StoryKnowledge → 向量索引。

节拍来源（按优先级，不由 LLM 现编）：
1. 知识库里该章已有 beat_sections（宏观规划 / 用户手填）
2. 结构树中该章节点 outline（规划节拍，按换行/分号拆条）
3. 仍无则保持空列表，仅写 summary。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from domain.ai.services.llm_service import LLMService, GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from domain.novel.value_objects.foreshadowing import (
    Foreshadowing,
    ForeshadowingStatus,
    ImportanceLevel,
)
from domain.novel.value_objects.novel_id import NovelId
from domain.structure.story_node import NodeType
from application.ai.structured_json_pipeline import (
    parse_and_repair_json,
    sanitize_llm_output,
)

logger = logging.getLogger(__name__)


def _extract_json_object(text: str) -> dict:
    """从模型输出中解析 JSON 对象，优先走通用清洗/修复管线。"""
    cleaned = sanitize_llm_output(text or "")
    if not cleaned:
        return {}

    data, errors = parse_and_repair_json(cleaned)
    if data is not None:
        return data

    raise json.JSONDecodeError(
        "Unable to parse chapter bundle JSON",
        cleaned,
        0,
    )


def _beats_from_structure_outline(novel_id: str, chapter_number: int) -> List[str]:
    """从结构树章节节点的 outline 拆成节拍条（规划层本来就有）。"""
    try:
        from application.paths import get_db_path
        from infrastructure.persistence.database.story_node_repository import StoryNodeRepository

        repo = StoryNodeRepository(str(get_db_path()))
        nodes = repo.get_by_novel_sync(novel_id)
        for n in nodes:
            if n.node_type != NodeType.CHAPTER:
                continue
            if int(n.number) != int(chapter_number):
                continue
            outline = (n.outline or "").strip()
            if not outline:
                return []
            # 优先按“行”拆分；若为一段式大纲，则再按常见中文标点拆分，避免 beat_sections 为空
            parts = re.split(r"[\n\r]+", outline)
            cleaned = [p.strip() for p in parts if p.strip()]
            if len(cleaned) <= 1:
                parts = re.split(r"[；;。！？!?]+", outline)
                cleaned = [p.strip() for p in parts if p.strip()]
            return cleaned[:32]
    except Exception as e:
        logger.debug("从结构树取 outline 失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)
    return []


def _resolve_beat_sections(
    novel_id: str,
    chapter_number: int,
    existing_beats: List[str],
) -> List[str]:
    """节拍：优先已有知识库条；否则用结构树 outline。"""
    cleaned = [str(b).strip() for b in (existing_beats or []) if str(b).strip()]
    if cleaned:
        return cleaned
    return _beats_from_structure_outline(novel_id, chapter_number)


async def llm_chapter_extract_bundle(
    llm: LLMService,
    chapter_content: str,
    chapter_number: int,
    pending_foreshadows: Optional[List[str]] = None,
) -> dict:
    """一次 LLM 调用：叙事摘要 + 关键事件/埋线 + 人物关系三元组 + 伏笔线索 + 伏笔消费检测 + 故事线进展 + 张力值 + 对话提取（避免多次调用）。
    
    Args:
        llm: LLM 服务
        chapter_content: 章节正文
        chapter_number: 章节号
        pending_foreshadows: 待回收伏笔描述列表（用于消费检测）
    """
    body = chapter_content.strip()
    if len(body) > 24000:
        body = body[:24000] + "\n\n…（正文过长已截断）"

    # 构建待回收伏笔提示
    foreshadow_context = ""
    if pending_foreshadows:
        foreshadow_list = "\n".join(f"  - {f}" for f in pending_foreshadows[:15])
        foreshadow_context = f"""
【待回收伏笔清单】
{foreshadow_list}

请判断本章是否呼应/回收了上述伏笔。如果章节内容明确揭示或回应了某个伏笔的悬念，则在 consumed_foreshadows 中列出该伏笔的原描述（需与清单中的描述高度匹配）。"""

    system = f"""你是网文叙事编辑与信息抽取。根据章节正文输出**一个** JSON 对象（不要其它说明文字）：
{{
  "summary": "string，200～500 字，章末叙事总结，便于检索与衔接",
  "key_events": "string",
  "open_threads": "string",
  "relation_triples": [ {{"subject": "主体", "predicate": "关系", "object": "客体"}} ],
  "foreshadow_hints": [ {{
    "description": "伏笔或悬念描述",
    "suggested_resolve_offset": 5,
    "importance": "medium",
    "resolve_hint": "预期回收场景提示"
  }} ],
  "consumed_foreshadows": [ "被回收的伏笔描述1", "被回收的伏笔描述2" ],
  "storyline_progress": [ {{"type": "主线|支线|感情线", "description": "本章该线进展"}} ],
  "dialogues": [ {{"speaker": "角色名", "content": "对话内容", "context": "对话场景"}} ],
  "timeline_events": [ {{"time_point": "时间描述", "event": "事件摘要", "description": "详细说明"}} ],
  "causal_edges": [ {{
    "source_event": "因果源事件描述",
    "causal_type": "causes",
    "target_event": "因果目标事件描述",
    "state_change": "角色内在状态如何变化",
    "involved_characters": ["角色名1"],
    "strength": 0.8
  }} ],
  "character_mutations": [ {{
    "character_name": "角色名",
    "mutation_type": "scar",
    "source_event": "触发事件描述",
    "impact_or_description": "心理影响或执念描述",
    "sensitivity_tags_or_priority": ["敏感词1"] 或 8,
    "intensity": 8
  }} ]
}}
约束：
- relation_triples：只写文中明确出现的关系，最多 8 条；无则 []。
- foreshadow_hints：潜在伏笔/未解悬念，最多 4 条；无则 []。
  - suggested_resolve_offset：建议在多少章后回收（整数，通常 3-15 章），快节奏短篇用 2-5，长篇用 5-15
  - importance：伏笔重要性，可选 "low"（次要）、"medium"（一般）、"high"（重要）、"critical"（关键）
  - resolve_hint：简短描述预期回收的场景或剧情点（可选，如"下一幕高潮"）
- consumed_foreshadows：本章回收/呼应的伏笔，从待回收清单中匹配，输出原描述；最多 5 条；无则 []。
- storyline_progress：本章推进的故事线，最多 5 条；无则 []。
- dialogues：重要对话（推动剧情/展现性格），最多 10 条；无则 []。
- timeline_events：本章发生的时间线事件（世界内历法/相对时间），最多 5 条；无则 []。
- causal_edges：本章中的因果关系链，最多 3 条；无则 []。
  - causal_type：可选 "causes"（导致）、"motivates"（驱动）、"triggers"（触发）、"prevents"（阻止）、"resolves"（解决）
  - state_change：描述角色内在状态变化，如"主角从'天真少年'变为'仇恨驱动的修行者'"
  - strength：因果强度 0-1，重大事件用 0.8-1.0，一般因果 0.5-0.7
- character_mutations：本章人物重大状态变化（心理创伤/新执念），最多 3 条；无则 []。
  - mutation_type："scar"（心理伤疤/创伤）或 "motivation"（新执念/新目标）或 "emotional_arc"（情感转折）
  - sensitivity_tags_or_priority：scar 填敏感标签数组如["背叛","信任"]；motivation 填优先级整数1-10
  - intensity：强度 1-10，10 为极端
- 不要编造 beat 列表；summary/key_events/open_threads 用中文；严格合法 JSON。{foreshadow_context}"""

    user = f"第 {chapter_number} 章正文如下：\n\n{body}"

    prompt = Prompt(system=system, user=user)
    config = GenerationConfig(max_tokens=4096, temperature=0.45)

    result = await llm.generate(prompt, config)
    raw = result.content if hasattr(result, "content") else str(result)
    data = _extract_json_object(raw)

    triples_raw = data.get("relation_triples") or data.get("triples") or []
    if not isinstance(triples_raw, list):
        triples_raw = []
    hints_raw = data.get("foreshadow_hints") or data.get("foreshadows") or []
    if not isinstance(hints_raw, list):
        hints_raw = []
    consumed_raw = data.get("consumed_foreshadows") or data.get("consumed") or []
    if not isinstance(consumed_raw, list):
        consumed_raw = []
    storyline_raw = data.get("storyline_progress") or []
    if not isinstance(storyline_raw, list):
        storyline_raw = []
    dialogues_raw = data.get("dialogues") or []
    if not isinstance(dialogues_raw, list):
        dialogues_raw = []
    timeline_raw = data.get("timeline_events") or []
    if not isinstance(timeline_raw, list):
        timeline_raw = []
    causal_raw = data.get("causal_edges") or []
    if not isinstance(causal_raw, list):
        causal_raw = []
    mutations_raw = data.get("character_mutations") or []
    if not isinstance(mutations_raw, list):
        mutations_raw = []

    return {
        "summary": str(data.get("summary", "")).strip(),
        "key_events": str(data.get("key_events", "")).strip(),
        "open_threads": str(data.get("open_threads", "")).strip(),
        # V9: 所有 LLM 提取的元数据默认标记为 "pending"，需要人类校准器确认
        # 原来直接截断不验证（[:8], [:4], [:3]），现在至少增加了状态标记
        # 后续 UI 界面可以展示 pending 项让作者确认/修改
        "relation_triples": [{"data": t, "status": "pending"} for t in triples_raw[:8]],
        "foreshadow_hints": [{"data": h, "status": "pending"} for h in hints_raw[:4]],
        "consumed_foreshadows": [str(c).strip() for c in consumed_raw[:5] if str(c).strip()],
        "storyline_progress": storyline_raw[:5],
        "dialogues": dialogues_raw[:10],
        "timeline_events": timeline_raw[:5],
        "causal_edges": [{"data": c, "status": "pending"} for c in causal_raw[:3]],
        "character_mutations": [{"data": m, "status": "pending"} for m in mutations_raw[:3]],
        # V9: 新增提取元数据，记录提取时的元信息
        "_meta": {
            "extract_version": "v9",
            "extraction_method": "llm",
            "needs_human_review": True,  # 默认需要人类审核
        },
    }


def _fuzzy_match_foreshadow(consumed_desc: str, pending_list: List[Any]) -> Optional[Any]:
    """模糊匹配消费的伏笔描述与待回收列表。
    
    Args:
        consumed_desc: LLM 返回的消费伏笔描述
        pending_list: 待回收伏笔列表（Foreshadowing 或 SubtextLedgerEntry）
    
    Returns:
        匹配到的伏笔对象，未匹配返回 None
    """
    if not consumed_desc or not pending_list:
        return None
    
    consumed_lower = consumed_desc.lower().strip()
    
    # 优先精确匹配
    for f in pending_list:
        desc = getattr(f, 'description', None) or getattr(f, 'question', None)
        if desc and desc.lower().strip() == consumed_lower:
            return f
    
    # 其次模糊匹配（包含关系）
    for f in pending_list:
        desc = getattr(f, 'description', None) or getattr(f, 'question', None)
        if desc:
            desc_lower = desc.lower().strip()
            # 检查是否有足够的重叠
            if consumed_lower in desc_lower or desc_lower in consumed_lower:
                return f
            # 检查关键词重叠（至少 50% 的词匹配）
            consumed_words = set(consumed_lower)
            desc_words = set(desc_lower)
            if consumed_words and desc_words:
                overlap = len(consumed_words & desc_words) / min(len(consumed_words), len(desc_words))
                if overlap >= 0.5:
                    return f
    
    return None


def persist_bundle_triples_and_foreshadows(
    novel_id: str,
    chapter_number: int,
    bundle: dict,
    triple_repository: Any,
    foreshadowing_repo: Any,
) -> None:
    """将 bundle 中的三元组与伏笔写入表，并处理伏笔消费状态更新。
    
    功能：
    1. 三元组落库
    2. 新伏笔注册（PLANTED 状态）
    3. 已消费伏笔状态更新（PLANTED -> RESOLVED / pending -> consumed）
    """
    triples = bundle.get("relation_triples") or []
    hints = bundle.get("foreshadow_hints") or []
    consumed = bundle.get("consumed_foreshadows") or []

    if triple_repository and triples:
        kr = getattr(triple_repository, "_kr", None)
        if kr is None:
            logger.warning("triple_repository 无 _kr，跳过三元组落库")
        else:
            for item in triples:
                # V9: 兼容新格式 {"data": t, "status": "pending"} 和旧格式（直接 dict）
                if isinstance(item, dict) and "data" in item:
                    actual_item = item["data"]
                    item_status = item.get("status", "pending")
                    # V9: pending 状态的项也落库，但 confidence 标记为 0.5（待人类确认）
                    confidence = 0.5 if item_status == "pending" else 0.7
                else:
                    actual_item = item
                    confidence = 0.7
                if not isinstance(actual_item, dict):
                    continue
                s = str(actual_item.get("subject", "")).strip()
                p = str(actual_item.get("predicate", "")).strip()
                o = str(actual_item.get("object", "")).strip()
                if not (s and p and o):
                    continue
                row = {
                    "id": str(uuid.uuid4()),
                    "subject": s,
                    "predicate": p,
                    "object": o,
                    "chapter_number": chapter_number,
                    "source_type": "autopilot_extract",
                    "confidence": confidence,  # V9: pending=0.5, confirmed=0.7
                    "entity_type": "character",
                    "note": "",
                }
                try:
                    kr.save_triple(novel_id, row)
                except Exception as e:
                    logger.debug("三元组落库跳过: %s", e)

    if foreshadowing_repo and hints:
        try:
            registry = foreshadowing_repo.get_by_novel_id(NovelId(novel_id))
            if not registry:
                # 创建新的 ForeshadowingRegistry
                from domain.novel.entities.foreshadowing_registry import ForeshadowingRegistry
                registry = ForeshadowingRegistry(
                    id=str(uuid.uuid4()),
                    novel_id=NovelId(novel_id)
                )
                logger.info("创建新伏笔账本 novel=%s", novel_id)

            # ★ Phase 2: 伏笔种植预算限制
            MAX_NEW_PER_CHAPTER = 2   # 每章最多种 2 条新伏笔
            MAX_TOTAL_PENDING = 15    # 总 pending 上限 15 条
            planted_count = 0
            current_pending = len(registry.get_unresolved())

            # ★ Phase 2: TTL 自动降级（每 10 章执行一次）
            if chapter_number % 10 == 0:
                try:
                    abandoned = registry.apply_ttl_downgrade(chapter_number, ttl_chapters=30)
                    if abandoned > 0:
                        logger.info(
                            "伏笔 TTL 降级 novel=%s ch=%s: 放弃 %d 条过期伏笔",
                            novel_id, chapter_number, abandoned
                        )
                        current_pending -= abandoned
                except Exception as e:
                    logger.warning("伏笔 TTL 降级失败: %s", e)

            for h in hints:
                # V9: 兼容新格式 {"data": h, "status": "pending"}
                if isinstance(h, dict) and "data" in h:
                    h = h["data"]
                if not isinstance(h, dict):
                    desc = str(h).strip()
                    resolve_offset = 5  # 默认 5 章后回收
                    importance_val = "medium"
                    resolve_hint = None
                else:
                    desc = str(h.get("description", "")).strip()
                    # 获取预期回收章节偏移量
                    resolve_offset = h.get("suggested_resolve_offset", 5)
                    try:
                        resolve_offset = int(resolve_offset)
                        resolve_offset = max(2, min(30, resolve_offset))  # 限制在 2-30 章
                    except (ValueError, TypeError):
                        resolve_offset = 5
                    # 获取重要性
                    importance_val = str(h.get("importance", "medium")).strip().lower()
                    if importance_val not in ("low", "medium", "high", "critical"):
                        importance_val = "medium"
                    # 获取回收提示
                    resolve_hint = h.get("resolve_hint")
                    if resolve_hint:
                        resolve_hint = str(resolve_hint).strip()[:100]  # 限制长度
                if not desc:
                    continue
                # ★ Phase 2: 种植预算检查
                planted_count += 1
                if planted_count > MAX_NEW_PER_CHAPTER:
                    logger.info(
                        "伏笔种植预算用尽 novel=%s ch=%s: 跳过第 %d 条（每章上限 %d）",
                        novel_id, chapter_number, planted_count, MAX_NEW_PER_CHAPTER
                    )
                    continue
                if current_pending >= MAX_TOTAL_PENDING:
                    logger.info(
                        "伏笔总 pending 上限达满 novel=%s ch=%s: 跳过种植（pending=%d, 上限=%d）",
                        novel_id, chapter_number, current_pending, MAX_TOTAL_PENDING
                    )
                    continue
                try:
                    # 计算预期回收章节 = 埋设章节 + 偏移量
                    suggested_resolve = chapter_number + resolve_offset
                    registry.register(
                        Foreshadowing(
                            id=str(uuid.uuid4()),
                            planted_in_chapter=max(1, chapter_number),
                            description=desc,
                            importance=_importance_str_to_level(importance_val),
                            status=ForeshadowingStatus.PLANTED,
                            suggested_resolve_chapter=suggested_resolve,
                        )
                    )
                    logger.debug(
                        "伏笔入库 novel=%s ch=%s resolve=%s importance=%s: %s",
                        novel_id, chapter_number, suggested_resolve, importance_val, desc[:50]
                    )
                    current_pending += 1  # ★ Phase 2: 跟踪 pending 计数
                except Exception as e:
                    logger.debug("伏笔入库跳过: %s", e)
            
            # 处理伏笔消费：将 LLM 识别的已消费伏笔标记为 RESOLVED/consumed
            if consumed:
                # 获取所有待回收伏笔
                pending_foreshadows = registry.get_unresolved()
                pending_subtext = registry.get_pending_subtext_entries()
                
                consumed_count = 0
                for consumed_desc in consumed:
                    if not consumed_desc:
                        continue
                    
                    # 1. 尝试匹配 Foreshadowing 对象
                    matched_foreshadow = _fuzzy_match_foreshadow(consumed_desc, pending_foreshadows)
                    if matched_foreshadow:
                        try:
                            registry.mark_resolved(
                                foreshadowing_id=matched_foreshadow.id,
                                resolved_in_chapter=chapter_number
                            )
                            consumed_count += 1
                            logger.info(
                                "伏笔已消费 novel=%s ch=%s: %s -> RESOLVED",
                                novel_id, chapter_number, consumed_desc[:50]
                            )
                            # 从待回收列表中移除已处理的
                            pending_foreshadows = [f for f in pending_foreshadows if f.id != matched_foreshadow.id]
                        except Exception as e:
                            logger.warning("伏笔消费状态更新失败: %s", e)
                        continue
                    
                    # 2. 尝试匹配 SubtextLedgerEntry 对象
                    matched_entry = _fuzzy_match_foreshadow(consumed_desc, pending_subtext)
                    if matched_entry:
                        try:
                            from dataclasses import replace
                            updated_entry = replace(
                                matched_entry,
                                status="consumed",
                                consumed_at_chapter=chapter_number
                            )
                            registry.update_subtext_entry(matched_entry.id, updated_entry)
                            consumed_count += 1
                            logger.info(
                                "潜台词条目已消费 novel=%s ch=%s: %s -> consumed",
                                novel_id, chapter_number, consumed_desc[:50]
                            )
                            # 从待回收列表中移除已处理的
                            pending_subtext = [e for e in pending_subtext if e.id != matched_entry.id]
                        except Exception as e:
                            logger.warning("潜台词条目消费状态更新失败: %s", e)
                
                if consumed_count > 0:
                    logger.info(
                        "伏笔消费检测完成 novel=%s ch=%s consumed=%d/%d",
                        novel_id, chapter_number, consumed_count, len(consumed)
                    )
            
            foreshadowing_repo.save(registry)
        except Exception as e:
            logger.warning("伏笔落库失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)


def _importance_str_to_level(importance_str: str) -> ImportanceLevel:
    """将字符串转换为 ImportanceLevel 枚举。"""
    mapping = {
        "low": ImportanceLevel.LOW,
        "medium": ImportanceLevel.MEDIUM,
        "high": ImportanceLevel.HIGH,
        "critical": ImportanceLevel.CRITICAL,
    }
    return mapping.get(importance_str, ImportanceLevel.MEDIUM)


def persist_causal_edges(
    novel_id: str,
    chapter_number: int,
    bundle: dict,
    causal_edge_repository: Any,
) -> int:
    """将 bundle 中的因果边写入 causal_edges 表，并检测已有因果边的闭环。

    Returns:
        成功落库的因果边数量
    """
    if not causal_edge_repository:
        return 0

    edges_raw = bundle.get("causal_edges") or []
    if not edges_raw:
        return 0

    from domain.novel.value_objects.causal_edge import CausalEdge, CausalType

    saved = 0
    for item in edges_raw:
        # V9: 兼容新格式 {"data": c, "status": "pending"}
        if isinstance(item, dict) and "data" in item:
            item = item["data"]
        if not isinstance(item, dict):
            continue

        source_event = str(item.get("source_event", "")).strip()
        target_event = str(item.get("target_event", "")).strip()
        if not (source_event and target_event):
            continue

        # 解析 causal_type
        causal_type_str = str(item.get("causal_type", "causes")).strip().lower()
        try:
            causal_type = CausalType(causal_type_str)
        except ValueError:
            causal_type = CausalType.CAUSES

        # 解析强度
        try:
            strength = float(item.get("strength", 0.8))
            strength = max(0.0, min(1.0, strength))
        except (ValueError, TypeError):
            strength = 0.8

        # 解析关联角色
        involved = item.get("involved_characters") or []
        if isinstance(involved, str):
            involved = [involved]

        state_change = str(item.get("state_change", "")).strip()

        edge = CausalEdge(
            novel_id=novel_id,
            source_event_summary=source_event,
            source_chapter=chapter_number,
            causal_type=causal_type,
            target_event_summary=target_event,
            target_chapter=None,  # 目标事件可能尚未发生
            strength=strength,
            confidence=0.7,
            state_change=state_change,
            involved_characters=[str(c).strip() for c in involved if str(c).strip()],
            is_resolved=False,
        )

        try:
            causal_edge_repository.save(edge)
            saved += 1
            logger.debug(
                "因果边入库 novel=%s ch=%s %s→%s type=%s strength=%.1f",
                novel_id, chapter_number,
                source_event[:30], target_event[:30],
                causal_type.value, strength,
            )
        except Exception as e:
            logger.debug("因果边入库跳过: %s", e)

    # ★ 检测因果边闭环：如果本章的事件匹配了某个未闭环因果边的 target_event
    if saved > 0 or bundle.get("summary") or bundle.get("key_events"):
        try:
            _try_resolve_causal_edges(novel_id, chapter_number, bundle, causal_edge_repository)
        except Exception as e:
            logger.debug("因果边闭环检测失败: %s", e)

    if saved > 0:
        logger.info("因果边落库完成 novel=%s ch=%s saved=%d", novel_id, chapter_number, saved)

    return saved


def _try_resolve_causal_edges(
    novel_id: str,
    chapter_number: int,
    bundle: dict,
    causal_edge_repository: Any,
) -> int:
    """检测本章事件是否闭环了已有的因果边。

    策略：检查 summary + key_events 中是否包含未闭环因果边的 target_event_summary 的关键词。
    """
    unresolved = causal_edge_repository.get_unresolved(novel_id)
    if not unresolved:
        return 0

    # 合并章节事件文本
    chapter_text = " ".join([
        str(bundle.get("summary", "")),
        str(bundle.get("key_events", "")),
        str(bundle.get("open_threads", "")),
    ]).lower()

    resolved_count = 0
    for edge in unresolved:
        # 简单关键词匹配：target_event 中的核心词出现在章节事件中
        target_lower = edge.target_event_summary.lower()
        # 提取关键片段（去掉常见连接词）
        keywords = [w for w in target_lower.split() if len(w) >= 2]
        if not keywords:
            # 对中文，使用整体匹配
            keywords = [target_lower]

        match_count = sum(1 for kw in keywords if kw in chapter_text)
        if keywords and match_count / len(keywords) >= 0.5:
            try:
                causal_edge_repository.resolve(edge.id, chapter_number)
                resolved_count += 1
                logger.info(
                    "因果边闭环 novel=%s ch=%s edge=%s %s→%s",
                    novel_id, chapter_number, edge.id[:8],
                    edge.source_event_summary[:20], edge.target_event_summary[:20],
                )
            except Exception as e:
                logger.debug("因果边闭环失败: %s", e)

    return resolved_count


def persist_character_mutations(
    novel_id: str,
    chapter_number: int,
    bundle: dict,
    character_state_repository: Any,
    bible_repository: Any = None,
) -> int:
    """将 bundle 中的 character_mutations 写入 character_states 表。

    策略：
    1. 从 LLM 返回的 character_mutations 中提取角色名
    2. 从 Bible 中查找 character_id
    3. 加载或创建 CharacterState
    4. 追加 Scar / Motivation / EmotionalArcNode

    Returns:
        成功处理的突变数量
    """
    if not character_state_repository:
        return 0

    mutations_raw = bundle.get("character_mutations") or []
    if not mutations_raw:
        return 0

    from domain.novel.value_objects.character_state import (
        CharacterState, Scar, Motivation, EmotionalArcNode,
    )

    # 构建 name → character_id 映射
    name_to_id: Dict[str, str] = {}
    if bible_repository:
        try:
            from domain.novel.value_objects.novel_id import NovelId
            bible = bible_repository.get_by_novel_id(NovelId(novel_id))
            if bible and bible.characters:
                for char in bible.characters:
                    name_to_id[char.name] = char.character_id.value if hasattr(char.character_id, 'value') else str(char.character_id)
        except Exception as e:
            logger.debug("Bible 加载失败，人物突变无法关联 character_id: %s", e)

    processed = 0
    for item in mutations_raw:
        # V9: 兼容新格式 {"data": m, "status": "pending"}
        if isinstance(item, dict) and "data" in item:
            item = item["data"]
        if not isinstance(item, dict):
            continue

        character_name = str(item.get("character_name", "")).strip()
        if not character_name:
            continue

        # 解析 character_id
        character_id = name_to_id.get(character_name, character_name)

        mutation_type = str(item.get("mutation_type", "scar")).strip().lower()
        source_event = str(item.get("source_event", "")).strip()
        impact_or_desc = str(item.get("impact_or_description", "")).strip()
        if not (source_event or impact_or_desc):
            continue

        # 解析强度
        try:
            intensity = int(item.get("intensity", 7))
            intensity = max(1, min(10, intensity))
        except (ValueError, TypeError):
            intensity = 7

        # 加载或创建 CharacterState
        state = character_state_repository.get(character_id, novel_id)
        if not state:
            # 从 Bible 获取 base_traits
            base_traits = []
            if bible_repository and character_name in name_to_id:
                try:
                    bible = bible_repository.get_by_novel_id(NovelId(novel_id))
                    if bible and bible.characters:
                        for char in bible.characters:
                            cid = char.character_id.value if hasattr(char.character_id, 'value') else str(char.character_id)
                            if cid == character_id:
                                if hasattr(char, 'traits') and char.traits:
                                    base_traits = list(char.traits)
                                elif hasattr(char, 'description') and char.description:
                                    base_traits = [char.description[:50]]
                                break
                except Exception:
                    pass

            state = CharacterState(
                character_id=character_id,
                novel_id=novel_id,
                base_traits=base_traits,
                last_updated_chapter=chapter_number,
            )

        # 根据类型追加状态
        if mutation_type == "scar":
            tags_or_priority = item.get("sensitivity_tags_or_priority", [])
            sensitivity_tags = []
            if isinstance(tags_or_priority, list):
                sensitivity_tags = [str(t).strip() for t in tags_or_priority if str(t).strip()]
            elif isinstance(tags_or_priority, (int, float)):
                # 如果误填了数字，作为 priority 提示但不用于 tags
                pass

            scar = Scar(
                source_event=source_event,
                source_chapter=chapter_number,
                impact=impact_or_desc,
                sensitivity_tags=sensitivity_tags,
                intensity=intensity,
            )
            state.add_scar(scar)

        elif mutation_type == "motivation":
            tags_or_priority = item.get("sensitivity_tags_or_priority", 5)
            try:
                priority = int(tags_or_priority)
                priority = max(1, min(10, priority))
            except (ValueError, TypeError):
                priority = 5

            motivation = Motivation(
                description=impact_or_desc,
                source_event=source_event,
                source_chapter=chapter_number,
                priority=priority,
            )
            state.add_motivation(motivation)

        elif mutation_type == "emotional_arc":
            arc_node = EmotionalArcNode(
                chapter=chapter_number,
                emotion=impact_or_desc,
                trigger=source_event,
                intensity=intensity,
                is_breakout=intensity >= 8,  # 高强度情感转折视为 breakout
            )
            state.add_emotional_arc_node(arc_node)

        else:
            # 未知类型，默认当 scar 处理
            scar = Scar(
                source_event=source_event,
                source_chapter=chapter_number,
                impact=impact_or_desc,
                intensity=intensity,
            )
            state.add_scar(scar)

        # 更新状态摘要和章节号
        state.current_state_summary = _build_state_summary(state)
        state.last_updated_chapter = chapter_number

        try:
            character_state_repository.save(state)
            processed += 1
            logger.debug(
                "人物状态突变入库 novel=%s ch=%s char=%s type=%s",
                novel_id, chapter_number, character_name, mutation_type,
            )
        except Exception as e:
            logger.debug("人物状态突变入库跳过: %s", e)

    if processed > 0:
        logger.info("人物状态突变落库完成 novel=%s ch=%s processed=%d", novel_id, chapter_number, processed)

    return processed


def _build_state_summary(state: Any) -> str:
    """根据当前状态构建简短摘要"""
    parts = []
    active_scars = state.get_active_scars()
    if active_scars:
        scar_desc = "; ".join(f"{s.impact}({s.intensity}/10)" for s in active_scars[:3])
        parts.append(f"伤疤: {scar_desc}")
    active_motivations = state.get_active_motivations()
    if active_motivations:
        top = state.get_top_motivations(3)
        mot_desc = "; ".join(f"{m.description}(P{m.priority})" for m in top)
        parts.append(f"执念: {mot_desc}")
    return " | ".join(parts) if parts else state.current_state_summary


def update_narrative_debts(
    novel_id: str,
    chapter_number: int,
    bundle: dict,
    debt_repository: Any,
    causal_edge_repository: Any = None,
) -> int:
    """根据本章内容更新叙事债务：新增债务 + 结算已回收债务 + 逾期标记。

    新增来源：
    1. 因果类债务：未闭环的高强度因果边
    2. 伏笔类债务：bundle 中的 foreshadow_hints
    3. 角色弧债务：character_mutations 中的 scar/motivation（已有优先级≥8 的执念需要闭环）

    结算来源：
    1. consumed_foreshadows 匹配已有债务
    2. 因果边闭环后自动结算对应债务

    Returns:
        新增债务数量
    """
    if not debt_repository:
        return 0

    from domain.novel.value_objects.narrative_debt import NarrativeDebt, DebtType

    new_debts = 0

    # ---- 1. 因果类债务：从 bundle 的 causal_edges 生成 ----
    causal_edges_raw = bundle.get("causal_edges") or []
    for edge_item in causal_edges_raw:
        # V9: 兼容新格式 {"data": c, "status": "pending"}
        if isinstance(edge_item, dict) and "data" in edge_item:
            edge_item = edge_item["data"]
        if not isinstance(edge_item, dict):
            continue
        source_event = str(edge_item.get("source_event", "")).strip()
        target_event = str(edge_item.get("target_event", "")).strip()
        if not (source_event and target_event):
            continue

        try:
            strength = float(edge_item.get("strength", 0.8))
        except (ValueError, TypeError):
            strength = 0.8

        # 只为高强度因果边创建债务（避免低强度边造成噪音）
        if strength < 0.6:
            continue

        importance = 4 if strength >= 0.9 else (3 if strength >= 0.7 else 2)
        involved_chars = edge_item.get("involved_characters") or []
        if isinstance(involved_chars, str):
            involved_chars = [involved_chars]

        # 预期回收章节：源事件后 10-20 章
        due_offset = 15 if strength >= 0.8 else 10
        due_chapter = chapter_number + due_offset

        debt = NarrativeDebt(
            novel_id=novel_id,
            debt_type=DebtType.CAUSAL_CHAIN,
            description=f"{source_event} → {target_event}",
            planted_chapter=chapter_number,
            due_chapter=due_chapter,
            importance=importance,
            involved_entities=[str(c).strip() for c in involved_chars if str(c).strip()],
            context=f"因果链未闭环，{target_event}尚未发生",
        )

        try:
            debt_repository.save(debt)
            new_debts += 1
        except Exception as e:
            logger.debug("因果债务入库跳过: %s", e)

    # ---- 2. 角色弧债务：从 character_mutations 中的高优先级执念 ----
    mutations_raw = bundle.get("character_mutations") or []
    for mut_item in mutations_raw:
        # V9: 兼容新格式 {"data": m, "status": "pending"}
        if isinstance(mut_item, dict) and "data" in mut_item:
            mut_item = mut_item["data"]
        if not isinstance(mut_item, dict):
            continue
        mutation_type = str(mut_item.get("mutation_type", "")).strip().lower()
        if mutation_type != "motivation":
            continue

        character_name = str(mut_item.get("character_name", "")).strip()
        impact_or_desc = str(mut_item.get("impact_or_description", "")).strip()
        if not impact_or_desc:
            continue

        tags_or_priority = mut_item.get("sensitivity_tags_or_priority", 5)
        try:
            priority = int(tags_or_priority)
        except (ValueError, TypeError):
            priority = 5

        # 只为高优先级执念创建角色弧债务
        if priority < 7:
            continue

        importance = 4 if priority >= 9 else 3
        due_chapter = chapter_number + 20  # 执念通常需要更长时间闭环

        debt = NarrativeDebt(
            novel_id=novel_id,
            debt_type=DebtType.CHARACTER_ARC,
            description=f"{character_name}的执念: {impact_or_desc}",
            planted_chapter=chapter_number,
            due_chapter=due_chapter,
            importance=importance,
            involved_entities=[character_name] if character_name else [],
            context=f"高优先级执念(P{priority})需要最终闭环",
        )

        try:
            debt_repository.save(debt)
            new_debts += 1
        except Exception as e:
            logger.debug("角色弧债务入库跳过: %s", e)

    # ---- 3. 结算已消费的伏笔债务 ----
    consumed = bundle.get("consumed_foreshadows") or []
    if consumed:
        try:
            foreshadow_debts = debt_repository.get_by_type(novel_id, DebtType.FORESHADOWING)
            for consumed_desc in consumed:
                if not consumed_desc:
                    continue
                consumed_lower = consumed_desc.lower().strip()
                for debt in foreshadow_debts:
                    if debt.is_resolved:
                        continue
                    debt_lower = debt.description.lower().strip()
                    # 模糊匹配
                    if consumed_lower in debt_lower or debt_lower in consumed_lower:
                        try:
                            debt_repository.resolve(debt.id, chapter_number)
                            logger.info(
                                "叙事债务结算 novel=%s ch=%s debt=%s",
                                novel_id, chapter_number, debt.description[:40],
                            )
                            break  # 一条消费对应一条债务
                        except Exception as e:
                            logger.debug("叙事债务结算失败: %s", e)
        except Exception as e:
            logger.debug("伏笔债务结算失败: %s", e)

    # ---- 4. 因果边闭环 → 结算对应债务 ----
    if causal_edge_repository:
        try:
            resolved_edges = [
                e for e in causal_edge_repository.get_by_novel(novel_id)
                if e.is_resolved and e.resolved_chapter == chapter_number
            ]
            if resolved_edges:
                causal_debts = debt_repository.get_by_type(novel_id, DebtType.CAUSAL_CHAIN)
                for edge in resolved_edges:
                    for debt in causal_debts:
                        if debt.is_resolved:
                            continue
                        if edge.source_event_summary in debt.description and edge.target_event_summary in debt.description:
                            try:
                                debt_repository.resolve(debt.id, chapter_number)
                                logger.info(
                                    "因果债务自动结算 novel=%s ch=%s debt=%s",
                                    novel_id, chapter_number, debt.description[:40],
                                )
                            except Exception as e:
                                logger.debug("因果债务结算失败: %s", e)
        except Exception as e:
            logger.debug("因果边闭环债务结算失败: %s", e)

    # ---- 5. 逾期标记 ----
    try:
        overdue_count = debt_repository.mark_overdue_batch(novel_id, chapter_number)
        if overdue_count > 0:
            logger.info("叙事债务逾期标记 novel=%s ch=%s overdue=%d", novel_id, chapter_number, overdue_count)
    except Exception as e:
        logger.debug("逾期标记失败: %s", e)

    if new_debts > 0:
        logger.info("叙事债务更新完成 novel=%s ch=%s new_debts=%d", novel_id, chapter_number, new_debts)

    return new_debts


def _auto_generate_plot_point(
    novel_id: str,
    chapter_number: int,
    tension_score: float,
    chapter_repository: Any,
    plot_arc_repository: Any,
) -> None:
    """自动生成剧情点：当张力值显著变化时添加到情节弧。

    优化后的触发阈值（原20分太苛刻，导致 PlotArc 几乎从不积累）：
    - 张力跃升 ≥10 分：标记为上升/转折/高潮
    - 张力骤降 ≥10 分：标记为回落/缓和
    - 绝对阈值：≥65 即标记为高潮（原85几乎不可达）
    """
    try:
        from domain.novel.value_objects.novel_id import NovelId
        from domain.novel.value_objects.plot_point import PlotPoint, PlotPointType
        from domain.novel.value_objects.tension_level import TensionLevel
        from domain.novel.value_objects.tension_dimensions import UNEVALUATED

        # 跳过未评估的章节
        if tension_score == UNEVALUATED:
            return

        # 🔥 性能优化：用轻量 SQL 查询替代 list_by_novel
        # 获取前一章的张力值
        prev_tension = None
        try:
            db = chapter_repository.db if hasattr(chapter_repository, 'db') else None
            if db is not None:
                row = db.fetch_one(
                    "SELECT tension_score FROM chapters WHERE novel_id = ? AND number = ?",
                    (novel_id, chapter_number - 1)
                )
                if row and row['tension_score'] is not None and row['tension_score'] != UNEVALUATED:
                    prev_tension = float(row['tension_score'])
        except Exception:
            pass

        if prev_tension is None:
            return  # 第一章不生成剧情点

        tension_diff = abs(tension_score - prev_tension)

        # 判断是否需要生成剧情点
        should_generate = False
        point_type = PlotPointType.RISING_ACTION
        description = ""

        # 1. 张力显著上升（≥10分，原阈值20）
        if tension_score - prev_tension >= 10:
            should_generate = True
            if tension_score >= 75:
                point_type = PlotPointType.CLIMAX
                description = f"高潮：张力从 {prev_tension:.0f} 跃升至 {tension_score:.0f}"
            elif tension_score >= 55:
                point_type = PlotPointType.TURNING_POINT
                description = f"转折：张力从 {prev_tension:.0f} 上升至 {tension_score:.0f}"
            else:
                point_type = PlotPointType.RISING_ACTION
                description = f"升温：张力从 {prev_tension:.0f} 提升至 {tension_score:.0f}"

        # 2. 张力显著下降（≥10分，原阈值20）
        elif prev_tension - tension_score >= 10:
            should_generate = True
            if prev_tension >= 65 and tension_score < 45:
                point_type = PlotPointType.FALLING_ACTION
                description = f"回落：张力从 {prev_tension:.0f} 降至 {tension_score:.0f}"
            else:
                point_type = PlotPointType.RESOLUTION
                description = f"缓和：张力从 {prev_tension:.0f} 回落至 {tension_score:.0f}"

        # 3. 达到高张力（≥65，原阈值85）
        elif tension_score >= 65 and prev_tension < 65:
            should_generate = True
            point_type = PlotPointType.CLIMAX
            description = f"高峰：张力达到 {tension_score:.0f}"

        # 4. 连续低张力（连续2章<30）——标记为需要调整的平缓段
        elif tension_score <= 30 and prev_tension <= 30:
            should_generate = True
            point_type = PlotPointType.OPENING
            description = f"持续低张：{prev_tension:.0f}→{tension_score:.0f}（需注入冲突）"

        if not should_generate:
            return

        # 使用 TensionLevel.from_score 将 0-100 分映射到 1-10 档
        tension_level = TensionLevel.from_score(tension_score)

        # 获取或创建情节弧
        plot_arc = plot_arc_repository.get_by_novel_id(NovelId(novel_id))
        if not plot_arc:
            from domain.novel.entities.plot_arc import PlotArc
            plot_arc = PlotArc(
                id=str(uuid.uuid4()),
                novel_id=NovelId(novel_id),
                slug="default",
                display_name="主情节弧"
            )

        # 检查该章是否已有剧情点
        existing = any(p.chapter_number == chapter_number for p in plot_arc.key_points)
        if existing:
            return

        # 添加剧情点
        plot_point = PlotPoint(
            chapter_number=chapter_number,
            point_type=point_type,
            description=description,
            tension=tension_level
        )
        plot_arc.add_plot_point(plot_point)
        plot_arc_repository.save(plot_arc)

        logger.info("自动生成剧情点 novel=%s ch=%s type=%s tension=%.0f level=%s",
                   novel_id, chapter_number, point_type.value, tension_score, tension_level.display_name)

    except Exception as e:
        logger.warning("自动生成剧情点失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)


def _auto_advance_milestone(
    novel_id: str,
    chapter_number: int,
    storyline_progress: List[dict],
    storyline_repository: Any,
) -> None:
    """自动推进里程碑：根据进展描述判断是否达成里程碑条件。"""
    try:
        from domain.novel.value_objects.novel_id import NovelId

        storylines = storyline_repository.get_by_novel_id(NovelId(novel_id))

        for progress_item in storyline_progress:
            if not isinstance(progress_item, dict):
                continue

            line_type = str(progress_item.get("type", "")).strip()
            description = str(progress_item.get("description", "")).strip()

            if not description:
                continue

            # 匹配故事线
            matched = None
            for sl in storylines:
                if line_type in sl.name or line_type in sl.storyline_type.value:
                    matched = sl
                    break

            if not matched or not matched.milestones:
                continue

            # 检查当前里程碑是否应该推进
            current_idx = matched.current_milestone_index
            if current_idx >= len(matched.milestones):
                continue  # 已完成所有里程碑

            current_milestone = matched.milestones[current_idx]

            # 判断是否达成里程碑（章节号在目标范围内）
            if (current_milestone.target_chapter_start <= chapter_number <=
                current_milestone.target_chapter_end):

                # 检查关键词匹配（简单实现）
                milestone_keywords = current_milestone.description.lower()
                progress_keywords = description.lower()

                # 如果进展描述包含里程碑关键词，认为达成
                keyword_match = any(
                    word in progress_keywords
                    for word in milestone_keywords.split()[:3]  # 取前3个词
                )

                if keyword_match or chapter_number >= current_milestone.target_chapter_end:
                    matched.current_milestone_index = current_idx + 1
                    storyline_repository.save(matched)
                    logger.info("自动推进里程碑 novel=%s storyline=%s milestone=%d->%d ch=%s",
                               novel_id, matched.name, current_idx, current_idx + 1, chapter_number)

    except Exception as e:
        logger.warning("自动推进里程碑失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)


def _initialize_first_chapter_snapshot(
    novel_id: str,
    chapter_number: int,
) -> None:
    """首章初始化：创建初始快照。"""
    try:
        from infrastructure.persistence.database.connection import get_database

        db = get_database()
        conn = db.get_connection()
        cursor = conn.cursor()

        # 检查是否已有快照
        cursor.execute(
            "SELECT COUNT(*) FROM novel_snapshots WHERE novel_id = ?",
            (novel_id,)
        )
        count = cursor.fetchone()[0]

        if count > 0:
            logger.info("首章已有快照，跳过初始化 novel=%s", novel_id)
            return

        # 创建初始快照
        snapshot_id = f"snapshot-{uuid.uuid4()}"
        now = datetime.utcnow().isoformat()

        cursor.execute("""
            INSERT INTO novel_snapshots (
                id, novel_id, trigger_type, name, description,
                chapter_pointers, bible_state, foreshadow_state, graph_state,
                branch_name, parent_snapshot_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            snapshot_id,
            novel_id,
            "AUTO",
            "第1章完成",
            "小说开篇，自动创建初始快照",
            json.dumps([f"{novel_id}-ch{chapter_number}"]),
            json.dumps({"exists": True, "timestamp": now}),
            json.dumps({}),
            json.dumps({}),
            "main",
            None,
            now
        ))

        conn.commit()
        logger.info("首章自动创建快照 novel=%s snapshot=%s", novel_id, snapshot_id)

    except Exception as e:
        logger.warning("首章快照初始化失败 novel=%s: %s", novel_id, e)


def _initialize_first_chapter_storyline(
    novel_id: str,
    chapter_number: int,
    bundle: dict,
    storyline_repository: Any,
) -> None:
    """首章初始化：基于章末总结创建主线故事线。

    使用 LLM 生成的 summary 作为依据，而不是硬匹配关键词。
    summary 来自 sync_chapter_narrative_after_save 中的 llm_chapter_extract_bundle。
    """
    try:
        from domain.novel.value_objects.novel_id import NovelId
        from domain.novel.value_objects.storyline_type import StorylineType
        from domain.novel.value_objects.storyline_status import StorylineStatus
        from domain.novel.entities.storyline import Storyline

        # 检查是否已有故事线
        existing = storyline_repository.get_by_novel_id(NovelId(novel_id))
        if existing:
            logger.info("首章已有故事线，跳过初始化 novel=%s", novel_id)
            return

        # 使用 LLM 生成的章末总结作为故事线描述
        summary = bundle.get("summary", "")

        # 默认创建主线，名称和描述基于首章内容
        storyline_name = "主线"
        storyline_desc = summary if summary else "小说主线剧情"

        # 创建主线
        main_storyline = Storyline(
            id=str(uuid.uuid4()),
            novel_id=NovelId(novel_id),
            storyline_type=StorylineType.MAIN_PLOT,
            status=StorylineStatus.ACTIVE,
            estimated_chapter_start=chapter_number,
            estimated_chapter_end=chapter_number + 20,  # 预估20章
            name=storyline_name,
            description=storyline_desc,
            progress_summary=summary  # 将首章摘要作为初始进展
        )
        storyline_repository.save(main_storyline)
        logger.info("首章自动初始化主线 novel=%s desc=%s", novel_id, storyline_desc[:50])

    except Exception as e:
        logger.warning("首章故事线初始化失败 novel=%s: %s", novel_id, e)


def _auto_adjust_storyline_range(
    novel_id: str,
    chapter_number: int,
    storyline_progress: List[dict],
    storyline_repository: Any,
) -> None:
    """自动调整故事线范围：检测新故事线开始或现有故事线结束。"""
    try:
        from domain.novel.value_objects.novel_id import NovelId
        from domain.novel.value_objects.storyline_type import StorylineType
        from domain.novel.value_objects.storyline_status import StorylineStatus
        from domain.novel.entities.storyline import Storyline

        storylines = storyline_repository.get_by_novel_id(NovelId(novel_id))

        for progress_item in storyline_progress:
            if not isinstance(progress_item, dict):
                continue

            line_type = str(progress_item.get("type", "")).strip()
            description = str(progress_item.get("description", "")).strip()

            if not description:
                continue

            # 检测关键词判断是否是新故事线开始或结束
            is_start = any(kw in description for kw in ["开始", "启动", "引入", "出现"])
            is_end = any(kw in description for kw in ["结束", "完成", "解决", "落幕"])

            # 匹配现有故事线
            matched = None
            for sl in storylines:
                if line_type in sl.name or line_type in sl.storyline_type.value:
                    matched = sl
                    break

            if matched:
                # 更新现有故事线范围
                if is_end and matched.status != StorylineStatus.COMPLETED:
                    # 故事线结束，更新结束章节
                    if chapter_number > matched.estimated_chapter_end:
                        matched.estimated_chapter_end = chapter_number
                        matched.status = StorylineStatus.COMPLETED
                        storyline_repository.save(matched)
                        logger.info("自动结束故事线 novel=%s storyline=%s end_ch=%d",
                                   novel_id, matched.name, chapter_number)

                elif chapter_number > matched.estimated_chapter_end:
                    # 故事线超出预期范围，自动延长
                    matched.estimated_chapter_end = chapter_number + 5  # 预留5章
                    storyline_repository.save(matched)
                    logger.info("自动延长故事线 novel=%s storyline=%s new_end=%d",
                               novel_id, matched.name, matched.estimated_chapter_end)

            elif is_start:
                # 创建新故事线
                storyline_type_map = {
                    "主线": StorylineType.MAIN_PLOT,
                    "支线": StorylineType.GROWTH,
                    "感情线": StorylineType.ROMANCE,
                    "暗线": StorylineType.GROWTH,
                }

                new_type = StorylineType.GROWTH  # 默认支线
                for key, stype in storyline_type_map.items():
                    if key in line_type:
                        new_type = stype
                        break

                new_storyline = Storyline(
                    id=str(uuid.uuid4()),
                    novel_id=NovelId(novel_id),
                    storyline_type=new_type,
                    status=StorylineStatus.ACTIVE,
                    estimated_chapter_start=chapter_number,
                    estimated_chapter_end=chapter_number + 10,  # 预估10章
                    name=line_type,
                    description=description
                )
                storyline_repository.save(new_storyline)
                logger.info("自动创建故事线 novel=%s type=%s name=%s start_ch=%d",
                           novel_id, new_type.value, line_type, chapter_number)

    except Exception as e:
        logger.warning("自动调整故事线范围失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)


def _write_tension_ephemeral(
    novel_id: str,
    chapter_number: int,
    tension_score: Optional[float],
    tension_dims: Optional[dict],
) -> bool:
    """将章节张力写入 DB（经 `get_database` → 持久化单写者；与 API 进程其它写路径一致）。"""
    import sqlite3

    from application.paths import get_db_path
    from infrastructure.persistence.database.connection import get_database

    try:
        db = get_database(get_db_path())
        if tension_dims:
            composite = tension_dims.get("composite_score", -1)
            if composite == -1:
                logger.warning(
                    "跳过 unevaluated 张力写入 novel=%s ch=%s",
                    novel_id,
                    chapter_number,
                )
            else:
                db.execute(
                    """UPDATE chapters SET
                        tension_score = ?,
                        plot_tension = ?,
                        emotional_tension = ?,
                        pacing_tension = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE novel_id = ? AND number = ?""",
                    (
                        tension_dims["composite_score"],
                        tension_dims["plot_tension"],
                        tension_dims["emotional_tension"],
                        tension_dims["pacing_tension"],
                        novel_id,
                        chapter_number,
                    ),
                )
                logger.debug(
                    "张力维度已落库 novel=%s ch=%s composite=%.1f",
                    novel_id,
                    chapter_number,
                    tension_dims["composite_score"],
                )
        elif tension_score is not None:
            db.execute(
                "UPDATE chapters SET tension_score = ?, updated_at = CURRENT_TIMESTAMP WHERE novel_id = ? AND number = ?",
                (float(tension_score), novel_id, chapter_number),
            )
            logger.debug(
                "张力值已落库 novel=%s ch=%s tension=%.1f",
                novel_id,
                chapter_number,
                tension_score,
            )

        db.commit()
        return True
    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower() or "busy" in str(e).lower():
            logger.warning("_write_tension_ephemeral: DB 被锁，写入失败: %s", e)
            return False
        raise
    except Exception as e:
        logger.warning("_write_tension_ephemeral: 张力值落库失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)
        return False


def persist_bundle_extras(
    novel_id: str,
    chapter_number: int,
    bundle: dict,
    storyline_repository: Any = None,
    chapter_repository: Any = None,
    plot_arc_repository: Any = None,
    narrative_event_repository: Any = None,
) -> None:
    """将 bundle 中的故事线进展、张力值、对话写入表，并自动生成剧情点、推进里程碑、调整故事线范围。

    🔥 核心修复：张力值写入改用独立短连接（_write_tension_ephemeral），
    避免在守护进程（multiprocessing.Process）中持有长连接写锁阻塞 API 进程。
    """
    # 1. 张力值写入 chapters 表
    # 🔥 核心修复：改用独立短连接，避免守护进程长连接写锁阻塞 API
    tension_score = bundle.get("tension_score")
    tension_dims = bundle.get("tension_dimensions")
    if tension_score is not None or tension_dims:
        _write_tension_ephemeral(novel_id, chapter_number, tension_score, tension_dims)

    # 2. 自动生成剧情点（基于张力变化）
    if chapter_repository and plot_arc_repository and tension_score is not None:
        _auto_generate_plot_point(
            novel_id, chapter_number, tension_score,
            chapter_repository, plot_arc_repository
        )

    # 3. 故事线进展更新
    # 🔥 核心修复：改用持久化队列写入，避免守护进程长连接写锁阻塞 API
    storyline_progress = bundle.get("storyline_progress") or []
    if storyline_repository and storyline_progress:
        try:
            from domain.novel.value_objects.novel_id import NovelId
            storylines = storyline_repository.get_by_novel_id(NovelId(novel_id))
            updated_storylines = []
            for progress_item in storyline_progress:
                if not isinstance(progress_item, dict):
                    continue
                line_type = str(progress_item.get("type", "")).strip()
                description = str(progress_item.get("description", "")).strip()
                if not description:
                    continue

                # 匹配故事线类型
                matched = None
                for sl in storylines:
                    if line_type in sl.name or line_type in sl.storyline_type.value:
                        matched = sl
                        break

                if matched:
                    matched.update_progress(chapter_number, description)
                    updated_storylines.append({
                        "id": matched.id,
                        "storyline_type": matched.storyline_type.value,
                        "status": matched.status.value,
                        "name": matched.name,
                        "description": matched.description,
                        "estimated_chapter_start": matched.estimated_chapter_start,
                        "estimated_chapter_end": matched.estimated_chapter_end,
                        "current_milestone_index": matched.current_milestone_index,
                        "last_active_chapter": matched.last_active_chapter,
                        "progress_summary": matched.progress_summary,
                    })
                    logger.debug("故事线进展已更新 novel=%s ch=%s type=%s", novel_id, chapter_number, line_type)

            # 🔥 通过持久化队列写入（主进程执行，无锁竞争）
            if updated_storylines:
                try:
                    from application.engine.services.persistence_queue import get_persistence_queue, PersistenceCommandType
                    get_persistence_queue().push(
                        PersistenceCommandType.UPDATE_STORYLINES.value,
                        {"novel_id": novel_id, "storylines": updated_storylines},
                    )
                    logger.debug("故事线已推送持久化队列 novel=%s count=%d", novel_id, len(updated_storylines))
                except Exception as pq_err:
                    # 持久化队列不可用，降级到直接写入（可能持锁）
                    logger.warning("持久化队列不可用，降级直接写入故事线: %s", pq_err)
                    for matched_data, sl in zip(updated_storylines, storylines):
                        if sl and hasattr(sl, 'progress_summary'):
                            storyline_repository.save(sl)
        except Exception as e:
            logger.warning("故事线进展落库失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)

    # 4. 自动推进里程碑
    if storyline_repository and storyline_progress:
        _auto_advance_milestone(novel_id, chapter_number, storyline_progress, storyline_repository)

    # 5. 自动调整故事线范围（或首章初始化）
    if storyline_repository:
        if chapter_number == 1 and not storyline_progress:
            # 首章且 LLM 未返回故事线进展，强制初始化主线
            _initialize_first_chapter_storyline(novel_id, chapter_number, bundle, storyline_repository)
        elif storyline_progress:
            _auto_adjust_storyline_range(novel_id, chapter_number, storyline_progress, storyline_repository)

    # 6. 首章初始化快照
    if chapter_number == 1:
        _initialize_first_chapter_snapshot(novel_id, chapter_number)

    # 7. 对话提取（写入 narrative_events 表）
    dialogues = bundle.get("dialogues") or []
    if narrative_event_repository and dialogues:
        try:
            for dialogue in dialogues:
                if not isinstance(dialogue, dict):
                    continue
                speaker = str(dialogue.get("speaker", "")).strip()
                content = str(dialogue.get("content", "")).strip()
                context = str(dialogue.get("context", "")).strip()

                if not (speaker and content):
                    continue

                # 构建事件摘要
                event_summary = f"{speaker}: {content[:100]}"
                if len(content) > 100:
                    event_summary += "..."

                # 构建 mutations（对话不涉及实体变更，可为空）
                mutations = []

                # 构建 tags
                tags = [f"对话:{speaker}"]
                if context:
                    tags.append(f"场景:{context}")

                # 写入 narrative_events
                narrative_event_repository.append_event(
                    novel_id=novel_id,
                    chapter_number=chapter_number,
                    event_summary=event_summary,
                    mutations=mutations,
                    tags=tags
                )

            logger.info("对话提取完成 novel=%s ch=%s count=%d", novel_id, chapter_number, len(dialogues))
        except Exception as e:
            logger.warning("对话落库失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)

    # 8. 时间轴事件提取（写入 timeline_notes）
    timeline_events = bundle.get("timeline_events") or []
    if timeline_events:
        try:
            from infrastructure.persistence.database.connection import get_database
            db = get_database()
            conn = db.get_connection()
            cursor = conn.cursor()

            for evt in timeline_events:
                if not isinstance(evt, dict):
                    continue
                time_point = str(evt.get("time_point", "")).strip()
                event = str(evt.get("event", "")).strip()
                description = str(evt.get("description", "")).strip()

                if not event:
                    continue

                # 写入 bible_timeline_notes 表
                note_id = f"tl-{uuid.uuid4()}"
                cursor.execute("""
                    INSERT INTO bible_timeline_notes (id, novel_id, time_point, event, description)
                    VALUES (?, ?, ?, ?, ?)
                """, (note_id, novel_id, time_point or f"第{chapter_number}章", event, description))

            conn.commit()
            logger.info("时间轴事件提取完成 novel=%s ch=%s count=%d", novel_id, chapter_number, len(timeline_events))
        except Exception as e:
            logger.warning("时间轴落库失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)


async def sync_chapter_narrative_after_save(
    novel_id: str,
    chapter_number: int,
    content: str,
    knowledge_service: Any,
    indexing_svc: Any,
    llm_service: LLMService,
    triple_repository: Any = None,
    foreshadowing_repo: Any = None,
    storyline_repository: Any = None,
    chapter_repository: Any = None,
    plot_arc_repository: Any = None,
    narrative_event_repository: Any = None,
    causal_edge_repository: Any = None,
    character_state_repository: Any = None,
    debt_repository: Any = None,
    bible_repository: Any = None,
) -> Dict[str, bool]:
    """异步：一次 LLM 写 summary/事件/埋线 + 可选三元组与伏笔 + 故事线/张力/对话 + 因果边/人物状态/债务 → 节拍来自规划 → upsert knowledge → 向量索引。

    返回各子步骤是否成功落库，供章后管线写入 last_audit_* 审阅快照。
    """
    empty_flags: Dict[str, bool] = {
        "vector_stored": False,
        "foreshadow_stored": False,
        "triples_extracted": False,
        "causal_edges_stored": False,
        "character_mutations_stored": False,
        "debt_updated": False,
    }
    if not content or not str(content).strip():
        logger.debug("跳过叙事同步：正文为空 novel=%s ch=%s", novel_id, chapter_number)
        return empty_flags

    flags: Dict[str, bool] = {
        "vector_stored": False,
        "foreshadow_stored": False,
        "triples_extracted": False,
        "causal_edges_stored": False,
        "character_mutations_stored": False,
        "debt_updated": False,
    }

    existing = None
    existing_beats: List[str] = []
    try:
        k = knowledge_service.get_knowledge(novel_id)
        for ch in getattr(k, "chapters", []) or []:
            if getattr(ch, "chapter_id", None) == chapter_number:
                existing = ch
                break
        if existing and getattr(existing, "beat_sections", None):
            existing_beats = list(existing.beat_sections or [])
    except Exception:
        pass

    # 获取待回收伏笔列表（用于 LLM 消费检测）
    pending_foreshadow_descs: List[str] = []
    if foreshadowing_repo:
        try:
            registry = foreshadowing_repo.get_by_novel_id(NovelId(novel_id))
            if registry:
                # 从 Foreshadowing 对象获取描述
                for f in registry.get_unresolved():
                    if f.description:
                        pending_foreshadow_descs.append(f.description)
                # 从 SubtextLedgerEntry 获取描述
                for e in registry.get_pending_subtext_entries():
                    if e.question:
                        pending_foreshadow_descs.append(e.question)
                if pending_foreshadow_descs:
                    logger.debug(
                        "伏笔消费检测：获取到 %d 个待回收伏笔 novel=%s ch=%s",
                        len(pending_foreshadow_descs), novel_id, chapter_number
                    )
        except Exception as e:
            logger.warning("获取待回收伏笔失败: %s", e)

    try:
        bundle = await llm_chapter_extract_bundle(
            llm_service, content, chapter_number,
            pending_foreshadows=pending_foreshadow_descs if pending_foreshadow_descs else None
        )
        summary = bundle.get("summary") or ""
        key_events = bundle.get("key_events") or ""
        open_threads = bundle.get("open_threads") or ""
    except Exception as e:
        logger.warning("LLM 章末 bundle 失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)
        summary, key_events, open_threads = "", "", ""
        bundle = {"relation_triples": [], "foreshadow_hints": []}

    # --- 独立多维张力评分 ---
    from application.analyst.services.tension_scoring_service import TensionScoringService
    from domain.novel.value_objects.tension_dimensions import TensionDimensions, UNEVALUATED

    tension_dimensions: Optional[TensionDimensions] = None
    try:
        prev_tension = 50.0
        if chapter_repository:
            try:
                # 🔥 性能优化：用轻量 SQL 查询替代 list_by_novel
                # 原来加载所有章节内容（可能几百 KB），现在只查一个值
                db = chapter_repository.db if hasattr(chapter_repository, 'db') else None
                if db is not None:
                    row = db.fetch_one(
                        "SELECT tension_score FROM chapters WHERE novel_id = ? AND number = ?",
                        (novel_id, chapter_number - 1)
                    )
                    if row and row['tension_score'] is not None and row['tension_score'] != -1:
                        prev_tension = float(row['tension_score'])
                else:
                    # 降级：用原方法
                    chapters = chapter_repository.list_by_novel(NovelId(novel_id))
                    prev_ch = next((ch for ch in chapters if ch.number == chapter_number - 1), None)
                    if prev_ch:
                        prev_tension = prev_ch.tension_score
            except Exception:
                pass

        tension_svc = TensionScoringService(llm_service)
        tension_dimensions = await tension_svc.score_chapter(
            chapter_content=content,
            chapter_number=chapter_number,
            prev_chapter_tension=prev_tension,
        )
        logger.info(
            "独立张力评分完成 novel=%s ch=%s composite=%.1f plot=%.0f emotional=%.0f pacing=%.0f",
            novel_id, chapter_number,
            tension_dimensions.composite_score,
            tension_dimensions.plot_tension,
            tension_dimensions.emotional_tension,
            tension_dimensions.pacing_tension,
        )
    except Exception as e:
        logger.warning("独立张力评分失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)

    # 将张力结果注入 bundle，供 persist_bundle_extras 使用
    if tension_dimensions is not None:
        bundle["tension_score"] = tension_dimensions.composite_score
        bundle["tension_dimensions"] = {
            "plot_tension": tension_dimensions.plot_tension,
            "emotional_tension": tension_dimensions.emotional_tension,
            "pacing_tension": tension_dimensions.pacing_tension,
            "composite_score": tension_dimensions.composite_score,
        }
    else:
        bundle["tension_score"] = UNEVALUATED
        bundle["tension_dimensions"] = {
            "plot_tension": UNEVALUATED,
            "emotional_tension": UNEVALUATED,
            "pacing_tension": UNEVALUATED,
            "composite_score": UNEVALUATED,
        }

    consistency_note = ""
    if existing:
        consistency_note = (existing.consistency_note or "") or ""
        if not key_events:
            key_events = existing.key_events or ""
        if not open_threads:
            open_threads = existing.open_threads or ""

    beat_sections = _resolve_beat_sections(novel_id, chapter_number, existing_beats)
    
    # 生成微观节拍
    micro_beats = []
    try:
        # 如果生成时已经创建，直接使用
        if bundle.get("micro_beats"):
            micro_beats = bundle.get("micro_beats")
        else:
            # 否则从大纲动态生成
            # 获取章节大纲（从结构树或 beat_sections 推断）
            outline_text = ""
            try:
                # 尝试从结构树获取大纲
                from application.paths import get_db_path
                from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
                from domain.structure.story_node import NodeType
                
                repo = StoryNodeRepository(str(get_db_path()))
                nodes = repo.get_by_novel_sync(novel_id)
                for n in nodes:
                    if n.node_type == NodeType.CHAPTER and int(n.number) == int(chapter_number):
                        outline_text = (n.outline or "").strip()
                        break
            except Exception as e:
                logger.debug("从结构树获取大纲失败: %s", e)
            
            # 如果有大纲，使用静态方法生成节拍
            if outline_text:
                try:
                    from application.engine.services.context_builder import ContextBuilder
                    # 使用静态启发式生成节拍（无需实例化）
                    beats = ContextBuilder(None, None, None, None, None, None).magnify_outline_to_beats(chapter_number, outline_text)
                    micro_beats = [
                        {
                            "description": beat.description,
                            "target_words": beat.target_words,
                            "focus": beat.focus
                        } for beat in beats
                    ]
                    logger.debug("从大纲生成微观节拍: %d 个", len(micro_beats))
                except Exception as e:
                    logger.debug("生成微观节拍失败: %s", e)
    except Exception as e:
        logger.debug("微观节拍处理失败: %s", e)
    
    knowledge_service.upsert_chapter_summary(
        novel_id=novel_id,
        chapter_id=chapter_number,
        summary=summary,
        key_events=key_events or "（未提取）",
        open_threads=open_threads or "无",
        consistency_note=consistency_note,
        beat_sections=beat_sections,
        micro_beats=micro_beats if micro_beats else None,
        sync_status="synced" if summary else "draft",
    )

    if triple_repository is not None or foreshadowing_repo is not None:
        try:
            persist_bundle_triples_and_foreshadows(
                novel_id,
                chapter_number,
                bundle,
                triple_repository,
                foreshadowing_repo,
            )
            if triple_repository is not None:
                flags["triples_extracted"] = True
            if foreshadowing_repo is not None:
                flags["foreshadow_stored"] = True
        except Exception as e:
            logger.warning(
                "bundle 三元组/伏笔落库失败 novel=%s ch=%s: %s", novel_id, chapter_number, e
            )

    if storyline_repository is not None or chapter_repository is not None or narrative_event_repository is not None:
        try:
            persist_bundle_extras(
                novel_id,
                chapter_number,
                bundle,
                storyline_repository,
                chapter_repository,
                plot_arc_repository,
                narrative_event_repository,
            )
        except Exception as e:
            logger.warning(
                "bundle 故事线/张力/对话落库失败 novel=%s ch=%s: %s", novel_id, chapter_number, e
            )

    # ★ V8 Feed-forward: 因果边提取 + 人物状态突变 + 叙事债务更新
    if causal_edge_repository is not None:
        try:
            saved_edges = persist_causal_edges(
                novel_id, chapter_number, bundle, causal_edge_repository
            )
            if saved_edges > 0:
                flags["causal_edges_stored"] = True
        except Exception as e:
            logger.warning(
                "因果边落库失败 novel=%s ch=%s: %s", novel_id, chapter_number, e
            )

    if character_state_repository is not None:
        try:
            saved_mutations = persist_character_mutations(
                novel_id, chapter_number, bundle, character_state_repository, bible_repository
            )
            if saved_mutations > 0:
                flags["character_mutations_stored"] = True
        except Exception as e:
            logger.warning(
                "人物状态突变落库失败 novel=%s ch=%s: %s", novel_id, chapter_number, e
            )

    if debt_repository is not None:
        try:
            new_debts = update_narrative_debts(
                novel_id, chapter_number, bundle, debt_repository, causal_edge_repository
            )
            if new_debts >= 0:  # 0 也算成功（可能没有新债务）
                flags["debt_updated"] = True
        except Exception as e:
            logger.warning(
                "叙事债务更新失败 novel=%s ch=%s: %s", novel_id, chapter_number, e
            )

    logger.info(
        "分章叙事已落库 novel=%s ch=%s beats=%d(src=planning/knowledge) summary_len=%d",
        novel_id,
        chapter_number,
        len(beat_sections),
        len(summary),
    )

    if indexing_svc is not None:
        text_for_vector = summary.strip() if summary.strip() else "；".join(beat_sections) if beat_sections else content[:800]
        try:
            await indexing_svc.ensure_collection(novel_id)
            await indexing_svc.index_chapter_summary(novel_id, chapter_number, text_for_vector)
            flags["vector_stored"] = True
            logger.debug("章节向量索引完成 novel=%s ch=%s", novel_id, chapter_number)
        except Exception as e:
            logger.warning("章节向量索引失败 novel=%s ch=%s: [%s] %s", novel_id, chapter_number, type(e).__name__, e, exc_info=True)

    # 🔥 将多维张力评分（0-100）传递给调用方，供审计流程替代旧式 _score_tension
    tension_composite = bundle.get("tension_score")
    if tension_composite is not None and tension_composite != UNEVALUATED:
        flags["tension_composite"] = tension_composite

    return flags


def sync_chapter_narrative_after_save_blocking(
    novel_id: str,
    chapter_number: int,
    content: str,
    knowledge_service: Any,
    indexing_svc: Any,
    llm_service: LLMService,
    triple_repository: Any = None,
    foreshadowing_repo: Any = None,
    storyline_repository: Any = None,
    chapter_repository: Any = None,
    causal_edge_repository: Any = None,
    character_state_repository: Any = None,
    debt_repository: Any = None,
    bible_repository: Any = None,
) -> None:
    """供 FastAPI BackgroundTasks 同步入口调用。"""
    _kwargs = dict(
        triple_repository=triple_repository,
        foreshadowing_repo=foreshadowing_repo,
        storyline_repository=storyline_repository,
        chapter_repository=chapter_repository,
        causal_edge_repository=causal_edge_repository,
        character_state_repository=character_state_repository,
        debt_repository=debt_repository,
        bible_repository=bible_repository,
    )
    try:
        asyncio.run(
            sync_chapter_narrative_after_save(
                novel_id,
                chapter_number,
                content,
                knowledge_service,
                indexing_svc,
                llm_service,
                **_kwargs,
            )
        )
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    sync_chapter_narrative_after_save(
                        novel_id,
                        chapter_number,
                        content,
                        knowledge_service,
                        indexing_svc,
                        llm_service,
                        **_kwargs,
                    )
                )
            finally:
                loop.close()
        else:
            raise
    except Exception as e:
        logger.warning("分章叙事同步失败 novel=%s ch=%s: %s", novel_id, chapter_number, e)
