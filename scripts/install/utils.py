# -*- coding: utf-8 -*-
"""
aitex 通用工具函数
━━━━━━━━━━━━━━━━━━
端口检测、进程管理、锁文件、Python 查找等
不依赖 tkinter，可在纯控制台环境下使用。
"""

import sys
import os
import socket
import subprocess
import shutil
import time

# ── 当 tkinter 可用时使用隐藏窗口标志，否则为 0 ──
try:
    import tkinter as tk
    _TK_OK = True
    NO_WIN = subprocess.CREATE_NO_WINDOW
except Exception:
    _TK_OK = False
    NO_WIN = 0


# ══════════════════════════════════════════════
# 路径 & 项目信息
# ══════════════════════════════════════════════

def get_proj_dir():
    """返回项目根目录（aitex/）

    兼容 3 种环境:
      - PyInstaller exe: exe所在目录的上2级 (tools/aitext/ -> 项目根)
      - 普通 Python: __file__ 往上3级 (install -> scripts -> 项目根)
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后: exe 在 dist/aitext/aitext.exe
        # 项目根 = exe 的父目录的父目录
        # 但如果 exe 被复制到了 tools/aitext/ 下，
        # 则项目根 = exe目录 的上级的上级
        # 更健壮的方式: 找 exe 目录中包含 requirements.txt 的最近祖先
        exe_dir = os.path.dirname(sys.executable)
        # 向上搜索包含 requirements.txt 的目录
        d = exe_dir
        while d and d != os.path.dirname(d):
            if os.path.exists(os.path.join(d, "requirements.txt")):
                return d
            d = os.path.dirname(d)
        # 兜底: 返回 exe 的上两级
        return os.path.dirname(os.path.dirname(exe_dir))
    else:
        # 普通 Python: __file__ 位于 scripts/install/utils.py
        # 往上 3 级: install -> scripts -> proj_root
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_venv_python(proj_dir=None):
    """返回虚拟环境 python.exe 路径，不存在则返回 None"""
    if proj_dir is None:
        proj_dir = get_proj_dir()
    p = os.path.join(proj_dir, ".venv", "Scripts", "python.exe")
    return p if os.path.exists(p) else None


def get_log_dir(proj_dir=None):
    """确保 logs 目录存在并返回路径"""
    if proj_dir is None:
        proj_dir = get_proj_dir()
    d = os.path.join(proj_dir, "logs")
    os.makedirs(d, exist_ok=True)
    return d


# ══════════════════════════════════════════════
# 端口
# ══════════════════════════════════════════════

def port_in_use(port):
    """检查端口是否被占用（仅本地 127.0.0.1）"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def find_free_port(start=8005, max_try=20):
    """从 start 开始找可用端口"""
    for p in range(start, start + max_try):
        if not port_in_use(p):
            return p
    return start

DEFAULT_PORT = 8005


# ══════════════════════════════════════════════
# 进程 & 锁文件
# ══════════════════════════════════════════════

LOCK_FILE = "aitext.lock"


def read_lock(proj_dir=None):
    """读取锁文件 → (pid, port) 或 None"""
    if proj_dir is None:
        proj_dir = get_proj_dir()
    path = os.path.join(proj_dir, LOCK_FILE)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r") as f:
            parts = f.read().strip().split("|")
            pid = int(parts[0])
            port = int(parts[1]) if len(parts) > 1 else DEFAULT_PORT
            return pid, port
    except Exception:
        return None


def write_lock(pid, port, proj_dir=None):
    """写入锁文件"""
    if proj_dir is None:
        proj_dir = get_proj_dir()
    try:
        with open(os.path.join(proj_dir, LOCK_FILE), "w") as f:
            f.write(f"{pid}|{port}")
    except OSError:
        pass


def remove_lock(proj_dir=None):
    """删除锁文件"""
    if proj_dir is None:
        proj_dir = get_proj_dir()
    try:
        os.remove(os.path.join(proj_dir, LOCK_FILE))
    except OSError:
        pass


def is_process_alive(pid):
    """检查进程是否存活（Windows tasklist）"""
    try:
        proc = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True,
            creationflags=NO_WIN,
        )
        return str(pid) in proc.stdout
    except Exception:
        return False


def kill_process(pid, timeout=3):
    """优雅终止进程 → 强杀（跨平台）"""
    import platform
    system = platform.system()
    try:
        if system == "Windows":
            # Windows: 使用 taskkill
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True, creationflags=NO_WIN,
            )
        else:
            # Unix: 使用 signal
            import signal
            os.kill(pid, signal.SIGTERM)
            time.sleep(min(timeout, 3))
            if is_process_alive(pid):
                os.kill(pid, signal.SIGKILL)
                time.sleep(0.5)
    except Exception:
        # 进程可能已不存在，忽略错误
        pass


