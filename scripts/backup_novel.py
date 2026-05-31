#!/usr/bin/env python3
"""
备份小说脚本：将源小说的引导状态（世界观、结构、大纲、人物等）复制到新小说，
清空所有已生成的正文内容，重置为规划阶段，以便重新生成。

用法：
    python scripts/backup_novel.py <source_novel_id> [target_novel_id]

示例：
    python scripts/backup_novel.py novel-1779868467739
    python scripts/backup_novel.py novel-1779868467739 novel-1799999999999
"""

import argparse
import itertools
import sqlite3
import sys
import time
from pathlib import Path

# =============================================================================
# 分类规则：
#   KEEP（保留）= 规划/引导数据：世界观、角色、大纲、节拍、伏笔、知识图谱等
#   DISCARD（丢弃）= 已生成内容 & 运行时状态：AI 评审、风格评分、三元组、
#                    叙事事件、进化快照、分支/检查点、DAG 版本等
# =============================================================================

# ✅ 保留：通过 novel_id 直接关联的规划表
PLANNING_TABLES_WITH_NOVEL_ID = [
    # 世界观 / Bible
    "bibles",
    "bible_characters",
    "bible_world_settings",
    "bible_locations",
    "bible_timeline_notes",
    "bible_style_notes",

    # 角色系统
    "unified_characters",
    "story_characters",
    "character_states",

    # 道具
    "unified_props",

    # 世界构建
    "worldbuilding",

    # 大纲 / 结构
    "storylines",
    "canonical_storylines",
    "plot_arcs",

    # 伏笔
    "foreshadows",
    "novel_foreshadow_registry",
    "narrative_contracts",
    "narrative_debts",

    # 实体 / 声音
    "entity_base",
    "voice_fingerprint",

    # 时间线
    "timeline_registries",
]

# ❌ 明确丢弃：AI 生成内容 & 运行时状态（仅作记录，实际通过不复制来实现）
DISCARD_TABLES = [
    # AI 分析
    "chapter_reviews",
    "chapter_style_scores",
    "narrative_events",
    "voice_vault",

    # 知识三元组 (AI 提取)
    "triples",
    "triple_tags",
    "triple_attr",
    "triple_more_chapters",
    "triple_provenance",

    # 运行时状态
    "novel_snapshots",
    "novel_checkpoints",
    "novel_branches",
    "dag_versions",
    "checkpoint_heads",
    "checkpoints",
    "novel_autopilot_states",
    "novel_audit_snapshots",

    # 章节演化跟踪
    "chapter_evolution_snapshots",
    "chapter_evolution_action_log",
    "chapter_evolution_conflicts",
    "chapter_guardrail_snapshots",
    "chapter_drafts",
    "chapter_bridges",
    "chapter_entity_mentions",
    "chapter_voice_samples",

    # 叙事跟踪
    "causal_edges",
    "confluence_points",
    "narrative_entities",
    "prop_chapter_snapshots",
    "prop_events",

    # 记忆系统
    "memory_atoms",
    "memory_atom_links",
    "memory_engine_state",
    "memory_projections",
    "memory_calibration_actions",

    # 治理 / 审计
    "governance_events",
    "governance_reports",
    "anti_ai_audits",
    "macro_diagnosis_results",
    "reader_simulations",

    # 引擎 / 调试
    "engine_traces",
    "prompt_debug_logs",

    # 系统
    "persistence_queue",
    "embedding_config",
    "llm_config_meta",
    "llm_profiles",
    "prompt_bindings",
    "prompt_nodes",
    "prompt_templates",
    "prompt_versions",
    "prompt_workflows",
    "migrations_applied",
]


def get_db_path() -> Path:
    """获取数据库文件路径"""
    root = Path(__file__).resolve().parent.parent
    data_dir = root / "data"
    primary = data_dir / "plotpilot.db"
    legacy = data_dir / "aitext.db"
    if primary.is_file():
        return primary
    if legacy.is_file():
        return legacy
    return primary


def generate_novel_id() -> str:
    """生成新的 novel ID"""
    return f"novel-{int(time.time() * 1000)}"


def _uid(prefix: str, counter: int) -> str:
    """生成唯一 ID"""
    return f"{prefix}-{int(time.time() * 1000)}-{counter}"


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table_name,),
    )
    return cur.fetchone() is not None


def get_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    cur = conn.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cur.fetchall()}


