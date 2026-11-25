# 日志与健康检查

运行时日志由 `interfaces/api/middleware/logging_config.py` 统一配置。环境变量的完整默认值以根目录 [`.env.example`](../.env.example) 为准。

## 配置

```dotenv
LOG_LEVEL=INFO
LOG_FILE=logs/plotpilot.log
```

`LOG_LEVEL` 支持 `DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL`。本地定位问题时临时使用 `DEBUG`；常规运行使用 `INFO`，避免长期产生大量详细日志。

## 启动与检查

从仓库根目录启动与前端代理一致的后端：

```bash
uvicorn interfaces.main:app --host 127.0.0.1 --port 8005 --reload
```

也可直接执行 `python interfaces/main.py`，该入口固定监听 `0.0.0.0:8000`，主要用于独立调试。开发前端默认把 `/api` 代理到 `127.0.0.1:8005`，因此日常联调应使用上面的 uvicorn 命令。

查看日志：

```bash
# 默认跟踪 logs/plotpilot.log
python scripts/tail_logs.py

# 指定文件和最近行数
python scripts/tail_logs.py logs/plotpilot.log 100

# 检查默认后端地址的健康状态
python scripts/check_health.py
```

系统命令也可以直接跟踪文件：

```powershell
Get-Content logs/plotpilot.log -Tail 50 -Wait
Select-String -Path logs/plotpilot.log -Pattern "ERROR|WARNING"
```

## 启动信息

后端启动日志会记录发布版本、构建 ID、Python 版本、工作目录、日志级别与日志文件。健康接口 `GET /health` 返回当前版本、构建 ID、运行时长和守护进程状态，可用于确认“请求到的是哪一个进程”，避免端口残留导致误判。

## 故障定位顺序

1. 请求 `/health`，确认版本、构建 ID 和守护进程状态。
2. 查看本次启动横幅，确认实际加载的日志路径和 Python 环境。
3. 用小说 ID、trace ID 或异常类型过滤日志，而不是上传整份日志。
4. AI 调用链问题使用 `python scripts/export_ai_traces.py <novel_id>` 导出结构化 trace。
5. 分享日志前移除 API Key、私有网关地址、用户作品正文与本机路径。

日志目录和 SQLite 数据均属于运行时数据，不应提交到 Git。
