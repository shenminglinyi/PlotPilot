# 项目风险与易错点

## 仍需注意

- GitHub 网络访问不稳定，git/zip/raw 下载都可能超时；后续补上游更新时，优先用 GitHub compare API 或小批量文件同步。
- 本地 `v1.0.4` 中少量 Tauri 图标由 `icon-source-1024.png` 重新生成，不保证与上游二进制逐字节一致；如后续需要发行安装包，再单独复核图标资源。
- 上游更新策略是“选择性吸收”，不要直接 merge/rebase 上游分支到 `local/novel-pro`。
- 番茄字体混淆已支持当前 `dc027189e0ba4cd` 字体映射；如果番茄更换字体文件或映射表，仍需重新补映射或切到更稳定的 JSON/API 来源。
- 宝塔旧库可能缺少最新 `topic_ideas` 列；已在 `DatabaseConnection` 启动前迁移中补齐当前列。后续新增选题表列时，应同步补启动前迁移，避免 `CREATE INDEX` 或仓储保存时被旧库阻断。
- 线上 AI 章节生成当前依赖 LLM 控制台配置；API Key/模型名为空时会回退 MockProvider，接口可以返回 SSE，但内容可能是测试 JSON 而不是小说正文。已改为 Kimi + DS profile，地址与模型名已配置；补 API Key 前不要把试写结果判断为真实模型质量。
- Kimi `coding-intl.dashscope.aliyuncs.com/v1` 网关支持 `/chat/completions`，但不支持 `/models`，拉模型列表会 404；后端已对该类网关做模型列表兜底，测试连接结果比模型列表更能代表真实可用性。
- 高频采集/全链路测试后曾出现 SQLite `database is locked`，重启 `plotpilot-novelpro.service` 后解除。后续若复现，需要优先检查是否有长事务或后台采集与章节生成并发写入。

## 已解除

- `v1.0.3` 基线落后于上游 `v1.0.4` 的问题已处理，本地二开主线当前同步到 `v1.0.4`。
