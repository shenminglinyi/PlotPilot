# 项目上下文

## 当前目标

在 PlotPilot 基础上建立本地自用二开版本，优先补强长期小说创作能力，而不是追随上游做通用产品扩展。

## 当前基线

- 本地二开目录：`/Users/frank/Documents/小说/PlotPilot-NovelPro`
- 当前开发分支：`local/novel-pro`
- 当前同步基线：`v1.0.4`
- v1.0.4 同步提交：`1166ceb`
- 原始冻结基线：`local/base-v1.0.3`
- 上游远程：`upstream`，push URL 已禁用，避免误推。

## 开发边界

- 默认在 `local/novel-pro` 或后续 `local/feature-*` 分支上开发。
- 不直接把上游更新合并进二开主线；后续只选择性吸收。
- 新功能要尽量复用现有章节、Bible、知识图谱、审计、生成和工作台能力。
- AI 改稿、生成、导入类能力默认保留预览、快照或回滚路径，避免直接覆盖正文。
- 当前 NovelPro 主流程要求：作者在 PP 内写作，AI 使用 PP 当前激活配置；Obsidian 作为长期主记忆回读源，PP SQLite Knowledge 作为运行缓存和写后导出来源。

## 已知说明

- `v1.0.4` 已通过 GitHub compare API 从 `v1.0.3` 补齐到本地二开主线。
- 少量 Tauri 图标资源因 GitHub API 限流和 raw 下载超时，使用上游 `icon-source-1024.png` 在本机重新生成；尺寸和用途匹配，但不保证与上游二进制逐字节一致。
