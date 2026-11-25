# -*- coding: utf-8 -*-
"""
将 FastAPI 后端打成 PyInstaller onedir，供 Tauri 拉起。

Windows 产物: plotpilot-backend.exe
macOS / Linux 产物: plotpilot-backend（无后缀）

前置：在专用 venv 中安装依赖（文档推荐 Python 3.12 + `.venv-nsis`）：
  pip install -r requirements-nsis.txt 与 pyinstaller。

用法:
  python scripts/build_backend_pyinstaller.py
  python scripts/build_backend_pyinstaller.py --force

产物:
  out/tauri/plotpilot-backend/<可执行文件名>
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJ_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = PROJ_ROOT / "scripts" / "tauri_backend_launcher.py"
SELF_SCRIPT = Path(__file__).resolve()
REQ_NSIS = PROJ_ROOT / "requirements-nsis.txt"
DIST_ROOT = PROJ_ROOT / "out" / "tauri"
BUNDLE_DIR = DIST_ROOT / "plotpilot-backend"
WORKPATH = PROJ_ROOT / "build" / "pyinstaller-backend"
STAMP_PATH = BUNDLE_DIR / ".freeze_stamp"
EXE_NAME = "plotpilot-backend"


def frozen_binary_filename() -> str:
    """PyInstaller onedir 内主程序名：Windows 为 .exe，类 Unix 无后缀。"""
    return f"{EXE_NAME}.exe" if os.name == "nt" else EXE_NAME


EXE_PATH = BUNDLE_DIR / frozen_binary_filename()

PROMPTS_SRC = PROJ_ROOT / "infrastructure" / "ai" / "prompts"
PROMPT_PACKAGES_SRC = PROJ_ROOT / "infrastructure" / "ai" / "prompt_packages"
TAXONOMY_SRC = PROJ_ROOT / "shared" / "taxonomy"
MIGRATIONS_DIR = (
    PROJ_ROOT / "infrastructure" / "persistence" / "database" / "migrations"
)
SCHEMA_SQL = PROJ_ROOT / "infrastructure" / "persistence" / "database" / "schema.sql"

# 与运行时强相关的第三方包，交给 PyInstaller 整包收集子模块
COLLECT_ALL = [
    "uvicorn", "fastapi", "starlette", "pydantic", "httpx", "anyio",
    "openai", "anthropic", "dotenv", "jinja2", "json_repair", "volcengine",
    "watchfiles", "websockets", "httptools", "h11", "email_validator",
    "sniffio", "pydantic_core",
]

# 本地向量 / ML 生态属于可选扩展，不能被桌面安装包默认打入。
# 这些包通常来自开发机环境中的 requirements-local.txt 或实验依赖；
# 运行时会按懒加载逻辑降级禁用本地向量能力。
EXCLUDE_MODULES = [
    "chromadb",
    "faiss",
    "faiss_cpu",
    "llvmlite",
    "numba",
    "numpy",
    "onnx",
    "onnxruntime",
    "pandas",
    "qdrant_client",
    "scipy",
    "sentence_transformers",
    "sklearn",
    "sympy",
    "tokenizers",
    "torch",
    "torchaudio",
    "torchvision",
    "transformers",
]

EXCLUDED_BUNDLE_TOP_LEVELS = {
    "chromadb",
    "faiss",
    "faiss_cpu.libs",
    "numpy",
    "numpy.libs",
    "onnx",
    "onnxruntime",
    "pandas",
    "qdrant_client",
    "scipy",
    "scipy.libs",
    "sentence_transformers",
    "sklearn",
    "tokenizers",
    "torch",
    "torchaudio",
    "torchvision",
    "transformers",
}

FINGERPRINT_SOURCE_DIRS = [
    PROJ_ROOT / "interfaces",
    PROJ_ROOT / "application",
    PROJ_ROOT / "domain",
    PROJ_ROOT / "infrastructure",
    TAXONOMY_SRC,
]

FINGERPRINT_SUFFIXES = {
    ".py",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".txt",
    ".md",
    ".sql",
    ".j2",
    ".jinja",
    ".jinja2",
}

FINGERPRINT_SKIP_PARTS = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}


def _update_tree_fingerprint(h: "hashlib._Hash", root: Path) -> None:
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in FINGERPRINT_SKIP_PARTS for part in path.parts):
            continue
        if path.suffix.lower() not in FINGERPRINT_SUFFIXES:
            continue
        rel = path.relative_to(PROJ_ROOT).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")


def _fingerprint() -> str:
    h = hashlib.sha256()
    h.update(LAUNCHER.read_bytes())
    h.update(SELF_SCRIPT.read_bytes())
    if REQ_NSIS.is_file():
        h.update(REQ_NSIS.read_bytes())
    for source_dir in FINGERPRINT_SOURCE_DIRS:
        _update_tree_fingerprint(h, source_dir)
    return h.hexdigest()


def _needs_build(force: bool) -> bool:
    if force:
        return True
    if not EXE_PATH.is_file():
        return True
    if not STAMP_PATH.is_file():
        return True
    try:
        return STAMP_PATH.read_text(encoding="utf-8").strip() != _fingerprint()
    except OSError:
        return True


def _try_kill_running_backend() -> None:
    """尽量结束仍占着输出目录的旧进程，避免覆盖失败（Windows 上尤为常见）。"""
    if os.name == "nt":
        r = subprocess.run(
            ["taskkill", "/F", "/IM", f"{EXE_NAME}.exe", "/T"],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            print("[freeze] 已结束正在运行的进程:", EXE_NAME + ".exe")
            time.sleep(0.6)
        return

    if sys.platform == "darwin":
        subprocess.run(
            ["pkill", "-f", EXE_NAME],
            capture_output=True,
            text=True,
        )
        time.sleep(0.3)


def _run_pyinstaller() -> None:
    if not LAUNCHER.is_file():
        raise FileNotFoundError(LAUNCHER)
    if not REQ_NSIS.is_file():
        raise FileNotFoundError(REQ_NSIS)

    DIST_ROOT.mkdir(parents=True, exist_ok=True)
    WORKPATH.mkdir(parents=True, exist_ok=True)

    tmp_parent = Path(tempfile.mkdtemp(prefix="pyi_", dir=str(DIST_ROOT)))

    cmd: list[str] = [
        sys.executable, "-m", "PyInstaller",
        "--name", EXE_NAME,
        "--onedir",
        # 无独立控制台：避免用户关掉黑窗时误杀后端；排错用 %APPDATA%\...\data\logs\plotpilot.log
        "--noconsole",
        "--noconfirm",
        "--clean",
        "--distpath", str(tmp_parent),
        "--workpath", str(WORKPATH),
        "--paths", str(PROJ_ROOT),
    ]

    for pkg in COLLECT_ALL:
        cmd.extend(["--collect-all", pkg])

    for pkg in ("interfaces", "application", "domain", "infrastructure"):
        cmd.extend(["--collect-submodules", pkg])

    for mod in EXCLUDE_MODULES:
        cmd.extend(["--exclude-module", mod])

    for mod in (
        "load_env",
        "scripts.start_daemon",
        "multipart",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
    ):
        cmd.extend(["--hidden-import", mod])

    sep = os.pathsep
    if PROMPTS_SRC.is_dir():
        cmd.extend(
            ["--add-data", f"{PROMPTS_SRC}{sep}infrastructure/ai/prompts"]
        )
    if PROMPT_PACKAGES_SRC.is_dir():
        cmd.extend(
            ["--add-data", f"{PROMPT_PACKAGES_SRC}{sep}infrastructure/ai/prompt_packages"]
        )
    if TAXONOMY_SRC.is_dir():
        cmd.extend(
            ["--add-data", f"{TAXONOMY_SRC}{sep}shared/taxonomy"]
        )

    if MIGRATIONS_DIR.is_dir():
        cmd.extend(
            ["--add-data",
                f"{MIGRATIONS_DIR}{sep}infrastructure/persistence/database/migrations",
            ]
        )
    if SCHEMA_SQL.is_file():
        cmd.extend(
            ["--add-data",
                f"{SCHEMA_SQL}{sep}infrastructure/persistence/database",
            ]
        )

    cmd.append(str(LAUNCHER))

    print("[pyinstaller] " + " ".join(cmd[:12]), "...", sep="")
    try:
        proc = subprocess.run(cmd, cwd=str(PROJ_ROOT))
        if proc.returncode != 0:
            raise SystemExit(proc.returncode)

        built_tree = tmp_parent / EXE_NAME
        built_exe = built_tree / frozen_binary_filename()
        if not built_exe.is_file():
            raise RuntimeError(f"PyInstaller 未生成 {built_exe}")

        shutil.rmtree(BUNDLE_DIR, ignore_errors=True)
        shutil.move(str(built_tree), str(BUNDLE_DIR))
    finally:
        shutil.rmtree(tmp_parent, ignore_errors=True)

    stray_spec = PROJ_ROOT / f"{EXE_NAME}.spec"
    if stray_spec.is_file():
        stray_spec.unlink(missing_ok=True)

    if not EXE_PATH.is_file():
        raise RuntimeError(f"未生成 {EXE_PATH}")

    _assert_optional_vector_modules_excluded()


def _assert_optional_vector_modules_excluded() -> None:
    """防止开发机里的本地向量依赖被误打进桌面安装包。"""
    internal = BUNDLE_DIR / "_internal"
    if not internal.is_dir():
        return
    leaked = []
    for child in internal.iterdir():
        name = child.name
        if name in EXCLUDED_BUNDLE_TOP_LEVELS:
            leaked.append(name)
            continue
        if any(
            name.startswith(f"{prefix}-")
            for prefix in (
                "chromadb",
                "faiss_cpu",
                "numpy",
                "onnxruntime",
                "pandas",
                "qdrant_client",
                "scipy",
                "sentence_transformers",
                "sklearn",
                "tokenizers",
                "torch",
                "transformers",
            )
        ):
            leaked.append(name)
    if leaked:
        raise RuntimeError(
            "PyInstaller 产物混入可选本地向量/ML 依赖，请使用干净环境或补充 exclude: "
            + ", ".join(sorted(leaked))
        )


def _restore_gitkeep() -> None:
    """PyInstaller COLLECT 会删掉整目录，重建占位以便 git / 空克隆场景一致。"""
    keep = BUNDLE_DIR / ".gitkeep"
    if not keep.exists():
        keep.write_text(
            "# 占位：使 Tauri 资源 glob 在首次克隆后仍能通过校验。\n"
            "# 发布前请运行: python scripts/build_backend_pyinstaller.py\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="PyInstaller 冻结 FastAPI 后端")
    parser.add_argument("--force",
        action="store_true",
        help="忽略指纹缓存，强制重打",
    )
    args = parser.parse_args()

    if not _needs_build(args.force):
        print(f"[freeze] Cache hit，跳过 PyInstaller（{EXE_PATH}）")
        return

    if args.force:
        _try_kill_running_backend()

    _run_pyinstaller()
    _restore_gitkeep()
    STAMP_PATH.write_text(_fingerprint() + "\n", encoding="utf-8")
    print(f"[freeze] 完成: {EXE_PATH}")


if __name__ == "__main__":
    main()
