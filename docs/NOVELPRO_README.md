# NovelPro 作者工作台增强说明

NovelPro 是一组面向长篇小说创作的工作台增强能力，目标是让 PlotPilot 不只负责“生成章节”，还负责把选题、候选稿、连续性、关系变化、战力约束、文风稳定和长期记忆放进同一条可验证链路里。

这份说明用于代码审核、部署评估和后续维护。所有功能都以现有 FastAPI + Vue + SQLite 架构为基础实现，不要求新增外部服务；需要真实模型或登录态数据的部分均可降级为空配置、手动输入或公开页面采集。

## 设计目标

- 降低长篇创作中的断线风险：角色掉线、关系沉默、时间线冲突、大纲偏离、战力跳升和文风漂移。
- 把“AI 生成正文”前移到“选题判断”和“候选稿决策”，减少一次生成失败后直接污染正文。
- 保留作者控制权：候选稿、精修稿、外部模型结果、AI 表单建议都以预览和采用动作进入主线。
- 支持可回读的长期记忆：Obsidian Markdown Vault 可作为主记忆源，SQLite 知识库作为运行缓存。
- 对市场信号保持可配置边界：公开榜单、API、登录态数据统一走来源配置和凭据表，接口不回传明文凭据。

## 功能总览

### 1. 选题立项池

选题模块提供从市场观察到新书创建的完整闭环：

- 手动输入选题补充说明。
- 手动导入市场观察文本。
- 公开来源采集标题级市场信号。
- 自动后台采集与来源健康状态。
- 市场信号去重、趋势摘要、平台权重统计。
- 漫画信号转译为小说题材机会。
- 选题生成、深化、评估、对比推荐。
- 采纳选题为新书，并把立项报告写入新书 premise。

#### 选题工作流

推荐使用顺序：

1. 打开首页的选题立项池。
2. 在“市场观察”中手动导入观察文本，或在“公开来源采集”中选择榜单来源采集样本。
3. 查看“市场摘要”，确认来源、类型、标签、漫画机会和近窗趋势。
4. 在生成表单里填写补充说明、类型、关键词、规避模式，并勾选要引用的市场信号。
5. 生成 3-5 个选题候选。
6. 对候选执行“深化”和“评估”，生成结构化立项报告。
7. 多选候选执行“对比推荐”。
8. 采纳候选为新书，系统会把选题阶段沉淀的信息写入新书 premise，供后续世界观、人物和章节生成继承。

#### 来源配置文件

市场信号来源集中定义在：

```text
application/topic/services/topic_signal_sources.py
```

当前默认来源包括：

| source key | 名称 | 类型 | 默认采集方式 | 榜单维度 |
|---|---|---|---|---|
| `qidian_rank` | 起点-小说榜 | 小说 | `public_page` | 热门榜 / 新书榜 / 快速上榜 |
| `jjwxc_rank` | 晋江-小说榜 | 小说 | `public_page` | 热门榜 / 新书榜 / 快速上榜 |
| `qimao_rank` | 七猫-小说榜 | 小说 | `public_page` | 热门榜 / 新书榜 / 快速上榜 |
| `fanqie_rank` | 番茄-小说榜 | 小说 | `public_page` | 热门榜 / 新书榜 / 快速上榜 |
| `qq_read` | 腾讯-QQ阅读 | 小说 | `api` | 热门榜 / 新书榜 / 快速上榜 |
| `tencent_comic_rank` | 腾讯动漫-漫画榜 | 漫画 | `public_page` | 热门榜 / 新书榜 / 快速上榜 |
| `kuaikan_comic` | 快看漫画-漫画 | 漫画 | `public_page` | 热门榜 / 新书榜 / 快速上榜 |

新增来源时，维护者只需要在 `MARKET_SIGNAL_SOURCES` 中增加一个 `TopicMarketSignalSourceDTO`：

