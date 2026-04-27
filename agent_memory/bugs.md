# 项目风险与易错点

## 仍需注意

- GitHub 网络访问不稳定，git/zip/raw 下载都可能超时；后续补上游更新时，优先用 GitHub compare API 或小批量文件同步。
- 本地 `v1.0.4` 中少量 Tauri 图标由 `icon-source-1024.png` 重新生成，不保证与上游二进制逐字节一致；如后续需要发行安装包，再单独复核图标资源。
- 上游更新策略是“选择性吸收”，不要直接 merge/rebase 上游分支到 `local/novel-pro`。
- 候选稿采纳已经复用现有 `ChapterAftermathPipeline`；后续任何 A/B、精修、外部模型写回都不要绕开这个入口，否则会再次出现“正文更新了但结构化记忆没更新”的双轨问题。
- API 集成测试会触发现有向量存储初始化；当前 worktree 只安装了 `requirements.txt`，未装 `requirements-local.txt`，因此会看到 `faiss` 缺失告警。现阶段不影响候选稿闭环测试，但后续如果要测向量相关能力，需要补本地依赖或显式 mock 掉向量层。
- 新建 worktree 默认没有 `frontend/node_modules`；前端改动验证前需要先在 worktree 下执行 `cd frontend && npm ci`，否则 `npm run build` 会因为缺少 `vue-tsc` 直接失败。
- 当前 `tests/integration/interfaces/api/v1/conftest.py` 使用 `DatabaseConnection(\":memory:\")`，而连接对象内部又按线程缓存 SQLite 连接；如果测试先在主线程手动写库、再通过 `TestClient` 走请求线程读取，容易出现“主线程有表，请求线程 no such table” 的假失败。此类用例优先写成纯单元测试，或把数据创建动作也放到请求线程侧完成。

## 已解除

- `v1.0.3` 基线落后于上游 `v1.0.4` 的问题已处理，本地二开主线当前同步到 `v1.0.4`。
