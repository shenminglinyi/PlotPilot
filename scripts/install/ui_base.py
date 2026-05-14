# -*- coding: utf-8 -*-
"""
PlotPilot 可复用 UI 组件基类
━━━━━━━━━━━━━━━━━━
提供所有窗口共用的 UI 构建块:
  - BaseWindow: 基础窗口（标题栏、拖拽、居中、overrideredirect）
  - LogPanel:   日志面板（带颜色 tag）
  - StatusCard:  状态卡片（图标 + 文字 + 进度条 + 百分比）
  - StepBar:    步骤指示器
  - FootBar:    底部操作栏
  - 弹窗工具:   fatal / warning / success popup
"""

import tkinter as tk
from tkinter import ttk
import threading
import os

from theme import (
    BG, BG2, BG3, ACCENT, ACCENT2, OK_C, WARN_C, ERR_C,
    TEXT, TEXT_DIM, BORDER,
    FONT_TITLE, FONT_BODY, FONT_SMALL, FONT_MONO,
    FONT_LOGO, FONT_ICON, FONT_BTN,
    WINDOW_W, WINDOW_H, TITLE_BAR_H, LOGO_H, FOOT_H, CARD_PADX,
    setup_progressbar_style,
)
from utils import NO_WIN


# ══════════════════════════════════════════════
# 系统托盘 (Windows) — 使用 ctypes 调用 Shell API
# ══════════════════════════════════════════════