def _delete_novel_cascade(conn: sqlite3.Connection, novel_id: str) -> None:
    """删除目标小说所有残留数据"""
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("DELETE FROM novels WHERE id = ?", (novel_id,))
    conn.execute("PRAGMA foreign_keys = OFF")


# =============================================================================
# 核心复制函数
# =============================================================================

def copy_table_simple(
    conn: sqlite3.Connection,
    table_name: str,
    old_novel_id: str,
    new_novel_id: str,
    id_counter: itertools.count,
    clear_columns: dict[str, object] | None = None,
    id_map: dict[str, str] | None = None,
) -> tuple[int, dict[str, str]]:
    """复制仅通过 novel_id 关联的表，返回 (行数, {旧id: 新id})"""
    empty_map: dict[str, str] = {}
    if not table_exists(conn, table_name):
        return 0, empty_map

    columns = get_table_columns(conn, table_name)
    if "novel_id" not in columns:
        return 0, empty_map

    rows = conn.execute(
        f"SELECT * FROM {table_name} WHERE novel_id = ?", (old_novel_id,)
    ).fetchall()
    if not rows:
        return 0, empty_map

    col_names = [desc[0] for desc in conn.execute(f"SELECT * FROM {table_name} LIMIT 0").description]
    has_id_col = "id" in columns
    inserted = 0
    local_map: dict[str, str] = {}

    for row in rows:
        row_dict = dict(zip(col_names, row))
        old_id = row_dict.get("id")
        row_dict["novel_id"] = new_novel_id
        if has_id_col:
            new_id = _uid(table_name[:8], next(id_counter))
            row_dict["id"] = new_id
            if old_id and id_map is not None:
                local_map[old_id] = new_id

        if clear_columns:
            for col, val in clear_columns.items():
                if col in row_dict:
                    row_dict[col] = val

        placeholders = ", ".join("?" for _ in col_names)
        values = [row_dict[c] for c in col_names]
        conn.execute(
            f"INSERT OR IGNORE INTO {table_name} ({', '.join(col_names)}) VALUES ({placeholders})",
            values,
        )
        inserted += 1

    if id_map is not None:
        id_map.update(local_map)
    return inserted, local_map


def copy_novel_record(
    conn: sqlite3.Connection,
    old_novel_id: str,
    new_novel_id: str,
) -> bool:
    """复制 novel 记录并重置为规划阶段"""
    row = conn.execute("SELECT * FROM novels WHERE id = ?", (old_novel_id,)).fetchone()
    if not row:
        return False

    col_names = [desc[0] for desc in conn.execute("SELECT * FROM novels LIMIT 0").description]
    row_dict = dict(zip(col_names, row))
    row_dict["id"] = new_novel_id
    row_dict["slug"] = new_novel_id

    # 重置为规划阶段
    row_dict["autopilot_status"] = "stopped"
    row_dict["auto_approve_mode"] = 0
    row_dict["current_stage"] = "planning"
    row_dict["current_act"] = 0
    row_dict["current_chapter_in_act"] = 0
    row_dict["current_auto_chapters"] = 0
    row_dict["last_chapter_tension"] = 0
    row_dict["consecutive_error_count"] = 0
    row_dict["current_beat_index"] = 0
    row_dict["beats_completed"] = 0

    # 重置审计状态
    for col in (
        "last_audit_chapter_number", "last_audit_similarity", "last_audit_at",
        "last_audit_quality_scores", "last_audit_issues", "audit_progress",
    ):
        if col in row_dict:
            row_dict[col] = None
    for col in (
        "last_audit_drift_alert", "last_audit_narrative_ok",
        "last_audit_vector_stored", "last_audit_foreshadow_stored",
        "last_audit_triples_extracted",
    ):
        if col in row_dict:
            row_dict[col] = 0

    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    row_dict["created_at"] = now
    row_dict["updated_at"] = now

    placeholders = ", ".join("?" for _ in col_names)
    values = [row_dict.get(c) for c in col_names]
    conn.execute(
        f"INSERT INTO novels ({', '.join(col_names)}) VALUES ({placeholders})",
        values,
    )
    return True


