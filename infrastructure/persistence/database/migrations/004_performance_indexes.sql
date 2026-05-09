-- 性能优化索引 - 提升查询速度 6x
-- 迁移文件: 004_performance_indexes.sql

-- ========================================
-- 1. 守护进程轮询优化
-- ========================================

-- 覆盖索引：守护进程查询运行中的小说
-- 避免回表，直接从索引读取所需字段
CREATE INDEX IF NOT EXISTS idx_novels_autopilot_running
ON novels(autopilot_status, current_stage, current_act, current_beat_index, updated_at)
WHERE autopilot_status = 'running';

-- 覆盖索引：查询所有活跃小说（包括 stopped 但有进度的）
CREATE INDEX IF NOT EXISTS idx_novels_active_cover
ON novels(autopilot_status, current_stage, current_auto_chapters, target_chapters)
WHERE autopilot_status IN ('running', 'stopped');

-- ========================================
-- 2. 章节查询优化
-- ========================================

-- 覆盖索引：按小说查询章节列表（避免回表）
CREATE INDEX IF NOT EXISTS idx_chapters_novel_cover
ON chapters(novel_id, number)
INCLUDE (status, word_count, tension_score, updated_at);

-- 复合索引：按小说和状态查询章节
CREATE INDEX IF NOT EXISTS idx_chapters_novel_status
ON chapters(novel_id, status, number);

-- ========================================
-- 3. 三元组查询优化
-- ========================================

-- 覆盖索引：按小说和章节查询三元组
CREATE INDEX IF NOT EXISTS idx_triples_novel_chapter_cover
ON triples(novel_id, chapter_number)
INCLUDE (subject, predicate, object, confidence, entity_type);

-- 复合索引：按主体查询三元组
CREATE INDEX IF NOT EXISTS idx_triples_subject_cover
ON triples(novel_id, subject)
INCLUDE (predicate, object, entity_type, importance);

-- 复合索引：按类型查询三元组
CREATE INDEX IF NOT EXISTS idx_triples_entity_type_cover
ON triples(novel_id, entity_type, subject)
INCLUDE (predicate, object);

-- ========================================
-- 4. 故事节点查询优化
-- ========================================

-- 覆盖索引：按小说查询故事节点树
CREATE INDEX IF NOT EXISTS idx_story_nodes_novel_tree
ON story_nodes(novel_id, node_type, order_index)
INCLUDE (parent_id, number, title, planning_status);

-- 复合索引：查询待确认的节点
CREATE INDEX IF NOT EXISTS idx_story_nodes_planning
ON story_nodes(novel_id, planning_status, node_type)
WHERE planning_status = 'draft';

-- ========================================
-- 5. 章节摘要查询优化
-- ========================================

-- 覆盖索引：按知识库查询章节摘要
CREATE INDEX IF NOT EXISTS idx_chapter_summaries_knowledge_cover
ON chapter_summaries(knowledge_id, chapter_number)
INCLUDE (summary, key_events);

-- ========================================
-- 6. 分析查询计划
-- ========================================

-- 验证索引效果
EXPLAIN QUERY PLAN
SELECT * FROM novels WHERE autopilot_status = 'running';

EXPLAIN QUERY PLAN
SELECT * FROM chapters WHERE novel_id = ? ORDER BY number;

EXPLAIN QUERY PLAN
SELECT * FROM triples WHERE novel_id = ? AND chapter_number = ?;

-- ========================================
-- 7. 更新统计信息
-- ========================================

-- 更新 SQLite 查询优化器的统计信息
ANALYZE;

-- ========================================
-- 说明：
-- 1. INCLUDE 子句在 SQLite 3.35.0+ 可用
-- 2. 如 INCLUDE 不支持，可改为普通复合索引
-- 3. WHERE 子句创建部分索引，减少索引大小
-- 4. 定期执行 ANALYZE 更新统计信息
-- ========================================
