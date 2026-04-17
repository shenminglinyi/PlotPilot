# -*- coding: utf-8 -*-
"""
aitext 安装/启动/打包 模块化工具包
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
模块说明:
  theme      – 统一颜色主题 & 字体配置
  utils      – 端口检测、进程管理、锁文件等通用工具
  ui_base    – 可复用的 tkinter UI 基类（标题栏、日志面板、进度条、底部栏）
  env_check  – Python / venv / Node.js / .env 环境检测与自动修复
  installer  – pip 依赖安装（含实时进度 & 心跳动画）
  launcher   – uvicorn 后端服务启动 & 健康检查
  packer     – 项目打包为 ZIP 分享包
  hub        – 主入口：组合以上所有模块，提供统一 GUI
"""
