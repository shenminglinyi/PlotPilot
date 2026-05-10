-- 007: 角色系统表
-- 对应架构治理 P2-4 / P2-5 / P2-8

-- 角色基础表（四维模型持久化）
CREATE TABLE IF NOT EXISTS characters (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    base_layer TEXT NOT NULL DEFAULT '{}',  -- JSON: 四维模型基础层
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 角色地质叠层Patch（Append-only）
CREATE TABLE IF NOT EXISTS character_patches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id TEXT NOT NULL,
    trigger_chapter INTEGER NOT NULL,
    trigger_event TEXT NOT NULL,
    changes TEXT NOT NULL DEFAULT '{}',     -- JSON: 修改内容
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (character_id) REFERENCES characters(id)
);

CREATE INDEX IF NOT EXISTS idx_character_patches_character
ON character_patches(character_id, trigger_chapter ASC);

-- 角色发言样本库（向量检索用）
CREATE TABLE IF NOT EXISTS character_voice_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    content TEXT NOT NULL,                   -- 发言原文
    embedding TEXT,                          -- 向量嵌入（JSON数组）
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (character_id) REFERENCES characters(id),
    UNIQUE(character_id, chapter_number)
);

CREATE INDEX IF NOT EXISTS idx_voice_samples_character
ON character_voice_samples(character_id, chapter_number ASC);

-- 故事-角色关联表
CREATE TABLE IF NOT EXISTS story_characters (
    story_id TEXT NOT NULL,
    character_id TEXT NOT NULL,
    character_name TEXT NOT NULL,
    role TEXT DEFAULT 'supporting',          -- protagonist/antagonist/supporting
    PRIMARY KEY (story_id, character_id)
);
