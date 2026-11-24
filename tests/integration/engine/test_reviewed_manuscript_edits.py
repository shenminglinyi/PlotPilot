import json

import pytest

from application.blueprint.services.narrative_progress_service import NarrativeProgressService
from domain.novel.entities.chapter import Chapter, ChapterStatus
from domain.novel.entities.novel import Novel, NovelStage
from domain.novel.value_objects.novel_id import NovelId
from domain.structure.story_node import NodeType, StoryNode
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_chapter_repository import SqliteChapterRepository
from infrastructure.persistence.database.sqlite_novel_repository import SqliteNovelRepository
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
from infrastructure.persistence.database.write_dispatch import sqlite_writes_bypass_queue


@pytest.fixture
async def reviewed_book(tmp_path):
    db = DatabaseConnection(str(tmp_path / 'novel.db'))
    try:
        with sqlite_writes_bypass_queue():
            books, chapters, nodes = SqliteNovelRepository(db), SqliteChapterRepository(db), StoryNodeRepository(db)
            book = Novel(NovelId('new'), '归航', '作者', 6, current_stage=NovelStage.COMPLETED)
            books.save(book)
            service = NarrativeProgressService(nodes, chapters, books)
            for volume in (1, 2):
                vid = f'v{volume}'
                await nodes.save(StoryNode(vid, 'new', NodeType.VOLUME, volume, vid, volume))
                for i in range(3):
                    n = (volume - 1) * 3 + i + 1
                    await nodes.save(StoryNode(f'c{n}', 'new', NodeType.CHAPTER, n, f'章{n}', n, parent_id=vid))
                    chapters.save(Chapter(f'p{n}', book.novel_id, n, f'章{n}', content=f'第{n}晚。她将船票还给他。',
                                          status=ChapterStatus.COMPLETED))
            for vid, n in [('v1', 1), ('v2', 4)]:
                item = dict(id='choice', description='她作出选择', status='resolved', evidence_chapters=[n],
                            evidence_passages=[{'chapter_number': n, 'quote': '她将船票还给他。'}])
                payload = {'milestones': [item], 'chapter_budget': 3}
                if vid == 'v2':
                    payload['ending_review'] = dict(reviewed_through_chapter=6, character_outcomes=item,
                                                    core_conflict=item, ending=item, open_ending_notes=['船驶向何处由读者想象'])
                await service.save_review('new', vid, payload)
            yield db, service
    finally:
        db.close_all()


async def test_unused_edit_keeps_verdict_and_last_chapter_edit_reopens_it(reviewed_book):
    db, service = reviewed_book
    report = await service.get_report('new')
    assert report['story_finished']
    quote = report['volumes'][0]['milestones'][0]['evidence_passages'][0]
    assert quote == {'quote': '她将船票还给他。', 'chapter_number': 1, 'start': 4, 'end': 12}
    conn = db.get_connection()
    conn.execute("UPDATE chapters SET content='同长的一段新文字' WHERE number=2")
    assert conn.execute("SELECT current_stage FROM novels").fetchone()[0] == 'completed'
    assert (await service.get_report('new'))['story_finished']
    conn.execute("UPDATE chapters SET content=replace(content, '还给', '留给') WHERE number=6")
    conn.commit()
    stage, epoch, raw = conn.execute("SELECT current_stage, autopilot_run_epoch, last_audit_issues FROM novels").fetchone()
    assert stage == 'paused_for_review' and epoch == 1
    assert '第6章' in json.loads(raw)[-1]['message']
    report = await service.get_report('new')
    assert not report['story_finished'] and not report['ending_review']['terminal_revision_current']
    assert all(v['exit_verified'] for v in report['volumes'])


async def test_stale_completion_cannot_win_when_edit_committed_first(reviewed_book):
    db, _ = reviewed_book
    conn = db.get_connection()
    conn.execute("UPDATE novels SET autopilot_status='running', current_stage='auditing'")
    conn.execute("UPDATE chapters SET content=replace(content, '给', '予') WHERE number=1")
    conn.execute("UPDATE novels SET current_stage='completed', autopilot_status='stopped'")
    assert conn.execute("SELECT current_stage FROM novels").fetchone()[0] == 'paused_for_review'


async def test_wrong_or_ambiguous_evidence_cannot_be_signed(reviewed_book):
    db, service = reviewed_book
    conn = db.get_connection()
    conn.execute("UPDATE chapters SET content='远行。远行。' WHERE number=1")
    conn.commit()
    item = dict(id='choice', description='出航', status='resolved', evidence_chapters=[1],
                evidence_passages=[dict(chapter_number=1, quote='远行。')])
    with pytest.raises(ValueError, match='多处'):
        await service.save_review('new', 'v1', {'milestones': [item]})
    item['evidence_passages'][0]['start'] = 1
    with pytest.raises(ValueError, match='不一致'):
        await service.save_review('new', 'v1', {'milestones': [item]})
    item['evidence_passages'][0]['start'] = 3
    report = await service.save_review('new', 'v1', {'milestones': [item]})
    assert report['volumes'][0]['milestones'][0]['evidence_current']


async def test_stale_author_review_preserves_new_plan_and_evidence(reviewed_book):
    db, service = reviewed_book
    rev = (await service.get_report('new'))['plan_revision']
    conn = db.get_connection()
    conn.execute("UPDATE story_nodes SET title='新的卷纲' WHERE id='v1'")
    conn.commit()
    with pytest.raises(ValueError, match='重新核读'):
        await service.save_review('new', 'v1', {'expected_plan_revision': rev, 'milestones': []})
    with pytest.raises(ValueError, match='重新核读'):
        await service.nodes.commit_narrative_review('new', 'v1', {}, rev)
    current = (await service.get_report('new'))['volumes'][0]
    assert current['title'] == '新的卷纲' and current['milestones'][0]['evidence_current']
