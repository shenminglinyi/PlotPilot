-- 008: 自动驾驶状态与审计快照拆分
-- 对应架构治理 P2-1 / P2-9
-- 视图替换法兼容旧代码

-- 自动驾驶状态表
CREATE TABLE IF NOT EXISTS novel_autopilot_states (
    novel_id TEXT PRIMARY KEY,
    autopilot_status TEXT NOT NULL DEFAULT 'stopped',
    auto_approve_mode INTEGER NOT NULL DEFAULT 0,
    current_stage TEXT NOT NULL DEFAULT 'planning',
    current_act INTEGER NOT NULL DEFAULT 0,
    current_chapter_in_act INTEGER NOT NULL DEFAULT 0,
    max_auto_chapters INTEGER NOT NULL DEFAULT 9999,
    current_auto_chapters INTEGER NOT NULL DEFAULT 0,
    last_chapter_tension INTEGER NOT NULL DEFAULT 0,
    consecutive_error_count INTEGER NOT NULL DEFAULT 0,
    current_beat_index INTEGER NOT NULL DEFAULT 0,
    beats_completed INTEGER NOT NULL DEFAULT 0,
    target_words_per_chapter INTEGER NOT NULL DEFAULT 2500,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id)
);

-- 审计快照表
CREATE TABLE IF NOT EXISTS novel_audit_snapshots (
    novel_id TEXT PRIMARY KEY,
    last_audit_chapter_number INTEGER,
    last_audit_similarity REAL,
    last_audit_drift_alert INTEGER NOT NULL DEFAULT 0,
    last_audit_narrative_ok INTEGER NOT NULL DEFAULT 1,
    last_audit_at TIMESTAMP,
    last_audit_vector_stored INTEGER NOT NULL DEFAULT 0,
    last_audit_foreshadow_stored INTEGER NOT NULL DEFAULT 0,
    last_audit_triples_extracted INTEGER NOT NULL DEFAULT 0,
    last_audit_quality_scores TEXT,          -- JSON
    last_audit_issues TEXT,                  -- JSON
    audit_progress TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id)
);

-- 兼容视图：旧代码读novels表时透明路由到新表
-- 注意：SQLite视图不支持INSTEAD OF触发器写操作
-- 迁移阶段：旧读走视图，新写直接写子表
CREATE VIEW IF NOT EXISTS novels_extended AS
SELECT
    n.*,
    ap.autopilot_status,
    ap.auto_approve_mode,
    ap.current_stage,
    ap.current_act,
    ap.current_chapter_in_act,
    ap.max_auto_chapters,
    ap.current_auto_chapters,
    ap.last_chapter_tension,
    ap.consecutive_error_count,
    ap.current_beat_index,
    ap.beats_completed,
    ap.target_words_per_chapter,
    aus.last_audit_chapter_number,
    aus.last_audit_similarity,
    aus.last_audit_drift_alert,
    aus.last_audit_narrative_ok,
    aus.last_audit_at,
    aus.last_audit_vector_stored,
    aus.last_audit_foreshadow_stored,
    aus.last_audit_triples_extracted,
    aus.last_audit_quality_scores,
    aus.last_audit_issues,
    aus.audit_progress
FROM novels n
LEFT JOIN novel_autopilot_states ap ON n.id = ap.novel_id
LEFT JOIN novel_audit_snapshots aus ON n.id = aus.novel_id;
