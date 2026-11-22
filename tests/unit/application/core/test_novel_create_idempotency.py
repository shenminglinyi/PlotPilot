"""Unit and SQLite concurrency tests for idempotent NovelService.create_novel and POST /novels."""

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from application.ai_invocation.variable_hub import VariableWrite
from application.core.services.novel_service import NovelService
from domain.novel.entities.chapter import Chapter, ChapterStatus
from domain.novel.entities.novel import AutopilotStatus, Novel, NovelStage
from domain.novel.value_objects.novel_id import NovelId
from domain.shared.exceptions import EntityConflictError, InvalidOperationError
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_ai_invocation_repository import (
    SqliteVariableHubRepository,
)
from infrastructure.persistence.database.sqlite_chapter_repository import SqliteChapterRepository
from infrastructure.persistence.database.sqlite_novel_repository import SqliteNovelRepository
from interfaces.api.v1.core.novels import CreateNovelRequest, create_novel


def _build_sqlite_service(
    tmp_path: Path,
) -> tuple[Path, DatabaseConnection, SqliteNovelRepository, SqliteChapterRepository, NovelService]:
    db_file = tmp_path / "idempotent_novels.db"
    db = DatabaseConnection(str(db_file))
    novel_repo = SqliteNovelRepository(db)
    chapter_repo = SqliteChapterRepository(db)
    service = NovelService(novel_repo, chapter_repo)
    return db_file, db, novel_repo, chapter_repo, service


def _snapshot_persisted_novel_and_vars(
    db: DatabaseConnection,
    novel_id: str,
) -> tuple[dict[str, object] | None, list[dict[str, object]], list[dict[str, object]]]:
    conn = db.get_connection()
    novel_row = conn.execute(
        "SELECT * FROM novels WHERE id = ?",
        (novel_id,),
    ).fetchone()
    var_rows = conn.execute(
        """
        SELECT *
        FROM variable_values
        WHERE scope_key = ?
        ORDER BY variable_key, version_number, id
        """,
        (f"novel_id:{novel_id}",),
    ).fetchall()
    lineage_rows = conn.execute(
        """
        SELECT l.*
        FROM variable_lineage l
        JOIN variable_values v ON v.id = l.variable_value_id
        WHERE v.scope_key = ?
        ORDER BY l.variable_value_id, l.id
        """,
        (f"novel_id:{novel_id}",),
    ).fetchall()
    return (
        dict(novel_row) if novel_row is not None else None,
        [dict(r) for r in var_rows],
        [dict(r) for r in lineage_rows],
    )


