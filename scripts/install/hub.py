# -*- coding: utf-8 -*-
"""
PlotPilot（墨枢）统一 GUI 中心（Hub）— 模块化重构版
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
双击即用，全自动流程，防闪退设计：
  ① 单实例检测（已运行则提示 / 杀掉重启动）
  ② 环境自检（Python → venv → 依赖 → 前端 → .env）
  ③ 启动后端服务（进度条 + 实时日志）
  ④ 可选：打包分享

架构:
  hub.py (本文件) = 薄胶水层，组装 UI + 各功能模块
  theme.py     = 颜色/字体主题
  utils.py     = 端口/进程/锁文件等工具
  ui_base.py   = 可复用 UI 组件
  env_check.py = 环境检测与修复
  installer.py = pip 依赖安装
  launcher.py  = 后端服务启动
  packer.py    = 项目打包分享
"""

import sys
import os
import time
import threading
import traceback

# ══════════════════════════════════════════════
# 关键：路径处理，兼容 3 种运行环境：
#   ① python scripts/install/hub.py   (开发调试)
#  ② python -m PyInstaller 打包的 exe   (分发)
#  ③ tools/plotpilot.bat 调用（用户）
# ══════════════════════════════════════════════
_HUB_FILE = os.path.abspath(__file__)
_HUB_DIR = os.path.dirname(_HUB_FILE)

# 检测是否在 PyInstaller 打包环境中
if getattr(sys, 'frozen', False):
    # PyInstaller: __file__ 在 _internal/scripts/install/hub.py
    # 同伴模块也在 _internal/scripts/install/ 下
    # 需要把 _internal/scripts/install 加入 sys.path 最前面
    # 以覆盖 PyInstaller 可能生成的顶层同名 .pyc
    _INSTALL_DIR = _HUB_DIR
else:
    # 普通 Python: __file__ 在 scripts/install/hub.py
    _INSTALL_DIR = _HUB_DIR
    # 项目根目录 = scripts/install -> scripts -> proj_root
    _PROJ_DIR = os.path.dirname(os.path.dirname(_HUB_DIR))
    if _PROJ_DIR not in sys.path:
        sys.path.insert(0, _PROJ_DIR)

# 确保 install 目录在 sys.path 最前面（优先级最高）
_sys_path_set = {p for p in sys.path}
if _INSTALL_DIR not in _sys_path_set:
    sys.path.insert(0, _INSTALL_DIR)

# ══════════════════════════════════════════════
# 第一层防御：import 阶段的异常兜底
# ══════════════════════════════════════════════
_import_errors = []
_base_modules = {
    "time": "time", "threading": "threading",
    "subprocess": "subprocess", "socket": "socket",
    "shutil": "shutil", "webbrowser": "webbrowser",
    "re": "re",
}
for _mod_name, _var_name in list(_base_modules.items()):
    try:
        exec(f"import {_mod_name}")
    except Exception as e:
        _import_errors.append(f"导入 {_mod_name} 失败: {e}")

_tk_ok = False
try:
    import tkinter as tk
    from tkinter import ttk
    _tk_ok = True
except Exception as e:
    _import_errors.append(f"导入 tkinter 失败: {e} (GUI 不可用)")

# 导入自身模块（使用非相对导入，兼容直接 python hub.py 运行）
from theme import (
    BG, BG2, BG3, ACCENT, ACCENT2, OK_C, WARN_C, ERR_C,
    TEXT, TEXT_DIM, BORDER,
    FONT_TITLE, FONT_BODY, FONT_SMALL, FONT_MONO,
    FONT_LOGO, FONT_ICON, FONT_BTN,
    WINDOW_W, WINDOW_H, TITLE_BAR_H, LOGO_H, FOOT_H, CARD_PADX,
)
from utils import (
    get_proj_dir, get_log_dir, NO_WIN, _TK_OK,
    read_lock, write_lock, remove_lock,
    is_process_alive, port_in_use, find_free_port,
    save_crash_log, kill_process, DEFAULT_PORT,
)
from ui_base import (
    BaseWindow, LogPanel, StatusCard, StepIndicator, FootBar,
    show_popup, show_fatal_console, start_dot_animation,
)
from env_check import EnvChecker, build_frontend
from installer import PipInstaller
from launcher import BackendLauncher
from packer import ProjectPacker