class SystemTray:
    """
    Windows 系统托盘图标。
    最小化后窗口隐藏到托盘，双击托盘图标恢复窗口。
    纯 ctypes 实现，无需第三方依赖。
    """

    def __init__(self, root_window, title="PlotPilot", on_double_click=None):
        self.root = root_window  # tk.Tk 实例
        self.title = title
        self.on_double_click = on_double_click or (lambda: None)
        self._visible = True
        self._tray_id = None

        # 仅在 Windows 上启用
        if os.name != "nt":
            return

        try:
            import ctypes
            from ctypes import wintypes

            # Windows 常量
            NIM_ADD = 0
            NIM_MODIFY = 1
            NIM_DELETE = 2
            NIF_MESSAGE = 1
            NIF_ICON = 2
            NIF_TIP = 4
            WM_USER = 0x0400
            WM_LBUTTONDBLCLK = WM_USER + 3
            LR_LOADFROMFILE = 0x0010
            IDI_APPLICATION = 32512  # 默认应用图标

            # NOTIFYICONDATA 结构体
            class NOTIFYICONDATA(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("hWnd", wintypes.HWND),
                    ("uID", wintypes.UINT),
                    ("uFlags", wintypes.UINT),
                    ("uCallbackMessage", wintypes.UINT),
                    ("hIcon", wintypes.HICON),
                    ("szTip", wintypes.CHAR * 128),
                    ("dwState", wintypes.DWORD),
                    ("dwStateMask", wintypes.DWORD),
                    ("szInfo", wintypes.CHAR * 256),
                    ("uTimeout", wintypes.UINT),
                    ("szInfoTitle", wintypes.CHAR * 64),
                    ("dwInfoFlags", wintypes.DWORD),
                ]

            user32 = ctypes.windll.user32
            shell32 = ctypes.windll.shell32
            kernel32 = ctypes.windll.kernel32

            # 创建隐藏消息窗口来接收托盘回调
            wc_name = "AitexTrayMsgWindow"
            wc = ctypes.wintypes.WNDCLASS()
            wc.lpszClassName = wc_name
            wc.lpfnWndProc = ctypes.WNDPROC(self._tray_wnd_proc)
            wc.hInstance = kernel32.GetModuleHandleW(None)

            reg = user32.RegisterClassW(ctypes.byref(wc))
            if not reg:
                return

            self._tray_hwnd = user32.CreateWindowExW(
                0, wc_name, "", 0,
                0, 0, 0, 0, 0, 0, wc.hInstance, None,
            )
            if not self._tray_hwnd:
                return

            # 加载默认图标
            h_icon = user32.LoadIconW(None, IDI_APPLICATION)

            # 设置 NOTIFYICONDATA
            nid = NOTIFYICONDATA()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
            nid.hWnd = self._tray_hwnd
            nid.uID = 0
            nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            nid.uCallbackMessage = WM_LBUTTONDBLCLK
            nid.hIcon = h_icon
            tip_bytes = title.encode("utf-8")[:127]
            nid.szTip = tip_bytes + b"\0" * (128 - len(tip_bytes))

            # 添加托盘图标
            shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
            self._nid = nid
            self._shell32 = shell32
            self._user32 = user32
            self._NIM_DELETE = NIM_DELETE

            # 启动消息循环线程
            self._msg_thread_running = True
            threading.Thread(target=self._message_loop, daemon=True).start()

        except Exception as e:
            # 托盘创建失败不影响主程序运行
            print(f"[WARN] System tray init failed: {e}")
            self._tray_hwnd = None

    def _tray_wnd_proc(self, hwnd, msg, wparam, lparam):
        """托盘消息处理：双击恢复窗口"""
        import ctypes
        from ctypes import wintypes
        WM_USER = 0x0400
        WM_LBUTTONDBLCLK = WM_USER + 3
        if msg == WM_LBUTTONDBLCLK:
            try:
                self.root.after(0, self._restore)
            except Exception:
                pass
        return 0

    def _message_loop(self):
        """后台消息循环，接收托盘事件"""
        import ctypes
        from ctypes import wintypes
        MSG = ctypes.Structure if False else None  # placeholder
        try:
            class MSG(ctypes.Structure):
                _fields_ = [
                    ("hwnd", wintypes.HWND),
                    ("message", wintypes.UINT),
                    ("wParam", wintypes.WPARAM),
                    ("lParam", wintypes.LPARAM),
                    ("time", wintypes.DWORD),
                    ("pt", wintypes.POINT),
                ]
            user32 = ctypes.windll.user32
            while self._msg_thread_running:
                m = MSG()
                if user32.PeekMessageW(ctypes.byref(m), 0, 0, 0, 1):
                    user32.TranslateMessage(ctypes.byref(m))
                    user32.DispatchMessageW(ctypes.byref(m))
                else:
                    import time
                    time.sleep(0.05)
        except Exception:
            pass

    def _restore(self):
        """从托盘恢复窗口"""
        try:
            self.root.deiconify()
            self.root.overrideredirect(True)
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(100, lambda: self.root.attributes("-topmost", False))
            self._visible = True
            self.on_double_click()
        except Exception:
            pass

    def hide_to_tray(self):
        """隐藏窗口到系统托盘"""
        if not getattr(self, '_tray_hwnd', None):
            return
        try:
            self.root.withdraw()  # 隐藏窗口（不是 iconify）
            self._visible = False
        except Exception:
            pass

    def remove(self):
        """移除托盘图标"""
        self._msg_thread_running = False
        if hasattr(self, "_shell32") and hasattr(self, "_nid"):
            try:
                self._shell32.Shell_NotifyIconW(
                    self._NIM_DELETE, ctypes.byref(self._nid))
            except Exception:
                pass


# ══════════════════════════════════════════════
# 基础窗口
# ══════════════════════════════════════════════

