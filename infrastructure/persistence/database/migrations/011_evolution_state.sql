CREATE TABLE IF NOT EXISTS chapter_evolution_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    branch_id TEXT NOT NULL DEFAULT 'main',
    chapter_number INTEGER NOT NULL,
    schema_version TEXT NOT NULL DEFAULT 'v2.0',
    status TEXT NOT NULL DEFAULT 'active',
    opening_state_json TEXT NOT NULL DEFAULT '{}',
    delta_actions_json TEXT NOT NULL DEFAULT '[]',
    machine_state_json TEXT NOT NULL DEFAULT '{}',
    override_patches_json TEXT NOT NULL DEFAULT '[]',
    ending_state_json TEXT NOT NULL DEFAULT '{}',
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    conflicts_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chapter_evolution_snapshots_active
    ON chapter_evolution_snapshots(novel_id, branch_id, status, chapter_number);

CREATE INDEX IF NOT EXISTS idx_chapter_evolution_snapshots_chapter
    ON chapter_evolution_snapshots(novel_id, branch_id, chapter_number, updated_at);

CREATE TABLE IF NOT EXISTS chapter_evolution_action_log (
    action_id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL,
    novel_id TEXT NOT NULL,
    branch_id TEXT NOT NULL DEFAULT 'main',
    chapter_number INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    source_ref_json TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 1.0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chapter_evolution_action_log_snapshot
    ON chapter_evolution_action_log(snapshot_id);

CREATE INDEX IF NOT EXISTS idx_chapter_evolution_action_log_novel_chapter
    ON chapter_evolution_action_log(novel_id, branch_id, chapter_number);

CREATE TABLE IF NOT EXISTS chapter_evolution_conflicts (
    conflict_id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL,
    novel_id TEXT NOT NULL,
    branch_id TEXT NOT NULL DEFAULT 'main',
    chapter_number INTEGER NOT NULL,
    conflict_type TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'blocking',
    message TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    resolution_status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_chapter_evolution_conflicts_open
    ON chapter_evolution_conflicts(novel_id, branch_id, resolution_status, chapter_number);
