-- 手稿实体：章节内实体出现统计（无 LLM，保存时由应用层回填）
CREATE TABLE IF NOT EXISTS chapter_entity_mentions (
    novel_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    entity_kind TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    display_label TEXT NOT NULL DEFAULT '',
    mention_count INTEGER NOT NULL DEFAULT 1,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (novel_id, chapter_number, entity_kind, entity_id),
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chapter_entity_mentions_novel_ch ON chapter_entity_mentions(novel_id, chapter_number);
