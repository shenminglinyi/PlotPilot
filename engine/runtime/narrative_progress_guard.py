"""Shared guard for planning, both writing modes, and target-reached audit."""
from domain.novel.entities.novel import AutopilotStatus, NovelStage
from domain.structure.narrative_progress import NARRATIVE_REVIEW_ISSUE
from application.blueprint.services.narrative_progress_service import NarrativeProgressService


def pause_for_progress(host, novel, reason, report=None):
    novel.current_stage = NovelStage.PAUSED_FOR_REVIEW
    novel.autopilot_status = AutopilotStatus.STOPPED
    previous = list(getattr(novel, 'last_audit_issues', None) or [])
    novel.last_audit_issues = [i for i in previous if i.get('code') != NARRATIVE_REVIEW_ISSUE] + [
        {'code': NARRATIVE_REVIEW_ISSUE, 'severity': 'high', 'message': reason}]
    host._flush_novel(novel)
    host._update_shared_state(novel.novel_id.value, current_stage=novel.current_stage.value,
                              autopilot_run_epoch=novel.autopilot_run_epoch,
                              autopilot_status=novel.autopilot_status.value,
                              autopilot_pause_reason=reason, narrative_review_reason=reason,
                              narrative_progress=report or {})


async def progress_policy(host, novel):
    return await NarrativeProgressService(host.story_node_repo, host.chapter_repository,
                                          host.novel_repository).policy(novel)


async def enforce_progress(host, novel, *, writing=False, force_limit=False, policy=None):
    if type(getattr(novel, 'target_chapters', None)) is not int or novel.target_chapters <= 0:
        return False  # Absent target belongs to macro planning.
    try:
        policy = policy if policy is not None else await progress_policy(host, novel)
        report = policy.report()
        if policy.generation_finished or force_limit:
            if report['story_finished']:
                novel.current_stage = NovelStage.COMPLETED
                novel.autopilot_status = AutopilotStatus.STOPPED
                novel.last_audit_issues = [i for i in novel.last_audit_issues
                                          if i.get('code') != NARRATIVE_REVIEW_ISSUE]
                host._flush_novel(novel)
                host._update_shared_state(novel.novel_id.value, current_stage='completed',
                                          autopilot_run_epoch=novel.autopilot_run_epoch,
                                          autopilot_status=novel.autopilot_status.value,
                                          autopilot_pause_reason='', narrative_review_reason='', narrative_progress=report)
            else:
                pause_for_progress(host, novel, '生成预算已结束，故事仍待验收：' + '；'.join(report['issues']), report)
            return True
        if writing:
            from domain.structure.writing_target import select_writing_target
            novel.current_auto_chapters = len(policy.written)
            select_writing_target(policy)
        return False
    except Exception as error:
        pause_for_progress(host, novel, f'无法确认剧情推进条件，已停止继续生成：{error}')
        return True
