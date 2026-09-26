-- 添加最近一次自动驾驶错误摘要字段
-- 连续失败挂起时记录最近一次异常的紧凑摘要，随 GET /autopilot/{id}/status 暴露给前端
-- （AutopilotPanel 恢复提示区展示），避免用户只能去守护进程日志翻真实原因。

ALTER TABLE novels ADD COLUMN last_error_summary TEXT NOT NULL DEFAULT '';
