CREATE TABLE IF NOT EXISTS narrative_contracts (
    novel_id TEXT PRIMARY KEY,
    title_promise TEXT NOT NULL DEFAULT '',
    core_question TEXT NOT NULL DEFAULT '',
    theme_anchors_json TEXT NOT NULL DEFAULT '[]',
    forbidden_early_payoffs_json TEXT NOT NULL DEFAULT '[]',
    reveal_budget_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS canonical_storylines (
    canonical_id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    canonical_key TEXT NOT NULL,
    title TEXT NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    goal TEXT NOT NULL DEFAULT '',
    conflict TEXT NOT NULL DEFAULT '',
    span_json TEXT NOT NULL DEFAULT '{}',
    promise_tags_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'active',
    source_storyline_ids_json TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(novel_id, canonical_key)
);

CREATE TABLE IF NOT EXISTS governance_reports (
    report_id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    severity TEXT NOT NULL,
    promise_hit_rate REAL NOT NULL DEFAULT 0,
    issues_json TEXT NOT NULL DEFAULT '[]',
    budget_patch_json TEXT NOT NULL DEFAULT '{}',
    should_pause_autopilot INTEGER NOT NULL DEFAULT 0,
    review_status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS governance_events (
    event_id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    chapter_number INTEGER,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_canonical_storylines_novel
    ON canonical_storylines(novel_id);

CREATE INDEX IF NOT EXISTS idx_governance_reports_novel_chapter
    ON governance_reports(novel_id, chapter_number);

CREATE INDEX IF NOT EXISTS idx_governance_events_novel
    ON governance_events(novel_id, created_at);
