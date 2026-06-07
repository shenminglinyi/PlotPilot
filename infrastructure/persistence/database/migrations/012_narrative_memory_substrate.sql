-- 012: Narrative Memory Substrate
-- Unified evidence ledger and projection read-model for characters first,
-- with entity-type room for props, locations, factions, and concepts.

CREATE TABLE IF NOT EXISTS narrative_entities (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    entity_type TEXT NOT NULL DEFAULT 'character',
    canonical_name TEXT NOT NULL DEFAULT '',
    aliases_json TEXT NOT NULL DEFAULT '[]',
    lifecycle_status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_narrative_entities_identity
ON narrative_entities(novel_id, entity_type, id);

CREATE INDEX IF NOT EXISTS idx_narrative_entities_lookup
ON narrative_entities(novel_id, entity_type, canonical_name);

CREATE TABLE IF NOT EXISTS memory_atoms (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    entity_type TEXT NOT NULL DEFAULT 'character',
    memory_type TEXT NOT NULL DEFAULT 'fact',
    scope TEXT NOT NULL DEFAULT 'global',
    source TEXT NOT NULL DEFAULT 'manual',
    status TEXT NOT NULL DEFAULT 'candidate',
    payload_json TEXT NOT NULL DEFAULT '{}',
    chapter_number INTEGER,
    text_span TEXT NOT NULL DEFAULT '',
    confidence REAL NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_memory_atoms_entity
ON memory_atoms(novel_id, entity_id, status, memory_type);

CREATE INDEX IF NOT EXISTS idx_memory_atoms_chapter
ON memory_atoms(novel_id, chapter_number, status);

CREATE UNIQUE INDEX IF NOT EXISTS ux_memory_atoms_dedupe
ON memory_atoms(
    novel_id,
    entity_id,
    memory_type,
    source,
    IFNULL(chapter_number, -1),
    text_span
);

CREATE TABLE IF NOT EXISTS memory_atom_links (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    source_atom_id TEXT NOT NULL,
    target_atom_id TEXT NOT NULL,
    relation_type TEXT NOT NULL DEFAULT 'related',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_memory_atom_links_source
ON memory_atom_links(novel_id, source_atom_id);

CREATE TABLE IF NOT EXISTS memory_projections (
    novel_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    entity_type TEXT NOT NULL DEFAULT 'character',
    projection_type TEXT NOT NULL DEFAULT 'character',
    version INTEGER NOT NULL DEFAULT 1,
    projection_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (novel_id, entity_id, projection_type)
);

CREATE TABLE IF NOT EXISTS memory_calibration_actions (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    atom_id TEXT NOT NULL,
    action TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_memory_calibration_atom
ON memory_calibration_actions(novel_id, atom_id);

