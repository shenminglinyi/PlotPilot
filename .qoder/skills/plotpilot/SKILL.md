---
name: plotpilot
description: >-
  Enforces PlotPilot (墨枢) DDD layering, FastAPI/Vue 3 conventions, DI, and test layout for this repository.
  Use when implementing or refactoring PlotPilot backend (domain/application/infrastructure/interfaces),
  frontend (Vue/TypeScript), scripts, or tests; or when the user requests project standards or consistency.
---

# PlotPilot 开发规范（必须遵守）

## 项目摘要

- **产品**：AI 长篇小说创作平台（自动驾驶生成、Bible、知识图谱、伏笔、文风分析、故事结构）。
- **后端**：Python **FastAPI**，入口 `interfaces/main.py`（`uvicorn interfaces.main:app`）。
- **前端**：**Vue 3 + TypeScript + Vite + Naive UI + Pinia + ECharts**（`frontend/`）。
- **数据**：**SQLite** 主库；向量检索 **Qdrant/Chroma**（`infrastructure/ai/`）。
- **文档**：架构说明见 `docs/ARCHITECTURE.md`；README 为运行与目录总览。

## 架构铁律（DDD四层）

改动前先判断代码属于哪一层；**禁止破坏依赖方向**。

| 层 | 路径 | 允许依赖 | 禁止 |
|----|------|----------|------|
| Domain | `domain/` | 标准库、本层 `domain/*` | 依赖 `application/`、`infrastructure/`、`interfaces/` |
| Application | `application/` | `domain/`、（构造时注入的）基础设施抽象接口类型 | 在领域服务中直接写 SQL/HTTP/SDK调用（应经仓储或已注入的端口） |
| Infrastructure | `infrastructure/` | `domain/`（实现接口）、第三方库 | 被 `domain/` 导入具体实现类 |
| Interfaces | `interfaces/` | `application/`、`domain/`（异常/DTO 等）、`infrastructure/`（组装、路由） | 在路由里堆业务规则；应委托 Application Service |

- **仓储**：接口在 `domain/*/repositories/`（如 `NovelRepository`）；实现命名为 `Sqlite*Repository` 等，放在 `infrastructure/persistence/database/`。
- **应用服务**：`*_service.py` 于 `application/<module>/services/`，编排用例；跨边界数据用 `application/*/dtos/`。
- **领域异常**：`domain/shared/exceptions.py`（如 `EntityNotFoundError`）；路由层捕获并映射为 HTTP 状态码。

## 后端实现约定

1. **路由**：`interfaces/api/v1/<领域>/`，`APIRouter(prefix=..., tags=...)`；版本与聚合与 `interfaces/main.py` 中 `include_router` 保持一致。
2. **请求/响应模型**：路由文件内 `pydantic.BaseModel` 或复用 `application` DTO；字段用 `Field(..., description=...)` 与项目现有风格一致。
3. **依赖注入**：新建可注入服务时，在 `interfaces/api/dependencies.py` 增加 `get_*` 工厂，路由使用 `Depends(get_*)`。**不要**在路由里 `new` 长生命周期资源。
4. **日志**：模块级 `logger = logging.getLogger(__name__)`；启动日志配置已由 `interfaces/main.py` / middleware 处理。
5. **启动副作用**：自动驾驶守护进程、运行中小说状态等与 `startup`/`shutdown` 相关的逻辑集中在 `interfaces/main.py`；新增后台行为前先评估是否应放入现有 daemon 流程。
6. **环境**：`interfaces/main.py` 顶部设置 HF/Transformers 离线变量；勿在领域层依赖 HuggingFace 隐式下载行为。
7. **异步**：领域仓储接口同时存在同步/异步方法时（如 `save` / `async_save`），调用方与守护进程路径须与现有用法一致，避免混用导致死锁或未落盘。

## 前端实现约定

1. **API 客户端**：`frontend/src/api/config.ts` 的 `apiClient`（`baseURL` 默认 `/api/v1`，超时较长以适配 LLM）；新接口按资源拆文件（如 `novel.ts`、`chapter.ts`），并在 `api/index.ts` 按需导出。
2. **类型**：共享 API 类型放 `frontend/src/types/api.ts`（若已有同类则扩展而非重复定义）。
3. **路由**：`frontend/src/router/index.ts`；页面在 `views/`，可复用块在 `components/`。
4. **状态**：Pinia store 放 `stores/`；跨页刷新信号等沿用现有 `workbenchRefreshStore` 等模式。
5. **安全展示**：用户生成内容渲染继续用 **DOMPurify** 等现有净化路径，勿引入未净化的 `v-html`。

## 测试与质量

- **单元测试**：`tests/unit/`，按层镜像目录（如 `tests/unit/application/...`）。
- **集成测试**：`tests/integration/`，含 API 与持久化等。
- 新行为：**优先**为应用服务或仓储增加单元测试；HTTP 行为用集成测试覆盖。
- 运行：`pytest tests/unit/ tests/integration/ -v`（或按 README 覆盖率命令）。

## 脚本与数据

-一次性迁移、评测、环境检查放在 `scripts/`；大规模数据迁移保持**可重复执行/幂等**说明（参考现有 `scripts/migrations/` 风格）。
- 数据目录与路径 helper使用 `application/paths.py`（如 `DATA_DIR`、`get_db_path`），避免硬编码仓库相对路径散落。

## 提交与范围

- **最小改动**：只改完成任务所需的文件；禁止顺带大范围格式化或无关重构。
- **Conventional Commits**（README）：`feat:`、`fix:` 等；说明用完整句子。
- **许可**：Apache 2.0 + Commons Clause；勿引入与商业闭源冲突或不可审计的依赖而不加说明。

## 新功能落地检查清单（复制使用）

```
- [ ] 领域模型/规则落在 domain/；无上层 import
- [ ] 用例编排在 application/*/services/；DTO 在 application/*/dtos/
- [ ] 新仓储接口在 domain/，实现在 infrastructure/persistence/database/
- [ ] 路由仅编排：Depends + Service；异常映射一致
- [ ] 新依赖在 dependencies.py 注册
- [ ] 前端 api 模块 + 路由/页面（如需要）
- [ ] tests/unit 或 tests/integration 覆盖核心路径
```

## 与用户沟通

- 用户要求中文时：**回复使用中文**；代码注释与已有文件保持一致（本项目中文注释较多）。

## 进一步阅读

- 分层与模块职责：`docs/ARCHITECTURE.md`
- 运行与环境变量：根目录 `README.md`