def copy_story_nodes(
    conn: sqlite3.Connection,
    old_novel_id: str,
    new_novel_id: str,
    id_counter: itertools.count,
) -> tuple[dict[str, str], dict[int, str]]:
    """复制故事节点结构，清空正文。

    返回 (old_id→new_id 全量映射, chapter_number→new_id 映射)。
    """
    if not table_exists(conn, "story_nodes"):
        return {}, {}

    rows = conn.execute(
        "SELECT * FROM story_nodes WHERE novel_id = ? ORDER BY order_index",
        (old_novel_id,),
    ).fetchall()
    if not rows:
        return {}, {}

    col_names = [desc[0] for desc in conn.execute("SELECT * FROM story_nodes LIMIT 0").description]
    id_map: dict[str, str] = {}
    chapter_number_to_new_id: dict[int, str] = {}

    for row in rows:
        row_dict = dict(zip(col_names, row))
        old_id = row_dict["id"]
        new_id = _uid("node", next(id_counter))
        is_chapter = row_dict.get("node_type") == "chapter"

        row_dict["id"] = new_id
        row_dict["novel_id"] = new_novel_id
        row_dict["content"] = ""
        if "word_count" in row_dict:
            row_dict["word_count"] = 0

        placeholders = ", ".join("?" for _ in col_names)
        conn.execute(
            f"INSERT INTO story_nodes ({', '.join(col_names)}) VALUES ({placeholders})",
            [row_dict[c] for c in col_names],
        )
        id_map[old_id] = new_id

        if is_chapter:
            try:
                cn = int(row_dict["number"])
                chapter_number_to_new_id[cn] = new_id
            except (TypeError, ValueError):
                pass

    # 更新 parent_id 引用
    for old_id, new_id in id_map.items():
        conn.execute(
            "UPDATE story_nodes SET parent_id = ? WHERE parent_id = ? AND novel_id = ?",
            (new_id, old_id, new_novel_id),
        )

    return id_map, chapter_number_to_new_id


def copy_chapters(
    conn: sqlite3.Connection,
    old_novel_id: str,
    new_novel_id: str,
    id_counter: itertools.count,
    chapter_number_to_node_id: dict[int, str] | None = None,
) -> dict[str, str]:
    """复制章节正文行，清空正文/重置状态。

    chapter_number_to_node_id: 章节号 → story_nodes 新 ID 映射。
    传入时，chapters.id 会复用对应 story_node 的 ID，保证应用层
    ChapterId(node.id) 能正确找到正文行。
    """
    if not table_exists(conn, "chapters"):
        return {}

    rows = conn.execute(
        "SELECT * FROM chapters WHERE novel_id = ? ORDER BY number", (old_novel_id,)
    ).fetchall()
    if not rows:
        return {}

    col_names = [desc[0] for desc in conn.execute("SELECT * FROM chapters LIMIT 0").description]
    id_map: dict[str, str] = {}
    node_id_map = chapter_number_to_node_id or {}

    for row in rows:
        row_dict = dict(zip(col_names, row))
        old_id = row_dict["id"]

        # 复用对应 story_node 的 ID，保证 ChapterId(node.id) 一致性
        try:
            cn = int(row_dict["number"])
        except (TypeError, ValueError):
            cn = None

        matched_node_id = node_id_map.get(cn) if cn is not None else None
        if matched_node_id:
            new_id = matched_node_id
        else:
            new_id = _uid("chapter", next(id_counter))

        row_dict["id"] = new_id
        row_dict["novel_id"] = new_novel_id
        row_dict["content"] = ""
        row_dict["status"] = "draft"
        if "word_count" in row_dict:
            row_dict["word_count"] = 0
        if "tension_score" in row_dict:
            row_dict["tension_score"] = 50.0
        if "plot_tension" in col_names:
            row_dict["plot_tension"] = 50.0
        if "emotional_tension" in col_names:
            row_dict["emotional_tension"] = 50.0
        if "pacing_tension" in col_names:
            row_dict["pacing_tension"] = 50.0

        placeholders = ", ".join("?" for _ in col_names)
        conn.execute(
            f"INSERT INTO chapters ({', '.join(col_names)}) VALUES ({placeholders})",
            [row_dict[c] for c in col_names],
        )
        id_map[old_id] = new_id

    return id_map


