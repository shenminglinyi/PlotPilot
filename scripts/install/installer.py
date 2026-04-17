# -*- coding: utf-8 -*-
"""
aitex 依赖安装器
━━━━━━━━━━━━━━
pip install 的 GUI 封装，支持分级安装策略：

  阶段 1 — 核心依赖（requirements.txt，秒级完成）
    FastAPI / Pydantic / OpenAI / Qdrant / httpx 等
    装完即可启动服务（OpenAI API 模式）

  阶段 2 — 扩展依赖（可选，requirements-local.txt，~2GB）
    sentence-transformers / torch / faiss-cpu / numpy
    仅在用户选择「本地模式」时才需要

特性:
  - 内置多个中国镜像源，自动 fallback
  - 实时逐行解析 pip 输出，显示到日志面板
  - 心跳动画：显示"已等待 Xs"
  - 写入阶段特殊提示（防止用户以为卡死）
  - 失败自动切换镜像源重试
  - 完整日志记录到文件
"""

import os
import re
import subprocess
import threading
import time

from theme import OK_C, WARN_C, ERR_C, ACCENT2, TEXT, BG3
from utils import get_proj_dir, get_log_dir, NO_WIN


# ══════════════════════════════════════════════
# 中国 pip 镜像源列表（按推荐优先级排序）
# ══════════════════════════════════════════════
PIP_MIRRORS = [
    {"name": "阿里云",   "url": "https://mirrors.aliyun.com/pypi/simple/",        "host": "mirrors.aliyun.com"},
    {"name": "清华大学", "url": "https://pypi.tuna.tsinghua.edu.cn/simple/",       "host": "pypi.tuna.tsinghua.edu.cn"},
    {"name": "中科大",   "url": "https://pypi.mirrors.ustc.edu.cn/simple/",         "host": "pypi.mirrors.ustc.edu.cn"},
    {"name": "腾讯云",   "url": "https://mirrors.cloud.tencent.com/pypi/simple/",   "host": "mirrors.cloud.tencent.com"},
    {"name": "华为云",   "url": "https://repo.huaweicloud.com/repository/pypi/simple/", "host": "repo.huaweicloud.com"},
    {"name": "官方源",   "url": "https://pypi.org/simple/",                          "host": "pypi.org"},
]


