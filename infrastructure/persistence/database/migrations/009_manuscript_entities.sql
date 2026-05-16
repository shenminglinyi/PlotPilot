-- 手稿实体：道具表 + 章节内实体出现统计（无 LLM，保存时由应用层回填）
CREATE TABLE IF NOT EXISTS bible_props (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    aliases_json TEXT NOT NULL DEFAULT '[]',
    holder_character_id TEXT,
    first_chapter INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_bible_props_novel ON bible_props(novel_id);

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
