"""静默回退守护检查（路线图 docs/FALLBACK_CLEANUP_ROADMAP.md 4.4）。

原则：迁移接口时保留旧代码、默认新接口，但**禁止**在新路径失败后回退旧路径。
本脚本用 AST 静态扫描防止违规模式重新出现：

  规则 A（禁止符号）: `_fallback_to_chat_cache` 类"运行时协议切换缓存"不得再次出现。
  规则 B（异常回退）: except 块内不得调用 `*_legacy_* / legacy_* / run_legacy_* /
                      confirm_macro_plan(旧版全量覆盖)`。

豁免方式：在违规调用所在行（或其 except 行）行尾/上方加注释标记
`fallback-check: allow <原因>`。迁移工具与遥测降级用此方式显式豁免。

用法::

    python scripts/check_no_silent_fallback.py [paths ...]

默认扫描 application/ engine/ infrastructure/ interfaces/ domain/，退出码非 0 表示发现违规。
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

DEFAULT_PATHS = ["application", "engine", "infrastructure", "interfaces", "domain"]
EXCLUDED_DIR_PARTS = {"__pycache__", ".git", "node_modules", "tests"}

# 规则 A：禁止再次出现的符号名（运行时协议切换缓存等）
FORBIDDEN_NAMES = {
    "_fallback_to_chat_cache",
}

# 规则 B：except 块内禁止调用的函数名模式（旧接口回退）
LEGACY_CALL_PREFIXES = ("legacy_", "run_legacy_")
LEGACY_CALL_INFIXES = ("_legacy_",)
LEGACY_CALL_EXACT = {
    "confirm_macro_plan",  # 旧版全量覆盖写入；safe 版为 confirm_macro_plan_safe
}
ALLOW_MARKER = "fallback-check: allow"


def _iter_py_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_file() and p.suffix == ".py":
            files.append(p)
        elif p.is_dir():
            for f in p.rglob("*.py"):
                if not (set(f.parts) & EXCLUDED_DIR_PARTS):
                    files.append(f)
    return sorted(set(files))


def _line_has_allow_marker(source_lines: list[str], lineno: int) -> bool:
    """检查违规行及其上一行是否带豁免标记。"""
    for idx in (lineno - 1, lineno - 2):
        if 0 <= idx < len(source_lines) and ALLOW_MARKER in source_lines[idx]:
            return True
    return False


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def check_file(path: Path) -> list[str]:
    violations: list[str] = []
    source = path.read_text(encoding="utf-8-sig")
    source_lines = source.splitlines()

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        violations.append(f"{path}: 语法错误，跳过检查: {exc}")
        return violations

    for node in ast.walk(tree):
        # 规则 A：禁止单名出现（定义、赋值、引用均算）
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            if not _line_has_allow_marker(source_lines, node.lineno):
                violations.append(
                    f"{path}:{node.lineno}: 禁止的运行时协议切换缓存 '{node.id}' "
                    f"(规则A；如需豁免加注释 '{ALLOW_MARKER} 原因')"
                )
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_NAMES:
            if not _line_has_allow_marker(source_lines, node.lineno):
                violations.append(
                    f"{path}:{node.lineno}: 禁止的运行时协议切换缓存 '.{node.attr}' "
                    f"(规则A)"
                )

        # 规则 B：except 块内回退旧接口
        if isinstance(node, ast.ExceptHandler):
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    name = _call_name(child)
                    if name is None:
                        continue
                    is_legacy = (
                        name.startswith(LEGACY_CALL_PREFIXES)
                        or any(infix in name for infix in LEGACY_CALL_INFIXES)
                        or name in LEGACY_CALL_EXACT
                    )
                    if not is_legacy:
                        continue
                    if _line_has_allow_marker(source_lines, child.lineno) or _line_has_allow_marker(
                        source_lines, node.lineno
                    ):
                        continue
                    violations.append(
                        f"{path}:{child.lineno}: except 块内回退旧接口 '{name}' "
                        f"(规则B；确属迁移工具/遥测降级请加注释 '{ALLOW_MARKER} 原因')"
                    )

    return violations


def main(argv: list[str]) -> int:
    paths = argv[1:] or DEFAULT_PATHS
    files = _iter_py_files(paths)

    all_violations: list[str] = []
    for f in files:
        all_violations.extend(check_file(f))

    if all_violations:
        print(f"发现 {len(all_violations)} 处静默回退违规：")
        for v in all_violations:
            print(f"  - {v}")
        return 1

    print(f"OK: {len(files)} 个文件未发现静默回退模式。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
