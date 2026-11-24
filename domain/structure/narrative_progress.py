"""Narrative budgets and evidence-backed closure, independent of runtime stages.

Chapter tree rows are plans, not manuscripts. Only the supplied committed chapter
revisions may satisfy a milestone or consume a volume's writing budget.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from domain.structure.story_node import NodeType, StoryNode


NARRATIVE_REVIEW_ISSUE = "narrative_progress_review_required"


class NarrativeProgressError(ValueError):
    pass


class NarrativeReviewConflict(NarrativeProgressError):
    """The manuscript or plan changed after the review was opened."""


@dataclass(frozen=True)
class VolumeProgress:
    node: StoryNode
    budget: int
    chapters: tuple[int, ...]
    issues: tuple[str, ...]
    estimated_budget: bool = False

    @property
    def remaining(self) -> int:
        return max(0, self.budget - len(self.chapters))

    def to_dict(self) -> dict:
        return {
            'id': self.node.id, 'title': self.node.title, 'chapter_budget': self.budget,
            'budget_is_estimated': self.estimated_budget, 'written_chapters': list(self.chapters),
            'remaining_chapters': self.remaining, 'exit_verified': not self.issues,
            'issues': list(self.issues),
        }


class NarrativeProgressPolicy:
    def __init__(self, nodes: Iterable[StoryNode], target: int, revisions: Mapping[int, str]):
        self.nodes = list(nodes)
        self.by_id = {n.id: n for n in self.nodes}
        self.target = target
        self.revisions = dict(revisions)
        self.written = frozenset(self.revisions)
        volumes = sorted((n for n in self.nodes if n.node_type == NodeType.VOLUME), key=self._path)
        self.structure_issues: list[str] = []
        if target <= 0:
            self.structure_issues.append('目标章节数必须大于零')
        if not volumes:
            self.structure_issues.append('缺少卷级规划')
        explicit = []
        for volume in volumes:
            contract = self.contract(volume)
            budget = contract.get('chapter_budget')
            if budget is None and volume.chapter_start and volume.chapter_end:
                budget = volume.chapter_end - volume.chapter_start + 1
            if budget is not None and (type(budget) is not int or budget <= 0):
                self.structure_issues.append(f'《{volume.title}》篇幅预算无效')
                budget = None
            explicit.append(budget)
        missing = explicit.count(None)
        remainder = target - sum(b for b in explicit if b is not None)
        if remainder < missing or (not missing and remainder != 0):
            self.structure_issues.append('各卷篇幅预算之和必须与全书目标一致，且每卷至少一章')
        fallback = max(0, remainder) // missing if missing else 0
        extra = max(0, remainder) % missing if missing else 0
        chapter_owner = {}
        for node in self.nodes:
            if node.node_type == NodeType.CHAPTER and node.number in self.written:
                owner = self.owner(node)
                if node.number in chapter_owner:
                    self.structure_issues.append(f'第{node.number}章存在重复结构节点')
                chapter_owner[node.number] = owner.id if owner else None
        self.unassigned = sorted(n for n in self.written if not chapter_owner.get(n))
        if self.unassigned:
            self.structure_issues.append('存在未归属到卷的正文：' + '、'.join(map(str, self.unassigned)))
        progress = []
        for volume, budget in zip(volumes, explicit):
            estimated = budget is None
            if estimated:
                budget = fallback + int(extra > 0)
                extra = max(0, extra - 1)
            chapters = tuple(sorted(n for n, owner in chapter_owner.items() if owner == volume.id))
            issues = self._volume_exit_issues(volume, chapters)
            if len(chapters) > budget:
                issues.append(f'正文{len(chapters)}章已超过卷预算{budget}章，需要重规划')
            progress.append(VolumeProgress(volume, budget, chapters, tuple(issues), estimated))
        self.volumes = tuple(progress)

    @staticmethod
    def contract(node: StoryNode) -> dict:
        value = (node.metadata or {}).get('narrative_progress', {})
        return value if isinstance(value, dict) else {}

    def _path(self, node: StoryNode) -> tuple:
        path, seen = [], set()
        while node and node.id not in seen:
            seen.add(node.id)
            path.append((node.order_index, node.number, node.id))
            node = self.by_id.get(node.parent_id)
        return tuple(reversed(path))

    def owner(self, node: StoryNode) -> StoryNode | None:
        seen = set()
        while node and node.id not in seen:
            seen.add(node.id)
            if node.node_type == NodeType.VOLUME:
                return node
            node = self.by_id.get(node.parent_id)
        return None

    def evidence_valid(self, item: dict, allowed: Iterable[int] | None = None) -> bool:
        if not isinstance(item, dict) or item.get('status') != 'resolved':
            return False
        refs, revisions = item.get('evidence_chapters'), item.get('evidence_revisions')
        if not isinstance(refs, list) or not refs or not isinstance(revisions, dict):
            return False
        allowed = set(self.written if allowed is None else allowed)
        return all(type(n) is int and n in allowed and revisions.get(str(n)) == self.revisions.get(n)
                   for n in refs)

    def _volume_exit_issues(self, volume: StoryNode, chapters: tuple[int, ...]) -> list[str]:
        issues = []
        if not chapters:
            issues.append('本卷尚无已完成正文')
        milestones = self.contract(volume).get('milestones', [])
        required = [m for m in milestones if isinstance(m, dict) and m.get('required', True)]
        if not required:
            issues.append('尚未声明并验收本卷必达剧情节点')
        for milestone in required:
            if not self.evidence_valid(milestone, chapters):
                issues.append('未兑现或证据已失效：' + str(milestone.get('description') or milestone.get('id')))
        return issues

    @property
    def generation_finished(self) -> bool:
        return self.target > 0 and len(self.written) >= self.target

    def report(self) -> dict:
        issues = list(self.structure_issues)
        if self.generation_finished:
            if self.written != frozenset(range(1, self.target + 1)):
                issues.append('正文编号未完整覆盖目标范围，或存在超出目标的正文')
            for volume in self.volumes:
                issues.extend(f'《{volume.node.title}》：{i}' for i in volume.issues)
            ending = (self.contract(self.volumes[-1].node).get('ending_review') or {}) if self.volumes else {}
            last = max(self.written)
            if ending.get('reviewed_through_chapter') != last:
                issues.append('缺少覆盖当前末章的全书终局验收')
            elif ending.get('reviewed_through_revision') != self.revisions[last]:
                issues.append(f'第{last}章正文版本缺少相应的终局验收，请重新核读末章')
            for key, label in [('core_conflict', '核心冲突'), ('character_outcomes', '主要人物去向'), ('ending', '全书结局')]:
                if not self.evidence_valid(ending.get(key, {})):
                    issues.append(label + '尚未有有效正文证据支持闭环')
            for promise in ending.get('required_promises', []):
                if promise.get('required', True) and not self.evidence_valid(promise):
                    issues.append('核心承诺未兑现：' + str(promise.get('description') or promise.get('id')))
        return {
            'target_chapters': self.target, 'completed_chapters': len(self.written),
            'generation_finished': self.generation_finished,
            'story_finished': self.generation_finished and not issues,
            'issues': issues, 'volumes': [v.to_dict() for v in self.volumes],
        }

    def next_volume(self, current_volume_id: str | None) -> VolumeProgress:
        if self.structure_issues:
            raise NarrativeProgressError('；'.join(self.structure_issues))
        if self.generation_finished:
            raise NarrativeProgressError('已达到全书篇幅预算，请先验收故事或重新规划')
        index = next((i for i, v in enumerate(self.volumes) if v.node.id == current_volume_id), 0)
        if current_volume_id and not any(v.node.id == current_volume_id for v in self.volumes):
            raise NarrativeProgressError('当前幕没有有效父卷')
        for previous in self.volumes[:index]:
            if previous.issues:
                raise NarrativeProgressError(f'前卷《{previous.node.title}》尚未验收：' + '；'.join(previous.issues))
        current = self.volumes[index]
        if current.remaining:
            return current
        if current.issues:
            raise NarrativeProgressError(f'《{current.node.title}》已达到篇幅预算：' + '；'.join(current.issues))
        if index + 1 >= len(self.volumes):
            raise NarrativeProgressError('所有卷预算已用尽，需要重规划')
        return self.volumes[index + 1]

    def ensure_can_write(self, chapter_number: int) -> None:
        if self.structure_issues:
            raise NarrativeProgressError('；'.join(self.structure_issues))
        node = next((n for n in self.nodes if n.node_type == NodeType.CHAPTER and n.number == chapter_number), None)
        if not node:
            return  # Runtime will enter act planning if no next chapter exists.
        owner = self.owner(node)
        if not owner:
            raise NarrativeProgressError('待写章节没有有效父卷')
        index = next(i for i, v in enumerate(self.volumes) if v.node.id == owner.id)
        for previous in self.volumes[:index]:
            if previous.issues:
                raise NarrativeProgressError(f'进入《{owner.title}》前须验收《{previous.node.title}》：' + '；'.join(previous.issues))
        if self.volumes[index].remaining <= 0:
            raise NarrativeProgressError(f'《{owner.title}》篇幅预算已用尽，不能继续追加本卷正文')
