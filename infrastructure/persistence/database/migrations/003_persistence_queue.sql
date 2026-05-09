-- 持久化队列表 - 替代内存队列，确保进程崩溃时数据不丢失
-- 迁移文件: 003_persistence_queue.sql

CREATE TABLE IF NOT EXISTS persistence_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command_type TEXT NOT NULL,
    payload TEXT NOT NULL,  -- JSON 格式
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending', 'processing', 'completed', 'failed')),
    priority INTEGER DEFAULT 0,  -- 优先级（数字越大优先级越高）
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
);

-- 索引：按状态和创建时间查询（FIFO）
CREATE INDEX IF NOT EXISTS idx_persistence_queue_status_created
ON persistence_queue(status, created_at);

-- 索引：按优先级排序
CREATE INDEX IF NOT EXISTS idx_persistence_queue_priority
ON persistence_queue(priority DESC, created_at);

-- 索引：清理已完成任务
CREATE INDEX IF NOT EXISTS idx_persistence_queue_completed
ON persistence_queue(completed_at)
WHERE status IN ('completed', 'failed');

-- 触发器：自动清理 7 天前的已完成任务
CREATE TRIGGER IF NOT EXISTS cleanup_old_completed_tasks
AFTER INSERT ON persistence_queue
WHEN (SELECT COUNT(*) FROM persistence_queue WHERE status IN ('completed', 'failed')) > 1000
BEGIN
    DELETE FROM persistence_queue
    WHERE status IN ('completed', 'failed')
    AND completed_at < datetime('now', '-7 days')
    LIMIT 100;
END;
