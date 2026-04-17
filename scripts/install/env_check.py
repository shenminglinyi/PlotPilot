# -*- coding: utf-8 -*-
"""
aitex 环境检测与自动修复
━━━━━━━━━━━━━━━━━━━━━━
对小白用户友好的环境自检流程:
  1. Python 版本检测（≥3.10）
  2. 虚拟环境 .venv 创建/确认
  3. pip 升级
  4. Node.js / 前端 dist 检测
  5. .env 配置文件生成

每个步骤都有清晰的中文提示和自动修复能力。
"""

import os
import shutil
import subprocess
import re

from theme import OK_C, WARN_C, ERR_C
from utils import (
    get_proj_dir, get_venv_python, get_log_dir,
    NO_WIN, find_python, check_uvicorn,
    ensure_embedded_python,
)


def _is_embedded_python(python_path):
    """判断给定的 python_path 是否为内嵌 Python（tools/python_embed/ 下）"""
    if not python_path:
        return False
    # 规范化路径后检查是否包含 python_embed 目录
    norm = os.path.normpath(python_path).lower()
    return "python_embed" in norm and norm.endswith("python.exe")


class EnvChecker:
    """
    环境检查器。
    通过回调函数报告进度/日志，不直接依赖 tkinter，
    可在 GUI 或控制台模式下使用。

    回调签名:
      on_log(msg, tag)       – tag: "info"|"ok"|"warn"|"error"|"title"
      on_progress(pct, label, icon, step_idx)
    """

    STEP_NAMES = [
        "Python 环境", "虚拟环境", "安装依赖",
        "构建前端", "配置文件",
    ]

    def __init__(self, on_log=None, on_progress=None):
        self.on_log = on_log or (lambda *a: None)
        self.on_progress = on_progress or (lambda *a: None)
        self.proj_dir = get_proj_dir()

    def _log(self, msg, tag="info"):
        self.on_log(msg, tag)

    def _prog(self, pct, label="", icon="⏳", step=-1):
        self.on_progress(pct, label, icon, step)

    # ── ① Python ───────────────────────────────
    def check_python(self):
        """检测 Python，返回 python_path 或 None

        优先级:
          - 内嵌 Python (3.11) → 自动解压自 zip，无需安装
          - 系统 Python → 需要 >= 3.10
        """
        self._prog(8, "正在检测 Python 环境...", "🔍", 0)
        self._log("检测系统 Python 版本...", "title")

        # ═══ 首先确保内嵌 Python 已解压（零配置核心！） ═══
        ensure_embedded_python(
            proj_dir=self.proj_dir,
            on_log=lambda msg, tag: self._log(msg, tag),
        )

        python_path, ver = find_python()
        if not python_path:
            self._log("未找到 Python！", "error")
            self._log("请先安装 Python 3.10 或更高版本", "warn")
            self._log("安装时务必勾选 [Add to PATH]", "warn")
            self._log("下载地址: https://www.python.org/downloads/", "title")
            return None

        # ═══ 检查是否为内嵌 Python ═══
        is_embedded = _is_embedded_python(python_path)
        if is_embedded:
            # 内嵌 Python = 自带 3.11，100% 可信，直接通过！
            self._log(f"✨ 使用内嵌 Python: {ver}（自带，免安装）", "ok")
            self._prog(14, f"内嵌 Python 就绪 ({ver})", "✔", 0)
            return python_path

        # ═══ 系统 Python：需要版本校验 ═══
        major_minor = ver.split(".")[:2]
        try:
            maj, min_ = int(major_minor[0]), int(major_minor[1])
        except (ValueError, IndexError):
            maj, min_ = 3, 9  # 兜底：无法解析就当它太旧

        MIN_PYTHON = (3, 10)
        if (maj, min_) < MIN_PYTHON:
            self._log(f"!!! Python 版本过低: {ver} (需要 >= 3.10)", "error")
            self._show_version_warning(ver)
            return None  # 拦截！

        self._log(f"检测到 {ver}", "ok")
        self._prog(14, f"Python 就绪 ({ver})", "✔", 0)
        return python_path

    def _show_version_warning(self, current_ver):
        """
        Python 版本过旧时弹出警告窗口。
        引导用户去官网下载新版本。
        """
        import webbrowser

        msg = (
            f"检测到您的 Python 版本过低 ({current_ver})。\n\n"
            "本项目依赖较新的底层库（PyTorch、Transformers 等），\n"
            "需要 Python 3.10 或更高版本才能稳定运行。\n\n"
            "推荐版本: Python 3.11 或 3.12 (64-bit)\n\n"
            "点击【确定】将为您打开 Python 官网下载页面。"
        )

        # 尝试用 tkinter 弹窗（GUI 模式下）
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)

            # 自定义弹窗（比 messagebox 更美观）
            from ui_base import show_popup, BG2, ERR_C, FONT_BTN, ACCENT

            def _open_download():
                webbrowser.open("https://www.python.org/downloads/")
                root.destroy()

            def _try_anyway():
                # 用户坚持要继续（不推荐但允许）
                root.destroy()

            show_popup(
                root,
                title="Python 版本过旧",
                icon="⚠",
                color=ERR_C,
                content=msg,
                buttons=[
                    ("下载 Python 3.11+", _open_download, {"bg": "#e74c3c"}),
                    ("强行继续（不推荐）", _try_anyway, {"bg": "#666"}),
                ],
                width=420,
            )
            root.mainloop()
        except Exception:
            # tkinter 不可用时的降级方案
            print(f"\n{'='*52}")
            print(f"  [FATAL] Python 版本过低: {current_ver}")
            print(f"  要求: Python >= 3.10")
            print(f"{'='*52}")
            try:
                webbrowser.open("https://www.python.org/downloads/")
            except Exception:
                pass

    # ── ② 虚拟环境 ─────────────────────────────
    def ensure_venv(self, system_python):
        """确保虚拟环境存在，返回 venv_python 或 None

        内嵌 Python 模式: 跳过 venv 创建，直接使用内嵌 Python
        系统 Python 模式: 创建/复用 .venv 虚拟环境
        """
        # ═══ 内嵌 Python：跳过 venv，直接用它本身 ═══
        if _is_embedded_python(system_python):
            self._log("✨ 内嵌 Python 模式 — 无需创建虚拟环境", "ok")
            self._prog(22, "内嵌 Python 就绪", "✔", 1)
            return system_python

        self._prog(17, "检查虚拟环境...", "⏳", 1)

        venv_py = get_venv_python(self.proj_dir)
        if venv_py:
            self._log("虚拟环境已存在 (.venv)", "ok")
        else:
            self._log("正在创建虚拟环境 .venv ...", "title")
            r = subprocess.run(
                [system_python, "-m", "venv", ".venv"],
                cwd=self.proj_dir, capture_output=True, text=True,
                creationflags=NO_WIN,
            )
            if r.returncode != 0:
                self._log(f"创建失败: {r.stderr[:200]}", "error")
                return None
            self._log("虚拟环境创建成功", "ok")
            venv_py = get_venv_python(self.proj_dir)

        if not venv_py:
            self._log("虚拟环境路径异常", "error")
            return None

        # 升级 pip
        self._log("升级 pip 到最新版本...", "info")
        subprocess.run(
            [venv_py, "-m", "pip", "install", "--upgrade", "pip",
             "-i", "https://mirrors.aliyun.com/pypi/simple/",
             "--trusted-host", "mirrors.aliyun.com", "-q"],
            cwd=self.proj_dir, capture_output=True,
            creationflags=NO_WIN,
        )

        self._prog(23, "虚拟环境就绪", "✔", 1)
        return venv_py

    # ── ③ 依赖检测（仅判断是否需要安装） ───────
    def check_deps(self, venv_py):
        """检查是否需要安装依赖，返回 bool"""
        self._prog(27, "检查依赖包...", "⏳", 2)
        needs_install = not check_uvicorn(venv_py)
        if needs_install:
            self._log("依赖包不完整，需要安装", "warn")
        else:
            self._log("依赖包已就绪 ✓", "ok")
        return needs_install

    # ── ④ 前端 ─────────────────────────────────
    def check_frontend(self):
        """检查前端是否已构建，返回 (needs_build, npm_exe)"""
        self._prog(58, "检查前端构建...", "⏳", 3)

        frontend_dir = os.path.join(self.proj_dir, "frontend")
        dist_index  = os.path.join(frontend_dir, "dist", "index.html")
        node_exe    = shutil.which("node")
        npm_exe     = shutil.which("npm")

        if node_exe and npm_exe and not os.path.exists(dist_index):
            self._log("前端未构建，需要 npm install + build", "title")
            return True, npm_exe
        elif os.path.exists(dist_index):
            self._log("前端已构建 (dist/index.html 存在)", "ok")
        elif not node_exe or not npm_exe:
            self._log("未找到 Node.js，跳过前端构建", "warn")

        self._prog(63, "前端检查完成", "✔", 3)
        return False, npm_exe

    # ── ⑤ 配置文件 ─────────────────────────────
    def ensure_env_file(self):
        """确保 .env 存在"""
        self._prog(65, "检查配置文件...", "⏳", 4)

        env_path    = os.path.join(self.proj_dir, ".env")
        env_example = os.path.join(self.proj_dir, ".env.example")

        if not os.path.exists(env_path):
            if os.path.exists(env_example):
                shutil.copy(env_example, env_path)
                self._log("配置文件已从模板 (.env.example) 创建", "ok")
            else:
                default_content = (
                    "# ══════════════════════════════════\n"
                    "# aitex 配置文件\n"
                    "# 请填写你的 API Key 后保存\n"
                    "# ══════════════════════════════════\n"
                    "\n"
                    "ARK_API_KEY=\n"
                    "ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3\n"
                    "ARK_MODEL=\n"
                    "ARK_TIMEOUT=120\n"
                    "\n"
                    "LOG_LEVEL=INFO\n"
                    "LOG_FILE=logs/aitext.log\n"
                )
                with open(env_path, "w", encoding="utf-8") as f:
                    f.write(default_content)
                self._log("默认配置文件已创建（请填写 API Key）", "ok")
        else:
            self._log("配置文件已存在", "ok")

        self._prog(70, "环境检查全部通过 ✓", "✔", 4)
        return True


