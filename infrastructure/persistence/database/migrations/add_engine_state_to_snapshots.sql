-- 扩展 novel_snapshots 表，加入引擎状态字段
-- 用于统一 Checkpoint 和 Snapshot 系统
-- 对应 Task 1: 扩展数据库表结构
--
-- 注意：此迁移是幂等的，可以安全地多次执行
-- 如果列已存在，SQLite 会报错，但这是预期的行为

-- 添加引擎状态字段
ALTER TABLE novel_snapshots ADD COLUMN story_state TEXT DEFAULT '{}';
ALTER TABLE novel_snapshots ADD COLUMN character_masks TEXT DEFAULT '{}';
ALTER TABLE novel_snapshots ADD COLUMN emotion_ledger TEXT DEFAULT '{}';
ALTER TABLE novel_snapshots ADD COLUMN active_foreshadows TEXT DEFAULT '[]';
ALTER TABLE novel_snapshots ADD COLUMN outline TEXT DEFAULT '';
ALTER TABLE novel_snapshots ADD COLUMN recent_chapters_summary TEXT DEFAULT '';
