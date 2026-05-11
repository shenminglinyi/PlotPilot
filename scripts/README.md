# 脚本目录

运维与工具脚本按子目录划分，与主应用测试（`tests/`）分开。


| 目录            | 说明                        |
| ------------- | ------------------------- |
| `install/`    | 图形安装器 / PyInstaller 相关入口  |
| `setup/`      | 环境自检、数据库初始化               |
| `evaluation/` | 离线评估与跑分                   |
| `migrations/` | 一次性数据迁移                   |
| `utils/`      | 模型下载、本地数据清理等              |
| `prototypes/` | 可选实验原型（模拟/真实 API），非 CI 依赖 |


迁移说明见 `MIGRATION_GUIDE.md`。其余见仓库根目录 `README.md`。