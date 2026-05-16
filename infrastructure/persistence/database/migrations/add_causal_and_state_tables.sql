-- Migration: add_causal_and_state_tables
-- Date: 2026-05-08
-- Description: 百章级长篇小说连贯性重构 - 因果图谱 / 人物状态机 / 叙事债务

-- ============================================================
-- 1. 因果边表（CausalGraphRAG）
-- ============================================================
CREATE TABLE IF NOT EXISTS causal_edges (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    source_event_summary TEXT NOT NULL,
    source_chapter INTEGER NOT NULL,
    causal_type TEXT NOT NULL DEFAULT 'causes'
        CHECK (causal_type IN ('causes', 'motivates', 'triggers', 'prevents', 'resolves')),
    target_event_summary TEXT NOT NULL,
    target_chapter INTEGER,
    strength REAL DEFAULT 0.8 CHECK (strength BETWEEN 0 AND 1),
    confidence REAL DEFAULT 0.7 CHECK (confidence BETWEEN 0 AND 1),
    state_change TEXT DEFAULT '',
    involved_characters TEXT DEFAULT '[]',
    is_resolved INTEGER DEFAULT 0 CHECK (is_resolved IN (0, 1)),
    resolved_chapter INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_causal_edges_novel ON causal_edges(novel_id);
CREATE INDEX IF NOT EXISTS idx_causal_edges_source_chapter ON causal_edges(novel_id, source_chapter);
CREATE INDEX IF NOT EXISTS idx_causal_edges_unresolved ON causal_edges(novel_id, is_resolved);

-- ============================================================
-- 2. 人物可变状态表（Character State Machine）
-- ============================================================
CREATE TABLE IF NOT EXISTS character_states (
    character_id TEXT NOT NULL,
    novel_id TEXT NOT NULL,
    base_traits TEXT DEFAULT '[]',
    scars TEXT DEFAULT '[]',
    motivations TEXT DEFAULT '[]',
    emotional_arc TEXT DEFAULT '[]',
    current_state_summary TEXT DEFAULT '',
    last_updated_chapter INTEGER DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (character_id, novel_id),
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_character_states_novel ON character_states(novel_id);

-- ============================================================
-- 3. 叙事债务表（Narrative Debt Validator）
-- ============================================================
CREATE TABLE IF NOT EXISTS narrative_debts (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    debt_type TEXT NOT NULL
        CHECK (debt_type IN ('foreshadowing', 'causal_chain', 'storyline', 'character_arc')),
    description TEXT NOT NULL,
    planted_chapter INTEGER NOT NULL,
    due_chapter INTEGER,
    importance INTEGER DEFAULT 2 CHECK (importance BETWEEN 1 AND 4),
    is_overdue INTEGER DEFAULT 0 CHECK (is_overdue IN (0, 1)),
    resolved_chapter INTEGER,
    involved_entities TEXT DEFAULT '[]',
    context TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_narrative_debts_novel ON narrative_debts(novel_id);
CREATE INDEX IF NOT EXISTS idx_narrative_debts_overdue ON narrative_debts(novel_id, is_overdue);
CREATE INDEX IF NOT EXISTS idx_narrative_debts_type ON narrative_debts(novel_id, debt_type);
