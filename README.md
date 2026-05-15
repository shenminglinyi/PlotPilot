# PlotPilot（墨枢）

<p align="center">
  <img src="docs/plotpilot-readme.256.png" alt="PlotPilot 墨枢" width="120" />
</p>

<p align="center">
  <strong>开源叙事引擎内核</strong>
</p>

<p align="center">
  长篇 AI 创作的基础设施基石 — 持久记忆 · 知识图谱 · 自动推进流水线 · 可扩展生态
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.9%2B-3776AB?style=flat&logo=python&logoColor=white" alt="Python"></a>
  <a href="https://vuejs.org/"><img src="https://img.shields.io/badge/Vue-3.5-4FC08D?style=flat&logo=vuedotjs&logoColor=white" alt="Vue"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.109%2B-009688?style=flat&logo=fastapi&logoColor=white" alt="FastAPI"></a>
  <a href="https://github.com/shenminglinyi/PlotPilot/releases"><img src="https://img.shields.io/github/v/release/shenminglinyi/PlotPilot?style=flat&logo=github&color=6e40c9" alt="Release"></a>
  <a href="https://github.com/shenminglinyi/PlotPilot/stargazers"><img src="https://img.shields.io/github/stars/shenminglinyi/PlotPilot?style=flat&logo=github" alt="Stars"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0%20%2B%20Commons%20Clause-D22128?style=flat&logo=apache&logoColor=white" alt="License"></a>
</p>

---

<p align="center">
  <img src="docs/screenshots/workbench-writing.png" alt="工作台 — 写作区与知识图谱" width="49%" />
  <img src="docs/screenshots/workbench-dag.png" alt="工作台 — 故事线 DAG 与人物设定" width="49%" />
</p>

---

## 这是什么

PlotPilot 是一个**叙事引擎内核（Narrative Engine Kernel）**，不是聊天式写作助手。

大多数 AI 写作工具解决的是"生成一段文字"的问题。PlotPilot 解决的是一个更难的工程问题：

> **如何让 AI 系统在数十万字的叙事跨度里，维持人物一致性、因果链完整性、伏笔闭合率，并在无人值守的条件下持续推进？**

这不是提示词优化问题，而是**系统工程问题**。PlotPilot 的答案是：构建一套完整的叙事状态管理基础设施，让 LLM 只做它最擅长的事——在结构化上下文的约束下生成高质量文本，其余的全部由引擎接管。

本仓库是这套基础设施的**开源内核**。上层生态（垂直应用、编辑器插件、云服务）均以此为基石构建。

---

## 内核架构

PlotPilot 内核由五个相互协作的子系统构成：

### 1. 叙事状态机（Narrative State Machine）

引擎在任意时刻都持有完整的叙事快照，包含：

- **Story Bible**：人物档案（含 POV 防火墙、登场频率调度）、地点图、世界设定三元组
- **章级摘要链**：每章生成后自动提炼的压缩摘要，构成跨章上下文骨架
- **叙事事件流**：关键事件的时序登记表，支持因果链追溯
- **故事线 DAG**：多故事线的有向无环图，可视化分支与汇合点
- **伏笔注册表**：钩子（Hook）的开启、悬置、消费状态完整追踪

任何一次章节生成，引擎都会从上述快照中动态装配上下文窗口，而非依赖模型自身的"记忆"。

### 2. 向量语义检索层（Vector Retrieval Layer）

引擎维护两条并行索引：

- **章内容索引**：基于 FAISS / ChromaDB 的本地向量库，对所有已写章节做语义切片索引
- **三元组索引**：从正文中自动抽取的 `(主体, 关系, 客体)` 三元组，支持结构化与语义混合查询

生成时，引擎通过当前场景语义自动召回相关历史内容，注入上下文，消除"模型失忆"问题。嵌入服务支持 OpenAI 兼容 API（轻量）和本地 `sentence-transformers`（离线/高性能）两种模式。

### 3. 自动驾驶守护进程（Autopilot Daemon）

这是引擎最核心的系统组件。守护进程以阶段状态机的方式推进整部小说的生成：

```
宏观规划（部 / 卷 / 幕结构）
    └─▶ 幕级节拍规划（Beat Sheet 生成）
            └─▶ 章节生成循环
                    ├─▶ 上下文装配
                    ├─▶ LLM 调用（流式）
                    ├─▶ 章末管线（摘要 / 事件 / 三元组 / 伏笔）
                    ├─▶ 向量索引更新
                    ├─▶ 张力评分 & 文风检测
                    └─▶ [人工审阅节点] → 继续 / 重写 / 中止
```

关键工程特性：
- **熔断保护**：连续失败超过阈值自动暂停，附带诊断信息
- **单写者路由（Write Dispatch）**：所有 SQLite 写操作经由统一调度器串行执行，消除并发写冲突
- **SSE 实时推流**：生成进度、Token 消耗、当前阶段、错误信息全部通过 Server-Sent Events 实时推送到前端
- **检查点快照**：阶段推进前自动存档，支持从任意检查点恢复