# ══════════════════════════════════════════════
# 前端构建工具（独立函数）
# ══════════════════════════════════════════════

def build_frontend(proj_dir, npm_exe, on_log=None):
    """
    执行 npm install + npm run build。
    返回 True 成功 / False 失败
    """
    _log = on_log or (lambda *a: None)
    frontend_dir = os.path.join(proj_dir, "frontend")

    _log("正在安装前端依赖（npm install）...", "info")
    r_ni = subprocess.run(
        [npm_exe, "install", "--registry", "https://registry.npmmirror.com"],
        cwd=frontend_dir, capture_output=True, text=True,
        encoding="utf-8", errors="replace", creationflags=NO_WIN,
    )
    if r_ni.returncode != 0:
        _log(f"npm install 失败: {r_ni.stderr[:200]}", "error")
        _log("前端构建失败，可手动执行:", "warn")
        _log("  cd frontend && npm install && npm run build", "title")
        return False

    _log("npm install 完成，正在构建（npm run build）...", "info")
    _log("构建可能需要 1~3 分钟，请耐心等待...", "warn")
    r_build = subprocess.run(
        [npm_exe, "run", "build"],
        cwd=frontend_dir, capture_output=True, text=True,
        encoding="utf-8", errors="replace", creationflags=NO_WIN,
    )
    if r_build.returncode != 0:
        _log(f"npm run build 失败: {r_build.stderr[:300]}", "error")
        _log("可手动执行: cd frontend && npm run build", "warn")
        return False

    _log("前端构建成功 ✓", "ok")
    return True
