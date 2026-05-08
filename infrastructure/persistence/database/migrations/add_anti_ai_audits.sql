-- Anti-AI 审计结果表 — 存储每章的 AI 味检测与审计结果
-- 供前端仪表板和趋势分析使用
CREATE TABLE IF NOT EXISTS anti_ai_audits (
    audit_id        TEXT PRIMARY KEY,
    novel_id        TEXT NOT NULL,
    chapter_number  INTEGER NOT NULL,
    total_hits      INTEGER NOT NULL DEFAULT 0,
    critical_hits   INTEGER NOT NULL DEFAULT 0,
    warning_hits    INTEGER NOT NULL DEFAULT 0,
    info_hits       INTEGER NOT NULL DEFAULT 0,
    severity_score  REAL NOT NULL DEFAULT 0.0,
    overall_assessment TEXT NOT NULL DEFAULT '未检测',
    hit_density     REAL NOT NULL DEFAULT 0.0,
    critical_density REAL NOT NULL DEFAULT 0.0,
    category_distribution TEXT,  -- JSON: {"微表情": 3, "声线": 2, ...}
    top_patterns    TEXT,         -- JSON: ["嘴角微表情", "声线变化", ...]
    recommendations TEXT,         -- JSON: ["建议1", "建议2", ...]
    improvement_suggestions TEXT, -- JSON: ["建议1", "建议2", ...]
    hits_detail     TEXT,         -- JSON: [{pattern, text, severity, category, hint}, ...]
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(novel_id, chapter_number)
);

-- 索引：按小说查询审计历史
CREATE INDEX IF NOT EXISTS idx_anti_ai_audits_novel
    ON anti_ai_audits(novel_id, chapter_number);
