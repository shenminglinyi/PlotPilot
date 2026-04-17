# 贡献指南 · Contributing Guide

> 欢迎来到 PlotPilot（墨枢）！本文档帮助你理解项目架构、贡献代码、扩展功能。
> 无论你是第一次参与开源，还是资深工程师，请先通读本文再动手。

---

## 目录

1. [快速上手](#1-快速上手)
2. [项目架构](#2-项目架构)
3. [各层职责与边界规则](#3-各层职责与边界规则)
4. [如何扩展功能](#4-如何扩展功能)
5. [提示词模板规范](#5-提示词模板规范)
6. [前端开发规范](#6-前端开发规范)
7. [测试规范](#7-测试规范)
8. [PR 流程](#8-pr-流程)
9. [常见问题](#9-常见问题)

---

## 1. 快速上手

```bash
# 克隆项目
git clone https://github.com/your-org/PlotPilot.git
cd PlotPilot

# 后端（Python 3.10+）
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # 填写 API Key

# 启动后端
python cli.py

# 前端（Node 18+）
cd frontend
npm install
npm run dev
```

Windows 用户可直接双击 `tools/aitext.bat`；Linux/macOS 用户运行 `./start.sh`。

---

## 2. 项目架构

PlotPilot 采用 **领域驱动设计（DDD）四层架构**：

```
PlotPilot/
├── domain/          # 领域层：业务规则的核心，不依赖任何外部框架
├── application/     # 应用层：用例编排，协调领域对象
├── infrastructure/  # 基础设施层：数据库、AI Provider、文件存储
├── interfaces/      # 接口层：HTTP API、CLI、WebSocket
└── frontend/        # 前端（Vue 3 + TypeScript）
```

### 依赖方向（严格单向）

```
interfaces  →  application  →  domain
               application  →  infrastructure（通过抽象接口）
interfaces  →  infrastructure（仅通过 dependencies.py 注入）
```

**核心原则：内层不知道外层的存在。**

### 关键目录一览

| 路径 | 说明 |
|------|------|
| `domain/novel/` | 小说、章节、伏笔等核心实体 |
| `domain/bible/` | 世界观（角色、地点、关系）实体 |
| `domain/ai/` | LLM、Embedding、VectorStore 抽象接口 |
| `application/core/` | 小说/章节 CRUD 用例 |
| `application/engine/` | AI 生成引擎（上下文构建、节拍放大、自动驾驶） |
| `application/world/` | 世界观生成（Bible、知识图谱） |
| `application/analyst/` | 叙事分析（张力、文风、实体状态） |
| `application/audit/` | 质量审计（陈词、冲突、宏观重构） |
| `application/blueprint/` | 故事规划（节拍表、连续规划） |
| `application/config.py` | **中央配置**，所有业务常量在此定义 |
| `infrastructure/ai/` | AI Provider 实现（Anthropic、OpenAI、Mock） |
| `infrastructure/persistence/` | SQLite 仓储实现 |
| `interfaces/api/dependencies.py` | **唯一的依赖注入入口** |
| `interfaces/api/v1/` | FastAPI 路由（按领域分目录） |

---

## 3. 各层职责与边界规则

### 3.1 领域层（domain/）

**职责**：定义业务实体、值对象、领域服务、仓储接口。

**规则**：
- ✅ 可以：定义实体、值对象、领域事件、仓储接口（抽象类）
- ❌ 禁止：import FastAPI、SQLAlchemy、requests、任何 infrastructure 模块
- ❌ 禁止：直接操作数据库或调用 HTTP

```python
# ✅ 正确：仓储接口定义在 domain/
class NovelRepository(ABC):
    @abstractmethod
    def save(self, novel: Novel) -> None: ...

# ❌ 错误：直接 import SQLite 实现
from infrastructure.persistence.database.sqlite_novel_repository import SqliteNovelRepository
```

### 3.2 应用层（application/）

**职责**：实现用例（Use Case），协调领域对象与基础设施。

**规则**：
- ✅ 可以：import domain 实体、仓储接口；import infrastructure（通过构造函数注入）
- ✅ 可以：定义 DTO（数据传输对象）
- ❌ 禁止：直接实例化 `SqliteXxxRepository`（应通过构造函数注入）
- ❌ 禁止：import FastAPI、HTTP 相关库

```python
# ✅ 正确：通过构造函数注入仓储
class NovelService:
    def __init__(self, novel_repo: NovelRepository):
        self.novel_repo = novel_repo

# ❌ 错误：直接实例化基础设施
class NovelService:
    def __init__(self):
        self.novel_repo = SqliteNovelRepository(get_database())
```

### 3.3 基础设施层（infrastructure/）

**职责**：实现技术细节——数据库、AI Provider、文件存储、向量库。

**规则**：
- ✅ 可以：实现 domain 定义的仓储接口
- ✅ 可以：封装第三方 SDK（Anthropic、OpenAI、ChromaDB）
- ❌ 禁止：包含业务逻辑（业务逻辑属于 domain/application）

### 3.4 接口层（interfaces/）

**职责**：HTTP API 路由、请求/响应序列化、认证。

**规则**：
- ✅ 可以：import application 服务；通过 `Depends()` 注入
- ✅ 所有依赖**必须**通过 `interfaces/api/dependencies.py` 中的工厂函数注入
- ❌ 禁止：在路由文件中直接 import `infrastructure.*`（违反 DI 原则）
- ❌ 禁止：在路由中写业务逻辑

```python
# ✅ 正确：通过 Depends 注入
@router.get("/{novel_id}")
async def get_novel(
    novel_id: str,
    service: NovelService = Depends(get_novel_service),  # 来自 dependencies.py
):
    ...

# ❌ 错误：直接实例化基础设施
@router.get("/{novel_id}")
async def get_novel(novel_id: str):
    repo = SqliteNovelRepository(get_database())  # 违规！
    ...
```

---

## 4. 如何扩展功能

### 4.1 添加新 AI Provider

1. 在 `domain/ai/services/llm_service.py` 查看 `LLMService` 接口
2. 在 `infrastructure/ai/providers/` 新建 `my_provider.py`，实现接口
3. 在 `infrastructure/ai/provider_factory.py` 注册新 Provider
4. 在 `.env.example` 添加新的环境变量说明

```python
# infrastructure/ai/providers/my_provider.py
from domain.ai.services.llm_service import LLMService

class MyProvider(LLMService):
    def generate(self, prompt: str, **kwargs) -> str:
        # 实现调用逻辑
        ...
```

### 4.2 添加新题材技能（Theme Skill）

题材技能是注入写作管线的提示词增强器，无需改动核心代码：

1. 在 `infrastructure/ai/prompts/prompts_defaults.json` 中添加技能定义：

```json
{
  "key": "my_skill",
  "name": "我的技能",
  "description": "技能说明",
  "compatible_genres": ["xuanhuan", "wuxia"],
  "context_prompt": "写作时注意：...",
  "beat_prompt": "每个节拍需要：...",
  "beat_triggers": "战斗,修炼",
  "audit_checks": ["检查修炼体系逻辑"]
}
```

2. 或通过 API 动态创建（用户自定义技能）：
   `POST /api/v1/novels/{novel_id}/theme-skills/custom`

### 4.3 添加新 API 路由

1. 在 `interfaces/api/v1/` 对应领域目录下新建路由文件
2. 在 `interfaces/api/dependencies.py` 添加对应的工厂函数
3. 在 `interfaces/main.py` 注册路由

```python
# interfaces/api/v1/my_domain/my_routes.py
from fastapi import APIRouter, Depends
from interfaces.api.dependencies import get_my_service

router = APIRouter(prefix="/my-resource", tags=["my-domain"])

@router.get("/")
async def list_items(service = Depends(get_my_service)):
    return service.list()
```

### 4.4 添加新领域实体

1. 在 `domain/` 下新建领域目录（如 `domain/my_domain/`）
2. 创建实体（`entities/`）、值对象（`value_objects/`）、仓储接口（`repositories/`）
3. 在 `infrastructure/persistence/database/` 实现 SQLite 仓储
4. 在 `interfaces/api/dependencies.py` 注册工厂函数

### 4.5 修改业务配置常量

所有业务常量集中在 `application/config.py`：

```python
from application.config import AppConfig

# 使用常量
words = AppConfig.DEFAULT_WORDS_PER_CHAPTER  # 3500
port  = AppConfig.DEFAULT_PORT               # 8005
```

支持通过环境变量覆盖（见 `.env.example`）：

```bash
DEFAULT_WORDS_PER_CHAPTER=4000
CONTEXT_MAX_TOKENS=40000
```

---

## 5. 提示词模板规范

PlotPilot 使用 **数据库驱动的提示词管理**，所有提示词版本化存储，支持用户自定义。

### 5.1 提示词存储位置

| 类型 | 位置 | 说明 |
|------|------|------|
| 内置默认提示词 | `infrastructure/ai/prompts/prompts_defaults.json` | 随代码分发，首次启动写入 DB |
| 系统提示词文件 | `infrastructure/ai/prompts/*.txt` | 较长的系统级提示词单独存文件 |
| 运行时版本 | SQLite `prompt_templates` 表 | 用户修改后存入数据库 |

### 5.2 提示词模板变量语法

使用 `{variable_name}` 占位符（Jinja2 兼容）：

```json
{
  "key": "chapter_generation",
  "name": "章节生成",
  "category": "generation",
  "template": "你是一位专业小说作家。\n\n当前章节：第{chapter_number}章《{chapter_title}》\n\n世界观背景：\n{bible_summary}\n\n本章大纲：\n{outline}\n\n请按照以下要求写作：\n{style_constraints}\n\n目标字数：{target_words}字"
}
```

### 5.3 添加新提示词节点

1. 在 `prompts_defaults.json` 中添加条目
2. 提示词 `key` 全局唯一，使用 `snake_case` 命名
3. `category` 从以下选择：`generation` / `extraction` / `review` / `planning` / `world` / `creative`
4. 必须提供 `name`（中文）和 `description`（用途说明）

### 5.4 在代码中使用提示词

```python
from infrastructure.ai.prompt_manager import PromptManager

pm = PromptManager(db_path)
template = pm.get_template("chapter_generation")
prompt = template.render(
    chapter_number=5,
    chapter_title="第一次相遇",
    bible_summary="...",
    outline="...",
    style_constraints="...",
    target_words=3500,
)
```

---

## 6. 前端开发规范

### 6.1 类型定义

类型按领域拆分到 `frontend/src/types/` 下的独立文件：

| 文件 | 内容 |
|------|------|
| `common.ts` | 通用响应类型、Job、日志 |
| `novel.ts` | 小说/Book 相关 |
| `chapter.ts` | 章节相关 |
| `bible.ts` | 世界观设定 |
| `cast.ts` | 角色关系 |
| `knowledge.ts` | 知识图谱 |
| `stats.ts` | 统计数据 |
| `api.ts` | 统一 re-export（向后兼容入口） |

新增类型请放到对应领域文件，**不要直接写在 `api.ts`**。

### 6.2 API 客户端

每个领域对应 `frontend/src/api/` 下一个文件，不要在组件中直接调用 `axios`/`fetch`。

```typescript
// ✅ 正确：通过 API 模块调用
import { novelApi } from '@/api/novel'
const novel = await novelApi.getNovel(id)

// ❌ 错误：直接调用 fetch
const res = await fetch(`/api/v1/novels/${id}`)
```

### 6.3 组件规范

- 使用 `<script setup lang="ts">` Composition API
- Props 类型通过 `defineProps<{}>()` 定义
- 异步组件使用 `defineAsyncComponent` 懒加载（减少首屏体积）
- 状态管理使用 Pinia Store（`frontend/src/stores/`）

---

## 7. 测试规范

### 7.1 测试分层

```
tests/
├── unit/           # 单元测试：纯函数、领域逻辑（无 IO）
├── integration/    # 集成测试：数据库操作、仓储实现
└── e2e/            # E2E 测试：完整 API 流程
```

### 7.2 运行测试

```bash
# 单元测试
pytest tests/unit -q

# 集成测试（需要 SQLite）
pytest tests/integration -q

# 全部测试
pytest tests/ -q --tb=short
```

### 7.3 测试规范

- 单元测试不允许真实 IO（数据库/网络），使用 Mock
- 领域层测试不 Mock 领域内部，只 Mock 外部依赖
- 新功能必须附带单元测试，覆盖率目标 80%+

---

## 8. PR 流程

### 8.1 分支命名

```
feat/short-description    # 新功能
fix/issue-description     # Bug 修复
refactor/target-module    # 重构
docs/what-you-documented  # 文档
```

### 8.2 提交信息格式

```
<type>: <简短描述>（中文或英文均可）

<可选：详细说明>
```

类型：`feat` / `fix` / `refactor` / `docs` / `test` / `chore` / `perf`

### 8.3 PR 检查清单

提交 PR 前请确认：

- [ ] 遵守架构边界（domain 不 import infrastructure，路由通过 Depends 注入）
- [ ] 新常量添加到 `application/config.py`，不要硬编码
- [ ] 新提示词添加到 `prompts_defaults.json`，不要内联在代码里
- [ ] 新 API 路由有对应的 Request/Response Pydantic 模型
- [ ] 附带单元测试（新功能必须）
- [ ] 运行 `pytest tests/unit -q` 全部通过
- [ ] 前端类型变更同步到 `frontend/src/types/` 对应文件

---

## 9. 常见问题

**Q: 我想加一个新的 LLM 提供商，从哪里开始？**

A: 参考 [4.1 添加新 AI Provider](#41-添加新-ai-provider)，核心是实现 `domain/ai/services/llm_service.py` 中的抽象接口。

**Q: 为什么不能在路由文件里直接 import `SqliteXxxRepository`？**

A: 这违反了依赖倒置原则（DIP）。路由层只应依赖应用服务（application service），应用服务通过构造函数接受仓储接口。这样做使得：1) 单元测试可以注入 Mock；2) 更换数据库时只需改 `dependencies.py`，不用改业务代码。

**Q: `application/services/` 目录里的 `__init__.py` 是什么？**

A: 这是历史遗留的兼容垫片，将旧的 `application.services.xxx` 导入路径映射到新的分层路径。新代码请直接 import 正确路径（如 `application.core.services.novel_service`），不要再用旧路径。

**Q: 提示词改了之后在哪里生效？**

A: 提示词首次启动时从 `prompts_defaults.json` 写入 SQLite。之后修改 JSON 文件不会自动覆盖已有数据库记录（避免覆盖用户自定义）。如需强制重置，删除 `data/aitext.db` 中的 `prompt_templates` 表数据，重启服务。

**Q: Windows 双击 `aitext.bat` 闪退怎么办？**

A: 查看 `logs/hub_error.log`，错误信息会写入该文件。常见原因：Python 未安装、tkinter 缺失、端口被占用。

**Q: 如何在本地调试前端和后端？**

A: 后端运行在 `http://127.0.0.1:8005`，前端 `vite.config.ts` 已配置代理。只需分别启动 `python cli.py` 和 `npm run dev` 即可。

---

## 扩展思路（供贡献者参考）

以下是项目当前规划但尚未实现的扩展方向，欢迎认领：

| 方向 | 难度 | 说明 |
|------|------|------|
| 多模型并发评审 | ⭐⭐⭐ | 同一章节由多个 LLM 评审，取交集意见 |
| 写作风格迁移 | ⭐⭐⭐ | 基于用户上传样本，自动提取文风指纹并注入生成管线 |
| 跨小说知识复用 | ⭐⭐ | 将一部小说的世界观迁移到新项目 |
| 移动端适配 | ⭐⭐ | 响应式布局，支持平板阅读/审稿 |
| 插件系统 | ⭐⭐⭐⭐ | 允许外部 Python 包注册自定义 Theme Skill |
| 协作写作 | ⭐⭐⭐⭐ | 多用户同时编辑，基于 CRDT 或 OT 冲突解决 |
| 导出格式扩展 | ⭐ | 支持 AZW3、TXT、HTML 等更多格式 |
| CI 自动化测试 | ⭐⭐ | GitHub Actions 跑完整集成测试套件 |

---

感谢你的贡献！如有疑问，欢迎在 [Issues](https://github.com/your-org/PlotPilot/issues) 提问，或加入社区讨论。