def test_create_novel_idempotent_retry_preserves_runtime_audit_and_hydrates_chapters(
    tmp_path: Path,
) -> None:
    _, db, novel_repo, chapter_repo, service = _build_sqlite_service(tmp_path)
    try:
        first = service.create_novel(
            novel_id="novel-cold-001",
            title="夜雨寄北录",
            author="作者",
            target_chapters=0,
            premise="起笔意象与首章冲突",
            genre="悬疑 / 民俗诡事",
            world_preset="雨夜县志",
            story_structure="围绕选择推进冲突",
            pacing_control="舒展与冲突交替",
            writing_style="具体克制",
            special_requirements="保持知情边界一致",
            length_tier="standard",
        )
        assert first.id == "novel-cold-001"
        assert first.stage == "planning"

        # Simulate novel progressing into active writing/autopilot + audit columns + chapter 1
        novel_repo.patch(
            NovelId("novel-cold-001"),
            current_stage=NovelStage.WRITING,
            autopilot_status=AutopilotStatus.RUNNING,
            current_beat_index=3,
            last_audit_chapter_number=7,
            last_audit_drift_alert=True,
            last_audit_quality_scores={"pacing": 92, "coherence": 95},
            last_audit_issues=["minor cadence check"],
        )
        chapter_repo.save(
            Chapter(
                id="ch-cold-001-1",
                novel_id=NovelId("novel-cold-001"),
                number=1,
                title="第一章 雨夜叩门",
                content="青石阶上雨水横流，檐下铜铃无风自响。",
                status=ChapterStatus.COMPLETED,
                generation_hint="首章保持克制悬念",
            )
        )
        db.get_connection().commit()

        var_repo = SqliteVariableHubRepository(db)
        var_repo.set_value(
            VariableWrite(
                key="novel.writing_style",
                value="读者校准后的克制冷峻风",
                context_key="novel_id:novel-cold-001",
                source_trace_id="user_override",
                source_node_key="manual",
                value_type="string",
                display_name="写作风格",
                scope="global",
                stage="setup",
            )
        )

        # Delayed duplicate request with identical creation attributes arrives
        retried = service.create_novel(
            novel_id="novel-cold-001",
            title="夜雨寄北录",
            author="作者",
            target_chapters=0,
            premise="起笔意象与首章冲突",
            genre="悬疑 / 民俗诡事",
            world_preset="雨夜县志",
            story_structure="围绕选择推进冲突",
            pacing_control="舒展与冲突交替",
            writing_style="具体克制",
            special_requirements="保持知情边界一致",
            length_tier="standard",
        )

        assert retried.id == "novel-cold-001"
        assert retried.stage == "writing"
        assert retried.autopilot_status == "running"
        assert len(retried.chapters) == 1
        assert retried.chapters[0].id == "ch-cold-001-1"
        assert retried.chapters[0].title == "第一章 雨夜叩门"
        assert retried.total_word_count > 0

        reloaded = novel_repo.get_by_id(NovelId("novel-cold-001"))
        assert reloaded is not None
        assert reloaded.current_stage == NovelStage.WRITING
        assert reloaded.autopilot_status == AutopilotStatus.RUNNING
        assert reloaded.current_beat_index == 3
        assert reloaded.last_audit_chapter_number == 7
        assert reloaded.last_audit_drift_alert is True
        assert reloaded.last_audit_quality_scores == {"pacing": 92, "coherence": 95}
        assert reloaded.last_audit_issues == ["minor cadence check"]

        # Existing variable_hub customizations must not be overwritten by idempotent retry
        values = {
            item["variable_key"]: item["value"]
            for item in var_repo.list_current_values("novel_id:novel-cold-001")
        }
        assert values["novel.writing_style"] == "读者校准后的克制冷峻风"
    finally:
        db.close_all(skip_checkpoint=True)