class BaseWindow:
    """
    所有 PlotPilot GUI 窗口的基类。
    提供: 无边框窗口、标题栏(拖拽+关闭)、居中、Logo区
    子类只需实现 _build_body() 即可。

    重要: 所有弹窗(show_popup)必须等 root 映射后才能调用，
          否则 winfo_x/y 返回错误值导致崩溃。
    """

    def __init__(self, title, width=WINDOW_W, height=WINDOW_H,
                 show_minimize=False, on_close=None):
        self.width = width
        self.height = height
        self._running = True
        self._drag_x = self._drag_y = 0
        self._on_close_cb = on_close
        self._mapped = False  # 窗口是否已映射（<Map> 事件后为 True）
        self._tray = None     # 系统托盘实例

        self.root = tk.Tk()
        self.root.title(title)
        self.root.geometry(f"{width}x{height}")
        self.root.resizable(False, False)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 居中
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{width}x{height}+{(sw-width)//2}+{(sh-height)//2}")

        # 自定义标题栏
        self.root.overrideredirect(True)
        # 绑定 Map 事件：窗口首次显示后标记为已映射
        self.root.bind("<Map>", self._on_map_event, add=True)
        # 绑定 FocusIn：确保窗口在被点击/激活时提升到最前（防止被其他窗口遮挡后丢失）
        self.root.bind("<FocusIn>", lambda e: self._raise_window(), add=True)

        # 按顺序构建 UI
        self._build_title_bar(title, show_minimize)
        self._build_logo_area(title)
        self._build_separator()

        # 子类填充主体
        self._build_body()

        # 创建系统托盘（最小化时使用）
        if show_minimize:
            self._tray = SystemTray(
                self.root,
                title=title,
                on_double_click=self._on_tray_restore,
            )

    def _on_map_event(self, event):
        """窗口首次映射时调用——标记 _mapped=True"""
        self._mapped = True

    def _build_title_bar(self, title, show_minimize):
        """构建可拖拽的标题栏"""
        bar = tk.Frame(self.root, bg=BG2, height=TITLE_BAR_H)
        bar.pack(fill="x")
        bar.bind("<ButtonPress-1>", self._drag_start)
        bar.bind("<B1-Motion>",     self._drag_move)

        tk.Label(bar, text=f"  ✦  {title}",
                 bg=BG2, fg=TEXT, font=FONT_TITLE).pack(side="left", pady=6)

        btn_frame = tk.Frame(bar, bg=BG2)
        btn_frame.pack(side="right")

        if show_minimize:
            tk.Button(btn_frame, text="─", bg=BG2, fg=TEXT_DIM,
                      relief="flat", bd=0, font=("Arial", 12), cursor="hand2",
                      activebackground=BORDER, activeforeground=TEXT,
                      command=self._minimize).pack(side="right", padx=2, pady=4)

        tk.Button(btn_frame, text="✕", bg=BG2, fg=TEXT_DIM,
                  relief="flat", bd=0, font=("Arial", 12), cursor="hand2",
                  activebackground=ERR_C, activeforeground="#fff",
                  command=self._on_close).pack(side="right", padx=10, pady=4)

    def _build_logo_area(self, title):
        """Logo 区域（子类可覆写）"""
        logo_f = tk.Frame(self.root, bg=BG, height=LOGO_H)
        logo_f.pack(fill="x")
        logo_f.pack_propagate(False)
        tk.Label(logo_f, text="PlotPilot",
                 bg=BG, fg=ACCENT, font=FONT_LOGO).pack(expand=True)

    def _build_separator(self):
        """分割线"""
        tk.Frame(self.root, bg=BORDER, height=1).pack(
            fill="x", padx=CARD_PADX, pady=(8, 0))

    def _build_body(self):
        """子类覆写：在分割线下方构建主体内容"""
        pass

    # ── 拖拽 / 最小化 / 关闭 ────────────────────
    def _drag_start(self, e):
        self._drag_x = e.x_root - self.root.winfo_x()
        self._drag_y = e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        self.root.geometry(f"+{e.x_root-self._drag_x}+{e.y_root-self._drag_y}")

    def _raise_window(self):
        """将窗口提升到桌面最顶层（防止被其他窗口遮挡）"""
        try:
            self.root.lift()
            self.root.attributes("-topmost", True)
            # 短暂置顶后取消，避免永远遮挡其他窗口
            self.root.after(100, lambda: self.root.attributes("-topmost", False))
        except Exception:
            pass

    def _minimize(self):
        """最小化窗口 → 缩到任务栏（用户可在任务栏点击恢复）"""
        try:
            # 记录当前位置，方便恢复
            self._saved_geom = self.root.geometry()
            # 使用 iconify 最小化到任务栏（而不是 withdraw 完全隐藏）
            # withdraw 会让窗口从任务栏也消失，用户误以为程序闪退
            self.root.iconify()
        except Exception:
            pass

    def _auto_restore_if_hidden(self):
        """如果窗口仍然隐藏，自动恢复显示"""
        try:
            if self.root.winfo_exists():
                # 检查窗口是否被映射（visible）
                state = self.root.state()
                if state == "withdrawn":
                    self.root.deiconify()
                    self.root.lift()
                    self.root.attributes("-topmost", True)
                    self.root.after(200, lambda: self.root.attributes("-topmost", False))
        except Exception:
            pass

    def _cancel_auto_restore(self):
        """取消自动恢复定时器"""
        try:
            if hasattr(self, '_auto_restore_id'):
                self.root.after_cancel(self._auto_restore_id)
        except Exception:
            pass

    def _on_tray_restore(self):
        """从系统托盘恢复窗口"""
        try:
            self._cancel_auto_restore()
            self.root.deiconify()
            # 恢复 overrideredirect 模式
            self.root.overrideredirect(True)
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(100, lambda: self.root.attributes("-topmost", False))
        except Exception:
            pass

    def _on_restore(self, event=None):
        """从任务栏恢复窗口（非托盘模式）"""
        self.root.overrideredirect(True)
        self.root.title("PlotPilot（墨枢）· AI 小说创作平台")
        self.root.unbind("<Map>")

    def _on_close(self):
        self._running = False
        # 移除托盘图标
        if self._tray:
            self._tray.remove()
        if self._on_close_cb:
            self._on_close_cb()
        try:
            self.root.destroy()
        except Exception:
            pass


# ══════════════════════════════════════════════
# 可复用组件
# ══════════════════════════════════════════════

class LogPanel:
    """日志面板 (Text + Scrollbar + 颜色 tag)"""

    def __init__(self, parent):
        frame = tk.Frame(parent, bg=BG3)
        # 不用 expand=True，避免与 FootBar(side=bottom) 冲突
        # 改用固定高度 + fill both
        frame.pack(fill="both", expand=True, padx=CARD_PADX, pady=(0, 4))

        self.text = tk.Text(
            frame, bg=BG3, fg=TEXT, font=FONT_MONO,
            relief="flat", bd=0, state="disabled", wrap="none",
            selectbackground=ACCENT,
        )
        scroll = tk.Scrollbar(frame, command=self.text.yview, bg=BG3)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.text.pack(fill="both", expand=True, padx=4, pady=4)

        # 颜色 tag
        for tag, color in [
            ("info", TEXT_DIM), ("ok", OK_C),
            ("warn", WARN_C), ("error", ERR_C),
            ("title", ACCENT2),
        ]:
            if tag == "title":
                self.text.tag_configure(tag, foreground=color,
                                        font=(FONT_MONO[0], FONT_MONO[1], "bold"))
            else:
                self.text.tag_configure(tag, foreground=color)

    def log(self, msg, tag="info"):
        """线程安全：追加一行日志"""
        import time as _time
        def _do():
            try:
                self.text.configure(state="normal")
                ts = _time.strftime("%H:%M:%S")
                self.text.insert("end", f"[{ts}]  {msg}\n", tag)
                self.text.see("end")
                self.text.configure(state="disabled")
            except Exception:
                pass
        self.text.after(0, _do)


class StatusCard:
    """状态卡片：图标 + 标签 + 进度条 + 百分比"""

    def __init__(self, parent, port=8005):
        card = tk.Frame(parent, bg=BG2)
        card.pack(fill="x", padx=CARD_PADX, pady=10)

        row1 = tk.Frame(card, bg=BG2)
        row1.pack(fill="x", padx=16, pady=(10, 4))

        self.icon = tk.Label(row1, text="⏳", bg=BG2, fg=ACCENT2, font=FONT_ICON)
        self.icon.pack(side="left")

        self.label = tk.Label(row1, text="正在初始化...",
                               bg=BG2, fg=TEXT, font=("微软雅黑", 11, "bold"))
        self.label.pack(side="left", padx=8)

        self.port_badge = tk.Label(
            row1, text=f"端口 {port}",
            bg=ACCENT, fg="#fff", font=FONT_SMALL, padx=8, pady=2,
        )
        self.port_badge.pack(side="right", padx=4)

        # 进度条
        style_name = setup_progressbar_style()
        self.pv = tk.DoubleVar(value=0)
        ttk.Progressbar(card, variable=self.pv, maximum=100,
                        style=style_name, length=680).pack(padx=16, pady=(0, 4))

        self.pct_lbl = tk.Label(card, text="0%", bg=BG2, fg=TEXT_DIM, font=FONT_SMALL)
        self.pct_lbl.pack(anchor="e", padx=16)

    def update(self, pct, label="", icon="⏳"):
        """更新状态"""
        def _do():
            self.pv.set(pct)
            self.pct_lbl.config(text=f"{int(pct)}%")
            if label:
                self.label.config(text=label)
            if icon:
                self.icon.config(text=icon)
        self.icon.after(0, _do)


class StepIndicator:
    """步骤指示器：1. xxx  2. xxx  3. xxx ..."""

    def __init__(self, parent, step_names):
        self.labels = []
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="x", padx=CARD_PADX, pady=(0, 4))
        for i, name in enumerate(step_names):
            lbl = tk.Label(frame, text=f"{i+1}. {name}",
                           bg=BG, fg=TEXT_DIM, font=FONT_SMALL)
            lbl.pack(side="left", padx=10)
            self.labels.append(lbl)

    def highlight(self, current_idx):
        """高亮当前步骤，之前标绿，之后灰色"""
        def _do():
            for i, lbl in enumerate(self.labels):
                if i < current_idx:
                    lbl.config(fg=OK_C)
                elif i == current_idx:
                    lbl.config(fg=ACCENT2, font=(FONT_SMALL[0], FONT_SMALL[1], "bold"))
                else:
                    lbl.config(fg=TEXT_DIM, font=FONT_SMALL)
        # 找一个 after 的宿主
        widget = self.labels[0] if self.labels else None
        if widget:
            widget.after(0, _do)