```python
"example_rank": TopicMarketSignalSourceDTO(
    key="example_rank",
    name="示例平台-小说榜",
    url="https://example.com/rank",
    category="novel",
    source_type="public_page",
    requires_auth=False,
    rank_urls={
        "热门榜": "https://example.com/rank/hot",
        "新书榜": "https://example.com/rank/new",
        "快速上榜": "https://example.com/rank/rise",
    },
)
```

字段说明：

- `key`：来源唯一标识，会用于接口、数据库凭据、健康状态和平台权重。
- `name`：前端展示名称。
- `url`：默认采集入口。
- `category`：`novel` 或 `comic`；漫画来源会参与“漫画转题机会”分析。
- `source_type`：`public_page`、`api` 或 `authenticated_source`。
- `requires_auth`：是否要求配置凭据后才允许采集。
- `rank_urls`：按榜单维度配置多个采集入口；为空时使用 `url`。

平台默认权重定义在同一文件的 `DEFAULT_MARKET_SIGNAL_SOURCE_WEIGHTS`。权重会影响市场摘要、选题评估和候选对比推荐。

#### 采集器配置

采集器入口在：

```text
application/topic/services/topic_signal_collectors.py
```

内置三类 collector：

- `public_page`：抓取 HTML 页面，使用平台适配解析器或通用标题解析。
- `api`：请求 JSON API，优先解析 `books/items/list/records` 等常见榜单结构。
- `authenticated_source`：需要登录态或自定义 headers 的来源入口。

如果新增平台页面结构比较稳定，建议增加平台专用解析函数，并在 `PublicPageMarketSignalCollector` 中按 `source.key` 分发。这样可以提取更准确的标题、类型、标签、简介、排名和热度。

#### 凭据和 Endpoint 配置

前端配置入口：

```text
TopicIdeaPanel.vue -> 外部 API / 登录态
```

后端接口：

```http
GET   /api/v1/topics/signals/source-credentials
PATCH /api/v1/topics/signals/sources/{source_key}/credentials
```

可配置字段：

```json
{
  "api_key": "optional-api-key",
  "cookie": "optional-cookie",
  "endpoint_url": "https://example.com/custom/rank-api",
  "headers": {
    "User-Agent": "Mozilla/5.0",
    "X-Custom-Header": "value"
  }
}
```

保存位置：

```text
topic_market_signal_credentials
```

安全边界：

- API 只返回 `api_key_configured`、`cookie_configured`、`endpoint_configured` 和 `header_keys`。
- 明文 API Key / Cookie 只在服务端内部读取，不通过查询接口返回。
- 如果配置了 `endpoint_url`，采集时会优先使用该 Endpoint 覆盖来源默认 URL。
- 如果配置了 `api_key` 且没有显式 `Authorization` header，采集器会自动补 `Authorization: Bearer <api_key>`。
- 如果配置了 `cookie` 且没有显式 `Cookie` header，采集器会自动补 `Cookie`。

#### 手动采集配置

前端配置入口：

```text
TopicIdeaPanel.vue -> 公开来源采集 -> 立即采集
```

后端接口：

```http
POST  /api/v1/topics/signals/collect
GET   /api/v1/topics/signals/automation
PATCH /api/v1/topics/signals/automation
GET   /api/v1/topics/signals/source-health
```

手动采集请求：

```json
{
  "source_keys": ["qidian_rank", "fanqie_rank", "qq_read"],
  "limit_per_source": 8
}
```

保留的采集设置字段：

```json
{
  "enabled": false,
  "interval_minutes": 180,
  "limit_per_source": 8,
  "lookback_days": 30,
  "selected_source_keys": ["qidian_rank", "fanqie_rank", "qq_read"],
  "source_weights": {
    "qidian_rank": 1.0,
    "jjwxc_rank": 1.1,
    "fanqie_rank": 1.05
  }
}
```

保存位置：

```text
topic_market_signal_settings
topic_market_signal_source_health
```

当前本地应用默认不在 API 进程启动时创建市场信号定时采集线程，只在用户点击“立即采集”或调用 `/api/v1/topics/signals/collect` 后执行。独立脚本仍保留给需要一次性命令行采集或未来自行接入进程管理器的场景：