def test_c6_01_retry_never_overwrites_customizations_when_variable_lookup_or_repair_fails(
    tmp_path: Path,
) -> None:
    _, db, novel_repo, _, service = _build_sqlite_service(tmp_path)
    try:
        service.create_novel(
            novel_id="novel-c6-01",
            title="断读护栏录",
            author="作者",
            target_chapters=80,
            premise="验证读异常绝不退化为覆盖写",
            genre="武侠 / 江湖暗线",
            world_preset="边城客栈",
            story_structure="创世默认三幕结构",
            pacing_control="初始节奏",
            writing_style="初始文风",
            special_requirements="创世默认特殊要求",
        )
        var_repo = SqliteVariableHubRepository(db)
        var_repo.set_value(
            VariableWrite(
                key="novel.writing_style",
                value="用户定制的古龙式短句风",
                context_key="novel_id:novel-c6-01",
                source_trace_id="custom_1",
                source_node_key="manual",
                value_type="string",
                display_name="写作风格",
                scope="global",
                stage="setup",
            )
        )
        # Also customize via setup alias key to verify candidate-alias preservation
        var_repo.set_value(
            VariableWrite(
                key="novel.setup.pacing_control",
                value="用户通过别名定制的快切节奏",
                context_key="novel_id:novel-c6-01",
                source_trace_id="custom_alias",
                source_node_key="manual",
                value_type="string",
                display_name="节奏把控",
                scope="global",
                stage="setup",
            )
        )
        # Simulate one missing setup key ("novel.world_preset") needing healing
        db.get_connection().execute(
            "DELETE FROM variable_values WHERE variable_key = 'novel.world_preset' AND scope_key = 'novel_id:novel-c6-01'"
        )
        db.get_connection().commit()

        # 1) Even if list_current_values fails completely, atomic insert-if-absent heals only missing
        #    keys and never overwrites customized canonical or alias keys.
        with patch.object(
            SqliteVariableHubRepository,
            "list_current_values",
            side_effect=RuntimeError("simulated variable_hub read outage"),
        ):
            retried = service.create_novel(
                novel_id="novel-c6-01",
                title="断读护栏录",
                author="作者",
                target_chapters=80,
                premise="验证读异常绝不退化为覆盖写",
                genre="武侠 / 江湖暗线",
                world_preset="边城客栈",
                story_structure="创世默认三幕结构",
                pacing_control="初始节奏",
                writing_style="初始文风",
                special_requirements="创世默认特殊要求",
            )
            assert retried.id == "novel-c6-01"

        resolved_style = var_repo.get_value("novel.writing_style", "novel_id:novel-c6-01")
        resolved_pacing = var_repo.get_value("novel.pacing_control", "novel_id:novel-c6-01")
        resolved_world = var_repo.get_value("novel.world_preset", "novel_id:novel-c6-01")
        assert resolved_style is not None and resolved_style.value == "用户定制的古龙式短句风"
        assert resolved_pacing is not None and resolved_pacing.value == "用户通过别名定制的快切节奏"
        assert resolved_world is not None and resolved_world.value == "边城客栈"

        # 2) Capture BOTH canonical and alias persisted state (value + version_number + raw rows)
        #    before repair failure, then verify both remain 100% unchanged after OperationalError.
        style_before_err = var_repo.get_value("novel.writing_style", "novel_id:novel-c6-01")
        pacing_before_err = var_repo.get_value("novel.pacing_control", "novel_id:novel-c6-01")
        alias_row_before_err = db.get_connection().execute(
            """
            SELECT variable_key, value_json, version_number, is_current, source_trace_id
            FROM variable_values
            WHERE scope_key = 'novel_id:novel-c6-01' AND variable_key = 'novel.setup.pacing_control' AND is_current = 1
            """
        ).fetchone()
        snapshot_before_err = _snapshot_persisted_novel_and_vars(db, "novel-c6-01")
        assert style_before_err is not None and pacing_before_err is not None
        assert alias_row_before_err is not None

        with patch.object(
            novel_repo,
            "init_setup_variables_if_absent",
            side_effect=sqlite3.OperationalError("simulated transient lock timeout"),
        ):
            with pytest.raises(sqlite3.OperationalError, match="simulated transient lock timeout"):
                service.create_novel(
                    novel_id="novel-c6-01",
                    title="断读护栏录",
                    author="作者",
                    target_chapters=80,
                    premise="验证读异常绝不退化为覆盖写",
                    genre="武侠 / 江湖暗线",
                    world_preset="边城客栈",
                    story_structure="创世默认三幕结构",
                    pacing_control="初始节奏",
                    writing_style="初始文风",
                    special_requirements="创世默认特殊要求",
                )

        after_error_style = var_repo.get_value("novel.writing_style", "novel_id:novel-c6-01")
        after_error_pacing = var_repo.get_value("novel.pacing_control", "novel_id:novel-c6-01")
        alias_row_after_err = db.get_connection().execute(
            """
            SELECT variable_key, value_json, version_number, is_current, source_trace_id
            FROM variable_values
            WHERE scope_key = 'novel_id:novel-c6-01' AND variable_key = 'novel.setup.pacing_control' AND is_current = 1
            """
        ).fetchone()
        assert after_error_style is not None
        assert after_error_style.value == "用户定制的古龙式短句风"
        assert after_error_style.version_number == style_before_err.version_number
        assert after_error_pacing is not None
        assert after_error_pacing.value == "用户通过别名定制的快切节奏"
        assert after_error_pacing.version_number == pacing_before_err.version_number
        assert alias_row_after_err == alias_row_before_err
        assert _snapshot_persisted_novel_and_vars(db, "novel-c6-01") == snapshot_before_err

        # 3) Also verify mid-transaction SQLite failure inside init_setup_variables_if_absent rolls
        #    back partial repair writes AND preserves both canonical and alias customizations.
        conn = db.get_connection()
        conn.execute(
            """
            DELETE FROM variable_values
            WHERE scope_key = 'novel_id:novel-c6-01'
              AND variable_key IN ('novel.story_structure', 'novel.special_requirements')
            """
        )
        conn.commit()
        snapshot_before_mid_tx = _snapshot_persisted_novel_and_vars(db, "novel-c6-01")
        conn.execute(
            """
            CREATE TEMP TRIGGER abort_on_second_repair_key
            BEFORE INSERT ON variable_values
            WHEN NEW.variable_key = 'novel.special_requirements'
            BEGIN
                SELECT RAISE(ABORT, 'simulated mid-tx value failure');
            END
            """
        )
        try:
            with pytest.raises(sqlite3.IntegrityError, match="simulated mid-tx value failure"):
                service.create_novel(
                    novel_id="novel-c6-01",
                    title="断读护栏录",
                    author="作者",
                    target_chapters=80,
                    premise="验证读异常绝不退化为覆盖写",
                    genre="武侠 / 江湖暗线",
                    world_preset="边城客栈",
                    story_structure="创世默认三幕结构",
                    pacing_control="初始节奏",
                    writing_style="初始文风",
                    special_requirements="创世默认特殊要求",
                )
        finally:
            conn.execute("DROP TRIGGER IF EXISTS abort_on_second_repair_key")
        assert conn.in_transaction is False
        assert var_repo.get_value("novel.story_structure", "novel_id:novel-c6-01") is None
        assert _snapshot_persisted_novel_and_vars(db, "novel-c6-01") == snapshot_before_mid_tx
    finally:
        db.close_all(skip_checkpoint=True)


