-- 005: 持久化队列增强迁移
-- 新增: updated_at列, 僵尸任务恢复索引, updated_at触发器
-- 对应架构治理 P0-12

-- 1. 新增 updated_at 列（如果不存在）
-- SQLite不支持 IF NOT EXISTS 对 ALTER TABLE，使用异常处理
ALTER TABLE persistence_queue ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- 2. 僵尸任务恢复索引
CREATE INDEX IF NOT EXISTS idx_persistence_queue_status_updated
ON persistence_queue(status, updated_at);

-- 3. updated_at 自动更新触发器
CREATE TRIGGER IF NOT EXISTS update_queue_timestamp
AFTER UPDATE ON persistence_queue
FOR EACH ROW
BEGIN
    UPDATE persistence_queue
    SET updated_at = CURRENT_TIMESTAMP
    WHERE id = NEW.id;
END;

-- 4. 已完成任务的定期清理（7天前）
-- 注意：实际清理由 Python 代码执行，此处仅做记录
-- DELETE FROM persistence_queue
-- WHERE status IN ('completed', 'failed')
-- AND completed_at < datetime('now', '-7 days');
