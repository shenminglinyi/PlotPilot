# PlotPilot（墨枢）

<img width="400" height="300" alt="微信图片_20260415003740_893_102" src="https://github.com/user-attachments/assets/71f083b8-a787-4eaf-a927-b15185a4f317" />

> AI 驱动的长篇小说创作平台 — 自动驾驶写作、知识图谱管理、风格分析一体化。

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3.5-green.svg)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-teal.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

---

## 产品亮点

**全托管自动驾驶**：后台守护进程按阶段自动推进 宏观规划 → 幕级节拍 → 章节生成 → 章末审阅，支持熔断保护、人工审阅节点与 SSE 实时状态推流。无需逐章手动触发，启动后持续写完目标字数。

**统一章后管线**：章节生成结束后，一次 LLM 调用同时完成摘要提取、关键事件识别、人物三元组构建、伏笔注册与消费检测、故事线进展更新，最终写入知识库并建立向量索引。HTTP 手动保存与自动驾驶走同一套逻辑，永不漂移。

**多层记忆体系**：Story Bible（人物、地点、世界设定）、分章摘要、本地向量语义检索、伏笔台账、叙事事件与时间轴，多路信息协同注入生成上下文，兼顾长篇一致与局部鲜活。

**文风与张力监控**：章节级文风相似度与漂移告警；章末自动打分张力值（0–10），历史张力曲线实时可查；文风偏离时执行定向修写，不回滚章节。

**超过 20 个提示接点**：集中式提示词配置，角色声线锚点、节拍约束、字数层级、记忆引擎铁律等策略独立配置，支持短篇、超长篇、剧本、标书等多种文体切换。

**全功能工作台**：写作区实时预览、章节状态与审阅面板、张力心电图、伏笔账本、知识图谱、监控大盘与 LLM 控制台一体整合。

---

## 一键启动（Windows）

项目提供开箱即用的图形化启动器，**无需提前安装 Python、无需命令行**：

1. 将 `python-3.11.9-embed-amd64.zip` 放入 `tools/` 目录（首次使用）
2. 双击 `tools/aitext.bat`

启动器将自动完成：环境自检 → 创建虚拟环境 → 安装依赖（国内镜像源自动切换）→ 启动后端服务 → 打开浏览器。后续启动直接双击，秒开。

> 也支持 `aitext.bat pack` 打包整个项目分享给他人，对方双击即用。

---

## 开发者启动

**环境要求**：Python 3.9+、Node.js 18+

```bash
# 后端
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env    # 填写 LLM 凭证
uvicorn interfaces.main:app --host 127.0.0.1 --port 8005 --reload

# 前端（另开终端）
cd frontend && npm install && npm run dev
```

后端 API：`http://127.0.0.1:8005` · 文档：`http://127.0.0.1:8005/docs` · 前端：`http://localhost:3000`

生产构建后前端由 FastAPI 静态托管，无需单独部署前端服务。

---

## 技术栈

| 层 | 技术 |
|---|---|
| 后端框架 | FastAPI + uvicorn，DDD 四层架构 |
| AI 模型 | OpenAI 兼容协议 / Anthropic Claude / 火山方舟 Doubao |
| 向量存储 | 本地 FAISS（无需容器，开箱即用） |
| 嵌入模型 | OpenAI 兼容 API（默认）/ 本地 sentence-transformers |
| 主数据库 | SQLite（单文件，便于备份与迁移） |
| 前端 | Vue 3 + TypeScript + Vite + Naive UI + ECharts |

---

## 环境变量

| 变量 | 说明 |
|---|---|
| `ANTHROPIC_API_KEY` / `ARK_API_KEY` | 至少配置一个 LLM 凭证 |
| `EMBEDDING_SERVICE` | `openai`（默认）或 `local`（本地需额外安装约 2GB 模型） |
| `CORS_ORIGINS` | 生产环境前端域名，逗号分隔 |
| `DISABLE_AUTO_DAEMON` | 设为 `1` 禁止启动时自动拉起守护进程 |
| `LOG_LEVEL` / `LOG_FILE` | 日志级别与路径，默认 `INFO` / `logs/aitext.log` |

完整说明见 `.env.example`。

---

## 许可证

本项目采用 **Apache License 2.0**，并附加 **Commons Clause** 条件限制。

允许学习、修改与非商业内部部署；**严禁**将本项目（含修改版）用于任何营利行为，包括封装收费 SaaS、打包售卖源码或作为收费产品的增值服务。详见 [LICENSE](LICENSE)。