### 4. 提示词策略层（Prompt Strategy Layer）

引擎暴露 **20+ 独立提示接点**，每个接点均可通过 `prompt_packages/` 下的 YAML 配置文件独立覆写：

| 接点类型 | 包含接点 |
|----------|----------|
| 规划类 | `planning-main-plot-suggest` · `planning-quick-macro` |
| 生成类 | `scene-director` · `chapter-narrative-sync` |
| 知识类 | `bible-all` · `bible-characters` · `bible-locations` · `bible-worldbuilding` |
| 分析类 | `style-analysis` · `tension-analysis-diagnosis` |

每个提示包支持独立配置：系统提示、声线锚点、节拍约束、字数层级、记忆铁律、模型参数（temperature / top_p / max_tokens）。切换任务类型（短篇 / 超长篇 / 剧本 / 标书）只需替换提示包，引擎逻辑不变。

### 5. 质量监控子系统（Quality Monitor）

引擎内置叙事质量的量化监控，不依赖人工逐章审阅：

- **张力心电图**：每章生成后计算张力评分（0–10），历史曲线持久化，低谷自动触发诊断
- **文风相似度检测**：基于向量余弦相似度计算当前章节与风格基准的偏离程度
- **漂移告警 + 定向修写**：偏离超过阈值时，引擎不回滚章节，而是触发定向修写任务，保留已有进度
- **陈词滥调扫描**：规则库 + 语义相似度双重检测，标记高频套路表达

---

## 内核与生态

```
PlotPilot 内核（本仓库）
        │
        ├── 叙事状态机
        ├── 向量语义检索层
        ├── 自动驾驶守护进程
        ├── 提示词策略层（20+ 接点）
        └── 质量监控子系统
                │
                ▼
        REST API（FastAPI · v1 · 版本化）
                │
        ┌───────┴──────────────────────┐
        │                              │
  官方工作台前端               生态扩展层（基于内核）
  Vue 3 · TypeScript           ├── 垂直领域工具
  Naive UI · ECharts            │   （剧本/游戏剧情/IP 衍生……）
  Tauri 桌面客户端              ├── 第三方前端 / 编辑器插件
                                ├── 自定义提示词包
                                └── 云服务 / SaaS（需遵守许可证）
```

内核提供稳定的 REST API 边界；所有生态扩展均通过提示词包、工作流插件或上层应用的方式叠加能力，内核本身不感知。如果你在用内核做二创，欢迎各位大佬私信主播加入生态团队！

---

## 技术选型说明

| 层 | 技术 | 选型理由 |
|----|------|----------|
| 后端框架 | FastAPI + uvicorn | 原生异步 + 自动 OpenAPI 文档，SSE 支持开箱即用 |
| 架构范式 | DDD 四层（domain / application / infrastructure / interfaces） | 领域逻辑与技术实现严格隔离，生态扩展不污染内核 |
| AI 接入 | OpenAI 兼容协议 / Anthropic Claude / 火山方舟 Doubao | 统一接口抽象，模型切换不改业务代码 |
| 向量存储 | ChromaDB（默认）/ FAISS | 本地部署，零外部依赖，冷启动快 |
| 嵌入模型 | OpenAI 兼容 API / 本地 `bge-small-zh-v1.5` | 在线轻量与离线高性能双模式 |
| 主数据库 | SQLite + Write Dispatch 单写者路由 | 嵌入式零依赖，并发写冲突由调度层解决 |
| 前端 | Vue 3 + TypeScript + Vite + Naive UI + ECharts | 组件类型安全，知识图谱与 DAG 可视化由 ECharts 驱动 |
| 桌面客户端 | Tauri（Rust） | 比 Electron 内存占用低 80%+，原生系统集成 |

---

## 快速开始

### 方式一：一键启动（Windows，无需安装 Python）

1. 将 `python-3.11.9-embed-amd64.zip` 放入 `tools/` 目录（仅首次）
2. 双击 `tools/plotpilot.bat`

启动器自动完成：环境自检 → 创建虚拟环境 → 安装依赖（自动切换国内镜像源）→ 启动服务 → 打开浏览器。后续启动直接双击。

> 支持 `tools\plotpilot.bat pack` 打包整个项目分享给他人，对方双击即用。

### 方式二：桌面安装版（Windows · Tauri）