# ══════════════════════════════════════════════
# 主窗口 — 组装所有模块
# ══════════════════════════════════════════════

class HubWindow(BaseWindow):
    """PlotPilot 统一 GUI 中心窗口"""

    STEP_NAMES = [
        "实例检测", "环境检查", "虚拟环境",
        "安装依赖", "构建前端", "配置文件", "启动服务",
    ]

    def __init__(self, mode="auto"):
        self.mode = mode
        self.proj_dir = get_proj_dir()
        self._port = DEFAULT_PORT
        self._backend = None          # BackendLauncher 实例
        self._running_list = [True]   # 动画运行标志（引用语义供闭包用）
        self._venv_py = None         # 安装了依赖的 Python 路径

        # 初始化基类（内部会依次调用 _build_title_bar → _build_logo_area
        #                              → _build_separator → _build_body）
        super().__init__(
            title="PlotPilot（墨枢）· AI 小说创作平台",
            width=WINDOW_W, height=WINDOW_H,
            show_minimize=True,
            on_close=self._handle_close,
        )

        # 启动点点动画
        start_dot_animation(self.dot_label, self._running_list)

        # 初始底部文字（含致谢信息）
        self.foot_bar.set_text(
            "感谢 梦幻AI动漫 提供原始部署设计  |  抖音：林亦 91472902104 每晚9点随缘直播",
            fg="#4a5568",
        )

    def _build_logo_area(self, title):
        """覆写基类：在 Logo 区域加入副标题和点点动画"""
        logo_f = tk.Frame(self.root, bg=BG, height=LOGO_H + 24)
        logo_f.pack(fill="x")
        logo_f.pack_propagate(False)

        tk.Label(logo_f, text="PlotPilot",
                 bg=BG, fg=ACCENT, font=FONT_LOGO).pack(expand=True)

        # 点点动画标签
        self.dot_label = tk.Label(
            logo_f, text="● ● ●",
            bg=BG, fg=ACCENT2, font=("Arial", 10),
        )
        self.dot_label.place(relx=0.5, rely=0.82, anchor="center")

    def _build_body(self):
        """覆写基类钩子：在分割线下方构建所有主体组件"""
        root = self.root

        # 副标题
        tk.Label(root, text="AI 小说创作平台  ·  智能写作引擎",
                 bg=BG, fg=TEXT_DIM, font=FONT_SMALL).pack()

        tk.Frame(root, bg=BORDER, height=1).pack(fill="x", padx=CARD_PADX, pady=(8, 0))

        # ── 状态卡片 ──
        self.status_card = StatusCard(root, port=self._port)

        # ── 步骤指示器 ──
        self.step_bar = StepIndicator(root, self.STEP_NAMES)

        tk.Frame(root, bg=BORDER, height=1).pack(fill="x", padx=CARD_PADX, pady=(4, 0))

        # ── 日志面板 ──
        log_head = tk.Frame(root, bg=BG)
        log_head.pack(fill="x", padx=CARD_PADX, pady=(6, 2))
        tk.Label(log_head, text="▸ 运行日志", bg=BG, fg=TEXT_DIM,
                 font=FONT_SMALL).pack(side="left")

        self.log_panel = LogPanel(root)

        # ── 底部栏 ──
        self.foot_bar = FootBar(root, buttons=[
            ("打开浏览器", self._open_browser, {
                "bg": ACCENT, "fg": "#fff", "font": FONT_BTN,
                "activebackground": "#5b52e0", "state": "disabled",
            }),
            ("📦 打包分享", self._start_pack, {}),
            ("最小化", self._minimize, {}),
        ])
        self.open_btn = self.foot_bar.buttons.get("打开浏览器")
        self.pack_btn = self.foot_bar.buttons.get("📦 打包分享")

        # ── 致谢 & 联系方式（底部栏小字）──
        self.foot_bar.set_text(
            "感谢 梦幻AI动漫 提供原始部署设计  |  抖音：林亦 91472902104 每晚9点随缘直播",
            fg="#4a5568",
        )

    # ═══════════════════════════════════════
    # 日志 / 进度代理方法
    # ═══════════════════════════════════════
    def log(self, msg, tag="info"):
        self.log_panel.log(msg, tag)

    def set_progress(self, pct, label="", icon="⏳", step_idx=-1):
        self.status_card.update(pct, label, icon)
        if step_idx >= 0:
            self.step_bar.highlight(step_idx)
        if label:
            self.foot_bar.set_text(label)

    def _open_browser(self):
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{self._port}")

    # ═══════════════════════════════════════
    # 关闭处理
    # ═══════════════════════════════════════
    def _handle_close(self):
        self._running_list[0] = False
        remove_lock()
        if self._backend:
            self._backend.terminate()

    # ═══════════════════════════════════════
    # 核心流程
    # ═══════════════════════════════════════
    def run(self):
        # 用线程跑主流程，防止长时间操作阻塞 tkinter 主循环
        t = threading.Thread(target=self._main_flow, daemon=True, name="MainFlow")
        t.start()
        # 主线程跑 tkinter 事件循环
        try:
            self.root.mainloop()
        except tk.TclError:
            # 窗口已被外部销毁（如用户关闭），静默退出
            pass
        except KeyboardInterrupt:
            pass

    def _main_flow(self):
        """主流程——所有操作都在 try 内，任何异常都不闪退"""
        try:
            if self.mode == "pack":
                self._run_pack()
                return

            # ① 单实例检测
            if not self._check_single_instance():
                return

            # ② 环境自检 & 自动修复
            if not self._auto_env_check():
                return

            # ③ 启动后端服务
            self._launch_backend()

        except KeyboardInterrupt:
            self.log("用户中断", "warn")
            self._safe_exit()
        except Exception as e:
            tb = traceback.format_exc()
            self.log(f"程序异常: {e}", "error")
            save_crash_log(e, tb, self.proj_dir)
            # ═══ 防止 GUI 消失：确保 root 仍然存活再弹窗 ═══
            try:
                if self.root and self.root.winfo_exists():
                    self._show_fatal_error(e, tb)
                else:
                    # root 已销毁，用纯终端输出兜底
                    print(f"\n[FATAL] {e}\n{tb}")
                    show_fatal_console(f"PlotPilot 异常: {e}", tb[-2000:])
            except Exception:
                # 连弹窗都失败了，写文件兜底
                try:
                    with open(os.path.join(get_proj_dir(), "logs", "fatal.log"), "w", encoding="utf-8") as f:
                        f.write(f"{e}\n\n{tb}")
                except Exception:
                    pass

    def _safe_exit(self):
        self.root.after(100, lambda: self.root.quit() if self.root else None)

    # ────────────────────────────────────────
    # ① 单实例检测
    # ────────────────────────────────────────
    def _check_single_instance(self):
        self.set_progress(2, "检测是否已有实例在运行...", "🔍", 0)
        self.log("检查单实例锁...", "title")

        lock_info = read_lock()
        if lock_info:
            old_pid, old_port = lock_info
            if is_process_alive(old_pid) and port_in_use(old_port):
                self.log(f"发现旧实例 (PID={old_pid}, 端口={old_port})，自动终止...", "warn")
                self.log("正在清理旧进程...", "title")
                try:
                    kill_process(old_pid)
                    self.log(f"旧进程 PID={old_pid} 已终止", "ok")
                except Exception as e:
                    self.log(f"终止旧进程时出错: {e}", "warn")
                # 额外清理：杀掉同端口的残留 python 进程
                self._kill_orphan_processes(old_port)
                remove_lock()
                self.log("旧实例已清理，将重新启动", "ok")
            else:
                self.log("旧进程已不存在，清理残留锁文件", "ok")
                remove_lock()

        write_lock(os.getpid(), self._port)
        self.set_progress(5, "单实例检测通过", "✔", 0)
        return True

    def _kill_orphan_processes(self, port):
        """清理占用指定端口的孤儿 python/uvicorn 进程"""
        import subprocess as _sp
        try:
            # Windows: 用 netstat 找到占用端口的 PID
            r = _sp.run(
                ["netstat", "-ano"],
                capture_output=True, text=True, timeout=10,
                creationflags=NO_WIN,
            )
            for line in r.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if parts:
                        orphan_pid = parts[-1]
                        try:
                            pid_int = int(orphan_pid)
                            if pid_int != os.getpid():
                                kill_process(pid_int)
                                self.log(f"已清理孤儿进程 PID={pid_int}", "ok")
                        except (ValueError, Exception):
                            pass
        except Exception as e:
            self.log(f"清理孤儿进程时出错: {e}", "warn")

    def _show_running_dialog(self, old_pid, old_port):
        import webbrowser as _wb

        def _do():
            def _open_and_close():
                _wb.open(f"http://127.0.0.1:{old_port}")
                self.root.destroy()

            def _kill_and_restart():
                self.log(f"正在终止旧进程 PID={old_pid}...", "warn")
                try:
                    kill_process(old_pid)
                    self.log("旧进程已终止", "ok")
                except Exception as e:
                    self.log(f"终止进程时出错: {e}", "warn")
                remove_lock()
                threading.Thread(target=self._main_flow, daemon=True).start()

            btns = [
                ("✓ 打开浏览器", _open_and_close,
                 {"bg": OK_C, "fg": "#fff", "activebackground": "#22c55e"}),
                ("✕ 杀掉并重启", _kill_and_restart,
                 {"bg": ERR_C, "fg": "#fff", "activebackground": "#dc2626"}),
                ("取消", lambda: self.root.destroy(), {}),
            ]
            content = (
                f"检测到 PlotPilot 正在运行中：\n\n"
                f"  PID: {old_pid}    端口: {old_port}\n\n"
                f"请选择操作："
            )
            show_popup(
                self.root, "PlotPilot 已在运行", content,
                width=480, height=300, color=WARN_C, icon="⚠",
                buttons=btns,
            )
        self.root.after(0, _do)

    # ────────────────────────────────────────
    # ② 环境自检 & 自动修复（一键部署）
    # ────────────────────────────────────────
    def _auto_env_check(self):
        """一键环境检测 + 安装，所有逻辑收在此处"""
        checker = EnvChecker(
            on_log=lambda msg, tag: self.log(msg, tag),
            on_progress=lambda p, l, i, s: self.set_progress(p, l, i, s),
        )

        # ① Python（自动解压内嵌 / 检测系统）
        python_sys = checker.check_python()
        if not python_sys:
            self._show_fatal_simple(
                "未找到 Python",
                "请先安装 Python 3.10 或更高版本\n"
                "安装时务必勾选 [Add to PATH]\n\n"
                "下载地址:\nhttps://www.python.org/downloads/",
            )
            return False

        # ② 虚拟环境
        venv_py = checker.ensure_venv(python_sys)
        self._venv_py = venv_py  # 保存给 launcher 用
        if not venv_py:
            self._show_fatal_simple("虚拟环境创建失败", "请检查 Python 安装是否正常")
            return False

        # ③ 核心依赖安装
        needs_install = checker.check_deps(venv_py)
        # 创建唯一 installer 实例（核心 + 扩展共用）
        self._installer = PipInstaller(
            venv_py,
            on_log=lambda msg, tag: self.log(msg, tag),
            on_progress=lambda p, l, i, s: self.set_progress(p, l, i, s),
            on_heartbeat=lambda pkg, t: self.foot_bar.set_text(
                f"正在下载 {pkg} · 已等待 {t}", fg=ACCENT2),
        )
        self._venv_py = venv_py

        if needs_install:
            self.log("开始安装核心依赖（轻量级，约 1~3 分钟）...", "title")
            self.log("仅包含 FastAPI / OpenAI 等核心组件", "dim")
            if not self._installer.install():
                self._show_fatal_simple(
                    "核心依赖安装失败",
                    "请检查网络连接后重新双击启动\n"
                    "如使用代理，请确保终端能访问外网",
                )
                return False
            self.log("核心依赖安装完成 ✓", "ok")

        # ④ 前端构建
        needs_build, npm_exe = checker.check_frontend()
        if needs_build and npm_exe:
            self.log("前端未构建，开始 npm install + build...", "title")
            build_frontend(
                self.proj_dir, npm_exe,
                on_log=lambda msg, tag: self.log(msg, tag),
            )
        elif needs_build and not npm_exe:
            self.log("未找到 Node.js，跳过前端构建", "warn")

        # ⑤ 配置文件
        checker.ensure_env_file()

        self.set_progress(70, "环境就绪 ✓", "✔", 4)
        return True

    # ────────────────────────────────────────
    # ③ 启动后端服务
    # ────────────────────────────────────────
    def _launch_backend(self):
        self._backend = BackendLauncher(
            venv_py=self._venv_py,
            on_log=lambda msg, tag: self.log(msg, tag),
            on_progress=lambda p, l, i, s: self.set_progress(p, l, i, s),
            on_ready=self._on_backend_ready,
            on_failed=self._on_backend_failed,
        )
        self.set_progress(72, "正在启动后端服务...", "🚀", 6)
        self.log("准备启动 uvicorn 服务...", "title")

        # 在后台线程中执行完整启动流程
        threading.Thread(
            target=self._backend.launch, args=(self._port,),
            daemon=True,
        ).start()

    def _on_backend_ready(self, port):
        """后端就绪回调"""
        self._port = port
        def _do():
            try:
                self.root.title("PlotPilot（墨枢）· 运行中")
                self.status_card.update(100, "服务运行中", "✔")
                self.status_card.port_badge.config(
                    text=f"http://127.0.0.1:{port}", bg=OK_C)
                if self.open_btn:
                    self.open_btn.config(state="normal")
                self.foot_bar.set_text(
                    "⚠ 请勿关闭此窗口！关闭后网页将无法访问",
                    fg=WARN_C,
                )
                self._running_list[0] = False
                self.dot_label.config(text="✦  运行中  ✦", fg=OK_C)
                for lbl in self.step_bar.labels:
                    lbl.config(fg=OK_C)
                self.root.after(1500, self._show_ready_popup)
            except Exception:
                pass
        self.root.after(0, _do)

    def _show_ready_popup(self):
        """服务就绪弹窗 — 包含扩展包安装引导"""
        def _do():
            content = (
                "🎉 后端服务已成功启动！\n\n"
                f"  🌐 地址：http://127.0.0.1:{self._port}\n\n"
                "⚠  使用须知：\n"
                "  • 此窗口为服务控制台，请勿关闭\n"
                "  • 可点击「最小化」缩到任务栏\n"
                "  • 仅在完全退出时才关闭窗口\n"
            )

            # 使用列表来存储 popup 引用，避免闭包变量问题
            popup_ref = [None]

            # ── 按钮回调 ──
            def _on_minimize():
                if popup_ref[0]:
                    try:
                        popup_ref[0].destroy()
                    except Exception:
                        pass
                self._minimize()

            def _on_continue():
                if popup_ref[0]:
                    try:
                        popup_ref[0].destroy()
                    except Exception:
                        pass

            def _install_ext():
                """安装本地模型扩展包（~2GB）"""
                if popup_ref[0]:
                    try:
                        popup_ref[0].destroy()
                    except Exception:
                        pass
                self._start_install_extension()

            # 创建弹窗
            popup_ref[0] = show_popup(
                self.root, "✨ PlotPilot 已就绪！", content,
                width=520, height=400, color=OK_C, icon="✓",
                buttons=[
                    ("🚀 安装本地 AI 引擎", _install_ext,
                     {"bg": "#f59e0b", "fg": "#fff"}),
                    ("最小化到任务栏", _on_minimize,
                     {"bg": ACCENT}),
                    ("继续使用", _on_continue,
                     {"bg": BG3, "fg": TEXT_DIM}),
                ],
            )
        self.root.after(0, _do)

    def _start_install_extension(self):
        """后台线程中安装扩展依赖（requirements-local.txt）"""
        self.log("", "info")
        self.log("=" * 52, "title")
        self.log("  📦 开始安装本地 AI 扩展包", "title")
        self.log("  (sentence-transformers / torch / faiss)", "dim")
        self.log("  ⚠ 约 2GB，可能需要 5~20 分钟", "warn")
        self.log("=" * 52, "title")
        self.set_progress(56, "正在下载本地 AI 引擎...", "🧠", 2)

        installer = getattr(self, '_installer', None)
        if not installer:
            self.log("安装器未初始化，跳过扩展安装", "warn")
            return

        def _do_install():
            success = installer.install_local()
            if success:
                self.set_progress(90, "扩展包安装完成！", "✔", 2)
                self.log("═══ 本地 AI 引擎安装完成！ ═══", "ok")
                self.log("下次启动时可选择「本地嵌入模式」", "ok")

                # 弹窗提示
                def _show_done():
                    show_popup(
                        self.root, "🎉 扩展包安装完成！",
                        "本地 AI 引擎已安装完毕。\n\n"
                        "你现在可以：\n"
                        "  • 在设置页面切换到「本地嵌入模式」\n"
                        "  • 无需联网即可使用向量检索功能\n\n"
                        "重启服务后生效。",
                        width=460, height=320, color=OK_C, icon="✓",
                        buttons=[
                            ("好的", lambda: None,
                             {"bg": OK_C, "fg": "#fff"}),
                        ],
                    )
                self.root.after(1000, _show_done)
            else:
                self.set_progress(56, "扩展包安装失败", "✘", 2)
                self.log("扩展包安装失败，可稍后重试", "error")

                def _show_fail():
                    show_popup(
                        self.root, "⚠ 扩展包安装失败",
                        "本地 AI 引擎安装未成功。\n\n"
                        "可能的原因：\n"
                        "  • 网络不稳定（建议切换热点重试）\n"
                        "  • 磁盘空间不足（需要 ~5GB）\n\n"
                        "你可以：\n"
                        "  • 继续使用 OpenAI API 模式（无需扩展包）\n"
                        "  • 稍后重新启动 PlotPilot 再试",
                        width=460, height=360, color=WARN_C, icon="⚠",
                        buttons=[
                            ("知道了", lambda: None,
                             {"bg": ACCENT}),
                        ],
                    )
                self.root.after(1000, _show_fail)

        threading.Thread(target=_do_install, daemon=True).start()

    def _on_backend_failed(self, reason, detail=""):
        def _do():
            try:
                self.status_card.label.config(text="启动失败", fg=ERR_C)
                self.status_card.icon.config(text="✘", fg=ERR_C)
                self.foot_bar.set_text(
                    f"启动失败：{reason}  请查看日志", fg=ERR_C)
                self.dot_label.config(text="✘  失败", fg=ERR_C)
            except Exception:
                pass
        self.root.after(0, _do)

    # ────────────────────────────────────────
    # 打包模式
    # ────────────────────────────────────────
    def _start_pack(self):
        if self.pack_btn:
            self.pack_btn.config(state="disabled")
        threading.Thread(target=self._run_pack, daemon=True).start()

    def _run_pack(self):
        packer = ProjectPacker(
            on_log=lambda msg, tag: self.log(msg, tag),
            on_progress=lambda p, l, i: self.set_progress(p, l, i),
        )
        success, zip_path = packer.pack()
        if success and self.pack_btn:
            self.root.after(0, lambda: self.pack_btn.config(
                state="normal", text="📦 再次打包",
                bg=OK_C, activebackground="#22c55e"))
        elif not success and self.pack_btn:
            self.root.after(0, lambda: self.pack_btn.config(state="normal"))

    # ────────────────────────────────────────
    # 弹窗快捷方法
    # ────────────────────────────────────────
    def _show_fatal_error(self, exc, tb_text):
        """致命错误弹窗——显示 traceback"""
        def _do():
            show_popup(
                self.root, "PlotPilot 发生异常",
                f"异常类型: {type(exc).__name__}\n\n{str(exc)[:200]}",
                width=520, height=400, color=ERR_C, icon="✘",
                buttons=[
                    ("关闭程序", lambda: [
                        self._handle_close(),
                        self.root.destroy() if self.root else None,
                    ], {"bg": ERR_C, "activebackground": "#dc2626"}),
                    ("查看完整日志", self._open_crash_log,
                     {"bg": BG3, "fg": TEXT_DIM}),
                ],
            )
            # 追加可滚动的 traceback
            tf = tk.Frame(popup, bg=BG3)
            tf.pack(fill="both", expand=True, padx=24, pady=(0, 8))
            tb_widget = tk.Text(tf, bg=BG3, fg=TEXT_DIM, font=("Consolas", 8),
                                height=6, relief="flat", bd=0, wrap="word")
            tb_srl = tk.Scrollbar(tf, command=tb_widget.yview, bg=BG3)
            tb_widget.configure(yscrollcommand=tb_srl.set)
            tb_srl.pack(side="right", fill="y")
            tb_widget.pack(side="left", fill="both", expand=True, padx=4, pady=4)
            tb_widget.insert("end", tb_text[-1500:] if len(tb_text) > 1500 else tb_text)
            tb_widget.configure(state="disabled")
        self.root.after(0, _do)

    def _show_fatal_simple(self, title, detail):
        """简单致命错误弹窗"""
        def _do():
            show_popup(
                self.root, f"✘  {title}", detail,
                width=420, height=260, color=ERR_C,
                buttons=[
                    ("关闭", lambda: self.root.destroy(),
                     {"bg": ERR_C, "activebackground": "#dc2626"}),
                ],
            )
        self.root.after(0, _do)

    def _open_crash_log(self):
        crash_path = os.path.join(self.proj_dir, "logs", "crash.log")
        if os.path.exists(crash_path):
            os.startfile(crash_path)


