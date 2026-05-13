-- 章节历史草稿表：保存章节被覆写前的历史内容，支持重新生成时的版本回退
CREATE TABLE IF NOT EXISTS chapter_drafts (
    id          TEXT PRIMARY KEY,
    novel_id    TEXT NOT NULL,
    chapter_id  TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    content     TEXT NOT NULL DEFAULT '',
    outline     TEXT NOT NULL DEFAULT '',
    source      TEXT NOT NULL DEFAULT 'manual',   -- 'manual_save' | 'pre_regen' | 'auto_gen'
    word_count  INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chapter_drafts_lookup
    ON chapter_drafts(novel_id, chapter_number, created_at DESC);