class PipInstaller:
    """
    pip 安装器（多镜像源自动切换 + 分级安装）。

    用法:
      installer = PipInstaller(venv_py, on_log, on_progress)
      success = installer.install()           # 仅安装核心依赖
      success = installer.install_local()      # 安装本地模型扩展依赖
      success =.install_all()                 # 全部安装（核心 + 扩展）
    """

    PIP_TIMEOUT = 600  # 单次 pip install 最大等待 10 分钟

    def __init__(self, venv_py, on_log=None, on_progress=None,
                 on_heartbeat=None):
        self.venv_py = venv_py
        self.proj_dir = get_proj_dir()
        self.on_log = on_log or (lambda *a: None)
        self.on_progress = on_progress or (lambda *a: None)
        self.on_heartbeat = on_heartbeat or (lambda *a: None)

        self._dl_pkg = ""
        self._dl_start = 0.0
        self._mirror_idx = 0
        # 日志文件
        self._log_file = os.path.join(get_log_dir(), "pip_install.log")

    def _log(self, msg, tag="info"):
        self.on_log(msg, tag)

    def _prog(self, pct, label="", icon="⏳", step=-1):
        self.on_progress(pct, label, icon, step)

    def _write_log(self, text):
        """追加写入 pip 安装日志文件"""
        try:
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except Exception:
            pass

    def _current_mirror(self):
        return PIP_MIRRORS[self._mirror_idx % len(PIP_MIRRORS)]

    def _upgrade_pip(self):
        """
        升级虚拟环境中的 pip + setuptools + wheel 到最新版。
        返回 True=成功/跳过  False=失败
        """
        if not os.path.exists(self.venv_py):
            self._log(f"!!! Python 不存在: {self.venv_py}", "error")
            return False

        self._prog(28, "正在升级包管理器 (pip)...", "🔄", 2)
        self._log("升级 pip + setuptools + wheel（这可能需要 1~2 分钟）...", "title")

        m = PIP_MIRRORS[0]  # 用阿里云升级
        cmd = [
            self.venv_py, "-m", "pip", "install",
            "--upgrade", "pip", "setuptools", "wheel",
            "-i", m["url"],
            "--trusted-host", m["host"],
            "--no-cache-dir",
            "--disable-pip-version-check",
            "-q",
        ]

        try:
            proc = subprocess.Popen(
                cmd, cwd=self.proj_dir,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=NO_WIN,
            )
            output, _ = proc.communicate(timeout=300)  # 5 分钟超时

            if proc.returncode == 0:
                self._log("pip 升级完成 ✓", "ok")
                self._write_log("[PIP UPGRADE OK]")
                return True
            else:
                last_line = output.strip().split("\n")[-1] if output.strip() else "(无输出)"
                self._log(f"pip 升级异常: {last_line[:120]}", "warn")
                self._write_log(f"[PIP UPGRADE FAIL] rc={proc.returncode}: {output[-500:]}")
                return False

        except subprocess.TimeoutExpired:
            self._log("pip 升级超时（>5分钟），将用当前版本继续", "warn")
            proc.kill()
            return False
        except Exception as e:
            self._log(f"pip 升级出错: {e}", "warn")
            self._write_log(f"[PIP UPGRADE ERROR] {e}")
            return False

    # ══════════════════════════════════════════════
    # 公开 API：分级安装
    # ══════════════════════════════════════════════

    def install(self):
        """仅安装核心依赖（requirements.txt）。

        这是默认安装路径。装完后即可使用 OpenAI API 模式。
        返回 True=成功 / False=失败
        """
        return self._do_install(
            req_file_name="requirements.txt",
            batch_label="核心依赖",
            batch_icon="⚡",
            start_pct=25,
            end_pct=55,
            step_idx=2,
        )

    def install_local(self):
        """安装本地模型扩展依赖（requirements-local.txt）。

        包含 sentence-transformers / torch / faiss-cpu 等 ~2GB 的包。
        仅在用户主动选择「本地模式」时调用。
        返回 True=成功 / False=失败
        """
        return self._do_install(
            req_file_name="requirements-local.txt",
            batch_label="本地 AI 引擎（较大）",
            batch_icon="🧠",
            start_pct=56,
            end_pct=85,
            step_idx=2,
        )

    def install_all(self):
        """安装全部依赖（核心 + 扩展），返回是否全部成功"""
        core_ok = self.install()
        if not core_ok:
            return False
        local_ok = self.install_local()
        return local_ok

    # ══════════════════════════════════════════════
    # 内部实现
    # ══════════════════════════════════════════════

    def _do_install(self, req_file_name, batch_label, batch_icon,
                    start_pct, end_pct, step_idx):
        """通用安装流程：升级 pip → 安装指定 requirements 文件 → fallback"""
        # 步骤 0：强制升级 pip
        if not self._upgrade_pip():
            self._log("pip 升级失败，将尝试用当前版本继续...", "warn")

        # 清空旧日志
        try:
            with open(self._log_file, "w", encoding="utf-8") as f:
                f.write(f"=== aitext pip install log ===\n")
                f.write(f"time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"req_file: {req_file_name}\n")
                f.write(f"venv_py: {self.venv_py}\n")
                f.write(f"proj_dir: {self.proj_dir}\n")
                f.write(f"{'='*52}\n\n")
        except Exception:
            pass

        # 构建命令
        req_file = os.path.join(self.proj_dir, req_file_name)
        if not os.path.exists(req_file):
            self._log(f"!!! {req_file_name} 不存在: {req_file}", "error")
            self._write_log(f"ERROR: {req_file_name} not found: {req_file}")
            return False

        m = self._current_mirror()
        cmd = [
            self.venv_py, "-m", "pip", "install", "-r", req_file,
            "-i", m["url"],
            "--trusted-host", m["host"],
            "--timeout", str(self.PIP_TIMEOUT),
            "--retries", "1",
            "--no-cache-dir",
            "--progress-bar", "off",
            "--disable-pip-version-check",
        ]

        self._log("", "info")
        self._log("=" * 52, "title")
        self._log(f"  安装 {batch_label}", "title")
        self._log(f"  文件: {req_file_name}", "dim")
        self._log("=" * 52, "title")
        self._prog(start_pct, f"正在安装{batch_label}...", batch_icon, step_idx)

        # 直接执行安装（带多镜像 fallback）
        max_mirrors = len(PIP_MIRRORS)
        for attempt in range(max_mirrors):
            m = self._current_mirror()
            self._mirror_idx = attempt
            if attempt > 0:
                self._log(f"切换镜像源 [{m['name']}]", "title")
                # 更新 cmd 中的镜像
                cmd = self._build_cmd_with_mirror(cmd, m)

            self._write_log(f"\n--- Attempt {attempt+1}/{max_mirrors}: {m['name']} ---")

            if self._run_install(cmd, is_batch=True,
                                  start_pct=start_pct, end_pct=end_pct,
                                  step_idx=step_idx, batch_label=batch_label):
                self._write_log(f"\n=== INSTALL SUCCESS ({req_file_name}) ===")
                self._log("", "info")
                self._log("=" * 52, "ok")
                self._log(f"  {batch_label} 安装完成!", "ok")
                self._log("=" * 52, "ok")
                self._prog(end_pct, f"{batch_label}安装完成", "✔", step_idx)
                return True

        # 所有镜像都失败
        self._log(f"{batch_label} 安装失败！", "error")
        self._write_log(f"\n=== ALL FAILED ({req_file_name}) ===")
        return False

    def _build_cmd_with_mirror(self, base_cmd, mirror):
        """替换 base_cmd 中的镜像源参数"""
        cmd = list(base_cmd)
        for i, token in enumerate(cmd):
            if token == "-i" and i + 1 < len(cmd):
                cmd[i + 1] = mirror["url"]
            elif token == "--trusted-host" and i + 1 < len(cmd):
                cmd[i + 1] = mirror["host"]
        return cmd

    def _run_install(self, cmd, is_batch=False,
                     start_pct=25, end_pct=55, step_idx=-1, batch_label=""):
        """执行一次 pip install，返回是否成功。

        Args:
            cmd: pip 命令列表
            is_batch: 是否为分批模式（影响进度条显示策略）
            start_pct: 进度条起始百分比
            end_pct: 进度条结束百分比
            step_idx: 当前步骤索引
            batch_label: 当前批次名称（用于日志）
        """
        # 启动子进程
        try:
            proc = subprocess.Popen(
                cmd, cwd=self.proj_dir,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                bufsize=1, creationflags=NO_WIN,
            )
        except Exception as e:
            self._log(f"!!! 无法启动 pip 进程: {e}", "error")
            self._write_log(f"FATAL: Popen failed: {e}")
            return False

        collecting_count = 0
        heartbeat_running = [True]
        total_range = end_pct - start_pct

        # ── 心跳线程 ──
        def _heartbeat_thread():
            while heartbeat_running[0]:
                time.sleep(1)
                if not heartbeat_running[0]:
                    break
                elapsed = time.time() - self._dl_start
                if elapsed > 1 and self._dl_pkg:
                    mins = int(elapsed) // 60
                    secs = int(elapsed) % 60
                    t_str = f"{mins}m{secs:02d}s" if mins else f"{secs}s"
                    self.on_heartbeat(self._dl_pkg, t_str)

        threading.Thread(target=_heartbeat_thread, daemon=True).start()

        # ── 逐行解析输出 ──
        for line in proc.stdout:
            line = line.rstrip()
            if not line:
                continue

            # 记录到日志文件
            self._write_log(line)

            if "Successfully installed" in line:
                self._log(line, "ok")

            elif ("error" in line.lower() and "ERROR" in line) or \
                 line.startswith("ERROR"):
                self._log(line, "error")

            elif "warning" in line.lower() or "WARNING" in line or \
                 line.startswith("WARNING"):
                self._log(line, "warn")

            elif line.startswith("Collecting"):
                collecting_count += 1
                pkg = line.replace("Collecting", "").strip().split(" ")[0]
                self._log(line, "title")
                if is_batch and total_range > 0:
                    # 分批模式：按包数量平滑分配进度
                    pct = min(start_pct + min(collecting_count * 2, total_range * 0.6), end_pct - 10)
                else:
                    pct = min(30 + collecting_count * 1.5, 52)
                self._prog(pct, f"正在获取: {pkg}", "⚙", step_idx)
                self._dl_pkg = pkg
                self._dl_start = time.time()

            elif line.startswith("Downloading"):
                fname_match = re.search(r'/([^/]+\.(?:whl|tar\.gz|zip))', line)
                pkg_name = fname_match.group(1) if fname_match else line.strip()[11:60]
                self._dl_pkg = pkg_name
                self._dl_start = time.time()
                self._log(line, "title")

            elif "Installing collected packages" in line:
                self._log(line, "ok")
                self._dl_pkg = ""
                if is_batch:
                    self._prog(end_pct - 8, "正在写入文件...", "⏳", step_idx)
                else:
                    self._prog(52, "正在写入文件...", "⏳", step_idx)
                self._log("═" * 52, "warn")
                self._log("⚠  写入阶段！通常需要 1~5 分钟", "warn")
                self._log("│  界面可能暂时不更新，属正常现象！", "warn")
                self._log("═" * 52, "warn")

            else:
                self._log(line, "info")

        heartbeat_running[0] = False
        proc.wait()

        self._write_log(f"\nreturncode: {proc.returncode}")

        if proc.returncode != 0:
            m = self._current_mirror()
            self._log(f"镜像源 [{m['name']}] 失败 (code={proc.returncode})，准备切换...", "error")
            return False

        m = self._current_mirror()
        self._log(f"安装完成 ✓ (镜像源: {m['name']})", "ok")
        if is_batch:
            self._prog(end_pct, f"{batch_label}安装完成", "✔", step_idx)
        else:
            self._prog(55, "依赖安装完成", "✔", step_idx)
        return True