# ══════════════════════════════════════════════
# 入口 — 最终兜底
# ══════════════════════════════════════════════

def main():
    # 启动日志：记录每次启动，方便排查闪退
    _startup_time = time.strftime('%Y-%m-%d %H:%M:%S')
    try:
        _log_path = os.path.join(get_proj_dir(), "logs", "hub_startup.log")
        with open(_log_path, "a", encoding="utf-8") as _f:
            _f.write(f"[{_startup_time}] hub.py starting... PID={os.getpid()} Python={sys.executable}\n")
    except Exception:
        pass

    if _import_errors and not _TK_OK:
        print("=" * 56)
        print("[FATAL] PlotPilot 无法启动:")
        for err in _import_errors:
            print(f"  - {err}")
        print()
        print("请确保:")
        print("  1. Python 3.10+ 已正确安装")
        print("  2. tkinter 可用（通常随 Python 一起安装）")
        print("  3. 如使用精简版 Python，请安装完整版")
        print("=" * 56)
        show_fatal_console("PlotPilot 无法启动", "\n".join(_import_errors))
        sys.exit(1)

    mode = "auto"
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower().strip().lstrip("-/")
        if cmd in ("pack", "p", "打包"):
            mode = "pack"
        elif cmd in ("force", "f", "强制"):
            mode = "force"

    try:
        app = HubWindow(mode=mode)
        app.run()
    except KeyboardInterrupt:
        print("\n[INFO] 用户中断")
        sys.exit(0)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"\n[FATAL] 未捕获异常: {e}")
        print(tb)

        if _TK_OK:
            try:
                root = tk.Tk()
                root.withdraw()
                root.attributes("-topmost", True)
                from tkinter import messagebox
                messagebox.showerror(
                    "PlotPilot 启动失败",
                    f"发生未预期的错误:\n\n{e}\n\n"
                    f"详细日志已保存到 logs/crash.log\n"
                    f"也可在命令行运行: python scripts/install/hub.py",
                )
                root.destroy()
            except Exception:
                pass

        save_crash_log(e, tb)
        sys.exit(1)


if __name__ == "__main__":
    main()
