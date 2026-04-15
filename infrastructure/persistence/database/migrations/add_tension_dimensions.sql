-- 多维张力分析：为 chapters 表添加三个维度分值列
ALTER TABLE chapters ADD COLUMN plot_tension REAL DEFAULT 50.0;
ALTER TABLE chapters ADD COLUMN emotional_tension REAL DEFAULT 50.0;
ALTER TABLE chapters ADD COLUMN pacing_tension REAL DEFAULT 50.0;
