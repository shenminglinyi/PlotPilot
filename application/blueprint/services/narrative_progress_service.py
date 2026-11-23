"""Read and review narrative progress against committed manuscript revisions."""
from __future__ import annotations

from copy import deepcopy

from domain.novel.value_objects.novel_id import NovelId
from domain.structure.narrative_progress import NarrativeProgressPolicy
from domain.structure.story_node import NodeType


class NarrativeProgressService:
    def __init__(self, story_node_repo, chapter_repository, novel_repository):
        self.nodes = story_node_repo
        self.chapters = chapter_repository
        self.novels = novel_repository

    async def policy(self, novel):
        nodes = await self.nodes.get_by_novel(novel.novel_id.value)
        revisions = self.chapters.completed_revisions(novel.novel_id)
        return NarrativeProgressPolicy(nodes, novel.target_chapters, revisions)

    async def get_report(self, novel_id: str):
        novel = self.novels.get_by_id(NovelId(novel_id))
        if not novel:
            raise LookupError('小说不存在')
        return (await self.policy(novel)).report()

    async def save_review(self, novel_id: str, volume_id: str, payload: dict):
        novel = self.novels.get_by_id(NovelId(novel_id))
        if not novel:
            raise LookupError('小说不存在')
        node = await self.nodes.get_by_id(volume_id)
        if not node or node.novel_id != novel_id or node.node_type != NodeType.VOLUME:
            raise LookupError('本小说中不存在该卷')
        policy = await self.policy(novel)
        current = deepcopy(NarrativeProgressPolicy.contract(node))
        current.update(deepcopy(payload))
        all_items = [(item, True, 'milestones' in payload) for item in current.get('milestones', [])]
        ending = current.get('ending_review')
        if ending is not None:
            if not policy.volumes or policy.volumes[-1].node.id != volume_id:
                raise ValueError('全书终局验收只能记录在末卷')
            if ending.get('reviewed_through_chapter') != max(policy.written, default=0):
                raise ValueError('终局验收必须覆盖当前末章')
            all_items += [(ending.get(k, {}), False, 'ending_review' in payload)
                          for k in ('core_conflict', 'character_outcomes', 'ending')]
            all_items += [(item, False, 'ending_review' in payload)
                          for item in ending.get('required_promises', [])]
        for item, volume_item, is_new in all_items:
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
            if is_new:
                item['evidence_revisions'] = {str(n): policy.revisions[n] for n in refs}
        old = node.metadata
        node.metadata = {**(old or {}), 'narrative_progress': current}
        revised_nodes = [node if n.id == node.id else n for n in policy.nodes]
        check = NarrativeProgressPolicy(revised_nodes, novel.target_chapters, policy.revisions)
        if check.structure_issues:
            node.metadata = old
            raise ValueError('；'.join(check.structure_issues))
        await self.nodes.update(node)
        return check.report()