def test_c6_02_delayed_creator_and_interleaved_retry_preserve_concurrent_customizations(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "c6_02_interleaving.db"
    db_main = DatabaseConnection(str(db_file))
    try:
        creator_inserted_event = threading.Event()
        resume_creator_event = threading.Event()
        creator_errors: list[BaseException] = []

        def _creator_a() -> None:
            db_a = DatabaseConnection(str(db_file))
            try:
                repo_a = SqliteNovelRepository(db_a)
                svc_a = NovelService(repo_a, SqliteChapterRepository(db_a))
                orig_create = repo_a.create_if_absent

                def _paused_create_if_absent(novel: Novel) -> tuple[Novel, bool]:
                    res = orig_create(novel)
                    creator_inserted_event.set()
                    assert resume_creator_event.wait(timeout=10.0)
                    return res

                with patch.object(repo_a, "create_if_absent", side_effect=_paused_create_if_absent):
                    svc_a.create_novel(
                        novel_id="novel-c6-02",
                        title="并发交错录",
                        author="作者",
                        target_chapters=100,
                        premise="原请求在建表后暂停，重试与用户定制先行完成",
                        genre="科幻 / 深空遗迹",
                        world_preset="奥尔特云哨站",
                        story_structure="创世默认三幕结构",
                        writing_style="创世默认文风",
                    )
            except BaseException as exc:  # pragma: no cover - captured for assertion
                creator_errors.append(exc)
            finally:
                db_a.close_all(skip_checkpoint=True)

        thread_a = threading.Thread(target=_creator_a, daemon=True)
        thread_a.start()
        assert creator_inserted_event.wait(timeout=10.0)

        # While Creator A is paused before variable-hub init, Retry B completes initialization
        # and the user customizes writing_style AND world_preset.
        repo_b = SqliteNovelRepository(db_main)
        svc_b = NovelService(repo_b, SqliteChapterRepository(db_main))
        dto_b = svc_b.create_novel(
            novel_id="novel-c6-02",
            title="并发交错录",
            author="作者",
            target_chapters=100,
            premise="原请求在建表后暂停，重试与用户定制先行完成",
            genre="科幻 / 深空遗迹",
            world_preset="奥尔特云哨站",
            story_structure="创世默认三幕结构",
            writing_style="创世默认文风",
        )
        assert dto_b.id == "novel-c6-02"

        var_repo = SqliteVariableHubRepository(db_main)
        var_repo.set_value(
            VariableWrite(
                key="novel.writing_style",
                value="重试成功后用户精修的硬核冷峻文风",
                context_key="novel_id:novel-c6-02",
                source_trace_id="user_custom_after_retry",
                source_node_key="manual",
                value_type="string",
                display_name="写作风格",
                scope="global",
                stage="setup",
            )
        )

        # Now let Creator A resume its delayed variable-hub initialization
        resume_creator_event.set()
        thread_a.join(timeout=10.0)
        assert not thread_a.is_alive()
        assert creator_errors == []

        # Creator A must NOT overwrite the user's customization
        preserved = var_repo.get_value("novel.writing_style", "novel_id:novel-c6-02")
        assert preserved is not None
        assert preserved.value == "重试成功后用户精修的硬核冷峻文风"
        assert preserved.version_number == 2

        # Also verify repair interleaving when TWO keys ('novel.genre_label' and
        # 'novel.story_structure') were absent, and a concurrent user customization writes to
        # 'novel.genre_label' (the SAME missing key targeted for repair!) right before the real
        # initializer runs: the user's customization on 'novel.genre_label' MUST win without a
        # replacement version, while 'novel.story_structure' is still legitimately repaired.
        db_main.get_connection().execute(
            """
            DELETE FROM variable_values
            WHERE scope_key = 'novel_id:novel-c6-02'
              AND variable_key IN ('novel.genre_label', 'novel.story_structure')
            """
        )
        db_main.get_connection().commit()

        orig_init = repo_b.init_setup_variables_if_absent

        def _interleaved_init(novel_id: str, entries):
            var_repo.set_value(
                VariableWrite(
                    key="novel.genre_label",
                    value="抢在修复落盘前由用户写入的太空歌剧",
                    context_key=f"novel_id:{novel_id}",
                    source_trace_id="interleaved_missing_key_custom",
                    source_node_key="manual",
                    value_type="string",
                    display_name="题材标签",
                    scope="global",
                    stage="setup",
                )
            )
            var_repo.set_value(
                VariableWrite(
                    key="novel.world_preset",
                    value="抢在修复落盘前写入的木卫二冰海",
                    context_key=f"novel_id:{novel_id}",
                    source_trace_id="interleaved_custom",
                    source_node_key="manual",
                    value_type="string",
                    display_name="世界基调",
                    scope="global",
                    stage="setup",
                )
            )
            return orig_init(novel_id, entries)

        with patch.object(repo_b, "init_setup_variables_if_absent", side_effect=_interleaved_init):
            svc_b.create_novel(
                novel_id="novel-c6-02",
                title="并发交错录",
                author="作者",
                target_chapters=100,
                premise="原请求在建表后暂停，重试与用户定制先行完成",
                genre="科幻 / 深空遗迹",
                world_preset="奥尔特云哨站",
                story_structure="创世默认三幕结构",
                writing_style="创世默认文风",
            )

        healed_genre = var_repo.get_value("novel.genre_label", "novel_id:novel-c6-02")
        healed_structure = var_repo.get_value("novel.story_structure", "novel_id:novel-c6-02")
        interleaved_world = var_repo.get_value("novel.world_preset", "novel_id:novel-c6-02")
        genre_rows = db_main.get_connection().execute(
            """
            SELECT version_number, is_current, source_trace_id
            FROM variable_values
            WHERE scope_key = 'novel_id:novel-c6-02' AND variable_key = 'novel.genre_label'
            """
        ).fetchall()
        assert healed_genre is not None and healed_genre.value == "抢在修复落盘前由用户写入的太空歌剧"
        assert healed_genre.version_number == 1
        assert [tuple(r) for r in genre_rows] == [(1, 1, "interleaved_missing_key_custom")]
        assert healed_structure is not None and healed_structure.value == "创世默认三幕结构"
        assert interleaved_world is not None and interleaved_world.value == "抢在修复落盘前写入的木卫二冰海"
    finally:
        db_main.close_all(skip_checkpoint=True)


def test_c6_03_rejects_active_outer_transaction_and_guarantees_independent_reader_visibility(
    tmp_path: Path,
) -> None:
    db_file, db, novel_repo, _, service = _build_sqlite_service(tmp_path)
    try:
        conn = db.get_connection()
        conn.execute("BEGIN")
        conn.execute(
            """
            INSERT INTO novels (id, title, slug, author, target_chapters, premise)
            VALUES ('outer-uncommitted', '外层未提交事务', 'outer-uncommitted', '作者', 10, '')
            """
        )
        assert conn.in_transaction is True

        # Must reject active outer transaction rather than silently releasing a savepoint
        # (which would violate immediate visibility) or committing unrelated outer work.
        with pytest.raises(InvalidOperationError, match="top-level transaction ownership"):
            service.create_novel(
                novel_id="novel-inside-outer-tx",
                title="不应伪报成功",
                author="作者",
                target_chapters=50,
                premise="处于外层未提交事务中",
            )

        # Unrelated outer transaction is still uncommitted; independent reader sees neither row
        assert conn.in_transaction is True
        with sqlite3.connect(str(db_file)) as ext_conn:
            ext_rows = ext_conn.execute("SELECT id FROM novels").fetchall()
            assert ext_rows == []

        conn.rollback()
        assert novel_repo.list_all() == []

        # Also verify init_setup_variables_if_absent enforces top-level transaction ownership
        # WITHOUT rolling back or committing caller-owned uncommitted sentinel work.
        conn.execute("BEGIN")
        conn.execute(
            """
            INSERT INTO novels (id, title, slug, author, target_chapters, premise)
            VALUES ('outer-sentinel-init', '初始化守卫外层哨兵', 'outer-sentinel-init', '作者', 12, '未提交哨兵')
            """
        )
        assert conn.in_transaction is True
        with pytest.raises(InvalidOperationError, match="top-level transaction ownership"):
            novel_repo.init_setup_variables_if_absent(
                "any-novel",
                [("novel.title", "书名", "string", "书名")],
            )
        assert conn.in_transaction is True
        sentinel_row = conn.execute(
            "SELECT id, title FROM novels WHERE id = 'outer-sentinel-init'"
        ).fetchone()
        assert sentinel_row is not None and tuple(sentinel_row) == (
            "outer-sentinel-init",
            "初始化守卫外层哨兵",
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM variable_values WHERE scope_key = 'novel_id:any-novel'"
            ).fetchone()[0]
            == 0
        )
        with sqlite3.connect(str(db_file)) as ext_conn:
            assert ext_conn.execute("SELECT id FROM novels").fetchall() == []
        conn.rollback()
        assert conn.in_transaction is False
        assert (
            conn.execute("SELECT id FROM novels WHERE id = 'outer-sentinel-init'").fetchall() == []
        )

        # Now verify standalone creation with direct_writes=False is durably committed and
        # immediately visible to a brand-new independent sqlite3 connection.
        with patch(
            "infrastructure.persistence.database.write_environment.SQLiteWriteEnvironmentSettings.from_env"
        ) as mock_env:
            mock_env.return_value.direct_writes = False
            created = service.create_novel(
                novel_id="novel-sync-visibility-001",
                title="立即可读",
                author="作者",
                target_chapters=60,
                premise="无需等待后台持久化队列即可立刻被独立连接读取",
                genre="奇幻 / 史诗",
            )
            assert created.id == "novel-sync-visibility-001"

        with sqlite3.connect(str(db_file)) as ext_conn:
            novel_row = ext_conn.execute(
                "SELECT id, title FROM novels WHERE id = ?",
                ("novel-sync-visibility-001",),
            ).fetchone()
            assert novel_row == ("novel-sync-visibility-001", "立即可读")
            var_count = ext_conn.execute(
                "SELECT COUNT(*) FROM variable_values WHERE scope_key = ? AND is_current = 1",
                ("novel_id:novel-sync-visibility-001",),
            ).fetchone()[0]
            assert var_count >= 5
    finally:
        db.close_all(skip_checkpoint=True)


