# -*- coding: utf-8 -*-
"""
PlotPilot 启动器打包脚本
━━━━━━━━━━━━━━━━
将 scripts/install/ 打包为独立 exe。
双击即用，无需 Python 环境。

用法:
  python build_exe.py          # 打包
  python build_exe.py run      # 打包后自动运行测试
  python build_exe.py clean    # 清理构建缓存

输出:
  dist/plotpilot/   (包含 plotpilot.exe 的文件夹)
"""

import os
import sys
import subprocess
import shutil

# ══════════════════════════════════════════════
# 路径配置
# ══════════════════════════════════════════════
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INSTALL_DIR = SCRIPT_DIR  # scripts/install/
PROJ_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # 项目根目录
ENTRY_FILE = os.path.join(INSTALL_DIR, "__main__.py")  # Bootstrap 入口
DIST_DIR = os.path.join(PROJ_DIR, "dist")
BUILD_DIR = os.path.join(PROJ_DIR, "build")
EXE_NAME = "plotpilot"
ICON_PATH = os.path.join(PROJ_DIR, "docs", "plotpilot.ico")
EMBED_PYTHON_DIR = os.path.join(PROJ_DIR, "tools", "python_embed")  # 内嵌 Python 目录（运行时自动解压）
EMBED_PYTHON_ZIP = os.path.join(PROJ_DIR, "tools")  # zip 所在目录


def clean():
    """清理构建缓存"""
    for d in [BUILD_DIR, DIST_DIR]:
        if os.path.exists(d):
            shutil.rmtree(d)
            print(f"  [CLEAN] Removed: {d}")
    print("  Clean done.")