# ══════════════════════════════════════════════
# Python 环境检测
# ══════════════════════════════════════════════

def find_python():
    """
    查找可用的 Python 解释器。
    返回 (path, version_str) 或 (None, error_msg)

    优先级（从高到低）:
      0. 内嵌 Python (tools/python_embed/python.exe) — 自动解压自 zip
      1. 虚拟环境 .venv
      2. 系统 Python 3.10+ (PATH / py launcher)
      3. 系统 Python 任何版本（兜底）
    """
    proj_dir = get_proj_dir()

    # 辅助函数：检查版本是否 >= 3.10
    def _version_ok(ver_str):
        if not ver_str:
            return False
        try:
            parts = ver_str.split()[-1].split(".")[:2]
            maj, min_ = int(parts[0]), int(parts[1])
            return (maj, min_) >= (3, 10)
        except (ValueError, IndexError):
            return False

    # ══════════════════════════════════════════════
    # 0) 内嵌 Python（最高优先级！自带 3.11）
    # ══════════════════════════════════════════════
    embedded = _find_embedded_python(proj_dir)
    if embedded:
        return embedded

    # 1) 虚拟环境
    venv_py = get_venv_python(proj_dir)
    if venv_py:
        ver = _get_version(venv_py)
        if ver:
            return venv_py, ver

    # 2) 系统 PATH — 收集所有候选
    candidates = []
    for cmd in ("python", "python3"):
        path = shutil.which(cmd)
        if path:
            ver = _get_version(path)
            if ver:
                candidates.append((path, ver))

    # Windows: py launcher
    if os.name == "nt":
        for ver_flag in ("3.12", "3.11", "3.10", "3.13", "3"):
            try:
                r = subprocess.run(
                    ["py", f"-{ver_flag}", "--version"],
                    capture_output=True, text=True, timeout=5,
                    creationflags=NO_WIN,
                )
                ver = (r.stdout + r.stderr).strip()
                if ver and _version_ok(ver):
                    return (f"py -{ver_flag}", ver)
            except Exception:
                pass

    # 从 PATH 候选中优先返回 3.10+
    for path, ver in candidates:
        if _version_ok(ver):
            return path, ver

    # 兜底
    if candidates:
        return candidates[0]

    return None, "未找到 Python，请先安装 Python 3.10+"


def _find_embedded_python(proj_dir):
    """
    查找内嵌的 Python（自带的 3.11 embeddable）。

    优先从 tools/python_embed/ 查找（首次启动时自动解压自 zip），
    其次查找 PyInstaller 打包后的路径。

    返回 (path, version_str) 或 None
    """
    # 可能的内嵌 Python 目录列表
    search_dirs = []

    # A) 项目目录下的 tools/python_embed（开发时 / 解压后）
    dev_embed = os.path.join(proj_dir, "tools", "python_embed")
    search_dirs.append(dev_embed)

    # B) PyInstaller 打包后的路径（zip 在 _MEIPASS/tools/ 下）
    if getattr(sys, 'frozen', False):
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            # zip 被 --add-data 打包到 tools/ 下，解压后 python_embed/ 在这里
            search_dirs.append(os.path.join(meipass, "tools", "python_embed"))
            search_dirs.append(os.path.join(meipass, "python_embed"))

        exe_dir = os.path.dirname(sys.executable)
        search_dirs.append(os.path.join(exe_dir, "_internal", "tools", "python_embed"))
        search_dirs.append(os.path.join(exe_dir, "_internal", "python_embed"))
        search_dirs.append(os.path.join(exe_dir, "python_embed"))
        search_dirs.append(os.path.join(exe_dir, "..", "python_embed"))

    for embed_dir in search_dirs:
        embed_dir = os.path.abspath(embed_dir)
        py_exe = os.path.join(embed_dir, "python.exe")
        if os.path.exists(py_exe):
            ver = _get_version(py_exe)
            if ver:
                return py_exe, ver

    return None