```bash
python scripts/start_topic_signal_collector.py --once --force
python scripts/start_topic_signal_collector.py --poll-interval 60
```

相关环境变量：

| 变量 | 默认值 | 说明 |
|---|---:|---|
| `TOPIC_SIGNAL_POLL_INTERVAL_SECONDS` | `60` | 独立守护进程检查配置是否到期的轮询间隔，单位秒 |
| `LOG_LEVEL` | `INFO` | 独立守护进程日志级别 |
| `LOG_FILE` | `logs/aitext.log` | 独立守护进程日志文件 |
| `DISABLE_SSL_VERIFY` | `false` | 调试网络证书问题时可临时关闭 SSL 校验，不建议生产使用 |

当前默认不建议配置 systemd、cron 或其他定时任务；需要采集时优先使用前端“立即采集”按钮。

#### 数据库表

选题模块新增或使用以下 SQLite 表：

| 表 | 用途 |
|---|---|
| `topic_ideas` | 选题候选、立项报告、评估结果、采纳状态 |
| `topic_market_signals` | 手动导入和采集得到的市场信号 |
| `topic_market_signal_settings` | 采集偏好、单源条数、趋势窗口、平台权重 |
| `topic_market_signal_credentials` | 来源 API Key、Cookie、Endpoint 和自定义 headers |
| `topic_market_signal_source_health` | 每个来源最近采集状态、条数和错误 |

这些表和必要列由 `infrastructure/persistence/database/connection.py` 在启动时幂等创建或补齐，旧库无需手动迁移。

#### API 清单

主要接口：

```http
POST /api/v1/topics/generate
GET  /api/v1/topics/
GET  /api/v1/topics/{topic_id}
POST /api/v1/topics/{topic_id}/deepen
POST /api/v1/topics/{topic_id}/evaluate
POST /api/v1/topics/compare
POST /api/v1/topics/{topic_id}/adopt

POST /api/v1/topics/signals/import
POST /api/v1/topics/signals/collect
GET  /api/v1/topics/signals/summary
GET  /api/v1/topics/signals/sources
POST /api/v1/topics/signals/sources/test
GET  /api/v1/topics/signals/source-health

GET   /api/v1/topics/signals/automation
PATCH /api/v1/topics/signals/automation
GET   /api/v1/topics/signals/source-credentials
PATCH /api/v1/topics/signals/sources/{source_key}/credentials
```

#### 验证选题功能

推荐后端测试：

```bash
pytest \
  tests/unit/domain/topic/test_topic_idea.py \
  tests/unit/infrastructure/database/test_sqlite_topic_idea_repository.py \
  tests/unit/application/services/test_topic_idea_service.py \
  tests/unit/application/services/test_topic_signal_automation_service.py \
  tests/unit/application/services/test_topic_signal_collectors.py \
  tests/unit/interfaces/api/test_topic_ideas.py \
  tests/unit/scripts/test_start_topic_signal_collector.py \
  -q
```

推荐手工验收：

1. `GET /api/v1/topics/signals/sources` 返回 7 个默认来源。
2. `POST /api/v1/topics/signals/sources/test` 能返回每源样例标题或明确错误。
3. `POST /api/v1/topics/signals/import` 可导入手动观察。
4. `POST /api/v1/topics/signals/collect` 可采集至少一个来源并入库。
5. `GET /api/v1/topics/signals/summary` 返回来源、类型、标签、日统计和漫画转题机会。
6. `POST /api/v1/topics/generate` 能引用市场信号生成候选。
7. `deepen / evaluate / compare / adopt` 全链路可用，采纳后创建新书。

相关后端模块：

- `domain/topic/`
- `application/topic/`
- `interfaces/api/v1/topic/`
- `infrastructure/persistence/database/sqlite_topic_idea_repository.py`

相关前端模块：

- `frontend/src/components/topic/TopicIdeaPanel.vue`
- `frontend/src/api/topic.ts`

### 2. 候选稿与精修闭环

候选稿模块让章节生成进入“候选 -> 对比 -> 审稿 -> 采用/拒绝”的流程，而不是直接覆盖正文：

