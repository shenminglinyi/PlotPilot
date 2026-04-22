"""回归测试：_handle_act_planning 中 rec_chapters_per_act 的 UnboundLocalError。

在 commit b1327cb (feat(continuous-planning): implement structure calculation engine)
中，rec_chapters_per_act / rec_acts_per_volume 仅在 `if not target_act:` 分支内
定义；当 target_act 已存在（正常流程）时，后续
`chapter_budget = target_act.suggested_chapter_count or rec_chapters_per_act`
会抛 UnboundLocalError，导致守护进程在幕规划阶段连续失败被熔断。

本测试通过静态读取源码验证两个变量的定义出现在 `if not target_act:` 之外。
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from application.engine.services.autopilot_daemon import AutopilotDaemon


def _get_handle_act_planning_source() -> str:
    """取 _handle_act_planning 方法的源码文本。"""
    source = inspect.getsource(AutopilotDaemon._handle_act_planning)
    return source


def _parse_method_ast() -> ast.AsyncFunctionDef:
    """解析 autopilot_daemon.py 整个模块，返回 _handle_act_planning 的 AST。

    相比 inspect.getsource + dedent，直接读文件更稳（不受缩进困扰）。
    """
    from application.engine.services import autopilot_daemon
    source_path = Path(autopilot_daemon.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    for cls in tree.body:
        if isinstance(cls, ast.ClassDef) and cls.name == "AutopilotDaemon":
            for item in cls.body:
                if isinstance(item, ast.AsyncFunctionDef) and item.name == "_handle_act_planning":
                    return item
    raise AssertionError("AutopilotDaemon._handle_act_planning not found")


def test_rec_chapters_per_act_defined_outside_if_branch() -> None:
    """rec_chapters_per_act 必须在 `if not target_act:` 分支之外赋值，
    否则当 target_act 已存在时访问该变量会抛 UnboundLocalError。
    """
    func_def = _parse_method_ast()

    # 找出所有顶层（不在 if 语句内）的赋值，收集 target 名称
    top_level_names: set[str] = set()
    for node in func_def.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    top_level_names.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            top_level_names.add(node.target.id)

    # 这两个变量必须在函数体的顶层赋值，不能只在 if 分支里
    assert "rec_chapters_per_act" in top_level_names, (
        "rec_chapters_per_act 必须在 `if not target_act:` 之外赋值，"
        "否则 target_act 已存在时会触发 UnboundLocalError。"
    )
    assert "rec_acts_per_volume" in top_level_names, (
        "rec_acts_per_volume 必须在 `if not target_act:` 之外赋值。"
    )
