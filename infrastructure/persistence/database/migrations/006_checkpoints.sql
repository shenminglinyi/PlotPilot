-- 006: Checkpoint表（Git式版本控制）
-- 对应架构治理 P1-1

CREATE TABLE IF NOT EXISTS checkpoints (
    id TEXT PRIMARY KEY,                        -- UUID
    story_id TEXT NOT NULL,                     -- 故事ID
    parent_id TEXT,                             -- 父节点（树状结构）
    trigger_type TEXT NOT NULL,                 -- chapter/act/milestone/manual
    trigger_reason TEXT NOT NULL DEFAULT '',    -- 触发原因描述

    -- 快照内容（JSON）
    story_state TEXT NOT NULL DEFAULT '{}',     -- 故事状态
    character_masks TEXT NOT NULL DEFAULT '{}', -- 角色面具
    emotion_ledger TEXT NOT NULL DEFAULT '{}',  -- 情绪账本
    active_foreshadows TEXT NOT NULL DEFAULT '[]', -- 活跃伏笔
    outline TEXT NOT NULL DEFAULT '',           -- 当前大纲
    recent_chapters_summary TEXT NOT NULL DEFAULT '', -- 近期章节摘要

    -- 软删除
    is_active INTEGER NOT NULL DEFAULT 1,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- 索引
    FOREIGN KEY (story_id) REFERENCES novels(id)
);

-- 按故事查询Checkpoint
CREATE INDEX IF NOT EXISTS idx_checkpoints_story_id
ON checkpoints(story_id, created_at DESC);

-- 按父节点查询（树遍历）
CREATE INDEX IF NOT EXISTS idx_checkpoints_parent_id
ON checkpoints(parent_id);

-- 按触发类型查询
CREATE INDEX IF NOT EXISTS idx_checkpoints_trigger_type
ON checkpoints(trigger_type);

-- 按活跃状态查询
CREATE INDEX IF NOT EXISTS idx_checkpoints_active
ON checkpoints(story_id, is_active, created_at DESC);

-- HEAD指针表（当前Checkpoint指针）
CREATE TABLE IF NOT EXISTS checkpoint_heads (
    story_id TEXT PRIMARY KEY,
    checkpoint_id TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (checkpoint_id) REFERENCES checkpoints(id),
    FOREIGN KEY (story_id) REFERENCES novels(id)
);