class FootBar:
    """底部操作栏"""

    def __init__(self, parent, buttons=None):
        """
        buttons: [(text, callback, style_opts), ...]
          style_opts: dict 如 {"bg": ACCENT, "fg": "#fff"}
        """
        foot = tk.Frame(parent, bg=BG2, height=FOOT_H)
        # 关键修复：不用 side="bottom"，改用普通 pack 顺序
        # 避免 LogPanel(expand=True) 与 FootBar(side=bottom) 的冲突
        foot.pack(fill="x", side="bottom")
        foot.pack_propagate(False)

        self.lbl = tk.Label(foot, text="", bg=BG2, fg=TEXT_DIM, font=FONT_SMALL)
        self.lbl.pack(side="left", padx=12, pady=10)

        self.btn_frame = tk.Frame(foot, bg=BG2)
        self.btn_frame.pack(side="right", padx=8)

        self.buttons = {}
        if buttons:
            for text, cmd, opts in buttons:
                self.add_button(text, cmd, **opts)

    def set_text(self, msg, fg=None):
        def _do():
            self.lbl.config(text=msg)
            if fg:
                self.lbl.config(fg=fg)
        self.lbl.after(0, _do)

    def add_button(self, text, command, **opts):
        default_opts = {
            "bg": BG3, "fg": TEXT_DIM, "relief": "flat", "bd": 0,
            "font": FONT_SMALL, "cursor": "hand2", "padx": 10, "pady": 3,
            "activebackground": BORDER,
        }
        default_opts.update(opts)
        btn = tk.Button(self.btn_frame, text=text, command=command, **default_opts)
        btn.pack(side="left", padx=2, pady=6)
        self.buttons[text] = btn
        return btn


