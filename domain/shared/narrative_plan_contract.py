"""Plan-first narrative consistency contract.

Micro beats describe writing intent, not truth. This module normalizes both
new structured beats and older ref fields into one contract shape so preflight,
auto-validation, and context assembly can share the same policy.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Optional


ENTITY_REF_RE = re.compile(
    r"(?:\[\[)?(?P<kind>char|loc|location|faction|prop|system|skill|clue|evidence|foreshadow):(?P<eid>[^\]|\s]+)(?:\|(?P<label>[^\]]+))?(?:\]\])?",
    re.UNICODE,
)

KIND_ALIASES = {
    "character": "char",
    "人物": "char",
    "location": "loc",
    "地点": "loc",
    "item": "prop",
    "道具": "prop",
    "系统": "system",
    "规则": "system",
    "机制": "system",
    "organization": "faction",
    "组织": "faction",
    "势力": "faction",
}


@dataclass(frozen=True)
class ContractEntity:
    kind: str
    id: str
    label: str
    role: str = ""
    beat_index: int = 0
    bound: bool = False
    source: str = "plan"

    @property
    def ref(self) -> str:
        return f"{self.kind}:{self.id}" if self.id else f"{self.kind}:{self.label}"


@dataclass(frozen=True)
class StateRequirement:
    entity: ContractEntity
    key: str
    must_be: str
    beat_index: int = 0


@dataclass(frozen=True)
class StateChange:
    entity: ContractEntity
    key: str
    from_value: str = ""
    to_value: str = ""
    event_type: str = ""
    beat_index: int = 0
    evidence: str = ""


@dataclass(frozen=True)
class FactIntent:
    subject: ContractEntity
    predicate: str
    object: ContractEntity
    beat_index: int = 0


@dataclass
class NarrativePlanContract:
    novel_id: str
    chapter_number: int
    active_entities: list[ContractEntity] = field(default_factory=list)
    state_requirements: list[StateRequirement] = field(default_factory=list)
    state_changes: list[StateChange] = field(default_factory=list)
    fact_intents: list[FactIntent] = field(default_factory=list)
    forbidden_overrides: list[str] = field(default_factory=list)
    acceptance_evidence: list[str] = field(default_factory=list)
    text_promises: list[dict[str, Any]] = field(default_factory=list)
    source: str = "none"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["active_entity_count"] = len(self.active_entities)
        data["bound_entity_count"] = sum(1 for e in self.active_entities if e.bound)
        data["unbound_entity_count"] = sum(1 for e in self.active_entities if not e.bound)
        return data


def normalize_kind(raw: Any) -> str:
    value = str(raw or "").strip().lower()
    return KIND_ALIASES.get(value, value)


def _as_list(raw: Any) -> list[Any]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, tuple):
        return list(raw)
    return [raw]


def parse_entity_ref(
    raw: Any,
    *,
    default_kind: str = "knowledge",
    role: str = "",
    beat_index: int = 0,
    source: str = "plan",
) -> Optional[ContractEntity]:
    if isinstance(raw, dict):
        entity_raw = raw.get("entity") or raw.get("ref")
        if entity_raw:
            base = parse_entity_ref(
                entity_raw,
                default_kind=raw.get("kind") or default_kind,
                role=str(raw.get("role") or role or ""),
                beat_index=beat_index,
                source=source,
            )
            if base:
                return base
        kind = normalize_kind(raw.get("kind") or raw.get("entity_kind") or default_kind)
        eid = str(raw.get("id") or raw.get("entity_id") or "").strip()
        label = str(raw.get("label") or raw.get("name") or raw.get("entity_label") or eid).strip()
        if not (eid or label):
            return None
        return ContractEntity(
            kind=kind,
            id=eid or label,
            label=label or eid,
            role=str(raw.get("role") or role or ""),
            beat_index=beat_index,
            bound=bool(eid),
            source=source,
        )

    text = str(raw or "").strip()
    if not text:
        return None
    match = ENTITY_REF_RE.search(text)
    if match:
        kind = normalize_kind(match.group("kind"))
        eid = match.group("eid").strip()
        label = (match.group("label") or "").strip() or eid
        return ContractEntity(kind, eid, label, role, beat_index, True, source)
    if ":" in text:
        kind_raw, eid_raw = text.split(":", 1)
        kind = normalize_kind(kind_raw)
        eid = eid_raw.split("|", 1)[0].strip()
        label = eid_raw.split("|", 1)[1].strip() if "|" in eid_raw else eid
        if kind and eid:
            return ContractEntity(kind, eid, label or eid, role, beat_index, True, source)
    return ContractEntity(normalize_kind(default_kind), text, text, role, beat_index, False, source)


def _unique_entities(items: Iterable[ContractEntity]) -> list[ContractEntity]:
    out: list[ContractEntity] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in items:
        key = (item.kind, item.id, item.label, item.role)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def normalize_micro_beats(
    novel_id: str,
    chapter_number: int,
    micro_beats: Iterable[dict[str, Any]] | None,
    *,
    source: str = "micro_beats",
) -> NarrativePlanContract:
    contract = NarrativePlanContract(novel_id=novel_id, chapter_number=chapter_number, source=source)
    entities: list[ContractEntity] = []

    for idx, beat in enumerate(list(micro_beats or []), start=1):
        if not isinstance(beat, dict):
            continue
        for raw in _as_list(beat.get("active_entities")):
            ent = parse_entity_ref(raw, beat_index=idx, role="active")
            if ent:
                entities.append(ent)
        for field_name, kind, role in (
            ("cast_refs", "char", "actor"),
            ("location_refs", "loc", "setting"),
            ("prop_refs", "prop", "prop"),
            ("knowledge_refs", "clue", "knowledge"),
        ):
            for raw in _as_list(beat.get(field_name)):
                ent = parse_entity_ref(raw, default_kind=kind, role=role, beat_index=idx, source="legacy_ref")
                if ent:
                    entities.append(ent)

        for raw in _as_list(beat.get("state_requirements")):
            if not isinstance(raw, dict):
                continue
            ent = parse_entity_ref(raw.get("entity"), beat_index=idx)
            key = str(raw.get("key") or raw.get("state_key") or "").strip()
            must_be = str(raw.get("must_be") or raw.get("value") or "").strip()
            if ent and key and must_be:
                contract.state_requirements.append(StateRequirement(ent, key, must_be, idx))
                entities.append(ent)

        for raw in _as_list(beat.get("state_changes")):
            if not isinstance(raw, dict):
                continue
            ent = parse_entity_ref(raw.get("entity"), beat_index=idx)
            key = str(raw.get("key") or raw.get("state_key") or "").strip()
            to_value = str(raw.get("to") or raw.get("to_value") or raw.get("value") or "").strip()
            if ent and key and to_value:
                contract.state_changes.append(
                    StateChange(
                        entity=ent,
                        key=key,
                        from_value=str(raw.get("from") or raw.get("from_value") or "").strip(),
                        to_value=to_value,
                        event_type=str(raw.get("event_type") or "").strip(),
                        beat_index=idx,
                        evidence=str(raw.get("evidence") or "").strip(),
                    )
                )
                entities.append(ent)

        for raw in _as_list(beat.get("fact_intents")):
            if not isinstance(raw, dict):
                continue
            subj = parse_entity_ref(raw.get("subject"), beat_index=idx)
            obj = parse_entity_ref(raw.get("object"), beat_index=idx)
            pred = str(raw.get("predicate") or "").strip()
            if subj and obj and pred:
                contract.fact_intents.append(FactIntent(subj, pred, obj, idx))
                entities.extend([subj, obj])

        for raw in _as_list(beat.get("forbidden_overrides")):
            text = str(raw or "").strip()
            if text:
                contract.forbidden_overrides.append(text)
        for raw in _as_list(beat.get("acceptance_evidence")):
            text = str(raw or "").strip()
            if text:
                contract.acceptance_evidence.append(text)
        for field_name in ("visible_action", "active_action", "delta", "conflict", "handoff_to_next"):
            text = str(beat.get(field_name) or "").strip()
            if text:
                contract.text_promises.append({"beat_index": idx, "field": field_name, "text": text})

    contract.active_entities = _unique_entities(entities)
    return contract


def load_plan_contract(
    db,
    novel_id: str,
    chapter_number: Optional[int] = None,
    *,
    micro_beats: Iterable[dict[str, Any]] | None = None,
) -> NarrativePlanContract:
    ch = int(chapter_number or _latest_planned_chapter(db, novel_id) or 0)
    if ch <= 0:
        return NarrativePlanContract(novel_id=novel_id, chapter_number=0)
    if micro_beats is not None:
        return normalize_micro_beats(novel_id, ch, micro_beats, source="runtime_micro_beats")

    beats = _load_chapter_summary_micro_beats(db, novel_id, ch)
    if beats:
        return normalize_micro_beats(novel_id, ch, beats, source="chapter_summaries.micro_beats")

    rows = db.fetch_all(
        """
        SELECT payload_json FROM narrative_deltas
        WHERE novel_id = ? AND chapter_number = ? AND source = 'micro_beat_plan'
        ORDER BY id
        """,
        (novel_id, ch),
    )
    payloads: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"] or "{}")
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            payloads.append(payload)
    return normalize_micro_beats(novel_id, ch, payloads, source="narrative_deltas.micro_beat_plan")


def _latest_planned_chapter(db, novel_id: str) -> Optional[int]:
    row = db.fetch_one(
        """
        SELECT MAX(chapter_number) AS ch FROM narrative_deltas
        WHERE novel_id = ? AND source = 'micro_beat_plan'
        """,
        (novel_id,),
    )
    if row and row["ch"] is not None:
        return int(row["ch"])
    row = db.fetch_one(
        """
        SELECT MAX(cs.chapter_number) AS ch
        FROM chapter_summaries cs
        JOIN knowledge k ON k.id = cs.knowledge_id
        WHERE k.novel_id = ? AND COALESCE(cs.micro_beats, '') != ''
        """,
        (novel_id,),
    )
    return int(row["ch"]) if row and row["ch"] is not None else None


def _load_chapter_summary_micro_beats(db, novel_id: str, chapter_number: int) -> list[dict[str, Any]]:
    row = db.fetch_one(
        """
        SELECT cs.micro_beats
        FROM chapter_summaries cs
        JOIN knowledge k ON k.id = cs.knowledge_id
        WHERE k.novel_id = ? AND cs.chapter_number = ?
        """,
        (novel_id, chapter_number),
    )
    raw = row.get("micro_beats") if row else None
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    return data if isinstance(data, list) else []


def build_plan_contract_section(contract: NarrativePlanContract) -> str:
    if contract.chapter_number <= 0:
        return ""
    lines = [f"【本章叙事合同】第 {contract.chapter_number} 章"]
    if contract.active_entities:
        lines.append("必须锚定实体：")
        for ent in contract.active_entities[:16]:
            mark = "" if ent.bound else "（待补ID）"
            lines.append(f"   - {ent.label}（{ent.kind}:{ent.id}）{mark} · {ent.role or 'active'}")
    if contract.state_requirements:
        lines.append("状态前提：")
        for req in contract.state_requirements[:10]:
            lines.append(f"   - {req.entity.label}（{req.entity.ref}）.{req.key} 必须为 {req.must_be}")
    if contract.state_changes:
        lines.append("计划状态变化：")
        for chg in contract.state_changes[:10]:
            prefix = f"{chg.from_value} -> " if chg.from_value else ""
            lines.append(f"   - {chg.entity.label}（{chg.entity.ref}）.{chg.key}: {prefix}{chg.to_value}")
    if contract.fact_intents:
        lines.append("计划关系事实：")
        for fact in contract.fact_intents[:10]:
            lines.append(f"   - {fact.subject.label}（{fact.subject.ref}）—{fact.predicate}→ {fact.object.label}（{fact.object.ref}）")
    if contract.forbidden_overrides:
        lines.append("禁止覆盖：")
        for item in contract.forbidden_overrides[:8]:
            lines.append(f"   - {item}")
    return "\n".join(lines)


def _fetch_optional_one(db, sql: str, params: tuple = ()) -> Any:
    """Query a legacy table without failing when migration 013 already dropped it."""
    try:
        return db.fetch_one(sql, params)
    except Exception:
        return None


def current_entity_state(db, novel_id: str, entity: ContractEntity, key: str) -> Optional[str]:
    key_norm = str(key or "").strip()
    if entity.kind == "prop" and key_norm in {"lifecycle_state", "state", "状态"}:
        row = db.fetch_one(
            "SELECT lifecycle_state FROM unified_props WHERE novel_id = ? AND id = ?",
            (novel_id, entity.id),
        )
        return str(row["lifecycle_state"]) if row else None
    if entity.kind == "char" and key_norm in {"mental_state", "心理状态"}:
        row = (
            db.fetch_one(
                "SELECT mental_state FROM unified_characters WHERE novel_id = ? AND id = ?",
                (novel_id, entity.id),
            )
            or _fetch_optional_one(
                db,
                "SELECT mental_state FROM bible_characters WHERE novel_id = ? AND id = ?",
                (novel_id, entity.id),
            )
        )
        return str(row["mental_state"]) if row else None
    return None


def entity_exists(db, novel_id: str, entity: ContractEntity) -> bool:
    if not entity.bound:
        return False
    if entity.kind == "char":
        return bool(
            db.fetch_one("SELECT 1 FROM unified_characters WHERE novel_id = ? AND id = ?", (novel_id, entity.id))
            or _fetch_optional_one(
                db,
                "SELECT 1 FROM bible_characters WHERE novel_id = ? AND id = ?",
                (novel_id, entity.id),
            )
        )
    if entity.kind == "prop":
        return bool(
            db.fetch_one("SELECT 1 FROM unified_props WHERE novel_id = ? AND id = ?", (novel_id, entity.id))
            or _fetch_optional_one(
                db,
                "SELECT 1 FROM bible_props WHERE novel_id = ? AND id = ?",
                (novel_id, entity.id),
            )
        )
    if entity.kind == "loc":
        return bool(
            db.fetch_one("SELECT 1 FROM bible_locations WHERE novel_id = ? AND id = ?", (novel_id, entity.id))
            or db.fetch_one("SELECT 1 FROM chapter_entity_mentions WHERE novel_id = ? AND entity_kind = ? AND entity_id = ? LIMIT 1", (novel_id, entity.kind, entity.id))
            or db.fetch_one("SELECT 1 FROM narrative_deltas WHERE novel_id = ? AND entity_kind = ? AND entity_id = ? LIMIT 1", (novel_id, entity.kind, entity.id))
        )
    return bool(
        db.fetch_one("SELECT 1 FROM chapter_entity_mentions WHERE novel_id = ? AND entity_kind = ? AND entity_id = ? LIMIT 1", (novel_id, entity.kind, entity.id))
        or db.fetch_one("SELECT 1 FROM narrative_deltas WHERE novel_id = ? AND entity_kind = ? AND entity_id = ? LIMIT 1", (novel_id, entity.kind, entity.id))
    )


def build_state_lock_section(db, novel_id: str, chapter_number: Optional[int] = None) -> str:
    contract = load_plan_contract(db, novel_id, chapter_number)
    lines: list[str] = []
    for req in contract.state_requirements:
        current = current_entity_state(db, novel_id, req.entity, req.key)
        suffix = f"；当前={current}" if current is not None else "；当前未知"
        lines.append(f"- {req.entity.label}（{req.entity.ref}）.{req.key} 必须为 {req.must_be}{suffix}")
    for ent in contract.active_entities:
        if ent.kind != "prop" or not ent.bound:
            continue
        row = db.fetch_one(
            "SELECT lifecycle_state, holder_character_id FROM unified_props WHERE novel_id = ? AND id = ?",
            (novel_id, ent.id),
        )
        if row:
            holder = f"，持有者={row['holder_character_id']}" if row.get("holder_character_id") else ""
            lines.append(f"- {ent.label}（{ent.ref}）当前状态={row['lifecycle_state']}{holder}")
    if not lines:
        return ""
    return "【状态锁（STATE_LOCK）】\n" + "\n".join(dict.fromkeys(lines))


def preflight_plan_contract(db, novel_id: str, chapter_number: Optional[int] = None) -> dict[str, Any]:
    contract = load_plan_contract(db, novel_id, chapter_number)
    issues: list[dict[str, Any]] = []
    missing = 0
    for ent in contract.active_entities:
        if not ent.bound:
            missing += 1
            issues.append({
                "severity": "soft",
                "type": "missing_entity_id",
                "message": f"计划实体「{ent.label}」缺少 canonical id，不能进入硬锁。",
                "entity": asdict(ent),
            })
        elif not entity_exists(db, novel_id, ent):
            missing += 1
            issues.append({
                "severity": "soft",
                "type": "unknown_entity_anchor",
                "message": f"计划实体「{ent.label}（{ent.ref}）」没有找到权威或影子锚点。",
                "entity": asdict(ent),
            })
    for req in contract.state_requirements:
        current = current_entity_state(db, novel_id, req.entity, req.key)
        if current is not None and current != req.must_be:
            issues.append({
                "severity": "hard" if current == "RESOLVED" else "soft",
                "type": "state_requirement_mismatch",
                "message": f"{req.entity.label} 的 {req.key} 当前为 {current}，但计划要求 {req.must_be}。",
                "entity": asdict(req.entity),
                "current": current,
                "expected": req.must_be,
            })
    for change in contract.state_changes:
        current = current_entity_state(db, novel_id, change.entity, change.key)
        if current == "RESOLVED" and change.to_value != "RESOLVED":
            issues.append({
                "severity": "hard",
                "type": "potential_hard_override",
                "message": f"{change.entity.label} 已结局，计划试图改为 {change.to_value}，需要人审。",
                "entity": asdict(change.entity),
            })
    hard = sum(1 for i in issues if i["severity"] == "hard")
    return {
        "chapter_number": contract.chapter_number,
        "contract": contract.to_dict(),
        "issues": issues,
        "missing_entity_ids": missing,
        "hard_blockers": hard,
        "plan_entity_count": len(contract.active_entities),
        "state_requirement_count": len(contract.state_requirements),
        "state_change_count": len(contract.state_changes),
        "fact_intent_count": len(contract.fact_intents),
        "state_lock": build_state_lock_section(db, novel_id, contract.chapter_number),
        "contract_section": build_plan_contract_section(contract),
    }
