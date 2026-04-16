CREATE TABLE IF NOT EXISTS chapter_versions (
    id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL,
    novel_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    summary TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id, chapter_number) REFERENCES chapters(novel_id, number) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chapter_versions_novel_chapter
    ON chapter_versions(novel_id, chapter_number);

CREATE INDEX IF NOT EXISTS idx_chapter_versions_created_at
    ON chapter_versions(created_at);
