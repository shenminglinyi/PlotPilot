# -*- coding: utf-8 -*-
"""
Tauri / NSIS 安装包构建入口。

产物与目录（详情见 docs/BUILD_INSTALLER.md）:
  - Windows 安装包: frontend/src-tauri/target/release/bundle/nsis/*.exe
  - macOS: frontend/src-tauri/target/release/bundle/dmg/*.dmg（需在 tauri.conf 中启用 dmg）
  - PyInstaller 冻结后端: out/tauri/plotpilot-backend/（Windows 为 .exe，macOS/Linux 无后缀）

用法:
  python scripts/build_installer.py
  python scripts/build_installer.py --clean   # 清理 dist / Tauri target / PyInstaller 工作目录等（不删 node_modules，避免 Windows 文件锁）
  python scripts/build_installer.py --dev
  python scripts/build_installer.py --skip-frozen-backend
  python scripts/build_installer.py --version 4.7.2        # 同步全部运行时版本号
  python scripts/build_installer.py -V 2.0.0-beta --clean  # 短参数形式
"""
from __future__ import annotations

import os
import sys
import subprocess
import shutil
import argparse
from pathlib import Path

# ══════════════════════════════════════════════
# 路径配置
# ══════════════════════════════════════════════
PROJ_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = PROJ_ROOT / "frontend"
TAURI_DIR = FRONTEND_DIR / "src-tauri"
FROZEN_BUNDLE_DIR = PROJ_ROOT / "out" / "tauri" / "plotpilot-backend"


def frozen_backend_exe_path() -> Path:
    """与 build_backend_pyinstaller 一致：Windows 为 .exe，类 Unix 无后缀。"""
    name = "plotpilot-backend.exe" if os.name == "nt" else "plotpilot-backend"
    return FROZEN_BUNDLE_DIR / name


def _frozen_bundle_unpacked_size() -> int:
    if not FROZEN_BUNDLE_DIR.is_dir():
        return 0
    total = 0
    for f in FROZEN_BUNDLE_DIR.rglob("*"):
        if f.is_file():
            total += f.stat().st_size
    return total


def _warn_if_bundle_exceeds_nsis_limits() -> None:
    """NSIS 编译超大安装包时常见 mmap / #12345 失败，多与总资源超过约 2GiB 有关。"""
    size = _frozen_bundle_unpacked_size()
    limit = 1800 * 1024 * 1024
    if size <= limit:
        return
    gib = size / (1024**3)
    print_warning(
        f"冻结后端目录约 {gib:.2f} GiB，NSIS 可能无法完成打包（mmap 错误）。"
        "请使用仅安装 requirements-nsis.txt 的干净 Python/venv 再运行本脚本，"
        "避免把本机 torch 等重型包装进 PyInstaller。"
    )


PYINSTALLER_WORK = PROJ_ROOT / "build" / "pyinstaller-backend"
BUILD_BACKEND_SCRIPT = PROJ_ROOT / "scripts" / "build_backend_pyinstaller.py"


def remove_pycaches(package_roots: list[Path]) -> None:
    """发布前删除源码树中的 __pycache__，减小安装包体积。"""
    for root in package_roots:
        if not root.is_dir():
            continue
        for p in root.rglob("__pycache__"):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)

# ══════════════════════════════════════════════
# 颜色输出
# ══════════════════════════════════════════════
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}  {text}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")


def print_step(step_num, text):
    print(f"{Colors.CYAN}[{step_num}/6]{Colors.ENDC} {Colors.BOLD}{text}{Colors.ENDC}")


def print_success(text):
    print(f"{Colors.GREEN}✓ {text}{Colors.ENDC}")


def print_warning(text):
    print(f"{Colors.YELLOW}⚠ {text}{Colors.ENDC}")


def print_error(text):
    print(f"{Colors.RED}✗ {text}{Colors.ENDC}")


def print_info(text):
    print(f"{Colors.BLUE}ℹ {text}{Colors.ENDC}")

