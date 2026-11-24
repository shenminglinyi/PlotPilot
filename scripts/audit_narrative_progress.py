"""Read-only narrative audit; optionally preserve a complete manuscript snapshot.

This never changes chapter ownership, status, or prose in the source database.
"""
from __future__ import annotations

import argparse
from dataclasses import fields
from datetime import datetime, timezone, timedelta
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from domain.structure.narrative_progress import NarrativeProgressPolicy
from domain.structure.story_node import StoryNode
from infrastructure.persistence.database.sqlite_chapter_repository import read_completed_revisions


def audit(db_path: Path, novel_id: str | None = None, *, snapshot=False):
    with sqlite3.connect(db_path.resolve().as_uri() + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('BEGIN')
        if novel_id is None:
            novels = conn.execute('SELECT id FROM novels ORDER BY id').fetchall()
            if len(novels) != 1:
                raise ValueError('数据库中不是恰好一本小说，请使用 --novel-id 指定')
            novel_id = novels[0]['id']
        novel_row = conn.execute(
            'SELECT id,title,premise,target_chapters,current_stage,autopilot_status,updated_at '
            'FROM novels WHERE id=?', (novel_id,)).fetchone()
        if novel_row is None:
            raise ValueError('小说不存在')
        novel = dict(novel_row)
        raw_nodes = [dict(r) for r in conn.execute('SELECT * FROM story_nodes WHERE novel_id=?', (novel_id,))]
        allowed = {field.name for field in fields(StoryNode)} - {'created_at', 'updated_at'}
        nodes = [StoryNode(**{k:v for k,v in row.items() if k in allowed}) for row in raw_nodes]
        chapters = [dict(r) for r in conn.execute(
            'SELECT number,title,status,content,word_count,updated_at FROM chapters WHERE novel_id=? ORDER BY number',
            (novel_id,))]
        revisions = read_completed_revisions(conn.execute, novel_id)
        report = NarrativeProgressPolicy(nodes,novel['target_chapters'],revisions).report()
        report['source_state'] = novel
        report['audited_at'] = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
        report['source_database_modified'] = False
        report['chapter_records'] = [
            {k:v for k,v in chapter.items() if k!='content'} |
            {'content_sha256':hashlib.sha256((chapter['content'] or '').encode()).hexdigest()}
            for chapter in chapters]
        report['data_limitation'] = '结构、篇幅和证据有效性审计；不把关键词匹配或登记状态当成文学性、历史准确性或剧情闭环的自动证明。'
        preservation = {'novel':novel,'story_nodes':raw_nodes,'chapters':chapters} if snapshot else None
    return report,preservation


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--novel-id')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--snapshot',action='store_true')
    args=parser.parse_args()
    report,preservation=audit(args.db,args.novel_id,snapshot=args.snapshot)
    args.output.mkdir(parents=True,exist_ok=True)
    path=args.output/'narrative-progress-audit.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if preservation is not None:
        with gzip.open(args.output/'manuscript-preserved.json.gz','wt',encoding='utf-8') as out:
            json.dump(preservation,out,ensure_ascii=False)
    print(json.dumps({'report':str(path),'generation_finished':report['generation_finished'],
                     'story_finished':report['story_finished'],'issues':len(report['issues'])},ensure_ascii=False))


if __name__=='__main__':
    main()