def ensure_embedded_python(proj_dir=None, on_log=None):
    """
    确保内嵌 Python 存在：如果 python_embed/ 不存在但 zip 在，自动解压。

    这是「零配置」体验的核心：用户甚至不需要安装系统 Python！

    Args:
        proj_dir: 项目根目录
        on_log: 日志回调 (msg, tag)

    返回 True=已就绪 / False=失败(无zip且无目录)
    """
    if proj_dir is None:
        proj_dir = get_proj_dir()
    _log = on_log or (lambda *a: None)

    # 搜索 zip 的候选目录列表
    search_tools_dirs = [os.path.join(proj_dir, "tools")]

    # PyInstaller 模式：zip 可能被打包到 _MEIPASS/tools/ 下
    if getattr(sys, 'frozen', False):
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            search_tools_dirs.append(os.path.join(meipass, "tools"))
            # 也检查 _MEIPASS 根目录（旧兼容）
            search_tools_dirs.append(meipass)

    embed_dir = None
    py_exe = None
    zip_file = None

    for tools_dir in search_tools_dirs:
        _embed_dir = os.path.join(tools_dir, "python_embed")
        _py_exe = os.path.join(_embed_dir, "python.exe")

        # 已存在 → 直接通过
        if os.path.exists(_py_exe):
            return True

        # 记录第一个可写的解压目标（优先项目目录）
        if embed_dir is None:
            # 判断是否可写（PyInstaller 的 _MEIPASS 是只读的）
            try:
                test_file = os.path.join(_embed_dir, ".write_test")
                os.makedirs(_embed_dir, exist_ok=True)
                with open(test_file, 'w') as f:
                    f.write("test")
                os.remove(test_file)
                embed_dir = _embed_dir
                py_exe = _py_exe
            except (OSError, PermissionError):
                pass

        # 查找 zip 文件
        if not zip_file and os.path.isdir(tools_dir):
            for f in os.listdir(tools_dir):
                if re.match(r'python-\d+\.\d+\.\d+-embed-amd64\.zip$', f):
                    zip_file = os.path.join(tools_dir, f)
                    break

    # 已有可写目标 + 找到 zip → 解压
    if embed_dir and zip_file:
        import zipfile
        _log(f"正在解压 Python 内嵌包: {os.path.basename(zip_file)}...", "title")
        try:
            os.makedirs(embed_dir, exist_ok=True)
            with zipfile.ZipFile(zip_file, 'r') as zf:
                zf.extractall(embed_dir)
            _log("Python 内嵌包解压完成 ✓", "ok")
            return True
        except Exception as e:
            _log(f"解压失败: {e}", "error")
            return False

    if not zip_file:
        _log("未找到 Python embed 包 (zip)，将使用系统 Python", "warn")
    return False


def _get_version(exe):
    """执行 python --version，成功返回版本字符串，失败返回 None"""
    try:
        r = subprocess.run(
            [exe, "--version"],
            capture_output=True, text=True, timeout=10,
            creationflags=NO_WIN,
        )
        return (r.stdout + r.stderr).strip() or None
    except Exception:
        return None


def check_uvicorn(exe):
    """检查指定 Python 是否安装了 uvicorn"""
    try:
        r = subprocess.run(
            [exe, "-c", "import uvicorn"],
            capture_output=True, timeout=5,
            creationflags=NO_WIN,
        )
        return r.returncode == 0
    except Exception:
        return False


def ensure_venv(proj_dir=None, system_python=None):
    """
    确保 .venv 存在。
    返回 (venv_python_path, success, message)
    """
    if proj_dir is None:
        proj_dir = get_proj_dir()
    venv_py = get_venv_python(proj_dir)
    if venv_py:
        return venv_py, True, "虚拟环境已存在"

    if not system_python:
        _found_py, _err_msg = find_python()
        if _found_py:
            system_python = _found_py
        else:
            return None, False, f"无法创建虚拟环境: {_err_msg}"

    r = subprocess.run(
        [system_python, "-m", "venv", ".venv"],
        cwd=proj_dir, capture_output=True, text=True,
        creationflags=NO_WIN,
    )
    if r.returncode != 0:
        return None, False, f"虚拟环境创建失败: {r.stderr[:300]}"

    new_venv = get_venv_python(proj_dir)
    return new_venv, True, "虚拟环境创建成功"


# ══════════════════════════════════════════════
# 崩溃日志
# ══════════════════════════════════════════════

def save_crash_log(exc, tb_text="", proj_dir=None):
    """追加写入崩溃日志"""
    if proj_dir is None:
        proj_dir = get_proj_dir()
    try:
        log_dir = get_log_dir(proj_dir)
        path = os.path.join(log_dir, "crash.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"CRASH @ {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Python: {sys.version}\n")
            f.write(f"Exception: {exc}\n\n")
            f.write(tb_text)
            f.write(f"\n{'='*60}\n")
    except Exception:
        pass
