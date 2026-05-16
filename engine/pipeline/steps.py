"""Step Result — 单步骤的执行结果

每个 _step_xxx() 返回 StepResult，管线根据它决定是否继续。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class StepResult:
    """单步骤执行结果

    - passed=True  → 继续管线
    - passed=False → 短路：停止管线（但已完成步骤的副作用不回滚）
    - skip=True    → 跳过当前步骤，继续管线
    """
    passed: bool = True
    skip: bool = False
    message: str = ""
    score: Optional[float] = None
    violations: List[Dict[str, Any]] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def ok(message: str = "") -> "StepResult":
        return StepResult(passed=True, message=message)

    @staticmethod
    def fail(message: str, score: float = 0.0,
             violations: List[Dict[str, Any]] = None) -> "StepResult":
        return StepResult(
            passed=False, message=message, score=score,
            violations=violations or [],
        )

    @staticmethod
    def skip_step(reason: str = "") -> "StepResult":
        return StepResult(skip=True, message=reason)