前往 [GitHub Releases](https://github.com/shenminglinyi/PlotPilot/releases) 下载最新安装包，内含冻结后端，无需单独安装 Python。

构建流程见 [docs/BUILD_INSTALLER.md](docs/BUILD_INSTALLER.md)。

---

## 开发者文档

**环境要求**：Python 3.9+、Node.js 18+

```bash
# 后端 — Windows
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env    # 填写 LLM 凭证
uvicorn interfaces.main:app --host 127.0.0.1 --port 8005 --reload
```

```bash
# 后端 — Linux / macOS
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn interfaces.main:app --host 127.0.0.1 --port 8005 --reload
```

```bash
# 前端（另开终端）
cd frontend && npm install && npm run dev
```

| 地址 | 说明 |
|------|------|
| `http://127.0.0.1:8005` | 后端 API |
| `http://127.0.0.1:8005/docs` | OpenAPI 交互文档 |
| `http://localhost:3000` | 前端开发服务器 |

生产构建后前端由 FastAPI 静态托管（`frontend/dist`），也可独立部署。

---

## 环境变量

| 变量 | 说明 |
|------|------|
| `ANTHROPIC_API_KEY` / `ARK_API_KEY` | 至少配置一个 LLM 凭证 |
| `EMBEDDING_SERVICE` | `openai`（默认）或 `local`（需额外安装模型，见 `requirements-local.txt`） |
| `CORS_ORIGINS` | 生产环境前端域名，逗号分隔 |
| `DISABLE_AUTO_DAEMON` | 设为 `1` 禁止启动时自动拉起守护进程 |
| `LOG_LEVEL` / `LOG_FILE` | 日志级别与路径 |

完整说明见 [`.env.example`](.env.example)。

---

## 架构目录

```
（项目根目录）/
├── domain/                 # 领域层 — 核心业务逻辑，零外部依赖
│   ├── novel/             # 小说聚合根、章节实体、故事线、伏笔注册表
│   ├── bible/             # 设定库聚合根、人物（POV 防火墙）、地点、时间线
│   ├── knowledge/         # 知识三元组、故事知识图
│   ├── ai/                # LLM 服务接口定义、提示词值对象、Token 统计
│   └── shared/            # 共享内核（基类、异常、领域事件）
│
├── application/           # 应用层 — 用例编排，协调 domain 与 infrastructure
│   ├── engine/            # AI 生成服务、自动驾驶守护进程、上下文装配器
│   ├── blueprint/         # 宏观规划（部-卷-幕）、幕级规划（Beat Sheet）
│   ├── world/             # Bible 管理、知识图谱构建、人物关系图
│   ├── audit/             # 章节审阅、宏观重构、陈词滥调扫描
│   ├── analyst/           # 文风分析、张力分析、漂移检测
│   └── workflows/         # 工作流编排（章后管线、检查点快照）
│
├── infrastructure/        # 基础设施层 — 技术实现，可替换
│   ├── ai/                # LLM 客户端、ChromaDB/FAISS 向量存储、嵌入服务
│   └── persistence/       # SQLite 仓储实现、Write Dispatch 单写者调度器
│
└── interfaces/            # 接口层 — 外部边界
    └── api/v1/            # REST API（FastAPI），按子域分路由
        ├── core/          # 小说 / 章节 CRUD
        ├── engine/        # 生成 / 自动驾驶 / SSE 推流
        ├── world/         # Bible / 知识图谱
        ├── blueprint/     # 规划
        ├── audit/         # 审阅
        └── analyst/       # 分析
```

完整设计与分层说明见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

---

## 测试

```bash
pytest tests/ -v
# 含覆盖率报告
pytest tests/ --cov=. --cov-report=term-missing
```

---

## 贡献指南

1. Fork 本仓库
2. 新建分支：`git checkout -b feat/your-feature`
3. 提交信息建议遵循 [Conventional Commits](https://www.conventionalcommits.org/)
4. 推送并发起 Pull Request

架构与分层说明见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)；其余文档索引见 [docs/README.md](docs/README.md)。

---

## 加入我们

引擎在持续演进，我们也在寻找对叙事工程感兴趣的同行。

**当前关注方向**：内核引擎研发、生态应用构建、提示词工程、前端工作台

如果你对"用工程化手段解决创作问题"这件事感兴趣，欢迎来直播间转一圈，大概就能判断这个项目的调性：

- **抖音**：搜索直播间 **91472902104**（每晚约 21:00 随缘开播）
- **联系方式**：直播间私信附简历即可

---

## 许可证

本项目采用 **Apache License 2.0**，并附加 **Commons Clause** 条件限制。

- **允许**：学习、修改、非商业内部部署、基于内核的生态扩展（非营利）
- **禁止**：将本项目（含修改版）封装为收费 SaaS、打包售卖源码或作为收费产品的增值服务

详见 [LICENSE](LICENSE)。

---

## Star History

<a href="https://www.star-history.com/?repos=shenminglinyi%2FPlotPilot&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=shenminglinyi/PlotPilot&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=shenminglinyi/PlotPilot&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=shenminglinyi/PlotPilot&type=date&legend=top-left" />
 </picture>
</a>
