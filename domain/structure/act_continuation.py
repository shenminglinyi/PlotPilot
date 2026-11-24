"""The destination and limits shared by manual and automatic act continuation."""
from dataclasses import dataclass

from domain.structure.narrative_progress import NarrativeProgressError, NarrativeProgressPolicy
from domain.structure.story_node import NodeType
from domain.structure.writing_target import plan_revision, select_writing_target


@dataclass(frozen=True)
class ActContinuation:
    source_id: str
    volume_id: str
    chapter_budget: int
    plan_revision: str
    existing_id: str | None


def decide_act_continuation(policy: NarrativeProgressPolicy, source_id: str, limit: int) -> ActContinuation:
    source = policy.by_id.get(source_id)
    if not source or source.node_type != NodeType.ACT:
        raise NarrativeProgressError('当前幕不存在或不属于本书')
    chapters = [n for n in policy.nodes if n.parent_id == source_id and n.node_type == NodeType.CHAPTER]
    if not chapters:
        raise NarrativeProgressError(f'请先为第{source.number}幕规划章节并完成正文')
    unfilled = sorted(n.number for n in chapters if n.number not in policy.written)
    if unfilled:
        raise NarrativeProgressError(f'第{unfilled[0]}章已有规划，须先完成正文')

    destination = policy.next_volume(source.parent_id)
    successors = [n for n in policy.nodes if n.node_type == NodeType.ACT and n.number == source.number + 1]
    if len(successors) > 1:
        raise NarrativeProgressError('下一幕的编号重复，请先修订结构')
    successor = successors[0] if successors else None
    if successor and successor.parent_id != destination.node.id:
        # The author's plan may advance before using up a fully reviewed volume.
        # An exhausted or earlier volume cannot become writable by naming it here.
        proposed = policy.next_volume(successor.parent_id)
        order = [v.node.id for v in policy.volumes]
        if proposed.node.id != successor.parent_id or order.index(proposed.node.id) < order.index(destination.node.id):
            raise NarrativeProgressError('已规划的下一幕与验收确定的目标卷不一致，请先调整大纲')
        destination = proposed
    budget = min(destination.remaining, policy.target - len(policy.written), limit)
    if budget <= 0:
        raise NarrativeProgressError('本卷或全书篇幅预算已用尽')
    pending = select_writing_target(policy)
    if pending and (not successor or pending.act_id != successor.id):
        raise NarrativeProgressError(f'第{pending.chapter_number}章已有规划，须先完成正文')
    return ActContinuation(source_id, destination.node.id, budget, plan_revision(policy),
                           successor.id if successor else None)
