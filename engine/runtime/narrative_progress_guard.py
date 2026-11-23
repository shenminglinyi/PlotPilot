"""Shared guard for planning, both writing modes, and target-reached audit."""
from domain.novel.entities.novel import AutopilotStatus, NovelStage
from application.blueprint.services.narrative_progress_service import NarrativeProgressService


def pause_for_progress(host, novel, reason, report=None):
    novel.current_stage = NovelStage.PAUSED_FOR_REVIEW
    novel.autopilot_status = AutopilotStatus.STOPPED
    previous = list(getattr(novel, 'last_audit_issues', None) or [])
    novel.last_audit_issues = [i for i in previous if i.get('code') != 'narrative_progress_review_required'] + [
        {'code': 'narrative_progress_review_required', 'severity': 'high', 'message': reason}]
    host._update_shared_state(novel.novel_id.value, current_stage=novel.current_stage.value,
                              autopilot_pause_reason=reason, narrative_progress=report or {})
    host._flush_novel(novel)


async def progress_policy(host, novel):
    return await NarrativeProgressService(host.story_node_repo, host.chapter_repository,
                                          host.novel_repository).policy(novel)


async def enforce_progress(host, novel, *, writing=False, force_limit=False):
    if type(getattr(novel, 'target_chapters', None)) is not int or novel.target_chapters <= 0:
        return False  # Absent target belongs to macro planning.
    try:
        policy = await progress_policy(host, novel)
        report = policy.report()
        if policy.generation_finished or force_limit:
            if report['story_finished']:
                novel.current_stage = NovelStage.COMPLETED
                novel.autopilot_status = AutopilotStatus.STOPPED
                novel.last_audit_issues = [i for i in novel.last_audit_issues
                                          if i.get('code') != 'narrative_progress_review_required']
                host._update_shared_state(novel.novel_id.value, current_stage='completed',
                                          autopilot_pause_reason='', narrative_progress=report)
                host._flush_novel(novel)
            else:
                pause_for_progress(host, novel, '生成预算已结束，故事仍待验收：' + '；'.join(report['issues']), report)
            return True
        if writing:
            novel.current_auto_chapters = len(policy.written)
            from domain.structure.story_node import NodeType
            unwritten = sorted(n.number for n in policy.nodes
                               if n.node_type == NodeType.CHAPTER and n.number not in policy.written)
            policy.ensure_can_write(unwritten[0] if unwritten else max(policy.written, default=0) + 1)
        return False
    except Exception as error:
        pause_for_progress(host, novel, f'无法确认剧情推进条件，已停止继续生成：{error}')
        return True