def build():
    """执行 PyInstaller 打包"""
    # 确保 __init__.py 存在
    init_file = os.path.join(INSTALL_DIR, "__init__.py")
    if not os.path.exists(init_file):
        with open(init_file, "w", encoding="utf-8") as f:
            f.write("# PlotPilot installer package\n")

    # ═══ 检查内嵌 Python zip（运行时自动解压） ═══
    import re as _re
    zip_found = False
    tools_dir = EMBED_PYTHON_ZIP
    for f in os.listdir(tools_dir) if os.path.isdir(tools_dir) else []:
        if _re.match(r'python-\d+\.\d+\.\d+-embed-amd64\.zip$', f):
            zip_found = True
            zip_path = os.path.join(tools_dir, f)
            break
    if zip_found:
        print(f"  [EMBED] Found Python embed zip: {os.path.basename(zip_path)}")
    else:
        print(f"  [WARN] Python embed zip NOT found in: {tools_dir}")
        print("  [WARN] Build will continue without embedded Python (users need system Python).")

    # ═══ 把 requirements 文件打包进去（供安装器使用） ═══
    req_files = []
    for req_name in ["requirements.txt", "requirements-local.txt"]:
        req_path = os.path.join(PROJ_DIR, req_name)
        if os.path.exists(req_path):
            req_files.append(f"{req_path}{os.pathsep}.{os.pathsep}")

    # 可选：仅有目录时才打入，避免无 Tauri / 未 build 前端时 PyInstaller 失败
    optional_bundles: list[str] = []
    frontend_dist = os.path.join(PROJ_DIR, "frontend", "dist")
    if os.path.isdir(frontend_dist):
        optional_bundles.extend(
            ["--add-data", f"{frontend_dist}{os.pathsep}dist"]
        )
    else:
        print(f"  [SKIP] 未找到前端构建目录，跳过: {frontend_dist}")

    frontend_tauri = os.path.join(PROJ_DIR, "frontend", "src-tauri")
    if os.path.isdir(frontend_tauri):
        optional_bundles.extend(
            ["--add-data", f"{frontend_tauri}{os.pathsep}src-tauri"]
        )
    else:
        print(f"  [SKIP] 未找到 Tauri 工程目录，跳过: {frontend_tauri}")

    # PyInstaller 命令
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", EXE_NAME,
        "--onedir",
        "--windowed",          # 隐藏控制台黑框（GUI 模式）
        "--noconfirm",
        "--clean",
        # 把整个 install 目录作为数据文件打包进去
        "--add-data", f"{INSTALL_DIR}{os.pathsep}scripts/install",
        # requirements 文件（核心 + 扩展）
        *req_files,
        *optional_bundles,
        # tkinter + 常用标准库（PyInstaller 可能遗漏的）
        "--hidden-import", "tkinter",
        "--hidden-import", "tkinter.ttk",
        "--hidden-import", "tkinter.font",
        "--hidden-import", "tkinter.messagebox",
        "--hidden-import", "webbrowser",
        "--hidden-import", "threading",
        "--hidden-import", "subprocess",
        "--hidden-import", "shutil",
        "--hidden-import", "socket",
        "--hidden-import", "json",
        "--hidden-import", "re",
        "--hidden-import", "time",
        "--hidden-import", "os",
        "--hidden-import", "sys",
        "--hidden-import", "traceback",
        "--hidden-import", "pathlib",
        "--hidden-import", "urllib.parse",
        "--hidden-import", "urllib.request",
        "--hidden-import", "html",
        "--hidden-import", "http.client",
        "--hidden-import", "email",
        "--hidden-import", "email.mime",
        "--hidden-import", "email.mime.text",
        # 搜索路径
        "--paths", PROJ_DIR,
        "--paths", INSTALL_DIR,
        # 用 __main__.py 作为入口（它用 exec 加载 hub.py，
        # 避免 PyInstaller 静态分析 import 冲突）
        ENTRY_FILE,
    ]

    # ═══ 把 Python embed zip 打入 exe（运行时自动解压到 python_embed/） ═══
    if zip_found:
        cmd.extend([
            "--add-data", f"{zip_path}{os.pathsep}tools",
        ])
        print(f"  [EMBED] Packing python embed zip into exe...")

    if os.path.exists(ICON_PATH):
        cmd.extend(["--icon", ICON_PATH])
        print(f"  [ICON] Using: {ICON_PATH}")
    else:
        print(f"  [ICON] No icon found, skipping.")

    print("=" * 56)
    print("  Building PlotPilot launcher...")
    print(f"  Entry:  {ENTRY_FILE} (bootstrap)")
    print(f"  Output: {os.path.join(DIST_DIR, EXE_NAME)}")
    print("=" * 56)

    result = subprocess.run(cmd, cwd=PROJ_DIR)

    if result.returncode == 0:
        print()
        print("=" * 56)
        print("  BUILD SUCCESS!")
        exe_path = os.path.join(DIST_DIR, EXE_NAME, EXE_NAME + ".exe")
        print(f"  Exe:  {exe_path}")
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"  Size: {size_mb:.1f} MB")
        print()
        print("  Distribute the folder:")
        print(f"    {os.path.join(DIST_DIR, EXE_NAME)}/")
        print("=" * 56)

        # 复制到 tools/
        exe_src = os.path.join(DIST_DIR, EXE_NAME)
        exe_dst = os.path.join(PROJ_DIR, "tools", EXE_NAME)
        if os.path.exists(exe_src):
            if os.path.exists(exe_dst):
                shutil.rmtree(exe_dst)
            shutil.copytree(exe_src, exe_dst)
            print(f"\n  Copied to: {exe_dst}/")

            # 同时确保 Python embed zip 也在 tools/ 下（运行时自动解压）
            # python_embed/ 不需要复制，首次启动时 ensure_embedded_python() 会自动从 zip 解压
            print(f"  (python_embed 将在首次启动时自动解压)")
    else:
        print("\n  BUILD FAILED!")
        sys.exit(1)


def main():
    action = (sys.argv[1] if len(sys.argv) > 1 else "").lower()
    if action == "clean":
        clean()
    elif action == "run":
        build()
        exe = os.path.join(DIST_DIR, EXE_NAME, EXE_NAME + ".exe")
        if os.path.exists(exe):
            print(f"\n  Running: {exe}")
            subprocess.Popen([exe], cwd=PROJ_DIR)
        else:
            print(f"  ERROR: exe not found at {exe}")
    else:
        build()


if __name__ == "__main__":
    main()
