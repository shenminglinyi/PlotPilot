import sqlite3
from infrastructure.persistence.database.sqlite_confluence_point_repository import SqliteConfluencePointRepository
from domain.novel.entities.confluence_point import ConfluencePoint


def _make_repo():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    class _DB:
        def get_connection(self): return conn
        def fetch_one(self, sql, params=()):
            cur = conn.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None
        def fetch_all(self, sql, params=()):
            cur = conn.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    return SqliteConfluencePointRepository(_DB())


def _cp(id="cp-1", target_chapter=38, merge_type="absorb", **kw):
    defaults = dict(
        novel_id="novel-1",
        source_storyline_id="sl-sub",
        target_storyline_id="sl-main",
        context_summary="苏蔓汇流",
        pre_reveal_hint="",
        behavior_guards=[],
    )
    defaults.update(kw)
    return ConfluencePoint(id=id, target_chapter=target_chapter, merge_type=merge_type, **defaults)


def test_save_and_get_by_id():
    repo = _make_repo()
    repo.save(_cp())
    loaded = repo.get_by_id("cp-1")
    assert loaded is not None
    assert loaded.target_chapter == 38
    assert loaded.merge_type == "absorb"
    assert loaded.resolved is False


def test_get_by_novel_id_ordered_by_chapter():
    repo = _make_repo()
    repo.save(_cp("cp-2", target_chapter=62))
    repo.save(_cp("cp-1", target_chapter=38))
    results = repo.get_by_novel_id("novel-1")
    assert results[0].target_chapter == 38
    assert results[1].target_chapter == 62


def test_behavior_guards_roundtrip():
    repo = _make_repo()
    guards = ["禁止让林警官怀疑顾言之", "禁止提及幕后人存在"]
    repo.save(_cp("cp-r", merge_type="reveal", behavior_guards=guards))
    loaded = repo.get_by_id("cp-r")
    assert loaded.behavior_guards == guards


def test_resolved_flag():
    repo = _make_repo()
    cp = _cp()
    cp.resolved = True
    repo.save(cp)
    loaded = repo.get_by_id("cp-1")
    assert loaded.resolved is True


def test_delete():
    repo = _make_repo()
    repo.save(_cp())
    repo.delete("cp-1")
    assert repo.get_by_id("cp-1") is None