def test_create_novel_rejects_conflicting_attributes_and_distinct_id_slug_collision_with_409(
    tmp_path: Path,
) -> None:
    _, db, novel_repo, _, service = _build_sqlite_service(tmp_path)
    try:
        service.create_novel(
            novel_id="novel-conflict-001",
            title="原始书名",
            author="作者甲",
            target_chapters=120,
            premise="原始梗概",
            genre="仙侠",
        )
        novel_repo.patch(
            NovelId("novel-conflict-001"),
            current_stage=NovelStage.WRITING,
            autopilot_status=AutopilotStatus.RUNNING,
            current_beat_index=4,
            last_audit_chapter_number=6,
            last_audit_drift_alert=True,
            last_audit_quality_scores={"pacing": 91},
            last_audit_issues=["preserve audit on conflict"],
        )
        conn = db.get_connection()
        conn.execute(
            """
            UPDATE novels
            SET auto_approve_mode = 'auto',
                current_act = 2,
                current_chapter_in_act = 5,
                current_auto_chapters = 9,
                beats_completed = 3,
                generation_prefs_json = '{"temperature":0.7}',
                updated_at = '2026-11-14T00:00:00'
            WHERE id = 'novel-conflict-001'
            """
        )
        conn.commit()
        before_conflict = _snapshot_persisted_novel_and_vars(db, "novel-conflict-001")
        assert before_conflict[0] is not None
        assert len(before_conflict[0]) >= 18

        with pytest.raises(EntityConflictError):
            service.create_novel(
                novel_id="novel-conflict-001",
                title="碰撞的新书名",
                author="作者甲",
                target_chapters=120,
                premise="完全不同的梗概",
                genre="都市异能",
            )

        assert _snapshot_persisted_novel_and_vars(db, "novel-conflict-001") == before_conflict
        reloaded = novel_repo.get_by_id(NovelId("novel-conflict-001"))
        assert reloaded is not None
        assert reloaded.title == "原始书名"
        assert reloaded.premise == "原始梗概"

        # Distinct-ID slug collision: existing row owns slug 'slug-claimed-001' under a different id
        conn.execute(
            """
            INSERT INTO novels (
                id, title, slug, author, target_chapters, premise,
                current_stage, autopilot_status, auto_approve_mode, current_act,
                current_beat_index, last_audit_chapter_number, generation_prefs_json, updated_at
            )
            VALUES (
                'legacy-owner-id', '既有书目', 'slug-claimed-001', '既有作者', 80, '既有梗概',
                'writing', 'running', 'auto', 3, 5, 11, '{"pov":"third"}', '2026-11-14T01:00:00'
            )
            """
        )
        conn.commit()
        var_repo = SqliteVariableHubRepository(db)
        var_repo.set_value(
            VariableWrite(
                key="novel.genre_label",
                value="既有门派志",
                context_key="novel_id:legacy-owner-id",
                source_trace_id="owner_seed",
                source_node_key="manual",
                value_type="string",
                display_name="题材标签",
                scope="global",
                stage="setup",
            )
        )
        before_slug_owner = _snapshot_persisted_novel_and_vars(db, "legacy-owner-id")

        with pytest.raises(EntityConflictError):
            service.create_novel(
                novel_id="slug-claimed-001",
                title="既有书目",
                author="既有作者",
                target_chapters=80,
                premise="既有梗概",
                genre="企图污染的变量",
            )

        assert _snapshot_persisted_novel_and_vars(db, "legacy-owner-id") == before_slug_owner
        assert _snapshot_persisted_novel_and_vars(db, "slug-claimed-001") == (None, [], [])
        slug_owner = novel_repo.get_by_id(NovelId("legacy-owner-id"))
        assert slug_owner is not None
        assert slug_owner.title == "既有书目"
        assert novel_repo.get_by_id(NovelId("slug-claimed-001")) is None
    finally:
        db.close_all(skip_checkpoint=True)