def copy_relation_tables(
    conn: sqlite3.Connection,
    old_novel_id: str,
    new_novel_id: str,
    id_counter: itertools.count,
    id_maps: dict[str, dict[str, str]],
) -> None:
    """复制通过父表间接关联 novel_id 的关系表（自身无 novel_id 列）。

    通过 JOIN 父表来定位源数据，再利用 id_maps 中的新旧 ID 映射来关联新记录。
    """
    relation_configs = [
        # (表名, 自身 ID 列, 外键列, 父表, 父表 ID 列, ID 前缀, 额外外键列映射)
        {
            "table": "bible_character_relationships",
            "id_col": "id",
            "fk_col": "character_id",
            "parent_table": "bible_characters",
            "parent_id_col": "id",
            "prefix": "bcr",
            "extra_cols": None,
        },
        {
            "table": "unified_character_relationships",
            "id_col": "id",
            "fk_col": "character_id",
            "parent_table": "unified_characters",
            "parent_id_col": "id",
            "prefix": "ucr",
            "extra_cols": {"target_id": "unified_characters"},
        },
        {
            "table": "storyline_milestones",
            "id_col": "id",
            "fk_col": "storyline_id",
            "parent_table": "storylines",
            "parent_id_col": "id",
            "prefix": "slm",
            "extra_cols": None,
        },
        {
            "table": "plot_points",
            "id_col": "id",
            "fk_col": "plot_arc_id",
            "parent_table": "plot_arcs",
            "parent_id_col": "id",
            "prefix": "pp",
            "extra_cols": None,
        },
    ]

    for cfg in relation_configs:
        table = cfg["table"]
        if not table_exists(conn, table):
            continue

        parent_table = cfg["parent_table"]
        if not table_exists(conn, parent_table):
            continue

        fk_col = cfg["fk_col"]
        parent_id_col = cfg["parent_id_col"]

        # JOIN 父表来定位属于旧小说的行
        rows = conn.execute(
            f"SELECT r.* FROM {table} r "
            f"JOIN {parent_table} p ON r.{fk_col} = p.{parent_id_col} "
            "WHERE p.novel_id = ?",
            (old_novel_id,),
        ).fetchall()
        if not rows:
            continue

        col_names = [desc[0] for desc in conn.execute(f"SELECT * FROM {table} LIMIT 0").description]
        id_col = cfg["id_col"]
        id_map = id_maps.get(parent_table, {})
        inserted = 0

        for row in rows:
            row_dict = dict(zip(col_names, row))
            old_fk = row_dict[fk_col]
            new_fk = id_map.get(old_fk)
            if new_fk is None:
                continue

            row_dict[fk_col] = new_fk

            # 处理额外外键列映射
            extra_cols = cfg.get("extra_cols") or {}
            for extra_col, extra_parent_table in extra_cols.items():
                if extra_col in row_dict and row_dict[extra_col]:
                    extra_map = id_maps.get(extra_parent_table, {})
                    mapped = extra_map.get(row_dict[extra_col])
                    if mapped:
                        row_dict[extra_col] = mapped

            if id_col in col_names:
                row_dict[id_col] = _uid(cfg["prefix"], next(id_counter))

            placeholders = ", ".join("?" for _ in col_names)
            conn.execute(
                f"INSERT OR IGNORE INTO {table} ({', '.join(col_names)}) VALUES ({placeholders})",
                [row_dict[c] for c in col_names],
            )
            inserted += 1

        if inserted > 0:
            print(f"  {table}: 已复制 {inserted} 条 (通过 {parent_table} JOIN)")


