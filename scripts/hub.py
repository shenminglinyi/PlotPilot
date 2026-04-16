# -*- coding: utf-8 -*-
"""
aitex 统一入口 — 向后兼容薄包装
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
本文件保留在 scripts/hub.py 以兼容旧调用方式。
实际逻辑已全部迁移到 scripts/install/ 模块包中。

模块结构:
  scripts/install/
  ├── __init__.py     – 包说明
  ├── theme.py        – 统一颜色/字体主题
  ├── utils.py        – 端口/进程/锁文件等工具
  ├── ui_base.py      – 可复用 UI 组件基类
  ├── env_check.py    – 环境检测与自动修复
  ├── installer.py    – pip 依赖安装器
  ├── launcher.py     – 后端服务启动器
  ├── packer.py       – 项目打包分享
  └── hub.py          – 主窗口（组合以上所有模块）
"""

# 直接委托给模块化版本
from scripts.install.hub import main

if __name__ == "__main__":
    main()
