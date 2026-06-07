# PlotPilot（墨枢）日志系统使用指南

> 产品对外名称为 **PlotPilot（墨枢）**。下文中的 `logs/plotpilot.log` 等为环境变量默认路径里的**历史文件名**，与运行时配置一致即可。

## 快速开始

### 1. 配置日志级别

在 `.env` 文件中设置：

```bash
LOG_LEVEL=INFO      # 可选: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FILE=logs/plotpilot.log
LOG_COLOR=auto      # auto / always / never
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5
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
14:30:22 INFO  api.main               ------------------------------------------------
14:30:22 INFO  api.main               PlotPilot backend starting - release 1.0.2
14:30:22 INFO  api.main                 Build:       build-20260209-1200-c4d2
14:30:22 INFO  api.main                 Log level:   INFO
14:30:22 INFO  api.main                 Log file:    logs/plotpilot.log
14:30:22 INFO  api.main               ------------------------------------------------
```

### 3. 查看日志

**实时查看日志：**

```bash
python scripts/tail_logs.py
```

**查看最近 100 行：**

```bash
python scripts/tail_logs.py logs/plotpilot.log 100
```

**使用系统命令：**

```bash
# Windows PowerShell
Get-Content logs/plotpilot.log -Tail 50 -Wait

# Git Bash
tail -f logs/plotpilot.log
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
14:30:22 INFO  api.main               PlotPilot backend starting - release 1.0.2
14:30:23 INFO  api.main               FastAPI application started successfully
14:30:23 INFO  api.main               Registered 87 routes
```

### 自动驾驶守护进程日志

```
14:30:25 INFO  runtime.daemon_host    Autopilot daemon started
14:30:25 INFO  runtime.daemon_host    Poll interval: 5s
14:30:30 INFO  runtime.daemon_host    Loop #1: 发现 2 本活跃小说
14:30:30 INFO  runtime.writing        [novel-123] 开始写作 (第 2 幕)
14:30:30 INFO  runtime.writing        [novel-123] 开始写第 15 章：主角突破境界...
14:30:45 INFO  runtime.writing        [novel-123] 节拍 1/5 完成: 523 字
14:31:51 INFO  runtime.writing        [novel-123] 第 15 章完成：2525 字 (共 15/50 章)
```

### 错误日志

```
14:32:15 ERROR runtime.daemon_host    [novel-456] 处理失败: Connection timeout
14:32:15 WARN  runtime.daemon_host    [novel-456] 连续失败 1/3 次
14:32:25 ERROR runtime.daemon_host    [novel-456] 连续失败 3 次，挂起等待急救
```

文件日志会使用更适合检索的格式，包含毫秒、进程号、模块名与代码位置，例如：

```
2026-04-06 14:32:15.128 ERROR pid=18420  runtime.daemon_host          daemon_host.py:606       [novel-456] 处理失败: Connection timeout
```

## 调试技巧

### 查找特定小说的日志

```bash
# Windows PowerShell
Select-String -Path logs/plotpilot.log -Pattern "novel-123"

# Git Bash
grep "novel-123" logs/plotpilot.log
```

### 只看错误日志

```bash
grep -E "ERROR|WARNING" logs/plotpilot.log
```

### 统计章节完成数

```bash
grep "章完成" logs/plotpilot.log | wc -l
```

## 监控建议

1. **生产环境**: 使用 `LOG_LEVEL=INFO`，定期检查 ERROR 和 WARNING
2. **开发环境**: 使用 `LOG_LEVEL=DEBUG`，查看详细执行流程
3. **性能调优**: 关注 "耗时过长" 警告
4. **稳定性监控**: 关注熔断器触发、连续失败次数

