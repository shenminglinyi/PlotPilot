# PlotPilot（墨枢）架构

> **PlotPilot（墨枢）** 长篇小说创作平台源代码，采用 DDD（领域驱动设计）四层架构。产品说明与启动入口见根目录 [README.md](../README.md)。

## 系统概览

- **输入**：书名、梗概、类型、章数、每章目标字数、风格提示。
- **输出**：完整的小说项目，包含 Bible（设定库）、Outline（大纲）、Beat Sheets（章纲）、Chapters（正文）。

## DDD 四层架构

```
（项目根目录）/
├── domain/                 # 领域层 - 核心业务逻辑
│   ├── novel/             # 小说聚合根、章节实体、故事线
│   ├── bible/             # 设定库聚合根、人物、地点、世界设定
│   ├── cast/              # 人物关系图
│   ├── knowledge/         # 知识图谱三元组
│   ├── ai/                # AI 服务接口定义
│   └── shared/            # 共享内核（基类、异常、事件）
│
├── application/           # 应用层 - 用例编排
│   ├── core/              # 小说/章节基础服务
│   ├── blueprint/         # 规划服务（宏观规划、幕级规划）
│   ├── engine/            # 生成引擎、自动驾驶守护进程
│   ├── world/             # Bible、知识图谱服务
│   ├── audit/             # 审阅、宏观重构服务
│   ├── analyst/           # 文风分析、张力分析服务
│   └── workflows/         # 工作流编排
│
├── infrastructure/        # 基础设施层 - 技术实现
│   ├── ai/                # LLM 客户端、向量存储、嵌入服务
│   └── persistence/       # SQLite 仓储实现、数据库连接
│
└── interfaces/            # 接口层 - 外部接口
    └── api/               # REST API 路由（FastAPI）
        └── v1/            # API 版本化
            ├── core/      # 小说/章节 API
            ├── world/     # Bible/知识图谱 API
            ├── blueprint/ # 规划 API
            ├── engine/    # 生成/自动驾驶 API
            ├── audit/     # 审阅 API
            └── analyst/   # 分析 API
```

## 核心模块

### Domain 层

| 模块 | 职责 |
|------|------|
| `novel/` | 小说聚合根、章节实体、故事线、伏笔注册表 |
| `bible/` | 设定库、人物实体（含 POV 防火墙）、地点、时间线 |
| `knowledge/` | 知识三元组、故事知识 |
| `ai/` | LLM 服务接口、提示词值对象、Token 使用统计 |

### Application 层

| 模块 | 职责 |
|------|------|
| `core/` | 小说/章节的 CRUD 服务 |
| `blueprint/` | 宏观规划（部-卷-幕）、幕级规划（章节规划）|
| `engine/` | AI 生成服务、自动驾驶守护进程、上下文构建 |
| `world/` | Bible 管理、知识图谱构建、人物关系 |
| `audit/` | 章节审阅、宏观重构、陈词滥调扫描 |

### Infrastructure 层

| 模块 | 职责 |
|------|------|
| `ai/llm_client.py` | 方舟 SDK 封装 |
| `ai/chromadb_vector_store.py` | ChromaDB 向量存储 |
| `ai/local_embedding_service.py` | 本地嵌入模型 |
| `persistence/database/` | SQLite 仓储实现 |

## 数据流

### 自动驾驶模式

```
1. 宏观规划 → 生成部-卷-幕结构
2. 幕级规划 → 为当前幕生成章节大纲
3. 章节生成 → 节拍放大器生成正文
4. 章后管线 → 向量存储、伏笔提取、知识图谱更新
5. 审阅审计 → 文风检测、一致性检查
6. 循环至完成
```

### 人工辅助模式

```
用户创建小说 → 手动规划 → 手动撰写 → AI 辅助生成
```

## 入口点

在**仓库根目录**（含 `application/`、`interfaces/`；本文件在 `docs/` 下）执行：

```bash
# 推荐：与 README 一致，端口 8005
uvicorn interfaces.main:app --host 127.0.0.1 --port 8005 --reload
```

可选方式：

```bash
# 直接运行 FastAPI 模块（默认 0.0.0.0:8000，与 README 的 8005 不同，需自行改端口或改用 uvicorn）
python interfaces/main.py

# 自动驾驶守护进程（当前维护入口）
python scripts/start_daemon.py
```

## Web 前端（Vue 3）

- **目录**：`frontend/`
- **技术栈**：Vue 3 + Vite + Naive UI + ECharts
- **默认端口**：3000
- **API 代理**：`/api` → `http://localhost:8005`

```bash
cd frontend
npm install
npm run dev
```

## 测试

```bash
# 运行所有测试
python -m pytest tests -v

# 单元测试
python -m pytest tests/unit -v

# 集成测试
python -m pytest tests/integration -v
```

## 环境变量

以根目录 **[.env.example](../.env.example)** 为准（方舟 `ARK_*`、嵌入 `EMBEDDING_*`、`LOG_*`、`PLOTPILOT_PROD_DATA_DIR` 等；旧名 `AITEXT_PROD_DATA_DIR` 仍兼容）。复制为 `.env` 后按需填写，勿提交密钥。

## 数据库与数据目录

- **主数据库**：默认 SQLite 文件名为 `data/plotpilot.db`（旧版为 `aitext.db`，`get_db_path()` 会自动沿用）；实际目录由 `application.paths.DATA_DIR` 解析（未设置 `PLOTPILOT_PROD_DATA_DIR` / 旧名 `AITEXT_PROD_DATA_DIR` 且非冻结运行时指向仓库内 `data/`）。
- **向量存储**：默认在 `data/chromadb/` 下持久化（实现为本地 FAISS + 元数据，与 `.env` 中 `VECTOR_STORE_TYPE=chromadb` 对应）。
- **应用日志**：默认 `logs/plotpilot.log`（由 `LOG_FILE` 控制，见 `.env.example`）。
