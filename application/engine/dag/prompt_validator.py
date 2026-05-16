"""Prompt 模板安全校验器 -- 防止注入攻击"""
from __future__ import annotations

import re
from typing import List, Set

from application.engine.dag.validator import ValidationResult


class PromptTemplateValidator:
    """Prompt 模板安全校验器"""

    DANGEROUS_PATTERNS = [
        r"ignore\s+(previous|above|all)\s+instructions",
        r"system\s*:\s*you\s+are\s+now",
        r"<\|im_start\|>",
        r"\[INST\].*\[\/INST\]",
        r"```python.*exec\s*\(",
    ]

    ALLOWED_VARIABLES: dict = {
        "ctx_blueprint": {"world_rules", "taboos", "atmosphere"},
        "ctx_foreshadow": {"novel_id", "chapter_number"},
        "ctx_voice": {"novel_id", "chapter_number"},
        "ctx_memory": {"novel_id", "chapter_number"},
        "ctx_debt": {"novel_id"},
        "exec_planning": {"novel_id", "target_chapters"},
        "exec_writer": {"context", "outline", "voice_block", "beats", "foreshadowing_block", "debt_due_block"},
        "exec_beat": {"outline"},
        "exec_scene": {"content", "outline"},
        "val_style": {"voice_fingerprint", "scene_type", "drift_threshold", "content"},
        "val_tension": {"content"},
        "val_anti_ai": {"content"},
        "val_foreshadow": {"novel_id", "content"},
        "val_narrative": {"content"},
        "val_kg_infer": {"novel_id", "chapter_number"},
        "gw_condition": {"input"},
        "gw_retry": {"input", "max_attempts", "content"},
    }

    MAX_TEMPLATE_LENGTH = 10000

    def validate(self, node_type: str, template: str) -> ValidationResult:
        errors: List[str] = []

        # 1. 危险模式检测
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, template, re.IGNORECASE):
                errors.append(f"检测到潜在 Prompt 注入模式: {pattern}")

        # 2. 变量白名单校验
        allowed = self.ALLOWED_VARIABLES.get(node_type, set())
        variables = re.findall(r'\{\{(\w+)\}\}', template)
        for var in variables:
            if var not in allowed and not var.startswith("custom_"):
                errors.append(f"变量 '{{{{{var}}}}}' 不在节点 {node_type} 的白名单中")

        # 3. 长度限制
        if len(template) > self.MAX_TEMPLATE_LENGTH:
            errors.append(f"Prompt 模板过长: {len(template)} 字符（上限 {self.MAX_TEMPLATE_LENGTH}）")

        # 4. 编码安全
        try:
            template.encode("utf-8").decode("utf-8")
        except UnicodeError:
            errors.append("Prompt 模板包含非法编码字符")

        return ValidationResult(errors=errors, warnings=[], is_valid=len(errors) == 0)