def copy_chapter_scoped_tables(
    conn: sqlite3.Connection,
    old_novel_id: str,
    new_novel_id: str,
    chapter_id_map: dict[str, str],
    story_node_id_map: dict[str, str],
    id_counter: itertools.count,
) -> None:
    """复制通过 chapter_id 关联的表（节拍表、章节元素、章节场景）"""

    # beat_sheets → chapters.id
    if table_exists(conn, "beat_sheets") and chapter_id_map:
        rows = conn.execute(
            "SELECT bs.* FROM beat_sheets bs "
            "JOIN chapters c ON bs.chapter_id = c.id "
            "WHERE c.novel_id = ?",
            (old_novel_id,),
        ).fetchall()
        if rows:
            col_names = [desc[0] for desc in conn.execute("SELECT * FROM beat_sheets LIMIT 0").description]
            count = 0
            for row in rows:
                row_dict = dict(zip(col_names, row))
                old_cid = row_dict["chapter_id"]
                if old_cid in chapter_id_map:
                    row_dict["chapter_id"] = chapter_id_map[old_cid]
                    row_dict["id"] = _uid("beat", next(id_counter))
                    conn.execute(
                        f"INSERT OR IGNORE INTO beat_sheets ({', '.join(col_names)}) VALUES ({', '.join('?' for _ in col_names)})",
                        [row_dict[c] for c in col_names],
                    )
                    count += 1
            print(f"  beat_sheets: 已复制 {count} 条")

    # chapter_elements → story_nodes.id
    if table_exists(conn, "chapter_elements") and story_node_id_map:
        rows = conn.execute(
            "SELECT ce.* FROM chapter_elements ce "
            "JOIN story_nodes sn ON ce.chapter_id = sn.id "
            "WHERE sn.novel_id = ?",
            (old_novel_id,),
        ).fetchall()
        if rows:
            col_names = [desc[0] for desc in conn.execute("SELECT * FROM chapter_elements LIMIT 0").description]
            count = 0
            for row in rows:
                row_dict = dict(zip(col_names, row))
                old_nid = row_dict["chapter_id"]
                if old_nid in story_node_id_map:
                    row_dict["chapter_id"] = story_node_id_map[old_nid]
                    row_dict["id"] = _uid("ce", next(id_counter))
                    conn.execute(
                        f"INSERT OR IGNORE INTO chapter_elements ({', '.join(col_names)}) VALUES ({', '.join('?' for _ in col_names)})",
                        [row_dict[c] for c in col_names],
                    )
                    count += 1
            print(f"  chapter_elements: 已复制 {count} 条")

    # chapter_scenes → story_nodes.id, 清空 content
    if table_exists(conn, "chapter_scenes") and story_node_id_map:
        rows = conn.execute(
            "SELECT cs.* FROM chapter_scenes cs "
            "JOIN story_nodes sn ON cs.chapter_id = sn.id "
            "WHERE sn.novel_id = ?",
            (old_novel_id,),
        ).fetchall()
        if rows:
            col_names = [desc[0] for desc in conn.execute("SELECT * FROM chapter_scenes LIMIT 0").description]
            count = 0
            for row in rows:
                row_dict = dict(zip(col_names, row))
                old_nid = row_dict["chapter_id"]
                if old_nid in story_node_id_map:
                    row_dict["chapter_id"] = story_node_id_map[old_nid]
                    row_dict["id"] = _uid("cs", next(id_counter))
                    row_dict["content"] = ""
                    if "word_count" in row_dict:
                        row_dict["word_count"] = 0
                    conn.execute(
                        f"INSERT OR IGNORE INTO chapter_scenes ({', '.join(col_names)}) VALUES ({', '.join('?' for _ in col_names)})",
                        [row_dict[c] for c in col_names],
                    )
                    count += 1
            print(f"  chapter_scenes: 已复制 {count} 条 (正文已清空)")


def copy_knowledge_tables(
    conn: sqlite3.Connection,
    old_novel_id: str,
    new_novel_id: str,
    id_counter: itertools.count,
) -> None:
    """复制 knowledge 和 chapter_summaries，清空 AI 生成的摘要内容"""
    if not table_exists(conn, "knowledge"):
        return

    old_knowledge = conn.execute(
        "SELECT * FROM knowledge WHERE novel_id = ?", (old_novel_id,)
    ).fetchone()
    if not old_knowledge:
        return

    col_names = [desc[0] for desc in conn.execute("SELECT * FROM knowledge LIMIT 0").description]
    row_dict = dict(zip(col_names, old_knowledge))
    old_knowledge_id = row_dict["id"]
    new_knowledge_id = _uid("know", next(id_counter))
    row_dict["id"] = new_knowledge_id
    row_dict["novel_id"] = new_novel_id

    conn.execute(
        f"INSERT INTO knowledge ({', '.join(col_names)}) VALUES ({', '.join('?' for _ in col_names)})",
        [row_dict[c] for c in col_names],
    )
    print("  knowledge: 已复制")

    # chapter_summaries — 保留章节结构，清空 AI 摘要
    if table_exists(conn, "chapter_summaries"):
        summaries = conn.execute(
            "SELECT * FROM chapter_summaries WHERE knowledge_id = ? ORDER BY chapter_number",
            (old_knowledge_id,),
        ).fetchall()
        if summaries:
            cs_col_names = [desc[0] for desc in conn.execute("SELECT * FROM chapter_summaries LIMIT 0").description]
            for s in summaries:
                s_dict = dict(zip(cs_col_names, s))
                s_dict["knowledge_id"] = new_knowledge_id
                s_dict["id"] = _uid("cs", next(id_counter))
                s_dict["summary"] = ""
                for col in ("key_events", "open_threads", "consistency_note",
                            "beat_sections", "micro_beats"):
                    if col in s_dict:
                        s_dict[col] = None
                if "sync_status" in s_dict:
                    s_dict["sync_status"] = "draft"

                conn.execute(
                    f"INSERT INTO chapter_summaries ({', '.join(cs_col_names)}) VALUES ({', '.join('?' for _ in cs_col_names)})",
                    [s_dict[c] for c in cs_col_names],
                )
            print(f"  chapter_summaries: 已复制 {len(summaries)} 条 (摘要已清空)")


