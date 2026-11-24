"""Read and review narrative progress against committed manuscript revisions."""
from __future__ import annotations

from copy import deepcopy

from domain.novel.value_objects.novel_id import NovelId
from domain.structure.narrative_progress import NarrativeProgressPolicy, NarrativeReviewConflict
from domain.structure.writing_target import plan_revision
from domain.structure.story_node import NodeType


class NarrativeProgressService:
    def __init__(self, story_node_repo, chapter_repository, novel_repository):
        self.nodes = story_node_repo
        self.chapters = chapter_repository
        self.novels = novel_repository

    async def policy(self, novel):
        if getattr(type(self.nodes), "get_plan_nodes_sync", None):
            nodes = self.nodes.get_plan_nodes_sync(novel.novel_id.value)
        else:
            nodes = await self.nodes.get_by_novel(novel.novel_id.value)
        revisions = self.chapters.completed_revisions(novel.novel_id)
        return NarrativeProgressPolicy(nodes, novel.target_chapters, revisions)

    async def get_report(self, novel_id: str):
        novel = self.novels.get_by_id(NovelId(novel_id))
        if not novel:
            raise LookupError('小说不存在')
        return self._author_report(await self.policy(novel))

    @staticmethod
    def _author_report(policy):
        report = policy.report()
        report['plan_revision'] = plan_revision(policy)
        for volume, summary in zip(policy.volumes, report['volumes']):
            contract = policy.contract(volume.node)
            summary['goal'] = contract.get('goal', '')
            summary['milestones'] = [
                {**item, 'evidence_current': policy.evidence_valid(item, volume.chapters)}
                for item in contract.get('milestones', [])
            ]
        if policy.volumes:
            ending = deepcopy(policy.contract(policy.volumes[-1].node).get('ending_review'))
            if ending:
                last = max(policy.written, default=None)
                ending['terminal_revision_current'] = (
                    last is not None and ending.get('reviewed_through_chapter') == last
                    and ending.get('reviewed_through_revision') == policy.revisions[last]
                )
                verdicts = [ending.get(k) for k in ('core_conflict', 'character_outcomes', 'ending')]
                for item in verdicts + ending.get('required_promises', []):
                    if isinstance(item, dict):
                        item['evidence_current'] = policy.evidence_valid(item)
                report['ending_review'] = ending
        return report

    def _locate_passages(self, item, novel_id):
        for passage in item.get('evidence_passages', []):
            number = passage['chapter_number']
            if number not in item.get('evidence_chapters', []):
                raise ValueError('片段必须属于本项引用的证据章节')
            chapter = self.chapters.get_by_novel_and_number(novel_id, number)
            content = chapter.content if chapter else ''
            quote = passage['quote']
            start = passage.get('start')
            if not quote.strip():
                raise ValueError('证据片段不能为空白')
            if start is None:
                start = content.find(quote)
                if start >= 0 and content.find(quote, start + 1) >= 0:
                    raise ValueError(f'第{number}章有多处相同片段，请指定起始位置')
            if start < 0 or not content.startswith(quote, start):
                raise ValueError(f'所引片段与第{number}章当前正文不一致')
            passage.update(start=start, end=start + len(quote))

    async def save_review(self, novel_id: str, volume_id: str, payload: dict):
        novel = self.novels.get_by_id(NovelId(novel_id))
        if not novel:
            raise LookupError('小说不存在')
        policy = await self.policy(novel)
        node = policy.by_id.get(volume_id)
        if not node or node.novel_id != novel_id or node.node_type != NodeType.VOLUME:
            raise LookupError('本小说中不存在该卷')
        expected = plan_revision(policy)
        payload = dict(payload)
        reviewed_revision = payload.pop('expected_plan_revision', None)
        if reviewed_revision is not None and reviewed_revision != expected:
            raise NarrativeReviewConflict('书稿或大纲已变化，请重新核读后再提交验收')
        current = deepcopy(NarrativeProgressPolicy.contract(node))
        current.update(deepcopy(payload))
        all_items = [(item, True, 'milestones' in payload) for item in current.get('milestones', [])]
        ending = current.get('ending_review')
        if ending is not None:
            if 'ending_review' in payload:
                if not policy.volumes or policy.volumes[-1].node.id != volume_id:
                    raise ValueError('全书终局验收只能记录在末卷')
                last = max(policy.written, default=None)
                through = ending.get('reviewed_through_chapter')
                if last is None or type(through) is not int or through != last:
                    raise ValueError('终局验收必须覆盖当前末章')
                ending['reviewed_through_revision'] = policy.revisions[last]
            all_items += [(ending.get(k, {}), False, 'ending_review' in payload)
                          for k in ('core_conflict', 'character_outcomes', 'ending')]
            all_items += [(item, False, 'ending_review' in payload)
                          for item in ending.get('required_promises', [])]
        for item, volume_item, is_new in all_items:
            if not is_new:
                continue
            refs = item.get('evidence_chapters', [])
            if item.get('status') == 'resolved' and not refs:
                raise ValueError('已兑现项必须提供正文证据章节')
            if any(type(n) is not int or n not in policy.written for n in refs):
                raise ValueError('证据必须引用已完成且非空的正文，不能引用规划或空白章节')
            # Bind only newly submitted assessments; never silently renew stale reviews.
            if volume_item:
                owner = next(v for v in policy.volumes if v.node.id == volume_id)
                if any(n not in owner.chapters for n in refs):
                    raise ValueError('卷级证据必须来自本卷正文')
            self._locate_passages(item, novel.novel_id)
            item['evidence_revisions'] = {str(n): policy.revisions[n] for n in refs}
        reviewed_node = deepcopy(node)
        reviewed_node.metadata = {**(node.metadata or {}), 'narrative_progress': current}
        revised_nodes = [reviewed_node if n.id == node.id else n for n in policy.nodes]
        check = NarrativeProgressPolicy(revised_nodes, novel.target_chapters, policy.revisions)
        if check.structure_issues:
            raise ValueError('；'.join(check.structure_issues))
        await self.nodes.commit_narrative_review(novel_id, volume_id, current, expected)
        return self._author_report(check)