# ══════════════════════════════════════════════
# 步骤 1: 检查环境
# ══════════════════════════════════════════════
def check_environment():
    """检查构建环境是否就绪"""
    print_step(1, "检查构建环境")

    checks = []

    # 检查 Node.js
    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print_success(f"Node.js: {result.stdout.strip()}")
            checks.append(True)
        else:
            print_error("Node.js 未安装或不在 PATH 中")
            checks.append(False)
    except FileNotFoundError:
        print_error("Node.js 未安装")
        checks.append(False)

    # 检查 npm
    try:
        result = subprocess.run(["npm", "--version"], capture_output=True, text=True, shell=True)
        if result.returncode == 0:
            print_success(f"npm: {result.stdout.strip()}")
            checks.append(True)
        else:
            print_error("npm 未安装")
            checks.append(False)
    except Exception as e:
        print_error(f"npm 检查失败: {e}")
        checks.append(False)

    # 检查 Rust
    try:
        result = subprocess.run(["rustc", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print_success(f"Rust: {result.stdout.strip()}")
            checks.append(True)
        else:
            print_error("Rust 未安装")
            checks.append(False)
    except FileNotFoundError:
        print_error("Rust 未安装 (访问 https://rustup.rs/ 安装)")
        checks.append(False)

    # 检查 Tauri CLI
    try:
        result = subprocess.run(["cargo", "tauri", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print_success(f"Tauri CLI: {result.stdout.strip()}")
            checks.append(True)
        else:
            print_warning("Tauri CLI 未安装，尝试安装...")
            install_result = subprocess.run(
                ["cargo", "install", "tauri-cli", "--version", "^2.0"],
                capture_output=True, text=True
            )
            if install_result.returncode == 0:
                print_success("Tauri CLI 安装成功")
                checks.append(True)
            else:
                print_error("Tauri CLI 安装失败")
                checks.append(False)
    except FileNotFoundError:
        print_error("Cargo 未安装")
        checks.append(False)

    # PyInstaller（冻结后端）
    try:
        pi = subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            capture_output=True,
            text=True,
        )
        if pi.returncode == 0:
            print_success(f"PyInstaller: {pi.stdout.strip()}")
            checks.append(True)
        else:
            print_error("PyInstaller 不可用，请执行: pip install pyinstaller")
            checks.append(False)
    except Exception as e:
        print_error(f"PyInstaller 检查失败: {e}")
        checks.append(False)

    # 运行时依赖（供 PyInstaller 分析，与 requirements-nsis 一致）
    try:
        im = subprocess.run(
            [sys.executable, "-c", "import fastapi, uvicorn"],
            capture_output=True,
            text=True,
        )
        if im.returncode == 0:
            print_success("当前 Python 已安装 fastapi / uvicorn（与 requirements-nsis 对齐）")
            checks.append(True)
        else:
            print_warning("当前 Python 缺少 fastapi 或 uvicorn，请先: pip install -r requirements-nsis.txt")
            checks.append(True)
    except Exception:
        checks.append(True)

    # 前 5 项：Node / npm / Rust / Tauri / PyInstaller
    if len(checks) >= 5 and all(checks[:5]):
        print_success("环境检查通过")
        return True
    print_error("环境检查失败，请安装缺失的依赖")
    return False

# ══════════════════════════════════════════════
# 步骤 2: 安装前端依赖
# ══════════════════════════════════════════════
def install_frontend_deps():
    """安装前端依赖"""
    print_step(2, "安装前端依赖")

    # 检查 node_modules 是否存在
    if (FRONTEND_DIR / "node_modules").exists():
        print_info("node_modules 已存在，跳过 npm install")
        return True

    result = subprocess.run(
        ["npm", "install"],
        capture_output=True,
        text=True,
        shell=True,
        cwd=str(FRONTEND_DIR),
    )
    if result.returncode == 0:
        print_success("前端依赖安装完成")
        return True
    else:
        print_error("前端依赖安装失败")
        print(result.stderr)
        return False

# ══════════════════════════════════════════════
# 步骤 3: 构建前端
# ══════════════════════════════════════════════
def build_frontend():
    """构建前端生产版本"""
    print_step(3, "构建前端生产版本")

    # 清理旧的构建产物
    dist_dir = FRONTEND_DIR / "dist"
    if dist_dir.exists():
        shutil.rmtree(dist_dir)
        print_info("清理旧的构建产物")

    remove_pycaches(
        [
            PROJ_ROOT / "interfaces",
            PROJ_ROOT / "application",
            PROJ_ROOT / "domain",
            PROJ_ROOT / "infrastructure",
        ]
    )

    result = subprocess.run(
        ["npm", "run", "build"],
        capture_output=True,
        text=True,
        shell=True,
        cwd=str(FRONTEND_DIR),
    )
    if result.returncode == 0:
        print_success("前端构建完成")
        # 显示构建产物大小
        if dist_dir.exists():
            total_size = sum(f.stat().st_size for f in dist_dir.rglob('*') if f.is_file())
            print_info(f"构建产物大小: {total_size / (1024*1024):.1f} MB")
        return True
    else:
        print_error("前端构建失败")
        print(result.stderr[-1000:])  # 打印最后1000字符
        return False

# ══════════════════════════════════════════════
# 步骤 4: PyInstaller 冻结后端
# ══════════════════════════════════════════════
def build_frozen_backend(skip: bool) -> bool:
    """生成 Tauri 随包分发的冻结后端，详见 scripts/build_backend_pyinstaller.py。"""
    print_step(4, "PyInstaller 冻结后端")

    exe_path = frozen_backend_exe_path()
    if skip:
        if not exe_path.is_file():
            print_error(
                f"已跳过冻结构建，但未找到 {exe_path}，请去掉 --skip-frozen-backend 后重试")
            return False
        print_success(f"已跳过冻结后端重建（使用现有 {exe_path}）")
        _warn_if_bundle_exceeds_nsis_limits()
        return True

    if not BUILD_BACKEND_SCRIPT.is_file():
        print_error(f"缺少 {BUILD_BACKEND_SCRIPT}")
        return False

    result = subprocess.run(
        [sys.executable, str(BUILD_BACKEND_SCRIPT)],
        cwd=str(PROJ_ROOT),
    )
    if result.returncode != 0:
        print_error("冻结后端构建失败")
        return False

    exe_path = frozen_backend_exe_path()
    if not exe_path.is_file():
        print_error(f"未生成 {exe_path}")
        return False

    print_success(f"冻结后端已就绪: {exe_path}")
    _warn_if_bundle_exceeds_nsis_limits()
    return True

# ══════════════════════════════════════════════
# 步骤 5: 构建 Tauri 应用
# ══════════════════════════════════════════════
def build_tauri():
    """构建 Tauri 应用"""
    print_step(5, "构建 Tauri 应用")

    # 使用 cargo tauri build 构建
    result = subprocess.run(
        ["cargo", "tauri", "build"],
        capture_output=False,  # 实时输出
        text=True,
        shell=True,
        cwd=str(FRONTEND_DIR),
    )

    if result.returncode == 0:
        print_success("Tauri 应用构建完成")
        return True
    else:
        print_error("Tauri 应用构建失败")
        return False

# ══════════════════════════════════════════════
# 步骤 6: 验证输出
# ══════════════════════════════════════════════
def verify_output():
    """验证构建输出"""
    print_step(6, "验证构建输出")

    bundle_dir = TAURI_DIR / "target" / "release" / "bundle"
    # 查找安装包
    nsis_dir = bundle_dir / "nsis"
    msi_dir = bundle_dir / "msi"
    dmg_dir = bundle_dir / "dmg"
    installer_found = False

    if nsis_dir.exists():
        installers = list(nsis_dir.glob("*.exe"))
        if installers:
            installer = max(installers, key=lambda p: p.stat().st_mtime)
            size_mb = installer.stat().st_size / (1024 * 1024)
            print_success(f"NSIS 安装包: {installer.name}")
            print_info(f"路径: {installer}")
            print_info(f"大小: {size_mb:.1f} MB")
            installer_found = True

    if msi_dir.exists():
        installers = list(msi_dir.glob("*.msi"))
        if installers:
            installer = max(installers, key=lambda p: p.stat().st_mtime)
            size_mb = installer.stat().st_size / (1024 * 1024)
            print_success(f"MSI 安装包: {installer.name}")
            print_info(f"路径: {installer}")
            print_info(f"大小: {size_mb:.1f} MB")
            installer_found = True

    if dmg_dir.exists():
        installers = list(dmg_dir.glob("*.dmg"))
        if installers:
            installer = max(installers, key=lambda p: p.stat().st_mtime)
            size_mb = installer.stat().st_size / (1024 * 1024)
            print_success(f"DMG: {installer.name}")
            print_info(f"路径: {installer}")
            print_info(f"大小: {size_mb:.1f} MB")
            installer_found = True

    if not installer_found:
        print_error("未找到安装包（NSIS / MSI / DMG）")
        return False

    return True

# ══════════════════════════════════════════════
# 清理
# ══════════════════════════════════════════════
def set_release_version(version: str) -> None:
    """更新唯一 VERSION 源，再由同步脚本更新所有运行时清单。"""
    version_file = PROJ_ROOT / "VERSION"
    sync_script = PROJ_ROOT / "scripts" / "sync_release_version.py"
    version_file.write_text(f"{version.strip()}\n", encoding="utf-8", newline="\n")
    result = subprocess.run([sys.executable, str(sync_script)], cwd=PROJ_ROOT)
    if result.returncode != 0:
        print_error("版本号同步失败")
        sys.exit(result.returncode)
    print_success(f"发布版本已同步为 {version}")


def clean_build():
    """清理构建产物"""
    print_header("清理构建产物")

    # 不删除 node_modules：Windows 上原生 .node 常被编辑器/防病毒占用，rmtree 易失败；
    # 全量重建依赖 dist / target / PyInstaller 工作目录与冻结后端即可。
    dirs_to_clean = [
        FRONTEND_DIR / "dist",
        TAURI_DIR / "target",
        PYINSTALLER_WORK,
    ]

    for d in dirs_to_clean:
        if d.exists():
            shutil.rmtree(d)
            print_success(f"删除: {d}")

    if FROZEN_BUNDLE_DIR.exists():
        for child in FROZEN_BUNDLE_DIR.iterdir():
            if child.name == ".gitkeep":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        print_success(f"已清空（保留 .gitkeep）: {FROZEN_BUNDLE_DIR}")

    print_success("清理完成")

# ══════════════════════════════════════════════
# 主函数
# ══════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="PlotPilot 安装包构建脚本")
    parser.add_argument("--clean", action="store_true", help="清理后构建")
    parser.add_argument("--dev", action="store_true", help="开发模式（不构建安装包）")
    parser.add_argument("--skip-checks", action="store_true", help="跳过环境检查")
    parser.add_argument("--skip-frozen-backend",
        action="store_true",
        help="不重建 PyInstaller 后端（需已存在当前平台下的冻结可执行文件）",
    )
    parser.add_argument("--version", "-V",
        metavar="X.Y.Z",
        help="指定应用版本号，会同步 VERSION 及所有运行时清单",
    )
    args = parser.parse_args()

    if args.clean:
        clean_build()

    # 若指定了版本号，在构建前同步所有运行时清单。
    if args.version:
        set_release_version(args.version)

    print_header("PlotPilot 安装包构建")
    print_info("冻结后端: out/tauri/plotpilot-backend/（见 docs/BUILD_INSTALLER.md）")
    print()

    # 步骤 1: 环境检查
    if not args.skip_checks:
        if not check_environment():
            sys.exit(1)
    else:
        print_step(1, "跳过环境检查")

    # 步骤 2: 安装前端依赖
    if not install_frontend_deps():
        sys.exit(1)

    # 步骤 3: 构建前端
    if not build_frontend():
        sys.exit(1)

    # 步骤 4: PyInstaller 冻结后端
    if not build_frozen_backend(skip=args.skip_frozen_backend):
        sys.exit(1)

    if args.dev:
        print_header("开发模式构建完成")
        print_info("前端构建产物: frontend/dist/")
        print_info("使用 'npm run tauri dev' 启动开发服务器")
        return

    # 步骤 5: 构建 Tauri 应用
    if not build_tauri():
        sys.exit(1)

    # 步骤 6: 验证输出
    if not verify_output():
        sys.exit(1)

    # 完成
    print_header("构建成功")
    print_info("安装包目录:")
    print(f"  {TAURI_DIR / 'target' / 'release' / 'bundle'}")


if __name__ == "__main__":
    main()
