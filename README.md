# PlotPilot（墨枢）


<img width="400" height="300" alt="微信图片_20260415003740_893_102" src="https://github.com/user-attachments/assets/71f083b8-a787-4eaf-a927-b15185a4f317" />


> AI 驱动的长篇小说创作平台 — 自动驾驶生成、知识图谱管理、风格分析一体化。

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3.5-green.svg)](https://vuejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-teal.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

- 自动驾驶模式：后台守护进程持续生成章节，支持 SSE 实时流式推送
- Story Bible：人物、地点、世界设定的结构化管理
- 知识图谱：自动提取故事三元组，语义检索历史内容
- 伏笔台账：追踪并自动闭合叙事钩子
- 风格分析：作者声音漂移检测与文体指纹
- 节拍表 & 故事结构：三幕式、章节节拍规划
- DDD 四层架构：domain / application / infrastructure / interfaces

## 技术栈

| 层 | 技术 |
|---|---|
| 后端框架 | FastAPI + uvicorn |
| AI 模型 | Anthropic Claude（主）、ByteDance Ark/Doubao（备） |
| 向量数据库 | Qdrant（可选 ChromaDB） |
| 嵌入模型 | BAAI/bge-small-zh-v1.5（本地） / OpenAI Embedding（可选） |
| 主数据库 | SQLite |
| 前端 | Vue 3 + TypeScript + Vite + Naive UI |
| 状态管理 | Pinia |
| 可视化 | ECharts |

## 快速开始

### 环境要求

- Python 3.9+
- Node.js 18+
- （可选）Docker — 用于启动 Qdrant 向量数据库

### 1. 克隆仓库

```bash
git clone https://github.com/shenminglinyi/PlotPilot.git
cd PlotPilot
```

### 2. 后端配置

```bash
# 创建虚拟环境（推荐）
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，至少填写以下任一 LLM 凭证：
#   ANTHROPIC_API_KEY   — 使用 Claude 模型
#   ARK_API_KEY         — 使用 ByteDance Doubao 模型
```

### 3. 启动向量数据库（可选）

语义检索功能依赖 Qdrant，若不需要可跳过此步骤。

```bash
docker compose up -d
# Qdrant 将运行在 http://localhost:6333
```

### 4. 下载嵌入模型

首次运行需下载本地嵌入模型（约 100 MB）：

```bash
python scripts/utils/download_embedding_model.py
# 或通过 ModelScope 镜像下载（国内推荐）：
python scripts/utils/download_model_via_modelscope.py
```

### 5. 启动后端

```bash
uvicorn interfaces.main:app --host 127.0.0.1 --port 8005 --reload
```

后端 API：http://localhost:8005  
交互文档：http://localhost:8005/docs

### 6. 启动前端

```bash
cd frontend
npm install
npm run dev
# 前端运行在 http://localhost:3000
```

## 环境变量参考

| 变量 | 必填 | 说明 |
|---|---|---|
| `ANTHROPIC_API_KEY` | 二选一 | Anthropic Claude API 密钥 |
| `ARK_API_KEY` | 二选一 | ByteDance Ark/Doubao API 密钥 |
| `ARK_BASE_URL` | 否 | Ark API 地址，默认北京节点 |
| `ARK_MODEL` | 否 | Doubao 模型 ID，默认 `doubao-seed-2-0-mini-260215` |
| `ANTHROPIC_BASE_URL` | 否 | 自建网关或代理地址 |
| `CORS_ORIGINS` | 否 | 生产环境允许的前端域名，逗号分隔；未设置时仅允许 localhost |
| `DISABLE_AUTO_DAEMON` | 否 | 设为 `1` 禁止自动驾驶守护进程在启动时自动运行 |
| `LOG_LEVEL` | 否 | 日志级别，默认 `INFO` |
| `LOG_FILE` | 否 | 日志文件路径，默认 `logs/aitext.log` |

## 系统架构

### DDD 四层架构

```
PlotPilot/
├── domain/          # 领域层：实体、值对象、仓储接口
│   ├── novel/       # 小说、章节、情节弧
│   ├── bible/       # 人物、地点、世界设定
│   ├── cast/        # 角色关系图
│   ├── knowledge/   # 知识三元组
│   └── shared/      # 基础实体、异常、领域事件
│
├── application/     # 应用层：用例编排、工作流、DTO
│   ├── engine/      # 生成引擎、自动驾驶守护进程
│   ├── analyst/     # 声音分析、张力分析、状态机
│   ├── audit/       # 章节审查、宏观重构
│   └── blueprint/   # 节拍表、故事结构规划
│
├── infrastructure/  # 基础设施层：技术实现
│   ├── ai/          # Anthropic / Ark 提供商、ChromaDB、Qdrant
│   └── persistence/ # SQLite 仓储、Schema 迁移
│
├── interfaces/      # 接口层：FastAPI 路由
│   └── api/v1/      # REST API（core / world / engine / audit / analyst）
│
└── frontend/        # Vue 3 前端
```

## 测试

### 运行测试

```bash
# 运行单元测试和集成测试
pytest tests/unit/ tests/integration/ -v

# 带覆盖率报告
pytest tests/unit/ tests/integration/ --cov=. --cov-report=term-missing

# 竞态检测（需安装 pytest-race 或使用 go test -race 类似工具）
pytest tests/ -v
```

## 贡献

1. Fork 项目
2. 创建特性分支：`git checkout -b feat/your-feature`
3. 提交更改：遵循 [Conventional Commits](https://www.conventionalcommits.org/)
4. 推送并创建 Pull Request

---

## 许可证

本项目采用 **Apache License 2.0** 协议，并附加 **Commons Clause** 条件限制。

> ** 核心授权与限制说明：**
> - ** 允许学习与魔改：** 您可以自由地拉取代码、阅读、学习、修改，甚至在您的个人设备或非商业性质的内部团队中部署使用。
> - ** 绝对禁止商业化（Commons Clause）：** 严禁将本项目（包含任何修改版本）用于任何形式的营利行为。这包括但不限于：将其封装为收费 SaaS 网页端、打包售卖源码、作为其他收费产品的引流工具或增值服务等。
> 
> 任何涉及资金交易的使用行为均构成侵权。详细法律条款请参阅项目根目录下的 [LICENSE](LICENSE) 文件。

## 交流与实战演示 (Live & Community)

纸上得来终觉浅。如果你想看这套系统在实际创作中是如何运行的，欢迎来我的直播间蹲点：

- **抖音 ID / 直播间搜索：** [91472902104]
- **直播时间：** 每晚 [9:00] 随缘直播
- **直播内容：** 现场用这套工具写脑洞、改 Bug、看 PR，以及解答大家在本地部署时遇到的一些通识问题。

欢迎真正的创作者和技术同行来直播间找我聊聊！
