-- 章节衔接引擎：存储每章末尾的5维桥段锚点
-- 供下一章首段衔接使用，消除章节间割裂感
CREATE TABLE IF NOT EXISTS chapter_bridges (
    novel_id        TEXT NOT NULL,
    chapter_number  INTEGER NOT NULL,
    bridge_data     TEXT NOT NULL,  -- JSON: {suspense_hook, emotional_residue, emotional_intensity, scene_state, character_positions, unfinished_actions, tail_text}
    created_at      TEXT NOT NULL,
    PRIMARY KEY (novel_id, chapter_number)
);
