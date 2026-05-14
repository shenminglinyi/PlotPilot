# -*- coding: utf-8 -*-
"""
PlotPilot 统一视觉主题
━━━━━━━━━━━━━━━━
所有 GUI 窗口共享同一套颜色/字体方案，
确保品牌一致、维护方便（改一处即全局生效）。
"""

# ── 调色板 ──────────────────────────────────────
BG      = "#0f1117"   # 主背景（深夜蓝黑）
BG2     = "#1a1d27"   # 卡片 / 标题栏背景
BG3     = "#22263a"   # 输入框 / 日志面板背景
ACCENT  = "#6c63ff"   # 主题紫（主按钮 / 强调）
ACCENT2 = "#4ecdc4"   # 青绿（次要强调 / 链接）
OK_C    = "#4ade80"   # 成功绿
WARN_C  = "#fbbf24"   # 警告黄
ERR_C   = "#f87171"   # 错误红
TEXT    = "#e2e8f0"   # 主文字颜色
TEXT_DIM= "#64748b"   # 弱化文字（占位符 / 提示）
BORDER  = "#2d3250"   # 分割线 / 边框

# ── 字体 ────────────────────────────────────────
FONT_TITLE  = ("微软雅黑", 11, "bold")   # 标题栏
FONT_BODY   = ("微软雅黑", 10)           # 正文
FONT_SMALL  = ("微软雅黑", 9)            # 小字（步骤标签 / 底部栏）
FONT_MONO   = ("Consolas", 9)            # 日志 / 代码
FONT_LOGO   = ("Arial Black", 28, "bold") # LOGO
FONT_ICON   = ("Segoe UI Emoji", 14)     # 状态图标
FONT_BTN    = ("微软雅黑", 10, "bold")    # 主要按钮

# ── 尺寸常量 ────────────────────────────────────
WINDOW_W = 740
WINDOW_H = 600
TITLE_BAR_H = 40
LOGO_H    = 80
FOOT_H    = 44
CARD_PADX = 30


def setup_progressbar_style(master=None):
    """配置 ttk.Progressbar 样式，返回 style 名"""
    import tkinter.ttk as ttk
    style = ttk.Style()
    style.theme_use("clam")
    style.configure(
        "Aitext.Horizontal.TProgressbar",
        troughcolor=BG3,
        background=ACCENT,
        bordercolor=BG3,
        lightcolor=ACCENT,
        darkcolor=ACCENT,
        thickness=8,
    )
    return "Aitext.Horizontal.TProgressbar"