def copy_planning_tables(
    conn: sqlite3.Connection,
    old_novel_id: str,
    new_novel_id: str,
    id_counter: itertools.count,
) -> tuple[dict[str, int], dict[str, dict[str, str]]]:
    """复制所有规划表，返回 (统计信息, {表名: {旧id: 新id}})"""
    stats: dict[str, int] = {}
    all_id_maps: dict[str, dict[str, str]] = {}
    for table_name in PLANNING_TABLES_WITH_NOVEL_ID:
        table_id_map: dict[str, str] = {}
        count, _ = copy_table_simple(
            conn, table_name, old_novel_id, new_novel_id, id_counter,
            id_map=table_id_map,
        )
        stats[table_name] = count
        if table_id_map:
            all_id_maps[table_name] = table_id_map
        if count > 0:
            print(f"  {table_name}: 已复制 {count} 条")
    return stats, all_id_maps


def validate_source_data(
    conn: sqlite3.Connection,
    old_novel_id: str,
) -> dict:
    """验证源小说数据完整性，返回摘要信息"""
    novel = conn.execute("SELECT * FROM novels WHERE id = ?", (old_novel_id,)).fetchone()
    if not novel:
        return {"valid": False, "error": f"源小说 {old_novel_id} 不存在"}

    col_names = [desc[0] for desc in conn.execute("SELECT * FROM novels LIMIT 0").description]
    novel_dict = dict(zip(col_names, novel))

    chapter_count = conn.execute(
        "SELECT COUNT(*) FROM chapters WHERE novel_id = ?", (old_novel_id,)
    ).fetchone()[0]

    node_count = conn.execute(
        "SELECT COUNT(*) FROM story_nodes WHERE novel_id = ?", (old_novel_id,)
    ).fetchone()[0]

    planning_counts = {}
    for table_name in PLANNING_TABLES_WITH_NOVEL_ID:
        if table_exists(conn, table_name):
            n = conn.execute(
                f"SELECT COUNT(*) FROM {table_name} WHERE novel_id = ?", (old_novel_id,)
            ).fetchone()[0]
            if n > 0:
                planning_counts[table_name] = n

    return {
        "valid": True,
        "title": novel_dict.get("title", "未知"),
        "chapters": chapter_count,
        "story_nodes": node_count,
        "planning_table_counts": planning_counts,
        "stage": novel_dict.get("current_stage", "未知"),
    }


def confirm_insert(conn: sqlite3.Connection, new_novel_id: str) -> dict:
    """确认入库结果：检查新小说的数据完整性"""
    novel = conn.execute("SELECT * FROM novels WHERE id = ?", (new_novel_id,)).fetchone()
    if not novel:
        return {"confirmed": False, "error": "新小说记录未找到"}

    col_names = [desc[0] for desc in conn.execute("SELECT * FROM novels LIMIT 0").description]
    novel_dict = dict(zip(col_names, novel))

    chapter_count = conn.execute(
        "SELECT COUNT(*) FROM chapters WHERE novel_id = ?", (new_novel_id,)
    ).fetchone()[0]

    node_count = conn.execute(
        "SELECT COUNT(*) FROM story_nodes WHERE novel_id = ?", (new_novel_id,)
    ).fetchone()[0]

    # 检查是否有不应出现的表被意外写入
    leaked = []
    for table in DISCARD_TABLES:
        if table_exists(conn, table):
            cols = get_table_columns(conn, table)
            if "novel_id" in cols:
                n = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE novel_id = ?", (new_novel_id,)
                ).fetchone()[0]
                if n > 0:
                    leaked.append(f"{table}({n})")

    copied_tables = []
    for table_name in PLANNING_TABLES_WITH_NOVEL_ID:
        if table_exists(conn, table_name) and "novel_id" in get_table_columns(conn, table_name):
            n = conn.execute(
                f"SELECT COUNT(*) FROM {table_name} WHERE novel_id = ?", (new_novel_id,)
            ).fetchone()[0]
            if n > 0:
                copied_tables.append(f"{table_name}({n})")

    return {
        "confirmed": True,
        "new_id": new_novel_id,
        "stage": novel_dict.get("current_stage"),
        "chapters": chapter_count,
        "story_nodes": node_count,
        "copied_tables": copied_tables,
        "leaked_tables": leaked,
    }


