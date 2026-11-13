# PlotPilot（墨枢）— 开源剧情引擎内核与开放叙事模组生态

<p align="center">
  <img src="frontend/src/assets/brand-logo.png" alt="PlotPilot 墨枢" width="120" />
</p>

<p align="center">
  <strong>开源剧情引擎内核 · 开放叙事模组生态（Mod Hub）</strong>
</p>

<p align="center">
  面向长篇小说、剧本与严肃叙事生产的基础设施：持久记忆 · 知识图谱 · 自动推进流水线 · 质量治理闭环 · <code>plotpilot-mod/v1</code> 模组协议
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.14.x-3776AB?style=flat&logo=python&logoColor=white" alt="Python"></a>
  <a href="https://vuejs.org/"><img src="https://img.shields.io/badge/Vue-3.5-4FC08D?style=flat&logo=vuedotjs&logoColor=white" alt="Vue"></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-0.109%2B-009688?style=flat&logo=fastapi&logoColor=white" alt="FastAPI"></a>
  <a href="#plotpilot-modv1-开放叙事模组协议规范"><img src="https://img.shields.io/badge/Mod_Protocol-plotpilot--mod%2Fv1-1f5e5b?style=flat" alt="Mod Protocol"></a>
  <a href="https://tauri.app/"><img src="https://img.shields.io/badge/Tauri-Desktop-7a5510?style=flat&logo=tauri&logoColor=white" alt="Tauri"></a>
  <a href="https://github.com/pipi333/PlotPilot/stargazers"><img src="https://img.shields.io/github/stars/pipi333/PlotPilot?style=flat&logo=github" alt="Stars"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0%20%2B%20Commons%20Clause-D22128?style=flat&logo=apache&logoColor=white" alt="License"></a>
</p>