@pytest.mark.asyncio
async def test_post_novels_route_maps_conflict_to_http_409_and_allows_idempotent_retry(
    tmp_path: Path,
) -> None:
    _, db, novel_repo, _, service = _build_sqlite_service(tmp_path)
    try:
        req = CreateNovelRequest(
            novel_id="novel-route-001",
            title="卷一",
            author="作者",
            target_chapters=0,
            premise="首章引子",
            genre="奇幻",
            world_preset="高塔纪元",
            length_tier="standard",
        )
        dto_a = await create_novel(req, service=service)
        dto_b = await create_novel(req, service=service)
        assert dto_a.id == "novel-route-001"
        assert dto_b.id == "novel-route-001"

        novel_repo.patch(
            NovelId("novel-route-001"),
            current_stage=NovelStage.WRITING,
            autopilot_status=AutopilotStatus.RUNNING,
            current_beat_index=2,
            last_audit_chapter_number=5,
            last_audit_drift_alert=True,
            last_audit_quality_scores={"coherence": 94},
            last_audit_issues=["keep route 409 untouched"],
        )
        conn = db.get_connection()
        conn.execute(
            """
            UPDATE novels
            SET auto_approve_mode = 'auto',
                current_act = 2,
                generation_prefs_json = '{"cadence":"steady"}',
                updated_at = '2026-11-14T02:00:00'
            WHERE id = 'novel-route-001'
            """
        )
        conn.commit()
        before_route_conflict = _snapshot_persisted_novel_and_vars(db, "novel-route-001")
        assert before_route_conflict[0] is not None
        assert len(before_route_conflict[0]) >= 18

        conflicting_req = CreateNovelRequest(
            novel_id="novel-route-001",
            title="卷一",
            author="作者",
            target_chapters=0,
            premise="首章引子",
            genre="完全不同的赛道",
            world_preset="赛博荒原",
            length_tier="standard",
        )
        with pytest.raises(HTTPException) as exc_info:
            await create_novel(conflicting_req, service=service)
        assert exc_info.value.status_code == 409
        assert _snapshot_persisted_novel_and_vars(db, "novel-route-001") == before_route_conflict
        var_repo = SqliteVariableHubRepository(db)
        genre_val = var_repo.get_value("novel.genre_label", "novel_id:novel-route-001")
        assert genre_val is not None and genre_val.value == "奇幻" and genre_val.version_number == 1
    finally:
        db.close_all(skip_checkpoint=True)