# =============================================================================
# 主编排
# =============================================================================

def _fixup_parent_ids(
    conn: sqlite3.Connection,
    new_novel_id: str,
    id_maps: dict[str, dict[str, str]],
) -> None:
    """修复自引用 parent_id 列：将旧的父 ID 替换为新的父 ID。

    storylines、bible_locations 等表有 parent_id 自引用层级结构。
    复制后所有 ID 都已刷新，需将 parent_id 从旧 ID 映射为新 ID。
    """
    tables_with_parent = [
        ("storylines", "storylines"),
        ("bible_locations", "bible_locations"),
    ]

    for table_name, map_key in tables_with_parent:
        id_map = id_maps.get(map_key)
        if not id_map:
            continue
        if not table_exists(conn, table_name):
            continue
        cols = get_table_columns(conn, table_name)
        if "parent_id" not in cols:
            continue

        fixed = 0
        for old_parent, new_parent in id_map.items():
            cur = conn.execute(
                f"UPDATE {table_name} SET parent_id = ? "
                "WHERE parent_id = ? AND novel_id = ?",
                (new_parent, old_parent, new_novel_id),
            )
            fixed += cur.rowcount

        if fixed > 0:
            print(f"  {table_name}.parent_id: 已修复 {fixed} 条引用")


def backup_novel(
    db_path: Path,
    old_novel_id: str,
    new_novel_id: str,
    dry_run: bool = False,
) -> bool:
    """执行小说备份"""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("PRAGMA journal_mode = WAL")

    try:
        # 0. 源数据验证
        print("\n[0/6] 验证源数据...")
        source_info = validate_source_data(conn, old_novel_id)
        if not source_info["valid"]:
            print(f"  失败：{source_info['error']}")
            return False

        print(f"  小说: {source_info['title']}")
        print(f"  阶段: {source_info['stage']}")
        print(f"  章节数: {source_info['chapters']}")
        print(f"  故事节点: {source_info['story_nodes']}")
        planning_count = sum(source_info["planning_table_counts"].values())
        print(f"  规划数据表: {len(source_info['planning_table_counts'])} 个表, 共 {planning_count} 条记录")

        if dry_run:
            print("\n[DRY RUN] 仅验证，不执行实际写入")
            conn.close()
            return True

        # 清理上次失败残留
        _delete_novel_cascade(conn, new_novel_id)

        id_counter = itertools.count(1)

        # 1. 复制小说主记录
        print("\n[1/6] 复制小说主记录...")
        if not copy_novel_record(conn, old_novel_id, new_novel_id):
            print("  失败：无法复制小说记录")
            return False
        print(f"  novels: 已复制 (新 ID: {new_novel_id}, 阶段已重置为 planning)")

        # 2. 复制故事节点（先于章节，以便章节复用节点 ID）
        print("\n[2/6] 复制故事节点（清空正文）...")
        story_node_id_map, chapter_number_to_node_id = copy_story_nodes(
            conn, old_novel_id, new_novel_id, id_counter,
        )
        print(f"  story_nodes: 已复制 {len(story_node_id_map)} 个节点 (正文已清空)")

        # 3. 复制章节正文行（清空正文，ID 对齐 story_nodes）
        print("\n[3/6] 复制章节正文行（清空正文）...")
        chapter_id_map = copy_chapters(
            conn, old_novel_id, new_novel_id, id_counter,
            chapter_number_to_node_id=chapter_number_to_node_id,
        )
        synced = sum(1 for v in chapter_id_map.values() if v in story_node_id_map.values())
        print(f"  chapters: 已复制 {len(chapter_id_map)} 章 (正文已清空, {synced} 章 ID 已对齐 story_nodes)")

        # 4. 复制规划表（世界观、角色、大纲等）
        print("\n[4/6] 复制世界观与结构数据...")
        planning_stats, id_maps = copy_planning_tables(conn, old_novel_id, new_novel_id, id_counter)
        total_copied = sum(planning_stats.values())
        tables_copied = sum(1 for v in planning_stats.values() if v > 0)
        print(f"  合计: {tables_copied} 个规划表, 共 {total_copied} 条记录, "
              f"{len(id_maps)} 个表已建立 ID 映射")

        # 修复自引用 parent_id（storylines、bible_locations 等有父子层级）
        _fixup_parent_ids(conn, new_novel_id, id_maps)

        # 5. 复制关系表 & 章节关联数据
        print("\n[5/6] 复制关系表与章节关联数据...")
        copy_relation_tables(conn, old_novel_id, new_novel_id, id_counter, id_maps)
        copy_chapter_scoped_tables(conn, old_novel_id, new_novel_id,
                                   chapter_id_map, story_node_id_map, id_counter)

        # 6. 复制知识图谱
        print("\n[6/6] 复制知识图谱...")
        copy_knowledge_tables(conn, old_novel_id, new_novel_id, id_counter)

        # 确认入库结果
        conn.commit()
        print("\n--- 入库确认 ---")
        confirmed = confirm_insert(conn, new_novel_id)
        if confirmed["confirmed"]:
            print(f"  [OK] 新小说 ID: {confirmed['new_id']}")
            print(f"  阶段: {confirmed['stage']}")
            print(f"  章节数: {confirmed['chapters']}")
            print(f"  故事节点: {confirmed['story_nodes']}")
            print(f"  已复制规划表: {len(confirmed['copied_tables'])} 个")
            if confirmed["leaked_tables"]:
                print(f"  [WARN] 发现应丢弃但被写入的表: {', '.join(confirmed['leaked_tables'])}")
            else:
                print(f"  [OK] 无泄漏表，所有生成内容/运行时状态已正确丢弃")
            print(f"\n[OK] 备份完成！新小说 ID: {new_novel_id}")
        else:
            print(f"  [FAIL] 入库确认失败: {confirmed.get('error', '未知错误')}")
            return False

        return True

    except Exception as e:
        conn.rollback()
        print(f"\n[FAIL] 备份失败: {e}")
        raise
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="备份小说：复制引导状态到新小说，清空所有正文内容",
    )
    parser.add_argument("source_novel_id", help="源小说 ID (如 novel-1779868467739)")
    parser.add_argument("target_novel_id", nargs="?", default=None,
                        help="目标小说 ID (可选，默认自动生成)")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅验证源数据，不执行实际复制")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="跳过确认提示，直接执行")
    args = parser.parse_args()

    db_path = get_db_path()
    if not db_path.is_file():
        print(f"错误：数据库文件不存在: {db_path}")
        sys.exit(1)

    new_id = args.target_novel_id or generate_novel_id()

    print(f"数据库: {db_path}")
    print(f"源小说: {args.source_novel_id}")
    print(f"目标小说: {new_id}")

    conn = sqlite3.connect(str(db_path))
    exists = conn.execute(
        "SELECT 1 FROM novels WHERE id = ?", (args.source_novel_id,)
    ).fetchone()
    if not exists:
        print(f"错误：源小说 {args.source_novel_id} 不存在")
        conn.close()
        sys.exit(1)

    target_exists = conn.execute(
        "SELECT 1 FROM novels WHERE id = ?", (new_id,)
    ).fetchone()
    conn.close()

    if target_exists:
        print(f"错误：目标小说 {new_id} 已存在，请指定其他 ID")
        sys.exit(1)

    if args.dry_run:
        backup_novel(db_path, args.source_novel_id, new_id, dry_run=True)
        return

    # 展示规划表复制清单
    print(f"\n将复制以下 {len(PLANNING_TABLES_WITH_NOVEL_ID)} 个规划表:")
    for t in PLANNING_TABLES_WITH_NOVEL_ID:
        print(f"  - {t}")

    print(f"\n以下 {len(DISCARD_TABLES)} 个表将被丢弃 (AI 生成 / 运行时状态):")
    # 只展示前 15 个作为提示
    for t in DISCARD_TABLES[:15]:
        print(f"  - {t}")
    if len(DISCARD_TABLES) > 15:
        print(f"  ... 及其他 {len(DISCARD_TABLES) - 15} 个表")

    if not args.yes:
        answer = input("\n确认执行备份? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("已取消")
            sys.exit(0)

    success = backup_novel(db_path, args.source_novel_id, new_id)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