> **开源演进与归属声明**：本仓库（[`pipi333/PlotPilot`](https://github.com/pipi333/PlotPilot)）基于上游内核仓库 [`shenminglinyi/PlotPilot`](https://github.com/shenminglinyi/PlotPilot) 深度演进构建，严格遵循 `Apache License 2.0` + `Commons Clause` 开源许可协议，并完整保留 [`LICENSE`](LICENSE) 与 [`CONTRIBUTORS.md`](CONTRIBUTORS.md) 中的全部历史贡献记录。在此基础上，本仓库新增了**墨枢模组中心（Mod Hub）双轨生态**、**`plotpilot-mod/v1` 开放叙事模组协议**、**宣纸松烟编辑室视觉系统**，以及**跨标签页 Web Locks WAL + SQLite 原子 CAS 与逐跳 IP 钉扎 SSRF 防护**等工程架构升级。

---

<p align="center">
  <img src="docs/screenshots/workbench-writing.png" alt="工作台 — 写作区与知识图谱" width="49%" />
  <img src="docs/screenshots/workbench-dag.png" alt="工作台 — 故事线 DAG 与人物设定" width="49%" />
</p>

---

## 这是什么

PlotPilot（墨枢）是一个面向长篇小说、剧本与严肃叙事生产的**开源剧情引擎内核（Narrative Engine Kernel）与开放叙事模组生态**，不是聊天式写作助手，也不是一组零散的提示词模板。

大多数 AI 写作工具解决的是“生成一段文字”的问题。PlotPilot 解决的是一个更难的系统工程与创作审美问题：

> **如何让 AI 系统在数十万字的叙事跨度里，维持人物一致性、因果链完整性、伏笔闭合率，并在消除廉价“AI 腔”、强化人物潜台词与商业连载审稿留存的前提下，实现高水准的长篇推进？**

这不是单一提示词调优问题，而是**状态机工程与开放模组协议问题**。PlotPilot 的答案是：在底层构建一套完整的剧情状态管理基础设施（Story Bible、章级摘要链、事件流、故事线 DAG、伏笔账本与向量检索），在上层通过 `plotpilot-mod/v1` 开放协议将文风滤镜、潜台词刀法、毒点审稿官与题材节拍器解耦为可自由安装、叠加、回滚与分享的**叙事模组（Narrative Mod Pack）**。

项目边界很明确：

- **不是** 单轮续写器：核心目标是长篇连续生产与章节质量治理，而不是回答一次孤立的写作请求。
- **不是** 大上下文堆料：世界观、人物、伏笔、故事线会被结构化为可追踪状态，按场次动态装配。
- **不是** 封闭黑盒应用：官方工作台通过版本化 REST API 与内核交互；全量 78 个内置内核提示词接点向创作者完全敞开，支持通过模组中心一键挂载或导出分享。

---

## 墨枢模组中心（Mod Hub）：中心化与去中心化双轨叙事生态

墨枢模组中心（路由 `/square` 及工作台内嵌面板，核心实现位于 `frontend/src/views/SquareView.vue` 与 `frontend/src/components/workbench/PromptPlaza.vue`）采用中心化云端广场与去中心化开源仓库双轨融合架构，让小说与剧本创作者无需触碰底层代码，即可像管理插件一样装配自己的叙事工作流。

### 四大主视图与全量内核透视

| 视图标签 | 核心定位与能力说明 |
|----------|--------------------|
| **发现** | 一站式浏览内置精选模组、`plotpilot.xyz` 官方书元、社区共享模组与全网热榜风向，支持按创作职能筛选与实测样章对比预览 |
| **已安装** | 集中检视当前已启用的模组清单、被接管的内核节点明细，支持单模组或单节点粒度的一键无损卸载与基线回滚 |
| **内置内核** | 直接检视与精细调优引擎内置 CPMS 全部 **78 个内置内核节点**，支持历史版本管理、JSON 导出/导入备份与新建自定义节点 |
| **反 AI 质检** | 集成 `AntiAIDashboard`，集中检视去 AI 味规则集、陈词滥调拦截与章节质量治理状态 |

### 六大面向创作者的叙事能力分区

模组中心摒弃晦涩的底层工程术语，直接按照长篇写作与审稿的真实痛点划分为六大职能分区（`MOD_ROLE_CATEGORIES`）：

| 分区标识 | 分区名称 | 解决的创作痛点 |
|----------|----------|----------------|
| `style-anti-ai` | **文风与去AI味** | 以具象器物动作与生理冷感替代空泛心理总结，根治排比升华、形容词堆砌与五官套话 |
| `opening-hook` | **题材开局包** | 聚焦黄金三章切入点、身份错位、倒计时危机与书元核心设定，提升开篇留存率 |
| `pacing-plot` | **剧情节拍器** | 控制章纲信息密度、爽点兑现周期与章末悬念留钩，砍除无效寒暄与赶路水戏 |
| `dialogue-voice` | **人物声线与潜台词** | 告别问答机式的“设定传声筒”，用动作停顿、顾左右而言他与句长位差推进人物博弈 |
| `review-guard` | **毒点审稿官** | 按商业连载留存标准拦截知情权越界（POV Firewall）、设定百科灌水、主角无收益憋屈与人设 OOC |
| `worldbuilding` | **世界观营造** | 编织力量体系代价、民俗器物考据、底层行规禁忌与多方势力暗线 |

### 开箱即用的 6 款精选叙事模组

仓库内置 6 款离线可直接启用的精选模组（定义于 `frontend/src/domain/modPack/curatedPacks.ts`），每款模组均附带同一测试场景大纲下的启用前后实测样章对比（`showcase`）：

| 模组 ID | 模组名称 | 职能分类 | 挂载内核接点 |
|---------|----------|----------|--------------|
| `mod-cold-realism-anti-ai` | **冷峻纪实 · 深度去 AI 味滤镜** | `style-anti-ai` | `chapter-generation-main`、`scene-generation` |
| `mod-subtext-blade-dialogue` | **话留三分 · 高张力潜台词对白包** | `dialogue-voice` | `dialogue-generation`、`anti-ai-character-state-lock` |
| `mod-golden-three-poison-guard` | **黄金三章 · 劝退毒点严审官** | `review-guard` | `review-character-consistency`、`review-storyline-consistency` |
| `mod-webnovel-fast-pacing-beat` | **快节奏爽点 · 节拍推进引擎** | `pacing-plot` | `beat-sheet-decomposition`、`outline-beat-partition` |
| `mod-oriental-mystery-folklore` | **诡秘民俗 · 器物考据与暗线营造** | `worldbuilding` | `bible-worldbuilding`、`scene-generation` |
| `mod-high-concept-opening-engine` | **强反差开局 · 书元利益钩子生成器** | `opening-hook` | `planning-quick-macro`、`planning-act` |

### 四源融合分发与创作者打包工坊

墨枢模组中心支持四种模组来源，并通过四级信任标签（`official` 官方内置、`cloud-verified` 云端认证、`community-unreviewed` 社区未审、`local` 本地构建）明确标识安全边界：

- **本地精选（Curated）**：随仓库内置，离线零网络依赖，开箱即用。
- **plotpilot.xyz 云端书元与社区共享（`cloudPackAdapter.ts`）**：通过内置云连接器（`/api/v1/cloud/*`）匿名拉取官方书元与社区共享目录，自动适配为标准 `NarrativeModPack` 一键安装至本地库；登录云端账号可解锁全网多平台聚合热榜风向与社区互动；云端不可达时采用非阻断内联提示，绝不遮挡本地模组与写作工作流。
- **GitHub / HTTPS JSON / 本机文件去中心化直装**：底部快捷安装栏支持直接输入 `github:owner/repo`（支持 `@ref` 或 `#ref` 指定分支/标签及子路径，自动探测仓库下的 `plotpilot-mod.json`、`mod.json`、`manifest.json`）、GitHub 仓库/blob/tree URL、任意公网 HTTPS JSON 直链，或直接选择本机 `.json` 文件一键安装。
- **创作者模组打包工坊（`ModPackBuilderModal.vue`）**：创作者在「内置内核」调优提示词节点后，点击顶栏「打包制作模组」，勾选目标节点（系统自动高亮“已调优”节点）、填写方章单字（`glyph`）、一句话人话摘要与启用前后实测样章对比，即可一键导出符合 `plotpilot-mod/v1` 规范的 JSON 清单文件。将其推送至任意 GitHub 仓库，全社区即可通过 `github:owner/repo` 坐标直接安装。

---

## `plotpilot-mod/v1` 开放叙事模组协议规范

为了确保多个叙事模组能够安全叠加、精准升级并在卸载时做到字节级无损还原，PlotPilot 设计并实现了 `plotpilot-mod/v1` 开放协议（核心实现位于 `frontend/src/domain/modPack/types.ts` 与 `frontend/src/domain/modPack/modProtocol.ts`）。

### 标准清单结构（`PlotPilotModManifest`）

```json
{
  "schema": "plotpilot-mod/v1",
  "exportedAt": "2026-11-13T08:00:00.000Z",
  "pack": {
    "id": "mod-cold-realism-anti-ai",
    "name": "冷峻纪实 · 深度去 AI 味滤镜",
    "glyph": "纪",
    "author": "作者署名",
    "repoOrOrigin": "github:owner/repo",
    "trustLevel": "local",
    "roleCategory": "style-anti-ai",
    "roleLabel": "文风滤镜",
    "summary": "一句话人话价值说明",
    "version": "v1.0.0",
    "license": "MIT",
    "updatedAt": "2026-11-13",
    "usageLabel": "本地构建",
    "replacesBuiltin": true,
    "tags": ["去AI味", "冷峻叙事"],
    "readmeSections": [{ "heading": "核心说明", "body": "..." }],
    "showcase": {
      "scenario": "测试场景",
      "beforeExcerpt": "未启用时的默认片段",
      "afterExcerpt": "启用模组后的实测片段"
    },
    "overrides": [
      {
        "nodeKey": "chapter-generation-main",
        "nodeLabel": "主工作流章节生成",
        "mode": "append_protocol",
        "systemContent": "【模组协议正文】..."
      }
    ]
  }
}
```

### 三种节点挂载与覆写模式（`ModNodeOverride.mode`）

| 模式名称 | 适用场景 | 协议行为与无损回滚机制 |
|----------|----------|------------------------|
| `append_protocol` | **无损协议追加（推荐默认）** | 在目标节点原 System 提示词末尾挂载独立协议块，100% 保留原有 `{context}`、`{outline}` 等模板变量插槽与 Pydantic 结构化输出契约；支持多个模组在同一节点按序叠加、各自独立卸载 |
| `replace_system` | **基线快照替换** | 安装前自动校验全文协议拓扑，捕获纯净原始 System 基线（`baselineSystem`）并保留其他已装模组的追加层；卸载时字节级还原安装前基线与块外手动编辑 |
| `standalone_node` | **加密归属独立节点** | 作为独立自定义节点安装进本地库（支持 `userTemplate` 与 `backendCategory`），基于浏览器 CSPRNG（`crypto.getRandomValues`）生成 128-bit 随机归属令牌（32 位小写十六进制 `originToken`）写入协议头，严格区分模组自建节点与用户同名手建节点 |

### 深度为 1 的单遍协议拓扑解析器（Fail-Closed 零误伤保障）

协议引擎采用有限状态单遍扫描器解析节点正文中的边界注释标记：

- 追加块标记：`<!-- [PlotPilot-Mod:<packId>:START:appended] -->` ... `<!-- [PlotPilot-Mod:<packId>:END] -->`
- 替换块标记：`<!-- [PlotPilot-Mod:<packId>:START:replaced] -->` ... `<!-- [PlotPilot-Mod:<packId>:END] -->`
- 独立块标记：`<!-- [PlotPilot-Mod:<packId>:START:standalone] -->` ... `<!-- [PlotPilot-Mod:<packId>:END] -->`
- 加密归属标记：`<!-- [PlotPilot-Mod:<packId>:START:custom:<32hex>] -->` ... `<!-- [PlotPilot-Mod:<packId>:END] -->`

**防注入与 Fail-Closed 保护**：协议严禁模组正文内包含受保护的 `PlotPilot-Mod:` 标记字面量；在每次安装、升级、卸载前均执行全文单遍顶层拓扑校验。一旦检测到任何嵌套、交叉、未闭合、大小写不一致或残缺标记，引擎立即中止自动改写并完整保留现场，绝不静默覆盖或误删创作者的任何自定义内容。

---

## 展馆级东方纸墨 UI 与底层并发/安全工程升级

### 宣纸松烟编辑室视觉系统

前端工作台（`frontend/src/assets/styles/main.css`、`frontend/src/assets/styles/internal-workbench-polish.css`）全面重构为东方纸墨编辑室美学，消除长时间码字的视觉疲劳：

- **色彩体系**：采用温润宣纸底（`#f4f4f2`）配松烟墨正文（`#161615`），辅以深黛青低饱和强调色（`#1f5e5b`，全屏占比严格控制在 `< 3%`）与古铜印金点缀（`#7a5510`），原生内置**亮色 / 暗色 / 黑金**三套主题。
- **排版与对比度门禁**：严格分离无衬线 UI 字体栈与衬线正文阅读字体栈，移除廉价紫色系、顶栏渐变条与常驻悬浮重阴影；全量文本对比度 `>= 4.5:1`（三级辅助正文对比度 `>= 5.0:1`），通过前端视觉静态门禁 0 FAIL 验证。

### `Alt+Z` 沉浸专注模式与窄屏响应式抽屉

- **工作台 `Alt+Z` 专注模式（Zen Focus Mode，`Workbench.vue`）**：通过快捷键 `Alt+Z` 或顶栏按钮即可一键收起左右辅助分栏，居中展开 `820px` 宣纸写作区与 `58ch` 黄金阅读行宽（`16px` 字号、`1.85` 行高），专注状态自动持久化保存。
- **移动端窄屏导航抽屉（`<768px`，`StatsSidebar.vue`）**：在窄屏窗口与移动设备下自动将侧栏收拢为顶栏汉堡触发钮与模态抽屉，确保书架与模组中心在小屏设备上保持 100% 宽度可用。

### 多标签页 Web Locks 预写日志（WAL）+ SQLite `BEGIN IMMEDIATE` 原子 CAS

针对创作者同时开启多个浏览器标签页调优提示词或安装/卸载模组的并发场景，系统构建了端到端的一致性保障：

- **前端跨标签页事务协调（`modHubStore.ts`、`modWalCommon.ts`、`modUninstallEngine.ts`）**：通过浏览器原生 `Web Locks API`（锁标识 `plotpilot:mod_hub_tx_lock`）配合进程内有序键锁，保证跨标签页模组事务串行互斥；每次节点变更前先将 `UnresolvedNodeMutation` 预写日志落盘至本地存储，配合 15 秒未决窗口与 `fenceNodeVersion` 版本围栏机制，即使遭遇页面崩溃或断网超时也能在重启后自动对账恢复。
- **后端乐观并发控制（`interfaces/api/v1/workbench/prompt_mutation_cas.py`）**：提示词节点的新建、更新、删除全量收敛至进程级 `PROMPT_MUTATION_LOCK` 与 SQLite `BEGIN IMMEDIATE` 写事务中，在数据库事务内原子比对 `expected_active_version_id`、`expected_version_count`、`expected_system`、`expected_user_template` 等前置条件；一旦检测到并发抢占修改，立即拒绝写入并返回 `HTTP 409 Conflict`，彻底杜绝静默覆盖。

### 远程模组拉取纵深 SSRF 防护

后端远程模组清单拉取端点（`POST /api/v1/llm-control/mods/fetch-remote`，实现于 `interfaces/api/v1/workbench/mod_manifest_remote.py`）内置了严密的抗 DNS Rebinding 与流式守卫机制：

- **协议与地址白名单边界**：强制要求公网 `HTTPS` 标准 `443` 端口，严格拦截 `localhost`、内网私有网段、环回地址、链路本地、保留网段及 IPv6 映射私有地址，阻断路径穿越（`..`）与内嵌 URL 凭据。
- **逐跳 DNS 重解析与公网 IP 钉扎**：每次 HTTP 重定向（最多允许 3 跳）均异步重新解析 DNS，校验通过后直接**钉扎已验证的公网 IP 发起底层连接**（同时显式携带原始 `Host` 请求头并通过 TLS `sni_hostname` 完成严格服务端证书校验），每一跳均使用独立 `AsyncClient` 实例且零连接池复用，彻底免疫 DNS Rebinding 攻击。
- **TLS 字节流级响应头守卫（`_WireHeaderGuardStream`）**：在 TLS 解密后的原始字节流层直接拦截超长响应头（上限 `64 KiB`）以及 `Location` 响应头中的控制字符与 CRLF 折行注入；强制声明 `Accept-Encoding: identity` 无压缩读取，实施 `1 MiB` 响应体硬上限与端到端双重超时控制（单跳 15 秒 / 路由总计 30 秒）。

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

任何一次章节生成，引擎都会从上述快照中动态装配上下文窗口，而非依赖模型自身的“记忆”。

### 2. 向量语义检索层（Vector Retrieval Layer）

引擎维护两条并行索引：

- **章内容索引**：基于 FAISS / ChromaDB 的本地向量库，对所有已写章节做语义切片索引
- **三元组索引**：从正文中自动抽取的 `(主体, 关系, 客体)` 三元组，支持结构化与语义混合查询

生成时，引擎通过当前场景语义自动召回相关历史内容，注入上下文，消除“模型失忆”问题。嵌入服务支持 OpenAI 兼容 API（轻量）和本地 `sentence-transformers` 模型（离线高性能）。

### 3. 剧情引擎运行时（Engine Runtime）

这是引擎最核心的系统组件。当前生产入口收敛在 `engine/runtime/engine_daemon.py`：由 `EngineDaemon` 承接守护进程生命周期，委托 `StoryPipelineRunner` 运行章节规划、写作、审计与状态推进；章节写作默认走 `BaseStoryPipeline` 十步管线。

```
宏观规划（部 / 卷 / 幕结构）
    └─▶ 幕级节拍规划（Beat Sheet 生成）
            └─▶ 章节生成循环
                    ├─▶ 叙事治理预算
                    ├─▶ 章节执行剧本准备
                    ├─▶ 上下文装配（人物 / 世界观 / 记忆 / 伏笔）
                    ├─▶ LLM 调用
                    ├─▶ 内容策略验证
                    ├─▶ 文风漂移检测
                    ├─▶ 章末管线（摘要 / 事件 / 三元组 / 伏笔）
                    ├─▶ 向量索引更新
                    ├─▶ 张力评分
                    └─▶ 状态落库 → 继续 / 重写 / 暂停
```

关键工程特性：
- **单一生产入口**：`scripts/start_daemon.py` 构造依赖并启动 `EngineDaemon`
- **可回退写作路径**：默认 `StoryPipeline` 写作，`PLOTPILOT_USE_STORY_PIPELINE=off/legacy` 可临时回退
- **熔断保护**：连续失败超过阈值自动暂停，附带诊断信息
- **单写者路由（Write Dispatch）**：所有 SQLite 写操作经由统一调度器串行执行，消除并发写冲突
- **SSE 实时推流**：生成进度、Token 消耗、当前阶段、错误信息全部通过 Server-Sent Events 实时推送到前端
- **检查点快照**：阶段推进前自动存档，支持从任意检查点恢复

### 4. 提示词策略层（Prompt Strategy Layer）

引擎暴露 **20+ 独立提示接点**（内置 CPMS 完整包含 78 个可调优内核节点），每个接点均可通过 `prompt_packages/` 下的 YAML 配置文件或墨枢模组中心的 `plotpilot-mod/v1` 模组包独立覆写：

| 接点类型 | 包含接点 |
|----------|----------|
| 规划类 | `planning-main-plot-suggest` · `planning-quick-macro` |
| 生成类 | `scene-director` · `chapter-narrative-sync` |
| 知识类 | `bible-all` · `bible-characters` · `bible-locations` · `bible-worldbuilding` |
| 分析类 | `style-analysis` · `tension-analysis-diagnosis` |

每个提示包支持独立配置：系统提示、声线锚点、节拍约束、字数层级、记忆铁律、模型参数（temperature / top_p / max_tokens）。切换任务类型（短篇 / 长篇 / 游戏剧本）不需要修改代码，只需切换提示包目录或挂载对应叙事模组。

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
        ├── 剧情引擎运行时
        ├── 提示词策略层（20+ 核心接点 / 78 个内置 CPMS 节点）
        └── 质量监控子系统
                │
                ▼
        REST API（FastAPI · v1 · 版本化 + 原子 CAS + SSRF 守卫）
                │
        ┌───────┴──────────────────────┐
        │                              │
  官方工作台前端               生态扩展层（基于内核与 plotpilot-mod/v1）
  Vue 3.5 · TypeScript         ├── 墨枢模组中心（Mod Hub 双轨生态）
  宣纸松烟 UI · ECharts         ├── 垂直领域工具（剧本/游戏剧情/IP 衍生……）
  Tauri 桌面客户端              ├── 第三方前端 / 编辑器插件
                                ├── 自定义提示词包与 GitHub 开源模组
                                └── 云服务 / SaaS（需遵守许可证）
```

内核提供稳定的 REST API 边界；所有生态扩展均通过 `plotpilot-mod/v1` 叙事模组、提示词包、工作流插件或上层应用的方式叠加能力，内核本身不感知。如果你在用内核做二创，建议从叙事模组、提示词包和工作流层开始，而非修改内核代码。

### 云广场连接与隐私数据契约（可选）

内核内置一个**云连接器**（`/api/v1/cloud/*`），可登录 [plotpilot.xyz](https://plotpilot.xyz) 官方文墨广场，浏览官方书元、社区共享模组、全网热榜以及进行妙/批注/追更/收飞鸽通知互动——把本地创作接到云端社区。数据边界是显式契约：

- **上云仅限**：会话凭证、广场目录拉取（官方书元/社区共享/热榜）、广场互动（妙/批注/追更/通知）、风格包落笔事件的最小元数据（书名）
- **永不上云**：作品手稿、章节、知识图谱、人物设定、生成配置、引擎状态——内核断云完全可用
- 会话凭证（refresh cookie）只存内核服务端本地文件（`data/cloud-session.json`，权限 `0600`），浏览器/前端全程零明文凭证；连接器路由仅接受本机回环客户端
- 代理路径白名单 = 广场目录 + 社区 + 社交接口，无通配转发（SSRF 免疫）
- 公开目录（题材/官方书元/社区共享）**匿名可读**：桌面端「墨枢模组中心」页（`/square`）拉下来自渲染并自动适配为标准模组包，不跳转外部站点；热榜/互动需登录，未登录时 401 透传引导登录，云端不可达时仅作非阻断内联提示

默认端点 `https://plotpilot.xyz`，可用 `PLOTPILOT_CLOUD_BASE_URL` 覆盖（自建兼容服务端时）。接入协议遵循 plotpilot.xyz 公开 API 契约（`/api/v1/prompt-square/*`、`/api/v1/social/*`），内核侧不含任何社交判定逻辑。

---

## 技术选型说明

| 层 | 技术 | 选型理由 |
|----|------|----------|
| 后端框架 | FastAPI + uvicorn | 原生异步 + 自动 OpenAPI 文档，SSE 支持开箱即用 |
| 架构范式 | DDD 分层 + 独立 `engine/` 运行内核 | 领域逻辑、用例编排、生产写作管线与技术实现分离，生态扩展不污染内核 |
| AI 接入 | OpenAI 兼容协议 / Anthropic Claude / 火山方舟 Doubao | 统一接口抽象，模型切换不改业务代码 |
| 向量存储 | ChromaDB（默认）/ FAISS | 本地部署，零外部依赖，冷启动快 |
| 嵌入模型 | OpenAI 兼容 API / 本地 `bge-small-zh-v1.5` | 在线轻量与离线高性能双模式 |
| 主数据库 | SQLite + Write Dispatch 单写者路由 + `BEGIN IMMEDIATE` 原子 CAS | 嵌入式零依赖，并发写冲突与多标签页抢占由调度层与事务级 CAS 解决 |
| 前端 | Vue 3.5 + TypeScript + Vite + Naive UI + ECharts | 组件类型安全，宣纸松烟视觉系统，知识图谱与 DAG 可视化由 ECharts 驱动 |
| 桌面客户端 | Tauri（Rust） | 比 Electron 内存占用低 80%+，原生系统集成 |

---

## 快速开始

### 方式一：一键启动（Windows，无需安装 Python）

1. 将 `python-3.14.5-embed-amd64.zip` 放入 `tools/` 目录（仅首次）
2. 双击 `tools/plotpilot.bat`

启动器自动完成：环境自检 → 创建虚拟环境 → 安装依赖（自动切换国内镜像源）→ 启动服务 → 打开浏览器。后续启动直接双击。

> 支持 `tools\plotpilot.bat pack` 打包整个项目分享给他人，对方双击即用。当前启动器固定使用 Python 3.14 系列；如需使用系统 Python，可设置 `PLOTPILOT_PYTHON_EXE` 指向 Python 3.14 的 `python.exe`。

### 方式二：桌面安装版（Windows · Tauri）

前往 [GitHub Releases](https://github.com/pipi333/PlotPilot/releases)（或上游 [`shenminglinyi/PlotPilot` Releases](https://github.com/shenminglinyi/PlotPilot/releases)）下载最新安装包，内含冻结后端，无需单独安装 Python。

构建流程见 [docs/BUILD_INSTALLER.md](docs/BUILD_INSTALLER.md)。

---

## 开发者文档

**环境要求**：Python 3.14.x、Node.js 18+

```bash
# 后端 — Windows
py -3.14 -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env    # 填写 LLM 凭证
uvicorn interfaces.main:app --host 127.0.0.1 --port 8005 --reload
```

```bash
# 后端 — Linux / macOS
python3.14 -m venv .venv && source .venv/bin/activate
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
| `LLM_PROVIDER` | 可选；指定默认 LLM 提供方 |
| `ANTHROPIC_API_KEY` / `ARK_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` | 至少配置一个 LLM 凭证 |
| `ARK_BASE_URL` / `ARK_MODEL`、`ANTHROPIC_BASE_URL` / `ANTHROPIC_MODEL`、`OPENAI_BASE_URL` / `OPENAI_MODEL`、`GEMINI_BASE_URL` / `GEMINI_MODEL` | 对应提供方的接口地址与模型名 |
| `EMBEDDING_SERVICE` | `openai`（`.env.example` 默认）或 `local`（需额外安装模型，见 `requirements-local.txt`） |
| `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` | 云端嵌入服务配置；`EMBEDDING_API_KEY` 为空时可回退读取 `OPENAI_API_KEY` |
| `EMBEDDING_MODEL_PATH` / `EMBEDDING_USE_GPU` | 本地嵌入模型路径与 GPU 开关 |
| `VECTOR_STORE_ENABLED` / `VECTOR_STORE_TYPE` / `VECTOR_STORE_PATH` | 向量索引开关、类型与持久化目录 |
| `CORS_ORIGINS` | 生产环境前端域名，逗号分隔 |
| `DISABLE_AUTO_DAEMON` | 设为 `1` 禁止启动时自动拉起守护进程 |
| `LOG_LEVEL` / `LOG_FILE` | 日志级别与路径 |
| `PLOTPILOT_CLOUD_BASE_URL` / `PLOTPILOT_CLOUD_CLIENT_NAME` / `PLOTPILOT_CLOUD_TIMEOUT` | 云广场连接器：端点（默认 `https://plotpilot.xyz`）、客户端标识（默认 `plotpilot-kernel`）、请求超时秒数 |

完整说明见 [`.env.example`](.env.example)。

---

## 架构目录

```
（项目根目录）/
├── domain/                 # 领域层 — 纯业务模型和值对象
│   ├── novel/             # 小说、章节、故事线、伏笔、因果、张力
│   ├── bible/             # 设定库、人物档案、地点、时间线
│   ├── character/         # 人物实体、人物状态、关系能力
│   ├── cast/              # 卡司与人物关系图
│   ├── knowledge/         # 知识三元组、故事知识图
│   ├── memory/            # 长期记忆与上下文状态
│   ├── prop/              # 道具生命周期与道具事件
│   ├── worldbuilding/     # 世界观领域模型
│   ├── structure/         # 故事结构节点
│   ├── evolution/         # 世界线 / 演化相关模型
│   ├── ai/                # AI 领域契约与值对象
│   └── shared/            # 共享基类、异常、事件、ID
│
├── application/           # 应用层 — 用例编排，协调领域、引擎与基础设施
│   ├── core/              # 小说 / 章节 / 导出等基础用例
│   ├── onboarding/        # 新书向导、前置设定生成
│   ├── blueprint/         # 宏观规划、连续规划、Beat Sheet、故事结构
│   ├── engine/            # 上下文构建、章后管线、治理预算、AI 调用编排
│   ├── governance/        # 叙事治理、质量约束、章节预算
│   ├── audit/             # 章节审阅、宏观重构、章节元素分析
│   ├── analyst/           # 文风、张力、伏笔账本、叙事状态分析
│   ├── world/             # Bible、知识图谱、世界观与人物关系服务
│   ├── ai/                # LLM / embedding 应用服务
│   ├── ai_invocation/     # AI 调用记录与审阅
│   ├── checkpoint/        # 检查点与快照用例
│   ├── memory/            # 记忆编排用例
│   ├── narrative/         # 叙事投影与状态同步
│   ├── narrative_engine/  # 叙事引擎应用服务
│   ├── manuscript/        # 正文实体索引与手稿服务
│   ├── prop/              # 道具应用服务
│   ├── reader/            # 读者模拟 / 阅读侧能力
│   ├── snapshot/          # 快照应用服务
│   ├── workbench/         # 工作台编排
│   └── workflows/         # 自动生成工作流、兼容编排与后台任务
│
├── engine/                # 剧情引擎内核 — 生产运行时、章节写作管线与题材扩展
│   ├── runtime/           # EngineDaemon、StoryPipelineRunner、守护进程委托、质量守门
│   ├── pipeline/          # BaseStoryPipeline 十步章节生成管线
│   ├── pipelines/         # 题材 Pipeline 注册与扩展（如武侠、通用题材桥接）
│   ├── core/              # 引擎侧实体、端口、服务契约
│   └── infrastructure/    # 引擎事件、记忆编排、checkpoint 适配
│
├── infrastructure/        # 基础设施层 — 技术实现，可替换
│   ├── ai/                # LLM Provider、Prompt Packages、向量存储、嵌入服务
│   ├── persistence/       # SQLite 仓储、迁移、Write Dispatch 单写者调度器
│   ├── export/            # DOCX / EPUB / PDF 导出
│   └── runtime/           # 数据目录、日志环境与进程级运行配置
│
├── interfaces/            # 接口层 — FastAPI、依赖注入、运行状态与外部边界
│   ├── main.py            # FastAPI 应用入口
│   ├── daemon_manager.py  # 后端内自动驾驶进程管理
│   └── api/v1/            # REST API（core / world / blueprint / engine / audit / analyst 等）
│       └── workbench/     # 工作台与模组中心接口
│           ├── mod_manifest_remote.py  # 远程模组清单安全拉取与逐跳 IP 钉扎 SSRF 防护
│           └── prompt_mutation_cas.py  # SQLite BEGIN IMMEDIATE 原子 CAS 提示词变更事务
│
├── frontend/              # 官方工作台 — Vue 3.5 + TypeScript + Tauri 桌面壳
│   ├── src/               # 工作台、自动驾驶、知识图谱、设置、API client
│   │   ├── components/modhub/   # 模组卡片、详情弹窗、创作者模组打包工坊（ModPackBuilderModal.vue）
│   │   ├── domain/modPack/      # plotpilot-mod/v1 协议解析器、内置精选包、云端适配器、WAL 卸载引擎
│   │   └── stores/modHubStore.ts # 跨标签页 Web Locks 事务级模组状态管理
│   └── src-tauri/         # Tauri 桌面客户端与后端 sidecar
│
├── shared/                # 跨端共享配置与分类体系资源
├── config/                # 本地配置与默认配置
├── scripts/               # 启动、安装、迁移、评估与维护脚本
├── tests/                 # 单元、集成、E2E 与 DAG 测试
│   └── unit/              # 含 test_mod_hub_remote.py、test_prompt_mutation_cas.py 等专项单测
└── tools/                 # Windows 启动器与内嵌 Python 包
```

完整设计与分层说明见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

---

## 测试

```bash
pytest tests/ -v
# 含覆盖率报告
pytest tests/ --cov=. --cov-report=term-missing
# 运行模组中心远程安全拉取与原子 CAS 专项单元测试
pytest tests/unit/test_mod_hub_remote.py tests/unit/test_prompt_mutation_cas.py -v
```

---

## 社区重启与贡献者招募

PlotPilot（PP）正在重新整理开源项目的维护机制与社区协作方式。

随着项目持续发展，我们将重新整理贡献者团队，仅保留活跃贡献者的仓库协作权限。此次调整只涉及当前维护权限，不会抹去任何人的历史贡献；所有曾参与代码、测试、文档、Issue、产品讨论或社区建设的成员，都会继续记录在 [CONTRIBUTORS.md](CONTRIBUTORS.md) 中。

这样做是为了降低沟通与管理成本、明确维护责任，让社区重新焕发活力。如果你认同 PlotPilot 的发展方向，并愿意持续参与 PP 的研发、测试、文档、设计、社区维护或生态建设，欢迎联系我们，申请加入贡献者团队：

- **联系方式**：抖音搜索 **91472902104**，通过私信联系

我们更看重长期参与意愿、实际行动和稳定协作，而不仅是一次性的代码提交。贡献者权限将根据参与方向、协作情况和维护责任逐步开放。

---

## 贡献指南

1. Fork 本仓库
2. 新建分支：`git checkout -b feat/your-feature`
3. 提交信息建议遵循 [Conventional Commits](https://www.conventionalcommits.org/)
4. 推送并发起 Pull Request

架构与分层说明见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)；其余文档索引见 [docs/README.md](docs/README.md)。

---

## 提交安全边界

请不要提交以下内容：

- `.env`、API Key、模型网关地址中的私有凭证
- `data/`、`logs/`、SQLite 数据库、向量库、运行时缓存
- Word / PPT / Excel 等办公文档（如 `.docx`、`.pptx`、`.xlsx`），尤其是未公开设定、商业计划、合同、客户资料
- 打包产物、安装包、Tauri / PyInstaller 输出目录

如果必须提交示例资料，请放入脱敏后的 Markdown / JSON / YAML，并确认不包含真实密钥、真实用户数据或未公开作品内容。

---

## 生态共建 (Community & Contribution)

PlotPilot 引擎仍在持续演进中，我们始终致力于用工程化手段解决复杂的创作状态管理问题。我们正在寻找对“叙事工程”与“大模型复杂系统架构”感兴趣的极客同行。

**当前生态演进方向**：内核引擎研发、开放叙事模组（`plotpilot-mod/v1`）生态构建、提示词工程、前端工作台、测试、文档与社区维护。如果你有志于长期共建，欢迎通过以下方式参与：

*   **核心代码与架构共建：** 请直接在 GitHub 提交 Issue 或 PR，引擎核心维护组会定期 Review。
*   **跨界应用探讨与联系：** 如果你对叙事工程的垂直生态应用（如游戏剧本、IP 衍生）感兴趣，或希望申请加入贡献者团队，可在抖音搜索 **91472902104**，通过私信联系。

---

## 许可证

本项目采用 **Apache License 2.0**，并附加 **Commons Clause** 条件限制。

- **允许**：学习、修改、非商业内部部署、基于内核的生态扩展（非营利）
- **禁止**：将本项目（含修改版）封装为收费 SaaS、打包售卖源码或作为收费产品的增值服务

详见 [LICENSE](LICENSE)。
