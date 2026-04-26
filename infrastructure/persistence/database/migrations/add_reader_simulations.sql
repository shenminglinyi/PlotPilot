-- 读者模拟反馈记录表
-- 存储每次读者模拟 Agent 的分析结果
CREATE TABLE IF NOT EXISTS reader_simulations (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    chapter_number INTEGER NOT NULL,
    -- 综合指标
    overall_readability REAL DEFAULT 50.0,
    chapter_hook_strength TEXT DEFAULT 'medium'
      CHECK(chapter_hook_strength IN ('weak', 'medium', 'strong')),
    pacing_verdict TEXT DEFAULT '',
    -- 三个读者的平均分（方便查询/排序）
    avg_suspense_retention REAL DEFAULT 50.0,
    avg_thrill_score REAL DEFAULT 50.0,
    avg_churn_risk REAL DEFAULT 30.0,
    avg_emotional_resonance REAL DEFAULT 50.0,
    -- 完整 JSON（feedbacks 数组的序列化，含每个读者的细项）
    feedbacks_json TEXT DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_reader_simulations_novel
  ON reader_simulations(novel_id);
CREATE INDEX IF NOT EXISTS idx_reader_simulations_chapter
  ON reader_simulations(novel_id, chapter_number);
CREATE INDEX IF NOT EXISTS idx_reader_simulations_churn
  ON reader_simulations(novel_id, avg_churn_risk DESC);
