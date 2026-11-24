"""The chapter a checked writing operation may modify."""
from dataclasses import dataclass
import hashlib
import json

from domain.structure.narrative_progress import NarrativeProgressError, NarrativeProgressPolicy
from domain.structure.story_node import NodeType


def fingerprint(value) -> str:
    data = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def plan_revision(policy: NarrativeProgressPolicy) -> str:
    # Authored plan fields and evidence matter. Bookkeeping timestamps, node word
    # counts and copied manuscript text do not define a writing decision.
    nodes = []
    for node in sorted(policy.nodes, key=lambda n: n.id):
        record = node.to_dict()
        for field in ("updated_at", "created_at", "content", "word_count", "status"):
            record.pop(field, None)
        nodes.append(record)
    return fingerprint([policy.target, nodes, sorted(policy.revisions.items())])


@dataclass(frozen=True)
class WritingTarget:
    chapter_id: str
    chapter_number: int
    act_id: str
    volume_id: str
    remaining_chapters: int
    plan_revision: str


def select_writing_target(policy: NarrativeProgressPolicy) -> WritingTarget | None:
    if policy.structure_issues:
        raise NarrativeProgressError("；".join(policy.structure_issues))
    if policy.generation_finished:
        return None
    number = next(n for n in range(1, policy.target + 1) if n not in policy.written)
    candidates = [node for node in policy.nodes if node.node_type == NodeType.CHAPTER and node.number == number]
    if not candidates:
        if any(node.node_type == NodeType.CHAPTER and node.number > number for node in policy.nodes):
            raise NarrativeProgressError(f"第{number}章缺少规划节点，请先补齐目录")
        return None
    if len(candidates) != 1:
        raise NarrativeProgressError(f"第{number}章存在重复规划节点")
    node = candidates[0]
    policy.ensure_can_write(number)
    act = policy.by_id.get(node.parent_id)
    if act is None or act.node_type != NodeType.ACT:
        raise NarrativeProgressError(f"第{number}章没有有效的所属幕")
    volume = next(v for v in policy.volumes if v.node.id == policy.owner(node).id)
    return WritingTarget(node.id, number, act.id, volume.node.id, volume.remaining, plan_revision(policy))
