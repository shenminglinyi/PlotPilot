-- Additive pilot only. Tombstones deliberately have no FK/cascade.
BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS plugin_pilot_revisions (
    kind TEXT NOT NULL, object_id TEXT NOT NULL, revision TEXT NOT NULL,
    PRIMARY KEY(kind, object_id)
);
INSERT OR IGNORE INTO plugin_pilot_revisions
    SELECT 'chapter', id, lower(hex(randomblob(16))) FROM chapters;
INSERT OR IGNORE INTO plugin_pilot_revisions
    SELECT 'character', id, lower(hex(randomblob(16))) FROM unified_characters;

CREATE TRIGGER IF NOT EXISTS plugin_pilot_chapter_insert AFTER INSERT ON chapters BEGIN
    INSERT INTO plugin_pilot_revisions VALUES ('chapter', NEW.id, lower(hex(randomblob(16))))
    ON CONFLICT(kind, object_id) DO UPDATE SET revision=excluded.revision;
END;
CREATE TRIGGER IF NOT EXISTS plugin_pilot_chapter_update AFTER UPDATE ON chapters BEGIN
    INSERT INTO plugin_pilot_revisions VALUES ('chapter', OLD.id, lower(hex(randomblob(16))))
    ON CONFLICT(kind, object_id) DO UPDATE SET revision=excluded.revision;
    INSERT INTO plugin_pilot_revisions VALUES ('chapter', NEW.id, lower(hex(randomblob(16))))
    ON CONFLICT(kind, object_id) DO UPDATE SET revision=excluded.revision;
END;
CREATE TRIGGER IF NOT EXISTS plugin_pilot_chapter_delete AFTER DELETE ON chapters BEGIN
    INSERT INTO plugin_pilot_revisions VALUES ('chapter', OLD.id, lower(hex(randomblob(16))))
    ON CONFLICT(kind, object_id) DO UPDATE SET revision=excluded.revision;
END;
CREATE TRIGGER IF NOT EXISTS plugin_pilot_character_insert AFTER INSERT ON unified_characters BEGIN
    INSERT INTO plugin_pilot_revisions VALUES ('character', NEW.id, lower(hex(randomblob(16))))
    ON CONFLICT(kind, object_id) DO UPDATE SET revision=excluded.revision;
END;
CREATE TRIGGER IF NOT EXISTS plugin_pilot_character_update AFTER UPDATE ON unified_characters BEGIN
    INSERT INTO plugin_pilot_revisions VALUES ('character', OLD.id, lower(hex(randomblob(16))))
    ON CONFLICT(kind, object_id) DO UPDATE SET revision=excluded.revision;
    INSERT INTO plugin_pilot_revisions VALUES ('character', NEW.id, lower(hex(randomblob(16))))
    ON CONFLICT(kind, object_id) DO UPDATE SET revision=excluded.revision;
END;
CREATE TRIGGER IF NOT EXISTS plugin_pilot_character_delete AFTER DELETE ON unified_characters BEGIN
    INSERT INTO plugin_pilot_revisions VALUES ('character', OLD.id, lower(hex(randomblob(16))))
    ON CONFLICT(kind, object_id) DO UPDATE SET revision=excluded.revision;
END;

CREATE TABLE IF NOT EXISTS plugin_pilot_candidates (
    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL, adopted_command_id TEXT UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_plugin_pilot_candidates_project
    ON plugin_pilot_candidates(project_id, created_at);
CREATE TABLE IF NOT EXISTS plugin_pilot_commands (
    id TEXT PRIMARY KEY, project_id TEXT NOT NULL, request_hash TEXT NOT NULL,
    result_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS plugin_pilot_adoptions (
    command_id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL UNIQUE,
    project_id TEXT NOT NULL, character_id TEXT NOT NULL,
    old_revision TEXT NOT NULL, new_revision TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
COMMIT;
