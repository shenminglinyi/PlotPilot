# 文档（PlotPilot / 墨枢）

本目录只保留长期有效、可由代码或流程验证的维护文档。一次性验收报告、截图审计、已经完成的实施计划和本机绝对路径不进入主分支。

| 文档 | 说明 |
|------|------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 分层目录、模块职责与数据流概览 |
| [BUILD_INSTALLER.md](BUILD_INSTALLER.md) | Windows / macOS 安装包的本地构建要点 |
| [RELEASE_DESKTOP.md](RELEASE_DESKTOP.md) | 三平台签名发布、GitHub Actions 与发布后验证 |
| [LOGGING.md](LOGGING.md) | 日志配置、查看与故障定位 |
| [embedding_model_download_guide.md](embedding_model_download_guide.md) | 本地向量嵌入模型下载与配置 |

仓库总览、启动方式与环境变量以根目录 [README.md](../README.md) 与 [.env.example](../.env.example) 为准。

新增或移动文档后运行 `python scripts/check_docs.py` 检查仓库内 Markdown 链接。请勿提交 `.docx`、`.pptx`、`.xlsx`、内部路线图、未公开设定稿、客户资料或包含密钥的运行日志。
