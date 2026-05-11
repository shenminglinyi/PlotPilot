# PlotPilot（墨枢）日志系统使用指南

> 产品对外名称为 **PlotPilot（墨枢）**。下文中的 `logs/aitext.log` 等为环境变量默认路径里的**历史文件名**，与运行时配置一致即可。

## 快速开始

### 1. 配置日志级别

在 `.env` 文件中设置：

```bash
LOG_LEVEL=INFO      # 可选: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FILE=logs/aitext.log
```

### 2. 启动后端

推荐（与根目录 README 一致，端口 **8005**）：

```bash
uvicorn interfaces.main:app --host 127.0.0.1 --port 8005 --reload
```

也可直接运行 FastAPI 入口模块（默认 **`0.0.0.0:8000`**，与上式端口不同）：

```bash
python interfaces/main.py
```

如需与前端开发代理一致，请改用 uvicorn 并指定 `--port 8005`，或修改 `interfaces/main.py` 末尾 `uvicorn.run` 的端口。

启动时会看到：

```
================================================================================
🚀 BACKEND STARTING - Version: 20260406-143022
   Timestamp: 2026-04-06 14:30:22
   Log Level: INFO
   Log File: logs/aitext.log
   Python: 3.11.0
   Working Dir: <项目根目录>
================================================================================
```

### 3. 查看日志

**实时查看日志：**

```bash
python scripts/tail_logs.py
```

**查看最近 100 行：**

```bash
python scripts/tail_logs.py logs/aitext.log 100
```

**使用系统命令：**

```bash
# Windows PowerShell
Get-Content logs/aitext.log -Tail 50 -Wait

# Git Bash
tail -f logs/aitext.log
```

### 4. 健康检查

```bash
python scripts/check_health.py
```

## 日志级别说明


| 级别           | 用途     | 示例              |
| ------------ | ------ | --------------- |
| **DEBUG**    | 详细调试信息 | 每个循环的处理时间、变量值   |
| **INFO**     | 常规运行信息 | 启动消息、阶段变更、章节完成  |
| **WARNING**  | 警告信息   | 熔断器触发、文风漂移、耗时过长 |
| **ERROR**    | 错误信息   | 处理失败、连续错误       |
| **CRITICAL** | 严重错误   | 系统崩溃级别错误        |


## 日志内容示例

### 后端启动日志

```
14:30:22 [INFO] __main__ - 🚀 BACKEND STARTING - Version: 20260406-143022
14:30:23 [INFO] __main__ - ✅ FastAPI application started successfully
14:30:23 [INFO] __main__ - 📊 Registered 87 routes
```

### 自动驾驶守护进程日志

```
14:30:25 [INFO] autopilot_daemon - 🚀 Autopilot Daemon Started
14:30:25 [INFO] autopilot_daemon -    Poll Interval: 5s
14:30:30 [INFO] autopilot_daemon - 🔄 Loop #1: 发现 2 本活跃小说
14:30:30 [INFO] autopilot_daemon - [novel-123] ✍️  开始写作 (第 2 幕)
14:30:30 [INFO] autopilot_daemon - [novel-123] 📖 开始写第 15 章：主角突破境界...
14:30:45 [INFO] autopilot_daemon - [novel-123]    ✅ 节拍 1/5 完成: 523 字
14:31:51 [INFO] autopilot_daemon - [novel-123] 🎉 第 15 章完成：2525 字 (共 15/50 章)
```

### 错误日志

```
14:32:15 [ERROR] autopilot_daemon - ❌ [novel-456] 处理失败: Connection timeout
14:32:15 [WARNING] autopilot_daemon - ⚠️  [novel-456] 连续失败 1/3 次
14:32:25 [ERROR] autopilot_daemon - 🚨 [novel-456] 连续失败 3 次，挂起等待急救
```

## 调试技巧

### 查找特定小说的日志

```bash
# Windows PowerShell
Select-String -Path logs/aitext.log -Pattern "novel-123"

# Git Bash
grep "novel-123" logs/aitext.log
```

### 只看错误日志

```bash
grep -E "ERROR|WARNING" logs/aitext.log
```

### 统计章节完成数

```bash
grep "章完成" logs/aitext.log | wc -l
```

## 监控建议

1. **生产环境**: 使用 `LOG_LEVEL=INFO`，定期检查 ERROR 和 WARNING
2. **开发环境**: 使用 `LOG_LEVEL=DEBUG`，查看详细执行流程
3. **性能调优**: 关注 "耗时过长" 警告
4. **稳定性监控**: 关注熔断器触发、连续失败次数

