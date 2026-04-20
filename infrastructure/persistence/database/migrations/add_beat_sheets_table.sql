-- 幂等：旧库可能早于 beat_sheets 引入，补表与 schema.sql 保持一致
CREATE TABLE IF NOT EXISTS beat_sheets (
    id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL UNIQUE,
    data TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_beat_sheets_chapter_id ON beat_sheets(chapter_id);
