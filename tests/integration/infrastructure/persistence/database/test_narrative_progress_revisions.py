import sqlite3

from domain.novel.value_objects.novel_id import NovelId
from infrastructure.persistence.database.sqlite_chapter_repository import SqliteChapterRepository


def test_completed_revision_query_excludes_plans_and_detects_edits(tmp_path):
    connection=sqlite3.connect(tmp_path/'chapters.db')
    connection.row_factory=sqlite3.Row
    connection.execute('CREATE TABLE chapters(novel_id TEXT,number INTEGER,status TEXT,content TEXT,updated_at TEXT)')
    connection.executemany('INSERT INTO chapters VALUES(?,?,?,?,?)',[
        ('n',1,'completed','真实正文','r1'),('n',2,'draft','仍在修改','r2'),
        ('n',3,'completed','   ','r3'),('other',1,'completed','另一部小说','r4')])

    class ReadOnlyDatabase:
        def fetch_all(self,sql,params):
            return connection.execute(sql,params).fetchall()

    repo=SqliteChapterRepository(ReadOnlyDatabase())
    assert repo.completed_revisions(NovelId('n'))=={1:'r1:4'}
    connection.execute("UPDATE chapters SET content='修改正文',updated_at='r5' WHERE novel_id='n' AND number=1")
    assert repo.completed_revisions(NovelId('n'))=={1:'r5:4'}
    connection.close()
