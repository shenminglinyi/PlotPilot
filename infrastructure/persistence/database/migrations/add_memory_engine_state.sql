-- MemoryEngine 跨章状态（已完成节拍 / 已揭露线索等），与 application.engine.services.memory_engine 一致
CREATE TABLE IF NOT EXISTS memory_engine_state (
    novel_id TEXT PRIMARY KEY,
    state_json TEXT NOT NULL DEFAULT '{}',
    last_updated_chapter INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