# ══════════════════════════════════════════════
# 弹窗工厂
# ══════════════════════════════════════════════

def show_popup(parent, title, content, width=480, height=340,
               color=ERR_C, icon="✘", buttons=None):
    """
    在 parent 上方显示模态弹窗。

    重要: 必须等 parent 映射后再调用！否则 winfo_x/y 返回 1 导致坐标异常。
    buttons: [(label, callback, opts), ...]
      opts 是传给 Button 的额外关键字参数
    """
    popup = tk.Toplevel(parent)
    popup.configure(bg=BG2)
    popup.resizable(False, False)
    popup.grab_set()

    # 安全获取父窗口位置（处理未映射情况）
    px, py = _safe_parent_pos(parent, width, height)
    popup.geometry(f"{width}x{height}+{px}+{py}")
    popup.overrideredirect(True)

    # 顶色条
    tk.Frame(popup, bg=color, height=4).pack(fill="x")

    hdr = tk.Frame(popup, bg=BG2)
    hdr.pack(fill="x", padx=20, pady=(14, 0))
    tk.Label(hdr, text=icon, bg=BG2, fg=color, font=("Segoe UI Emoji", 20)).pack(side="left")
    tk.Label(hdr, text=f"  {title}", bg=BG2, fg=color, font=FONT_BTN).pack(side="left")

    tk.Frame(popup, bg=BORDER, height=1).pack(fill="x", padx=20, pady=10)

    tk.Label(popup, text=content, bg=BG2, fg=TEXT, font=FONT_BODY,
             justify="left", wraplength=width - 48).pack(padx=24, pady=(0, 16))

    if buttons:
        btn_row = tk.Frame(popup, bg=BG2)
        btn_row.pack(pady=(0, 16))
        for label, cmd, opts in buttons:
            defaults = {"bg": ACCENT, "fg": "#fff", "relief": "flat", "bd": 0,
                        "cursor": "hand2", "font": FONT_BTN, "padx": 14, "pady": 6}
            defaults.update(opts)
            tk.Button(btn_row, text=label, command=cmd, **defaults).pack(side="left", padx=6)

    return popup