- 章节候选稿保存。
- 分支列表与差异对比。
- 监督审稿与拒绝理由。
- 候选稿状态流转。
- 外部模型生成结果台账。
- 精细改稿任务入口。

相关后端模块：

- `application/core/services/chapter_candidate_draft_service.py`
- `infrastructure/persistence/database/sqlite_chapter_candidate_draft_repository.py`
- `interfaces/api/v1/core/chapter_candidate_drafts.py`

相关前端模块：

- `frontend/src/components/workbench/CandidateRefinePanel.vue`
- `frontend/src/components/workbench/CandidateDraftBranchSwitcher.vue`
- `frontend/src/stores/candidateDraftBranchStore.ts`

### 3. 连续性巡检

连续性巡检把章节正文、知识库、关系事件和大纲节点合并成结构化监控：

- 角色掉线提醒。
- 关系线沉默提醒。
- 关系变化事件记录。
- 时间线事件与冲突检查。
- 大纲覆盖状态。
- 文风漂移信号接入。

相关后端模块：

- `application/analyst/services/continuity_overview_service.py`
- `interfaces/api/v1/analyst/continuity.py`

相关前端模块：

- `frontend/src/components/workbench/ContinuityPanel.vue`
- `frontend/src/api/continuity.ts`

### 4. 战力系统

战力系统用于约束玄幻、异能、竞技等类型中的能力跃迁：

- 战力规则维护。
- 角色战力档案。
- 战力变化事件。
- 异常跃迁提醒。
- 总览面板。

相关后端模块：

- `application/analyst/services/power_system_service.py`
- `infrastructure/persistence/database/sqlite_power_system_repository.py`
- `interfaces/api/v1/analyst/power_system.py`

相关前端模块：

- `frontend/src/components/workbench/PowerSystemPanel.vue`
- `frontend/src/api/powerSystem.ts`

### 5. Obsidian 长期记忆

Obsidian 集成把 PlotPilot 的章后知识沉淀导出为 Markdown Vault，并允许系统优先从 Vault 回读长期记忆：

- 事实锁。
- 分章摘要。
- 角色/故事关系图。
- 时间线。
- Vault 路径配置。
- 当前章节手动同步。
- NovelPro 监控中心读取主记忆状态。

该能力不要求安装 Obsidian 桌面应用。只要配置了 Vault 路径，就可以作为普通 Markdown 目录使用。

相关后端模块：

- `application/world/services/obsidian_memory_service.py`
- `interfaces/api/v1/analyst/novelpro_monitor.py`

相关文档：

- `docs/novelpro-obsidian-long-term-memory.md`

### 6. AI 味抑制与提示词广场

章节生成提示词增加了低 AI 味约束，并提供可编辑的提示词节点：

- `workflow-chapter-generation`
- `anti-ai-style-rules`
- `review-ai-flavor-audit`
- `rewrite-ai-flavor-naturalizer`

默认策略强调具体动作、对白潜台词、冲突慢写、信息增量和禁止空泛总结。运行时仍允许用户在提示词广场中编辑并保留版本历史。

相关模块：

- `application/audit/services/cliche_scanner.py`
- `application/workflows/auto_novel_generation_workflow.py`
- `infrastructure/ai/prompts/prompts_defaults.json`
- `frontend/src/components/workbench/promptPlaza/PromptDetailPanel.vue`

### 7. NovelPro 监控中心

监控中心把多个系统的状态收束到一个右侧面板：

- Obsidian 主记忆状态。
- 知识关系图统计。
- 连续性巡检摘要。
- 战力风险摘要。
- 红黄灯健康分。
- 自动提醒与操作建议。

时间线提醒做了分级处理：轻度可疑冲突会显示为 warning，只有多个冲突或缺少当前章节时间锚点时才升级为 error。

相关模块：

- `application/analyst/services/novelpro_monitor_service.py`
- `frontend/src/components/workbench/NovelProMonitorPanel.vue`

## API 概览

新增或扩展的主要 API：

