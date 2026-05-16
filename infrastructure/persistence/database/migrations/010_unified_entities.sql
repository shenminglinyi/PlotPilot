CREATE TABLE IF NOT EXISTS unified_characters (
    id                    TEXT PRIMARY KEY,
    novel_id              TEXT NOT NULL,
    name                  TEXT NOT NULL,
    description           TEXT NOT NULL DEFAULT '',
    public_profile        TEXT NOT NULL DEFAULT '',
    hidden_profile        TEXT NOT NULL DEFAULT '',
    reveal_chapter        INTEGER,
    role                  TEXT NOT NULL DEFAULT '',
    faction_id            TEXT,
    verbal_tic            TEXT NOT NULL DEFAULT '',
    idle_behavior         TEXT NOT NULL DEFAULT '',
    voice_style           TEXT NOT NULL DEFAULT '',
    sentence_pattern      TEXT NOT NULL DEFAULT '',
    speech_tempo          TEXT NOT NULL DEFAULT '',
    core_belief           TEXT NOT NULL DEFAULT '',
    moral_taboos_json     TEXT NOT NULL DEFAULT '[]',
    active_wounds_json    TEXT NOT NULL DEFAULT '[]',
    mental_state          TEXT NOT NULL DEFAULT 'NORMAL',
    mental_state_reason   TEXT NOT NULL DEFAULT '',
    emotional_arc_json    TEXT NOT NULL DEFAULT '[]',
    current_state_summary TEXT NOT NULL DEFAULT '',
    last_updated_chapter  INTEGER NOT NULL DEFAULT 0,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_unified_characters_novel ON unified_characters(novel_id);

CREATE TABLE IF NOT EXISTS unified_character_relationships (
    id               TEXT PRIMARY KEY,
    character_id     TEXT NOT NULL,
    target_id        TEXT,
    target_name      TEXT NOT NULL,
    relation         TEXT NOT NULL DEFAULT '',
    description      TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (character_id) REFERENCES unified_characters(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS unified_props (
    id                  TEXT PRIMARY KEY,
    novel_id            TEXT NOT NULL,
    name                TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    aliases_json        TEXT NOT NULL DEFAULT '[]',
    prop_category       TEXT NOT NULL DEFAULT 'OTHER',
    lifecycle_state     TEXT NOT NULL DEFAULT 'DORMANT',
    introduced_chapter  INTEGER,
    resolved_chapter    INTEGER,
    holder_character_id TEXT,
    attributes_json     TEXT NOT NULL DEFAULT '{}',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_unified_props_novel ON unified_props(novel_id);
CREATE INDEX IF NOT EXISTS idx_unified_props_holder ON unified_props(holder_character_id);

CREATE TABLE IF NOT EXISTS prop_events (
    id                  TEXT PRIMARY KEY,
    novel_id            TEXT NOT NULL,
    prop_id             TEXT NOT NULL,
    chapter_number      INTEGER NOT NULL,
    event_type          TEXT NOT NULL,
    actor_character_id  TEXT,
    from_holder_id      TEXT,
    to_holder_id        TEXT,
    description         TEXT NOT NULL DEFAULT '',
    source              TEXT NOT NULL DEFAULT 'MANUAL',
    created_at          TEXT NOT NULL,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE,
    FOREIGN KEY (prop_id) REFERENCES unified_props(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_prop_events_prop ON prop_events(prop_id);
CREATE INDEX IF NOT EXISTS idx_prop_events_novel_ch ON prop_events(novel_id, chapter_number);

CREATE TABLE IF NOT EXISTS prop_chapter_snapshots (
    prop_id                  TEXT NOT NULL,
    chapter_number           INTEGER NOT NULL,
    holder_character_id      TEXT,
    lifecycle_state          TEXT NOT NULL,
    attributes_snapshot_json TEXT NOT NULL DEFAULT '{}',
    captured_at              TEXT NOT NULL,
    PRIMARY KEY (prop_id, chapter_number),
    FOREIGN KEY (prop_id) REFERENCES unified_props(id) ON DELETE CASCADE
);