def _safe_parent_pos(parent, pop_w, pop_h):
    """
    安全获取父窗口居中坐标。
    如果父窗口尚未映射（winfo 返回 1），则使用屏幕居中。
    """
    try:
        px = parent.winfo_x()
        py = parent.winfo_y()
        pw = parent.winfo_width()
        ph = parent.winfo_height()

        # winfo_x/y 在窗口未映射时返回 1，winfo_width/height 返回 1
        # 这是 tkinter 的已知行为
        if px <= 1 and py <= 1 and pw <= 1 and ph <= 1:
            # 未映射 → 屏幕居中
            sw = parent.winfo_screenwidth()
            sh = parent.winfo_screenheight()
            return (sw - pop_w) // 2, (sh - pop_h) // 2

        return px + (pw - pop_w) // 2, py + (ph - pop_h) // 2
    except Exception:
        # 任何异常都回退到屏幕居中
        sw = parent.winfo_screenwidth()
        sh = parent.winfo_screenheight()
        return (sw - pop_w) // 2, (sh - pop_h) // 2


def show_fatal_console(title, message):
    """无 GUI 时的控制台错误提示（不闪退）"""
    print()
    print("  ╔" + "═" * 56 + "╗")
    print(f"  ║  {title:^54} ║")
    print("  ╠" + "═" * 56 + "╣")
    for line in message.split("\n"):
        print(f"  ║  {line:<52} ║")
    print("  ╚" + "═" * 56 + "╝")
    print()
    print("  按回车键退出...")
    try:
        input()
    except EOFError:
        import time as _t; _t.sleep(5)


def start_dot_animation(label_widget, running_ref):
    """启动 ● ○ 动画，running_ref 为 [bool] 列表"""
    frames = ["●  ○  ○", "○  ●  ○", "○  ○  ●", "○  ●  ○"]
    anim = [0]

    def tick():
        if not running_ref[0]:
            return
        label_widget.config(text=frames[anim[0] % len(frames)])
        anim[0] += 1
        label_widget.after(350, tick)

    tick()