def test_create_novel_concurrent_threads_same_id_produce_single_consistent_row(
    tmp_path: Path,
) -> None:
    db_file, db, novel_repo, _, _ = _build_sqlite_service(tmp_path)
    try:
        start_barrier = threading.Barrier(6)

        def _worker(idx: int) -> str:
            worker_db = DatabaseConnection(str(db_file))
            try:
                worker_service = NovelService(
                    SqliteNovelRepository(worker_db),
                    SqliteChapterRepository(worker_db),
                )
                if idx < 6:
                    start_barrier.wait(timeout=10.0)
                dto = worker_service.create_novel(
                    novel_id="novel-race-001",
                    title="并发立卷压测",
                    author="作者",
                    target_chapters=0,
                    premise="多线程同时提交同一恢复载荷",
                    genre="历史 / 架空",
                    length_tier="standard",
                )
                return dto.id
            finally:
                worker_db.close_all(skip_checkpoint=True)

        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(_worker, range(12)))

        assert results == ["novel-race-001"] * 12
        all_novels = novel_repo.list_all()
        assert len(all_novels) == 1
        assert all_novels[0].novel_id.value == "novel-race-001"
        conn = db.get_connection()
        dup_versions = conn.execute(
            """
            SELECT variable_key, COUNT(*), MAX(version_number)
            FROM variable_values
            WHERE scope_key = 'novel_id:novel-race-001'
            GROUP BY variable_key
            """
        ).fetchall()
        assert len(dup_versions) >= 5
        assert all(count == 1 and max_ver == 1 for _, count, max_ver in dup_versions)
        lineage_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM variable_lineage l
            JOIN variable_values v ON v.id = l.variable_value_id
            WHERE v.scope_key = 'novel_id:novel-race-001'
            """
        ).fetchone()[0]
        assert lineage_count == len(dup_versions)
    finally:
        db.close_all(skip_checkpoint=True)
