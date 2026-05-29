# -*- coding: utf-8 -*-
"""
PlotPilot 后端服务启动器
━━━━━━━━━━━━━━━━━━━━
负责:
  - 查找可用 Python（含 uvicorn）
  - 启动 uvicorn 子进程（pythonw 无黑框）
  - 健康检查轮询（等待端口就绪）
  - 自动打开浏览器
  - 实时追踪日志文件 → 回调显示
"""

import os
import sys
import subprocess
import time
import threading
import webbrowser

from theme import OK_C, WARN_C, ERR_C, ACCENT2
from utils import (
    get_proj_dir, get_log_dir, port_in_use, find_free_port,
    check_uvicorn, NO_WIN, DEFAULT_PORT,
    write_lock, kill_port, get_pid_by_port,
)


class BackendLauncher:
    """
    后端启动器。

    用法:
      launcher = BackendLauncher(
          on_log=...,
          on_progress=...,
          on_ready=...,        # 服务就绪回调
          on_failed=...,       # 失败回调
      )
      launcher.launch(initial_port)
      # ... 在后台线程运行 ...
      launcher.wait()         # 阻塞直到进程退出
    """

    # 启动阶段模拟进度
    LAUNCH_STEPS = [
        (74, "检测运行环境"),
        (78, "加载应用模块"),
        (82, "初始化数据库"),
        (86, "注册 API 路由"),
        (88, "启动 HTTP 服务"),
    ]

    def __init__(self, venv_py=None, on_log=None, on_progress=None,
                 on_ready=None, on_failed=None):
        self.venv_py = venv_py  # 已安装依赖的 Python 路径（优先使用）
        self.on_log = on_log or (lambda *a: None)
        self.on_progress = on_progress or (lambda *a: None)
        self.on_ready = on_ready or (lambda: None)
        self.on_failed = on_failed or (lambda *a: None)
        self.proj_dir = get_proj_dir()
        self.proc = None

    def _log(self, msg, tag="info"):
        self.on_log(msg, tag)

    def _prog(self, pct, label="", icon="⏳", step=-1):
        self.on_progress(pct, label, icon, step)

    def launch(self, port=DEFAULT_PORT):
        """
        在当前线程中执行完整启动流程。
        通常应在后台线程中调用。
        返回 True(成功) / False(失败)
        """
        try:
            return self._do_launch(port)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self._log(f"启动异常: {e}", "error")
            self.on_failed(str(e), tb)
            return False

    def _do_launch(self, port):
        """核心启动流程"""
        # ── 端口检测：占用则自动杀掉占用进程 ──
        if port_in_use(port):
            pid = get_pid_by_port(port)
            pid_info = f" (PID={pid})" if pid else ""
            self._log(f"端口 {port} 被占用{pid_info}，正在释放...", "warn")
            self._prog(70, f"释放端口 {port}...", "🔪", 5)
            if kill_port(port):
                self._log(f"端口 {port} 已释放", "ok")
            else:
                self._log(f"无法释放端口 {port}，自动切换备用端口...", "warn")
                port = find_free_port(port + 1)
                self._log(f"切换至端口 {port}", "warn")
        self._port = port
        self._prog(72, f"使用端口 {port}", "🚀", 5)

        # ── 模拟启动步骤 ──
        for pct, label in self.LAUNCH_STEPS:
            self._prog(pct, label, "⏳", 5)
            self._log(label + "...", "info")
            time.sleep(0.3)

        # ── 查找 Python ──
        python_exe = self._find_python()
        if not python_exe:
            return False

        # ── 启动子进程 ──
        if not self._spawn_process(python_exe, port):
            return False

        write_lock(self.proc.pid, port)
        self._log(f"服务进程已启动 (PID={self.proc.pid}, 端口={port})", "title")

        # ── 等待就绪 ──
        self._prog(90, "等待服务就绪...", "⏳", 5)
        if not self._wait_ready(port):
            return False

        self._log(f"服务已就绪 → http://127.0.0.1:{port}", "ok")
        self.on_ready(port)

        # ── 打开浏览器 ──
        time.sleep(0.6)
        try:
            webbrowser.open(f"http://127.0.0.1:{port}")
            self._log("浏览器已自动打开", "ok")
        except Exception:
            self._log("请手动打开浏览器访问上方地址", "warn")

        self._log("提示：此窗口可最小化，关闭将停止后端服务", "warn")

        # ── 日志追踪 ──
        threading.Thread(target=self._tail_log, daemon=True).start()

        # 阻塞等待退出
        self.proc.wait()
        from .utils import remove_lock
        remove_lock()
        self._log("服务已停止", "warn")
        return True

    def _find_python(self):
        """查找带 uvicorn 的 Python，强制优先 Python 3.14 系列。"""

        def _usable(python_exe):
            if not python_exe:
                return False
            try:
                r = subprocess.run(
                    [python_exe, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    creationflags=NO_WIN,
                )
                ver = (r.stdout + r.stderr).strip()
            except Exception:
                return False
            return is_preferred_python_version(ver) and check_uvicorn(python_exe)

        # 1) 调用方传入的 Python 只有在 3.14 且已安装 uvicorn 时才接受。
        if self.venv_py and os.path.exists(self.venv_py):
            if _usable(self.venv_py):
                return self.venv_py
            self._log(f"传入的 Python 不是项目要求的 Python 3.14 或缺少 uvicorn: {self.venv_py}", "warn")

        # 2) 统一发现逻辑会优先 PLOTPILOT_PYTHON_EXE / Python314 标准安装路径。
        found_py, found_ver = find_python()
        if found_py:
            if check_uvicorn(found_py):
                self._log(f"使用 Python 运行后端: {found_py} ({found_ver})", "ok")
                return found_py
            self._log(f"Python 3.14 已找到但缺少 uvicorn: {found_py}", "warn")

        # 3) 当前解释器兜底：也必须是 Python 3.14，避免 hub 由旧版本启动时继续误用旧版本。
        if _usable(sys.executable):
            return sys.executable

        self.on_failed(
            "找不到已安装 uvicorn 的 Python 3.14",
            "请使用 Python 3.14.5 安装 requirements.txt，或设置 PLOTPILOT_PYTHON_EXE 指向 Python314\\python.exe",
        )
        return None

    def _spawn_process(self, python_exe, port):
        """启动 uvicorn 子进程"""
        # 优先用 pythonw.exe（无控制台窗口）
        _dir = os.path.dirname(python_exe)
        _pythonw = os.path.join(_dir, "pythonw.exe")
        backend_exe = _pythonw if os.path.exists(_pythonw) else python_exe

        # 日志文件：记录后端启动日志（方便排查问题）
        _log_file = os.path.join(get_log_dir(), "backend_startup.log")

        try:
            self.proc = subprocess.Popen(
                [
                    backend_exe, "-m", "uvicorn",
                    "interfaces.main:app",
                    "--host", "127.0.0.1",
                    "--port", str(port),
                    "--log-level", "info",
                ],
                cwd=self.proj_dir,
                env={
                    **os.environ,
                    "PYTHONIOENCODING": "utf-8",
                    "PYTHONUNBUFFERED": "1",
                    "HF_HUB_OFFLINE": "1",
                    "TRANSFORMERS_OFFLINE": "1",
                },
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=NO_WIN,
            )

            # 后台线程：读取子进程输出并写入日志
            def _tail_backend():
                try:
                    with open(_log_file, "w", encoding="utf-8") as lf:
                        lf.write(f"[{time.strftime('%H:%M:%S')}] Starting backend: {backend_exe}\n")
                        lf.write(f"[{time.strftime('%H:%M:%S')}] Port: {port}\n")
                        lf.write(f"[{time.strftime('%H:%M:%S')}] Working dir: {self.proj_dir}\n")
                        lf.write("=" * 52 + "\n")
                        for line in iter(self.proc.stdout.readline, b""):
                            text = line.decode("utf-8", errors="replace").rstrip()
                            lf.write(text + "\n")
                            lf.flush()
                            self._log(text, "info")
                except Exception:
                    pass

            threading.Thread(target=_tail_backend, daemon=True).start()
            return True
        except Exception as e:
            self.on_failed(str(e), "")
            return False

    def _wait_ready(self, port, timeout=120):
        """轮询等待服务就绪（HTTP 健康检查）"""
        import urllib.request
        import urllib.error

        deadline = time.time() + timeout
        prog = 90.0
        health_url = f"http://127.0.0.1:{port}/health"

        # 第一阶段：等端口监听（最多 30 秒）
        while time.time() < min(deadline, time.time() + 30):
            if port_in_use(port):
                self._log(f"端口 {port} 已开始监听，等待服务初始化...", "title")
                break
            prog = min(prog + 0.3, 94)
            self._prog(prog, "等待后端进程启动...", "⏳", 5)
            time.sleep(0.4)
        else:
            self.on_failed(
                f"后端进程未能在 {timeout}s 内绑定端口 {port}",
                "可能原因：依赖缺失 / 端口被占用 / Python 环境异常\n"
                f"详细日志: logs/backend_startup.log"
            )
            return False

        # 第二阶段：等 HTTP 就绪（health check）
        while time.time() < deadline:
            try:
                req = urllib.request.Request(health_url, method="GET")
                with urllib.request.urlopen(req, timeout=3) as resp:
                    if resp.status == 200:
                        return True
            except Exception:
                pass
            prog = min(prog + 0.2, 97)
            self._prog(prog, "等待服务响应 (HTTP)...", "⏳", 5)
            time.sleep(0.5)

        # 超时：检查子进程是否还活着
        if self.proc and self.proc.poll() is not None:
            # 进程已退出！说明启动失败
            self.on_failed(
                "后端进程启动后立即退出了！",
                "请查看日志面板或 logs/backend_startup.log 获取错误详情\n"
                "常见原因：缺少依赖包 / import 错误 / 配置文件问题"
            )
        else:
            self.on_failed(
                f"服务启动超时（{timeout}s）",
                "端口已监听但 HTTP 无响应\n"
                f"请查看: logs/backend_startup.log"
            )
        return False

    @property
    def port(self):
        return getattr(self, '_port', DEFAULT_PORT)

    def wait(self):
        """阻塞直到子进程退出"""
        if self.proc:
            self.proc.wait()

    def terminate(self):
        """终止后端进程"""
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=4)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass

    def _tail_log(self):
        """实时追踪 logs/plotpilot.log，通过回调报告"""
        log_path = os.path.join(self.proj_dir, "logs", "plotpilot.log")

        # 等待文件出现
        for _ in range(20):
            if os.path.exists(log_path):
                break
            time.sleep(0.5)
        if not os.path.exists(log_path):
            return

        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(0, 2)  # 定位到末尾
            while self.proc and self.proc.poll() is None:
                line = f.readline()
                if not line:
                    time.sleep(0.3)
                    continue
                line = line.rstrip()
                if not line:
                    continue
                if "[ERROR]" in line or "[CRITICAL]" in line:
                    self._log(line, "error")
                elif "[WARNING]" in line:
                    self._log(line, "warn")
                elif "[OK]" in line or "启动成功" in line:
                    self._log(line, "ok")
                else:
                    self._log(line, "info")