- `GET/POST /api/v1/topics/...`
- `GET /api/v1/topics/signals/summary`
- `GET/PATCH /api/v1/topics/signals/credentials/{source_key}`
- `GET/PATCH /api/v1/topics/signals/automation`
- `GET /api/v1/topics/signals/source-health`
- `POST /api/v1/topics/signals/sources/test`
- `GET/POST /api/v1/novels/{novel_id}/candidate-drafts`
- `GET /api/v1/novels/{novel_id}/continuity/overview`
- `GET /api/v1/novels/{novel_id}/power-system/overview`
- `GET /api/v1/novels/{novel_id}/novelpro/monitor`
- `POST /api/v1/novels/{novel_id}/novelpro/obsidian/sync`
- `POST /api/v1/novels/{novel_id}/novelpro/suggestions/form`

## 数据库变更

新增表和字段均通过启动时幂等迁移创建，面向已有 SQLite 数据库保持兼容。

主要新增数据区域：

- 选题候选与市场信号。
- 市场信号手动采集设置。
- 市场信号来源健康状态。
- 来源凭据状态。
- 候选稿与候选稿分支。
- 战力规则、角色档案和事件。
- LLM 控制台配置补充字段。
- 文风指纹持久化修复。

凭据表会保存 API Key / Cookie 以供本地采集使用，但对外查询接口只返回是否已配置，不返回明文。

## 降级与安全边界

- 未配置真实 LLM 时，系统沿用现有 MockProvider 或空配置提示，不阻断页面打开。
- 未配置来源凭据时，市场采集仍可使用公开页面来源或手动输入。
- 外部 API 和登录态来源使用统一 collector 边界，后续可以替换为官方 API。
- Obsidian 未安装时仍可写 Markdown Vault。
- `generate-chapter-stream` 语义仍是流式生成正文和章后知识回写，不直接创建章节；前端需要把生成结果保存为章节。
- 本 PR 不包含任何用户 Cookie、API Key、数据库文件、宝塔部署地址或个人路径。

## 本地启动

后端：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn interfaces.main:app --host 127.0.0.1 --port 8005 --reload
```

前端：

```bash
cd frontend
npm install
npm run dev
```

可选环境变量：

```bash
PLOTPILOT_OBSIDIAN_VAULT=/path/to/obsidian-vault
DISABLE_TOPIC_SIGNAL_AUTOMATION=1
ANTHROPIC_API_KEY=...
ARK_API_KEY=...
OPENAI_API_KEY=...
```

## 验证建议

后端聚焦测试：

```bash
pytest \
  tests/unit/application/services/test_topic_idea_service.py \
  tests/unit/application/services/test_topic_signal_collectors.py \
  tests/unit/application/services/test_chapter_candidate_draft_service.py \
  tests/unit/application/services/test_continuity_overview_service.py \
  tests/unit/application/services/test_power_system_service.py \
  tests/unit/application/services/test_novelpro_monitor_service.py \
  tests/integration/interfaces/api/v1/test_chapter_candidate_drafts_api.py \
  tests/integration/interfaces/api/v1/test_continuity_api.py \
  tests/integration/interfaces/api/v1/test_power_system_api.py \
  -q
```

前端构建：

```bash
cd frontend
npm ci
npm run build
```

当前 fork 分支已通过 GitHub Actions：

- Backend CI
- Frontend CI

## 审核重点

这组变更规模较大，建议按模块拆分审核：

1. 先审数据库迁移和仓储兼容性。
2. 再审选题市场信号链路和凭据脱敏边界。
3. 再审候选稿闭环是否符合原项目产品方向。
4. 再审连续性、战力、Obsidian、监控中心是否需要全部进入主线，或拆成可选增强模块。
5. 最后审前端入口和工作台信息密度。

如果维护者倾向小 PR，建议从这个分支中拆出以下独立 PR：

- 选题立项池与市场信号。
- 候选稿与精修闭环。
- 连续性巡检与 NovelPro 监控中心。
- Obsidian 长期记忆。
- AI 味抑制提示词与俗套扫描增强。
