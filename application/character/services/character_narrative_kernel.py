from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import asdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from application.character.dtos.character_narrative import (
    CastSlot,
    CastSlotNotes,
    ChapterCastPlan,
    CharacterContextLocks,
    CharacterNarrativeProfile,
    NewCharacterCandidate,
)
from domain.bible.triple import SourceType, Triple
from domain.character.value_objects.character_id import CharacterId
from domain.novel.value_objects.character_state import CharacterState, EmotionalArcNode
from domain.structure.chapter_element import ElementType

logger = logging.getLogger(__name__)


class CharacterNarrativeKernel:
    """角色叙事内核。

    Backend-first orchestration for cast planning, context locks, new-character
    admission, aftermath reconciliation and character-centric read models.
    """

    MAX_CAST = 7
    _IMPORTANCE_ORDER = {
        "protagonist": 0,
        "major": 1,
        "major_supporting": 1,
        "important_supporting": 2,
        "supporting": 3,
        "minor": 4,
        "background": 5,
    }
    _IMPORTANCE_TO_SLOT = {
        "protagonist": "major",
        "major": "major",
        "major_supporting": "normal",
        "important_supporting": "normal",
        "supporting": "normal",
        "minor": "minor",
        "background": "minor",
    }
    _NON_CHARACTER_WORDS = {
        "本章", "章节", "大纲", "黑市", "拍卖", "拍卖会", "宗门", "学院",
        "城市", "房间", "大厅", "密室", "王城", "皇城", "森林", "山谷",
        "魔法", "修炼", "交易", "战斗", "对决", "发现", "突然", "随后",
        "因此", "因为", "但是", "然而", "一个", "少女", "男人", "女人",
        "老人", "少年", "侍卫", "店主", "路人", "众人",
    }

    def __init__(
        self,
        *,
        bible_service: Any = None,
        bible_repository: Any = None,
        chapter_element_repository: Any = None,
        story_node_repository: Any = None,
        triple_repository: Any = None,
        character_state_repository: Any = None,
        debt_repository: Any = None,
        unified_character_repository: Any = None,
    ) -> None:
        self.bible_service = bible_service
        self.bible_repo = bible_repository
        self.chapter_element_repo = chapter_element_repository
        self.story_node_repo = story_node_repository
        self.triple_repo = triple_repository
        self.character_state_repo = character_state_repository
        self.debt_repo = debt_repository
        self.unified_character_repo = unified_character_repository

    # ------------------------------------------------------------------
    # Cast planning
    # ------------------------------------------------------------------

    def plan_cast(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str = "",
        *,
        scene_director: Optional[Dict[str, Any]] = None,
        max_characters: int = MAX_CAST,
    ) -> ChapterCastPlan:
        bible = self._get_bible(novel_id)
        characters = list(getattr(bible, "characters", []) or []) if bible else []
        chapter_id = self.get_chapter_node_id(novel_id, chapter_number)
        existing_slots = self.get_cast_slots(novel_id, chapter_number)
        existing_ids = {s.character_id for s in existing_slots}

        mentioned_names = self._mentioned_names(characters, outline, scene_director)
        recent = self._recent_activity(novel_id, chapter_number)
        selected: List[CastSlot] = []

        # Existing/manual/kernel cast is authoritative.
        selected.extend(existing_slots)

        candidates = []
        for char in characters:
            char_id = self._char_id(char)
            if not char_id or char_id in existing_ids:
                continue
            in_outline = getattr(char, "name", "") in mentioned_names
            imp_raw = self._character_importance(char)
            activity = recent.get(char_id, {}).get("count", 0)
            candidates.append((
                (not in_outline, self._IMPORTANCE_ORDER.get(imp_raw, 4), -activity, getattr(char, "name", "")),
                char,
                in_outline,
            ))
        candidates.sort(key=lambda x: x[0])

        for _, char, in_outline in candidates:
            if len(selected) >= max_characters:
                break
            selected.append(self._slot_from_character(char, in_outline=in_outline))

        new_candidates = self.detect_new_character_candidates(
            novel_id,
            chapter_number,
            outline,
            characters,
            scene_director=scene_director,
        )

        plan = ChapterCastPlan(
            novel_id=novel_id,
            chapter_number=chapter_number,
            slots=selected[:max_characters],
            new_character_candidates=new_candidates,
        )
        plan.generated_context = self.build_context_locks(
            novel_id, chapter_number, plan=plan
        ).combined()
        plan.scheduling_log = [
            f"known_characters={len(characters)}",
            f"existing_slots={len(existing_slots)}",
            f"selected={len(plan.slots)}",
            f"new_candidates={len(new_candidates)}",
            f"chapter_node_id={chapter_id or 'missing'}",
        ]
        return plan

    def apply_cast_plan(
        self,
        plan: ChapterCastPlan,
        *,
        create_new_characters: bool = True,
    ) -> ChapterCastPlan:
        chapter_id = self.get_chapter_node_id(plan.novel_id, plan.chapter_number)
        if not chapter_id:
            logger.warning(
                "cast plan apply skipped: missing chapter node novel=%s ch=%s",
                plan.novel_id,
                plan.chapter_number,
            )
            return plan

        if create_new_characters:
            self._apply_new_character_candidates(plan, chapter_id)

        if self.chapter_element_repo:
            for order, slot in enumerate(plan.slots, start=1):
                slot.appearance_order = slot.appearance_order or order
                self.chapter_element_repo.upsert_cast_slot_sync(
                    chapter_id=chapter_id,
                    character_id=slot.character_id,
                    relation_type=slot.relation_type,
                    importance=slot.importance,
                    appearance_order=slot.appearance_order,
                    notes=json.dumps(slot.notes.to_dict(), ensure_ascii=False),
                )
        return plan

    def get_cast_slots(self, novel_id: str, chapter_number: int) -> List[CastSlot]:
        chapter_id = self.get_chapter_node_id(novel_id, chapter_number)
        if not chapter_id or not self.chapter_element_repo:
            return []
        rows = self.chapter_element_repo.get_planned_cast_sync(chapter_id)
        bible = self._get_bible(novel_id)
        by_id = {self._char_id(c): c for c in (getattr(bible, "characters", []) or [])}
        slots: List[CastSlot] = []
        for row in rows:
            char_id = str(row.get("element_id") or "")
            char = by_id.get(char_id)
            name = getattr(char, "name", "") or char_id
            slots.append(
                CastSlot(
                    character_id=char_id,
                    name=name,
                    importance=self._normalize_slot_importance(row.get("importance")),
                    relation_type=str(row.get("relation_type") or "appears"),
                    appearance_order=row.get("appearance_order"),
                    notes=self._parse_slot_notes(row.get("notes")),
                    is_new_suggestion=False,
                )
            )
        return slots

    # ------------------------------------------------------------------
    # Context projection
    # ------------------------------------------------------------------

    def build_context_locks(
        self,
        novel_id: str,
        chapter_number: int,
        *,
        plan: Optional[ChapterCastPlan] = None,
    ) -> CharacterContextLocks:
        plan = plan or ChapterCastPlan(
            novel_id=novel_id,
            chapter_number=chapter_number,
            slots=self.get_cast_slots(novel_id, chapter_number),
        )
        if not plan.slots:
            plan = self.plan_cast(novel_id, chapter_number)

        bible = self._get_bible(novel_id)
        by_id = {self._char_id(c): c for c in (getattr(bible, "characters", []) or [])}
        t0: List[str] = []
        t1: List[str] = []
        t2: List[str] = []

        for slot in plan.slots:
            char = by_id.get(slot.character_id)
            if not char:
                continue
            if slot.importance == "major":
                t0.append(self._format_t0_lock(char, slot, chapter_number))
            elif slot.importance == "normal":
                t1.append(self._format_t1_context(char, slot))
            else:
                t2.append(self._format_t2_permission(char, slot))

        return CharacterContextLocks(
            t0="\n".join(x for x in t0 if x),
            t1="\n".join(x for x in t1 if x),
            t2="\n".join(x for x in t2 if x),
        )

    # ------------------------------------------------------------------
    # Aftermath
    # ------------------------------------------------------------------

    def reconcile_after_chapter(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
        bundle: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Lightweight automatic reconciliation.

        The heavy extraction already happens in chapter_narrative_sync. This method
        adds cast-contract checks and projection sync without blocking save.
        """
        bundle = bundle or {}
        plan = ChapterCastPlan(
            novel_id=novel_id,
            chapter_number=chapter_number,
            slots=self.get_cast_slots(novel_id, chapter_number),
        )
        bible = self._get_bible(novel_id)
        characters = list(getattr(bible, "characters", []) or []) if bible else []
        by_id = {self._char_id(c): c for c in characters}
        planned_ids = {s.character_id for s in plan.slots}
        risks: List[Dict[str, Any]] = []
        mentioned_unplanned = []

        for char in characters:
            name = getattr(char, "name", "")
            cid = self._char_id(char)
            if name and cid and cid not in planned_ids and name in (content or ""):
                mentioned_unplanned.append({"character_id": cid, "name": name})

        for slot in plan.slots:
            char = by_id.get(slot.character_id)
            if not char:
                continue
            if slot.importance == "major":
                risks.extend(self._detect_major_character_risks(char, slot, chapter_number, content))

        self._sync_character_state_projection(novel_id, chapter_number)
        return {
            "checked": True,
            "planned_cast_count": len(plan.slots),
            "mentioned_unplanned": mentioned_unplanned,
            "consistency_risks": risks,
            "needs_review": any(r.get("severity") == "high" for r in risks),
        }

    # ------------------------------------------------------------------
    # Read model
    # ------------------------------------------------------------------

    def get_character_narrative_profile(
        self,
        novel_id: str,
        character_id: str,
    ) -> CharacterNarrativeProfile:
        bible = self._get_bible(novel_id)
        characters = list(getattr(bible, "characters", []) or []) if bible else []
        char = next((c for c in characters if self._char_id(c) == character_id), None)
        name = getattr(char, "name", "") or character_id

        state = self.character_state_repo.get(character_id, novel_id) if self.character_state_repo else None
        triples = self._triples_for_character(novel_id, character_id, name)
        cast_history = self._cast_history(character_id)
        risks = self._profile_risks(char, state, triples)

        return CharacterNarrativeProfile(
            character_id=character_id,
            name=name,
            base_profile=self._base_profile(char),
            current_state=state.to_dict() if state else {},
            cast_history=cast_history,
            relationship_edges=[
                self._triple_summary(t) for t in triples
                if getattr(t, "subject_type", "") == "character" and getattr(t, "object_type", "") == "character"
            ],
            knowledge_facts=[self._triple_summary(t) for t in triples],
            hidden_facts=[
                self._triple_summary(t) for t in triples
                if "hidden" in (getattr(t, "tags", []) or []) or "隐藏" in (getattr(t, "description", "") or "")
            ],
            open_debts=self._open_debts(novel_id, character_id, name),
            foreshadow_links=[
                self._triple_summary(t) for t in triples
                if "伏笔" in (getattr(t, "predicate", "") or "") or "foreshadow" in (getattr(t, "tags", []) or [])
            ],
            causal_links=[
                self._triple_summary(t) for t in triples
                if getattr(t, "predicate", "") in ("导致", "触发", "驱动", "阻止", "解决")
            ],
            recent_dialogue_samples=self._recent_dialogue_samples(novel_id, name),
            consistency_risks=risks,
        )

    # ------------------------------------------------------------------
    # New character admission
    # ------------------------------------------------------------------

    def detect_new_character_candidates(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
        characters: Sequence[Any],
        *,
        scene_director: Optional[Dict[str, Any]] = None,
    ) -> List[NewCharacterCandidate]:
        known_names = {getattr(c, "name", "") for c in characters if getattr(c, "name", "")}
        location_names = self._bible_location_names(novel_id)
        explicit = []
        if scene_director and isinstance(scene_director.get("characters"), list):
            explicit = [str(x).strip() for x in scene_director["characters"] if str(x).strip()]
        candidates = set(explicit)
        if outline:
            candidates.update(re.findall(r"[一-龥]{2,4}", outline))

        out: List[NewCharacterCandidate] = []
        for name in sorted(candidates):
            if name in known_names:
                continue
            if name in location_names or name in self._NON_CHARACTER_WORDS:
                out.append(NewCharacterCandidate(
                    name=name,
                    evidence=name,
                    narrative_function="non_character_entity",
                    recommendation="ignore",
                    confidence=0.7,
                    reason="已匹配为地点/组织/普通叙述词，不创建角色",
                ))
                continue
            if name in explicit:
                recommendation = "create_bible_character"
                function = "explicit_scene_cast"
                confidence = 0.82
                reason = "场记明确列为出镜角色，自动创建最小角色档案"
            elif self._looks_like_ephemeral(name, outline):
                recommendation = "ephemeral"
                function = "walk_on"
                confidence = 0.62
                reason = "更像本章一次性功能人物，只写入本章出场合同"
            else:
                recommendation = "ignore"
                function = "weak_name_candidate"
                confidence = 0.45
                reason = "仅由弱启发式识别，证据不足"
            out.append(NewCharacterCandidate(
                name=name,
                evidence=name,
                narrative_function=function,
                recommendation=recommendation,
                confidence=confidence,
                reason=reason,
            ))
        return out[:10]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def get_chapter_node_id(self, novel_id: str, chapter_number: int) -> Optional[str]:
        if not self.story_node_repo:
            return None
        try:
            for node in self.story_node_repo.get_by_novel_sync(novel_id):
                nt = node.node_type.value if hasattr(node.node_type, "value") else str(node.node_type)
                if nt == "chapter" and int(node.number) == int(chapter_number):
                    return node.id
        except Exception as e:
            logger.debug("chapter node lookup failed novel=%s ch=%s: %s", novel_id, chapter_number, e)
        return None

    def _get_bible(self, novel_id: str) -> Any:
        if self.bible_repo:
            try:
                from domain.novel.value_objects.novel_id import NovelId
                return self.bible_repo.get_by_novel_id(NovelId(novel_id))
            except Exception:
                return None
        if self.bible_service:
            try:
                dto = self.bible_service.get_bible_by_novel(novel_id)
                return dto
            except Exception:
                return None
        return None

    def _char_id(self, char: Any) -> str:
        cid = getattr(char, "character_id", None)
        if cid is not None:
            return getattr(cid, "value", str(cid))
        return str(getattr(char, "id", "") or "")

    def _character_importance(self, char: Any) -> str:
        raw = getattr(char, "importance", None) or getattr(char, "role", None) or ""
        raw = getattr(raw, "value", raw)
        raw = str(raw or "").lower()
        if raw:
            return raw
        desc = (getattr(char, "description", "") or "").lower()
        if "主角" in desc or "主人公" in desc:
            return "protagonist"
        if "主要配角" in desc:
            return "major_supporting"
        if "配角" in desc:
            return "supporting"
        return "supporting"

    def _slot_from_character(self, char: Any, *, in_outline: bool) -> CastSlot:
        imp = self._IMPORTANCE_TO_SLOT.get(self._character_importance(char), "normal")
        if in_outline and imp == "minor":
            imp = "normal"
        notes = CastSlotNotes(
            source="kernel",
            scene_function="conflict" if in_outline else "support",
            dramatic_pressure="由本章大纲点名出场" if in_outline else "",
            allowed_change="允许轻微状态推进，不允许无因性格反转",
            forbidden_drift=self._forbidden_drift(char),
        )
        return CastSlot(
            character_id=self._char_id(char),
            name=getattr(char, "name", ""),
            importance=imp,  # type: ignore[arg-type]
            notes=notes,
            is_new_suggestion=True,
        )

    def _mentioned_names(self, characters: Sequence[Any], outline: str, scene_director: Optional[Dict[str, Any]]) -> set:
        names = set()
        blob = outline or ""
        for char in characters:
            nm = getattr(char, "name", "")
            if nm and nm in blob:
                names.add(nm)
        if scene_director and isinstance(scene_director.get("characters"), list):
            names.update(str(x).strip() for x in scene_director["characters"] if str(x).strip())
        return names

    def _recent_activity(self, novel_id: str, chapter_number: int) -> Dict[str, Dict[str, int]]:
        if not self.chapter_element_repo:
            return {}
        try:
            rows = self.chapter_element_repo.get_recent_char_activity_sync(novel_id, chapter_number, window=5)
            return {r["element_id"]: {"count": int(r["count"]), "last_chapter": int(r["last_chapter"])} for r in rows}
        except Exception:
            return {}

    def _normalize_slot_importance(self, raw: Any) -> str:
        raw = str(raw or "normal").lower()
        return raw if raw in ("major", "normal", "minor") else "normal"

    def _parse_slot_notes(self, raw: Any) -> CastSlotNotes:
        if isinstance(raw, str) and raw.strip():
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    return CastSlotNotes(
                        source=str(data.get("source") or "kernel"),
                        scene_function=str(data.get("scene_function") or "support"),
                        dramatic_pressure=str(data.get("dramatic_pressure") or ""),
                        knowledge_boundary=list(data.get("knowledge_boundary") or []),
                        allowed_change=str(data.get("allowed_change") or ""),
                        forbidden_drift=list(data.get("forbidden_drift") or []),
                        new_character_policy=data.get("new_character_policy") or "none",
                        needs_review=bool(data.get("needs_review", False)),
                        risk_flags=list(data.get("risk_flags") or []),
                    )
            except Exception:
                pass
        return CastSlotNotes()

    def _format_t0_lock(self, char: Any, slot: CastSlot, chapter_number: int) -> str:
        parts = [f"- {getattr(char, 'name', slot.name)}"]
        if getattr(char, "public_profile", ""):
            parts.append(f"公开面:{getattr(char, 'public_profile')}")
        elif getattr(char, "description", ""):
            parts.append(f"公开面:{getattr(char, 'description')[:160]}")
        hidden = getattr(char, "hidden_profile", "") or ""
        reveal = getattr(char, "reveal_chapter", None)
        if hidden:
            if reveal is None or chapter_number >= int(reveal):
                parts.append(f"隐藏面:{hidden[:160]}")
            else:
                parts.append(f"知识边界: 第{reveal}章前不得泄露隐藏身份")
        if getattr(char, "core_belief", ""):
            parts.append(f"核心信念:{getattr(char, 'core_belief')[:220]}")
        for tab in (getattr(char, "moral_taboos", None) or [])[:4]:
            parts.append(f"禁忌:{str(tab)[:120]}")
        for wound in (getattr(char, "active_wounds", None) or [])[:3]:
            if isinstance(wound, dict):
                trig = (wound.get("trigger") or "")[:80]
                eff = (wound.get("effect") or "")[:80]
                if trig or eff:
                    parts.append(f"创伤触发:{trig}->{eff}")
        vp = getattr(char, "voice_profile", None) or {}
        if isinstance(vp, dict) and vp:
            bits = [str(vp[k]) for k in ("style", "sentence_pattern", "speech_tempo") if vp.get(k)]
            if bits:
                parts.append("声线:" + " / ".join(bits[:3]))
        if getattr(char, "mental_state", ""):
            reason = getattr(char, "mental_state_reason", "") or ""
            parts.append(f"当前状态:{getattr(char, 'mental_state')}{f'({reason})' if reason else ''}")
        if slot.notes.knowledge_boundary:
            parts.append("知识边界:" + "；".join(slot.notes.knowledge_boundary[:3]))
        if slot.notes.forbidden_drift:
            parts.append("禁止漂移:" + "；".join(slot.notes.forbidden_drift[:4]))
        return " | ".join(parts)

    def _format_t1_context(self, char: Any, slot: CastSlot) -> str:
        bits = [f"- {getattr(char, 'name', slot.name)}"]
        if getattr(char, "mental_state", ""):
            bits.append(f"状态:{getattr(char, 'mental_state')}")
        if slot.notes.scene_function:
            bits.append(f"场景功能:{slot.notes.scene_function}")
        if slot.notes.dramatic_pressure:
            bits.append(f"压力:{slot.notes.dramatic_pressure}")
        return " | ".join(bits)

    def _format_t2_permission(self, char: Any, slot: CastSlot) -> str:
        return f"- {getattr(char, 'name', slot.name)}：允许过场/提及，禁止抢走主线焦点"

    def _forbidden_drift(self, char: Any) -> List[str]:
        out = []
        cb = getattr(char, "core_belief", "") or ""
        if cb:
            out.append(f"不得无因违背核心信念：{cb[:80]}")
        for tab in (getattr(char, "moral_taboos", None) or [])[:2]:
            out.append(f"不得无因越过禁忌：{str(tab)[:80]}")
        return out

    def _bible_location_names(self, novel_id: str) -> set:
        bible = self._get_bible(novel_id)
        return {getattr(l, "name", "") for l in (getattr(bible, "locations", []) or []) if getattr(l, "name", "")}

    def _looks_like_ephemeral(self, name: str, outline: str) -> bool:
        nearby_words = ("侍卫", "掌柜", "店主", "弟子", "路人", "守卫", "仆人", "使者", "小二")
        return any(w in outline for w in nearby_words) or name.endswith(("甲", "乙"))

    def _apply_new_character_candidates(self, plan: ChapterCastPlan, chapter_id: str) -> None:
        for cand in plan.new_character_candidates:
            if cand.recommendation == "ephemeral":
                ephemeral_id = f"ephemeral-{plan.chapter_number}-{uuid.uuid5(uuid.NAMESPACE_URL, cand.name).hex[:8]}"
                slot = CastSlot(
                    character_id=ephemeral_id,
                    name=cand.name,
                    importance="minor",
                    notes=CastSlotNotes(
                        source="kernel",
                        scene_function=cand.narrative_function,
                        new_character_policy="ephemeral",
                    ),
                )
                plan.slots.append(slot)
            elif cand.recommendation == "create_bible_character":
                char_id = f"char-{uuid.uuid5(uuid.NAMESPACE_URL, plan.novel_id + cand.name).hex[:12]}"
                if self.bible_service:
                    try:
                        self.bible_service.add_character(
                            plan.novel_id,
                            char_id,
                            cand.name,
                            f"自动准入角色：{cand.reason}",
                            [],
                        )
                    except Exception as e:
                        logger.debug("auto create bible character skipped: %s", e)
                self._init_character_state(plan.novel_id, char_id, plan.chapter_number, cand)
                self._persist_character_triples(plan.novel_id, char_id, cand.name, plan.chapter_number, cand)
                plan.slots.append(CastSlot(
                    character_id=char_id,
                    name=cand.name,
                    importance="normal",
                    notes=CastSlotNotes(
                        source="kernel",
                        scene_function=cand.narrative_function,
                        new_character_policy="create_bible_character",
                        allowed_change="首次登场，只建立最小性格轮廓",
                    ),
                ))

    def _init_character_state(self, novel_id: str, character_id: str, chapter_number: int, cand: NewCharacterCandidate) -> None:
        if not self.character_state_repo:
            return
        try:
            existing = self.character_state_repo.get(character_id, novel_id)
            if existing:
                return
            state = CharacterState(
                character_id=character_id,
                novel_id=novel_id,
                current_state_summary=f"第{chapter_number}章首次登场：{cand.narrative_function}",
                last_updated_chapter=chapter_number,
            )
            state.add_emotional_arc_node(EmotionalArcNode(
                chapter=chapter_number,
                emotion="初登场",
                trigger=cand.reason,
                intensity=3,
            ))
            self.character_state_repo.save(state)
        except Exception as e:
            logger.debug("init character state skipped: %s", e)

    def _persist_character_triples(
        self,
        novel_id: str,
        character_id: str,
        name: str,
        chapter_number: int,
        cand: NewCharacterCandidate,
    ) -> None:
        if not self.triple_repo:
            return
        triples = [
            Triple(
                id=str(uuid.uuid4()),
                novel_id=novel_id,
                subject_type="character",
                subject_id=character_id,
                predicate="是",
                object_type="concept",
                object_id="人物",
                confidence=0.55,
                source_type=SourceType.AUTO_INFERRED,
                source_chapter_id=str(chapter_number),
                first_appearance=str(chapter_number),
                description=f"{name}：{cand.reason}",
                tags=["character_kernel", "auto_inferred"],
                attributes={"subject_label": name, "object_label": "人物", "status": "auto_inferred"},
            ),
            Triple(
                id=str(uuid.uuid4()),
                novel_id=novel_id,
                subject_type="character",
                subject_id=character_id,
                predicate="首次出场",
                object_type="chapter",
                object_id=str(chapter_number),
                confidence=0.65,
                source_type=SourceType.AUTO_INFERRED,
                source_chapter_id=str(chapter_number),
                first_appearance=str(chapter_number),
                description=f"{name}首次出场于第{chapter_number}章",
                tags=["character_kernel", "auto_inferred"],
                attributes={"subject_label": name, "object_label": f"第{chapter_number}章", "status": "auto_inferred"},
            ),
        ]
        for t in triples:
            try:
                self.triple_repo.persist_triple_sync(novel_id, t)
            except Exception as e:
                logger.debug("persist character triple skipped: %s", e)

    def _detect_major_character_risks(self, char: Any, slot: CastSlot, chapter_number: int, content: str) -> List[Dict[str, Any]]:
        risks: List[Dict[str, Any]] = []
        hidden = getattr(char, "hidden_profile", "") or ""
        reveal = getattr(char, "reveal_chapter", None)
        if hidden and reveal and chapter_number < int(reveal):
            markers = [hidden[:12], "卧底", "真实身份", "隐藏身份"]
            if any(m and m in content for m in markers):
                risks.append({
                    "character_id": self._char_id(char),
                    "name": getattr(char, "name", ""),
                    "type": "hidden_profile_leak",
                    "severity": "high",
                    "message": f"隐藏身份可能在第{reveal}章前泄露",
                })
        for tab in (getattr(char, "moral_taboos", None) or [])[:4]:
            tab_text = str(tab).strip()
            if tab_text and tab_text in content:
                risks.append({
                    "character_id": self._char_id(char),
                    "name": getattr(char, "name", ""),
                    "type": "taboo_collision",
                    "severity": "medium",
                    "message": f"正文触及角色禁忌：{tab_text[:80]}",
                })
        return risks

    def _sync_character_state_projection(self, novel_id: str, chapter_number: int) -> None:
        if not (self.character_state_repo and self.unified_character_repo):
            return
        try:
            for state in self.character_state_repo.get_by_novel(novel_id):
                char = self.unified_character_repo.get(CharacterId(state.character_id))
                if not char:
                    continue
                latest = state.emotional_arc[-1] if state.emotional_arc else None
                char.update_state(
                    chapter=max(chapter_number, state.last_updated_chapter or 0),
                    mental_state=latest.emotion if latest else None,
                    summary=state.current_state_summary or None,
                )
                self.unified_character_repo.save(char)
        except Exception as e:
            logger.debug("sync unified character projection skipped: %s", e)

    def _base_profile(self, char: Any) -> Dict[str, Any]:
        if not char:
            return {}
        return {
            "description": getattr(char, "description", "") or "",
            "public_profile": getattr(char, "public_profile", "") or "",
            "hidden_profile": getattr(char, "hidden_profile", "") or "",
            "reveal_chapter": getattr(char, "reveal_chapter", None),
            "core_belief": getattr(char, "core_belief", "") or "",
            "moral_taboos": list(getattr(char, "moral_taboos", None) or []),
            "voice_profile": dict(getattr(char, "voice_profile", None) or {}),
            "active_wounds": list(getattr(char, "active_wounds", None) or []),
            "mental_state": getattr(char, "mental_state", "NORMAL") or "NORMAL",
            "mental_state_reason": getattr(char, "mental_state_reason", "") or "",
            "verbal_tic": getattr(char, "verbal_tic", "") or "",
            "idle_behavior": getattr(char, "idle_behavior", "") or "",
        }

    def _triples_for_character(self, novel_id: str, character_id: str, name: str) -> List[Any]:
        if not self.triple_repo:
            return []
        try:
            return self.triple_repo.get_by_entity_ids_sync(novel_id, [character_id, name])
        except Exception:
            return []

    def _triple_summary(self, t: Any) -> Dict[str, Any]:
        return {
            "id": getattr(t, "id", ""),
            "subject": getattr(t, "subject_id", ""),
            "predicate": getattr(t, "predicate", ""),
            "object": getattr(t, "object_id", ""),
            "description": getattr(t, "description", "") or "",
            "confidence": getattr(t, "confidence", None),
            "source_type": getattr(getattr(t, "source_type", ""), "value", getattr(t, "source_type", "")),
            "tags": list(getattr(t, "tags", []) or []),
            "related_chapters": list(getattr(t, "related_chapters", []) or []),
        }

    def _cast_history(self, character_id: str) -> List[Dict[str, Any]]:
        if not self.chapter_element_repo:
            return []
        try:
            db = self.chapter_element_repo._db()
            raw = db.fetch_all(
                """
                SELECT sn.number, sn.title, ce.importance, ce.relation_type, ce.notes
                FROM chapter_elements ce
                LEFT JOIN story_nodes sn ON sn.id = ce.chapter_id
                WHERE ce.element_type = 'character' AND ce.element_id = ?
                ORDER BY sn.number
                """,
                (character_id,),
            )
            return [dict(r) for r in raw]
        except Exception:
            return []

    def _open_debts(self, novel_id: str, character_id: str, name: str) -> List[Dict[str, Any]]:
        if not self.debt_repo:
            return []
        try:
            debts = self.debt_repo.get_unresolved_by_novel_id(novel_id)
        except Exception:
            try:
                debts = self.debt_repo.get_by_novel_id(novel_id)
            except Exception:
                return []
        out = []
        for d in debts or []:
            blob = " ".join(str(getattr(d, k, "") or "") for k in ("description", "title", "context"))
            if character_id in blob or name in blob:
                out.append({k: getattr(d, k, None) for k in ("id", "debt_type", "description", "due_chapter", "importance")})
        return out[:12]

    def _recent_dialogue_samples(self, novel_id: str, name: str) -> List[Dict[str, Any]]:
        try:
            from infrastructure.persistence.database.connection import get_database
            db = get_database()
            rows = db.fetch_all(
                """
                SELECT chapter_number, event_summary
                FROM narrative_events
                WHERE novel_id = ? AND event_summary LIKE ?
                ORDER BY chapter_number DESC
                LIMIT 5
                """,
                (novel_id, f"{name}:%"),
            )
            return [dict(r) for r in rows]
        except Exception:
            return []

    def _profile_risks(self, char: Any, state: Any, triples: Sequence[Any]) -> List[Dict[str, Any]]:
        risks = []
        if char and getattr(char, "hidden_profile", "") and not getattr(char, "reveal_chapter", None):
            risks.append({"type": "hidden_profile_without_reveal", "severity": "medium", "message": "角色有隐藏面但没有揭示章节"})
        if char and not getattr(char, "core_belief", ""):
            risks.append({"type": "missing_core_belief", "severity": "low", "message": "缺少核心信念锚点"})
        if char and not getattr(char, "voice_profile", None) and not getattr(char, "verbal_tic", ""):
            risks.append({"type": "missing_voice", "severity": "low", "message": "缺少声线锚点"})
        return risks
