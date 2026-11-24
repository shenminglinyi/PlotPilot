"""Exercise packaged narrative guards on an explicitly marked disposable DB copy.

No network model is constructed. The one act-planning response is deterministic.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace


def verify_test_copy(db_path: Path) -> dict:
    db_path = db_path.resolve(strict=True)
    marker_path = db_path.parent / 'narrative-test-copy.json'
    marker = json.loads(marker_path.read_text(encoding='utf-8'))
    source = Path(marker['source_db']).resolve(strict=True)
    if marker.get('purpose') != 'plotpilot-narrative-progress-test-copy':
        raise ValueError('This database is not marked as a narrative test copy')
    if source.samefile(db_path):
        raise ValueError('Refusing to run acceptance writes against the original database')
    if Path(marker['copy_db']).resolve() != db_path:
        raise ValueError('Test-copy marker does not match the supplied database')
    if source.parent == db_path.parent:
        raise ValueError('Keep the disposable copy outside the production data directory')
    return marker


async def verify(db_path: Path) -> dict:
    marker = verify_test_copy(db_path)
    # Resolve runtime paths before importing application modules or initializing DBs.
    os.environ['PLOTPILOT_PROD_DATA_DIR'] = str(db_path.parent)
    os.environ['DISABLE_AUTO_DAEMON'] = '1'
    os.environ['PLOTPILOT_ALLOW_DIRECT_SQLITE_WRITES'] = '1'
    if not getattr(sys, 'frozen', False):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    from application.blueprint.services.continuous_planning_service import ContinuousPlanningService
    from application.blueprint.services.narrative_progress_service import NarrativeProgressService
    from domain.novel.entities.novel import Novel, NovelStage, AutopilotStatus
    from domain.novel.entities.chapter import Chapter, ChapterStatus
    from domain.novel.value_objects.novel_id import NovelId
    from domain.structure.story_node import StoryNode, NodeType
    from engine.runtime.act_planning_delegate import run_act_planning
    from engine.runtime.narrative_progress_guard import enforce_progress
    from infrastructure.persistence.database.connection import get_database
    from infrastructure.persistence.database.sqlite_chapter_repository import SqliteChapterRepository
    from infrastructure.persistence.database.sqlite_novel_repository import SqliteNovelRepository
    from infrastructure.persistence.database.story_node_repository import StoryNodeRepository

    db = get_database(str(db_path))
    nodes = StoryNodeRepository(db)
    chapters = SqliteChapterRepository(db)
    novels = SqliteNovelRepository(db)
    service = NarrativeProgressService(nodes, chapters, novels)
    model_calls = []

    class Host:
        story_node_repo = nodes
        chapter_repository = chapters
        novel_repository = novels
        shared = {}

        def _flush_novel(self, novel):
            novels.save(novel)

        def _update_shared_state(self, key, **values):
            self.shared[key] = values

        def _is_still_running(self, novel):
            return novel.autopilot_status == AutopilotStatus.RUNNING

    host = Host()
    copied_book = novels.get_by_id(NovelId(marker['novel_id']))
    assert copied_book is not None
    before = chapters.completed_revisions(copied_book.novel_id)
    book_report = await service.get_report(copied_book.novel_id.value)
    assert book_report['generation_finished'] and not book_report['story_finished']
    stopped = await enforce_progress(host, copied_book, writing=True)
    assert stopped and copied_book.current_stage == NovelStage.PAUSED_FOR_REVIEW
    assert copied_book.autopilot_status == AutopilotStatus.STOPPED
    assert chapters.completed_revisions(copied_book.novel_id) == before
    case1 = {'name': 'budget_reached_but_story_unfinished', 'passed': True,
             'completed_chapters': len(before), 'stage': copied_book.current_stage.value,
             'manuscript_unchanged': True}

    fixture_id = 'narrative-acceptance-fixture'
    if novels.get_by_id(NovelId(fixture_id)):
        raise ValueError('Use a fresh copy for each acceptance run')
    fixture = Novel(NovelId(fixture_id), 'Narrative acceptance fixture', 'Local test', 3,
                    current_auto_chapters=1, current_act=1, current_stage=NovelStage.ACT_PLANNING,
                    autopilot_status=AutopilotStatus.RUNNING, auto_approve_mode=True)
    novels.save(fixture)
    v1 = StoryNode('verify-v1', fixture_id, NodeType.VOLUME, 1, 'Opening volume', 0)
    v2 = StoryNode('verify-v2', fixture_id, NodeType.VOLUME, 2, 'Closing volume', 1)
    a1 = StoryNode('verify-a1', fixture_id, NodeType.ACT, 1, 'Opening act', 0, parent_id=v1.id)
    c1 = StoryNode('verify-c1', fixture_id, NodeType.CHAPTER, 1, 'Committed chapter', 0, parent_id=a1.id)
    for node in [v1, v2, a1, c1]:
        await nodes.save(node)
    chapters.save(Chapter('verify-prose-1', fixture.novel_id, 1, 'Committed chapter',
                          content='Synthetic committed prose for deterministic verification.', status=ChapterStatus.COMPLETED))
    db.commit()
    await service.save_review(fixture_id, v1.id, {'chapter_budget': 1, 'milestones': [
        {'id': 'opening-goal', 'description': 'Opening conflict changes the protagonist',
         'status': 'resolved', 'evidence_chapters': [1]}]})
    await service.save_review(fixture_id, v2.id, {'chapter_budget': 2})

    class FixturePlanningService(ContinuousPlanningService):
        async def _generate_next_act_info(self, novel_id, current_act, bible_context):
            model_calls.append({'kind': 'deterministic_stub', 'destination': bible_context['target_volume']['id']})
            return {'title': 'New volume act', 'description': 'Fulfill the closing volume',
                    'suggested_chapter_count': 9}

        async def create_next_act_auto(self, *args, **kwargs):
            result = await super().create_next_act_auto(*args, **kwargs)
            act = result['next_act']
            # Deterministic chapter planning; exercise real runtime routing without a model.
            for index in range(act['suggested_chapter_count']):
                await nodes.save(StoryNode(f'verify-plan-{index}', fixture_id, NodeType.CHAPTER,
                                          index + 2, 'Planned closing chapter', index, parent_id=act['id']))
            return result

    host.planning_service = FixturePlanningService(nodes, SimpleNamespace(), None, novel_repository=novels,
                                                   chapter_repository=chapters)
    await run_act_planning(host, fixture)
    all_nodes = await nodes.get_by_novel(fixture_id)
    next_act = next(n for n in all_nodes if n.node_type == NodeType.ACT and n.number == 2)
    assert next_act.parent_id == v2.id and next_act.suggested_chapter_count == 2
    assert fixture.current_stage == NovelStage.WRITING
    case2 = {'name': 'volume_boundary_routes_to_selected_volume', 'passed': True,
             'destination': next_act.parent_id, 'act_budget': next_act.suggested_chapter_count,
             'stage': fixture.current_stage.value}

    for number in [2, 3]:
        chapters.save(Chapter(f'verify-prose-{number}', fixture.novel_id, number, 'Closing chapter',
                              content=f'Synthetic closing prose {number}.', status=ChapterStatus.COMPLETED))
    db.commit()

    def item(key, evidence):
        return {'id': key, 'description': key, 'status': 'resolved', 'evidence_chapters': evidence}
    await service.save_review(fixture_id, v2.id, {
        'milestones': [item('closing-goal', [2, 3])],
        'ending_review': {'reviewed_through_chapter': 3, 'core_conflict': item('core', [3]),
                          'character_outcomes': item('outcomes', [2, 3]), 'ending': item('ending', [3])}})
    fixture.current_auto_chapters = 3
    fixture.autopilot_status = AutopilotStatus.RUNNING
    assert await enforce_progress(host, fixture, writing=True)
    assert fixture.current_stage == NovelStage.COMPLETED
    assert chapters.get_by_novel_and_number(fixture.novel_id, 4) is None
    final_report = await service.get_report(fixture_id)
    assert final_report['story_finished']
    case3 = {'name': 'reviewed_ending_completes_without_extra_chapter', 'passed': True,
             'stage': fixture.current_stage.value, 'completed_chapters': 3, 'extra_chapter_created': False}
    return {'passed': True, 'frozen_executable': bool(getattr(sys, 'frozen', False)),
            'cases': [case1, case2, case3], 'external_model_calls': 0,
            'deterministic_planning_responses': len(model_calls),
            'production_database_written': False, 'copy_db': str(db_path.resolve())}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args(argv)
    result = asyncio.run(verify(args.db))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    if sys.stdout:
        print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
