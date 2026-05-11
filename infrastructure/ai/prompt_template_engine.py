"""PromptTemplateEngine — CPMS 模板渲染引擎。

核心设计：
- 统一使用 Jinja2 作为模板引擎（替代原有的 format_map）
- 兼容旧版 {variable} 格式（自动转换为 Jinja2 的 {{ variable }} 语法）
- 支持条件渲染 {% if ... %}、循环 {% for ... %}、过滤器等高级特性
- 安全渲染：未定义变量不抛异常，保留原始占位符
- 沙盒模式：渲染前可做 Schema 校验（mock render）

Architecture:
  PromptTemplateEngine
    ├─ render()        — 正式渲染（生产路径）
    ├─ mock_render()   — 沙盒渲染（保存前校验，返回校验报告）
    ├─ validate()      — 变量 Schema 校验
    └─ extract_variables() — 从模板中提取变量列表
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ─── 兼容层：旧版 {variable} → Jinja2 {{ variable }} 自动转换 ───

# 匹配 {variable} 但排除 {{ variable }}（已转换的 Jinja2 语法）
# 以及 {%...%}（Jinja2 控制语句）和 {#...#}（Jinja2 注释）
_LEGACY_VAR_PATTERN = re.compile(
    r'(?<!\{)\{(?!\{)(?!\s*[%#])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}(?!\})'
)


def _legacy_to_jinja2(template: str) -> str:
    """将旧版 {variable} 格式转换为 Jinja2 {{ variable }} 格式。

    保留已有的 Jinja2 语法（{{ }}, {% %}, {# #}）不变。
    """
    if not template:
        return template
    return _LEGACY_VAR_PATTERN.sub(r'{{ \1 }}', template)


# ─── JSON 示例块转义 ───

# 匹配模板中作为 JSON 输出示例的 {{ }} 块（包含冒号或方括号的非变量引用）
# 例如：{{\"key\": \"value\"}} 或 {{\"items\": [...]}}
_JSON_BLOCK_PATTERN = re.compile(
    r'\{\{'                        # 开头 {{
    r'(?!\s*[a-zA-Z_])'           # 排除 Jinja2 变量 {{ var_name }}
    r'[^}]'                       # 第一个字符不是 }
    r'(?:[^}]|}(?!}))'            # 非贪婪：匹配 } 但不是 }}
    r'*?'                          # 懒惰匹配
    r'\}\}'                        # 结尾 }}
)


def _escape_json_blocks(template: str) -> str:
    """将模板中的 JSON 示例块用 {% raw %}...{% endraw %} 包裹。

    模板中大量使用 {{ \"key\": \"value\" }} 作为 LLM 输出的 JSON 格式示例。
    这些 {{ }} 不是 Jinja2 变量引用，而是字面文本。
    用 {% raw %} 块包裹后，Jinja2 会原样输出，不做任何解析。

    识别逻辑：{{ }} 内部包含冒号(:) 或 方括号([)，且不以标识符开头。
    - {{ var_name }}        → 不匹配（Jinja2 变量）
    - {{ \"key\": \"val\" }} → 匹配（JSON 示例，包含冒号）
    - {{ \"items\": [1] }}   → 匹配（JSON 示例，包含方括号）
    """
    if not template:
        return template

    # 逐个查找并包裹，避免嵌套 raw 块
    result = template
    offset = 0
    while True:
        match = _JSON_BLOCK_PATTERN.search(result, offset)
        if not match:
            break

        start, end = match.start(), match.end()
        # 检查是否已经在 {% raw %} 块内（简单启发式：往前找最近的 raw/endraw）
        preceding = result[:start]
        raw_count = preceding.count('{% raw %}')
        endraw_count = preceding.count('{% endraw %}')
        if raw_count > endraw_count:
            # 已在 raw 块内，跳过
            offset = end
            continue

        # 用 {% raw %}...{% endraw %} 包裹
        replacement = '{% raw %}' + match.group(0) + '{% endraw %}'
        result = result[:start] + replacement + result[end:]
        # 更新偏移量（replacement 比原匹配更长）
        offset = start + len(replacement)

    return result


# ─── 变量 Schema 定义 ───


class VariableType(str, Enum):
    """变量类型枚举。"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    ENUM = "enum"
    OBJECT = "object"
    LIST = "list"


class VariableScope(str, Enum):
    """变量作用域。"""
    GLOBAL = "global"       # 全局常量（如小说标题）
    NOVEL = "novel"         # 小说级（如 Bible 数据）
    CHAPTER = "chapter"     # 章节级（如大纲、上下文）
    SCENE = "scene"         # 场景级（如 POV 角色、地点）
    BEAT = "beat"           # 节拍级（如节拍目标、字数）


@dataclass
class VariableSchema:
    """全局变量注册表中的单个变量定义。

    这是 CPMS 契约化设计的核心：每个变量都有强类型的 Schema，
    在渲染前必须通过校验，防止因变量名拼写错误或类型不匹配导致生成崩溃。
    """
    name: str                           # 如 "character_name"
    display_name: str = ""              # 如 "角色名称"
    type: VariableType = VariableType.STRING
    required: bool = False
    default: Any = None
    description: str = ""
    source: str = ""                    # 数据来源（如 "bible.character.name"）
    scope: VariableScope = VariableScope.CHAPTER
    enum_values: List[str] = field(default_factory=list)  # 当 type=ENUM 时
    examples: List[str] = field(default_factory=list)     # 示例值

    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.name

    def validate_value(self, value: Any) -> Tuple[bool, str]:
        """校验给定值是否符合此变量的 Schema。

        Returns:
            (is_valid, error_message)
        """
        if value is None or value == "":
            if self.required and (self.default is None or self.default == ""):
                return False, f"必填变量 '{self.name}' 缺失且无默认值"
            return True, ""

        type_checks = {
            VariableType.STRING: lambda v: isinstance(v, str),
            VariableType.INTEGER: lambda v: isinstance(v, int) and not isinstance(v, bool),
            VariableType.FLOAT: lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            VariableType.BOOLEAN: lambda v: isinstance(v, bool),
            VariableType.LIST: lambda v: isinstance(v, list),
            VariableType.OBJECT: lambda v: isinstance(v, dict),
            VariableType.ENUM: lambda v: isinstance(v, str) and v in self.enum_values,
        }

        checker = type_checks.get(self.type)
        if checker and not checker(value):
            expected = self.type.value
            if self.type == VariableType.ENUM:
                expected = f"enum({self.enum_values})"
            return False, f"变量 '{self.name}' 期望类型 {expected}，实际为 {type(value).__name__}"

        return True, ""


# ─── 渲染结果 ───


@dataclass
class RenderResult:
    """渲染结果（含诊断信息）。"""
    system: str = ""
    user: str = ""
    success: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    missing_variables: List[str] = field(default_factory=list)
    rendered_variables: List[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    """Schema 校验结果。"""
    is_valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    missing_required: List[str] = field(default_factory=list)
    type_mismatches: List[str] = field(default_factory=list)


# ─── 核心引擎 ───


class PromptTemplateEngine:
    """CPMS 模板渲染引擎。

    职责：
    1. 将旧版 {variable} 模板自动转换为 Jinja2 {{ variable }}
    2. 安全渲染：未定义变量保留为 {{ name }} 而非抛异常
    3. 变量 Schema 校验：渲染前检查必填项和类型
    4. 沙盒渲染：保存前预检，返回校验报告
    5. 变量提取：从模板中提取所有变量名
    """

    def __init__(self, use_jinja2: bool = True):
        """
        Args:
            use_jinja2: 是否启用 Jinja2 引擎（默认 True）。
                       设为 False 则回退到 format_map（兼容模式）。
        """
        self._use_jinja2 = use_jinja2
        self._jinja2_env = None

        if use_jinja2:
            try:
                from jinja2 import BaseLoader, Environment, StrictUndefined, Undefined
                # 使用宽容的 Undefined：未定义变量不抛异常，保留原始文本
                class SafeUndefined(Undefined):
                    """未定义变量时返回 {{ name }} 形式而非抛异常。"""
                    def __str__(self):
                        return f"{{{{ {self._undefined_name} }}}}"

                    def __repr__(self):
                        return f"{{{{ {self._undefined_name} }}}}"

                    def __bool__(self):
                        return False

                self._jinja2_env = Environment(
                    loader=BaseLoader(),
                    undefined=SafeUndefined,
                    keep_trailing_newline=True,
                    trim_blocks=False,
                    lstrip_blocks=False,
                )
                # 注册自定义过滤器
                self._jinja2_env.filters["default_if_empty"] = (
                    lambda v, d="": d if v is None or v == "" else v
                )
            except ImportError:
                logger.warning(
                    "Jinja2 未安装，回退到 format_map 渲染模式。"
                    "建议执行: pip install jinja2"
                )
                self._use_jinja2 = False

    def render(
        self,
        system_template: str,
        user_template: str,
        variables: Dict[str, Any],
        variable_schemas: Optional[Dict[str, VariableSchema]] = None,
    ) -> RenderResult:
        """渲染提示词模板。

        Args:
            system_template: system prompt 模板
            user_template: user prompt 模板
            variables: 变量字典
            variable_schemas: 可选的变量 Schema 字典（用于校验）

        Returns:
            RenderResult 包含渲染结果和诊断信息
        """
        result = RenderResult()

        # Schema 校验（如果提供了 schemas）
        if variable_schemas:
            validation = self.validate(variables, variable_schemas)
            if not validation.is_valid:
                result.errors.extend(validation.errors)
                result.success = False
            result.warnings.extend(validation.warnings)
            result.missing_required.extend(validation.missing_required)

        # 渲染 system
        system_rendered, sys_missing, sys_rendered = self._render_template(
            system_template, variables
        )
        result.system = system_rendered
        result.missing_variables.extend(sys_missing)
        result.rendered_variables.extend(sys_rendered)

        # 渲染 user
        user_rendered, usr_missing, usr_rendered = self._render_template(
            user_template, variables
        )
        result.user = user_rendered
        result.missing_variables.extend(usr_missing)
        result.rendered_variables.extend(usr_rendered)

        # 去重
        result.missing_variables = list(dict.fromkeys(result.missing_variables))
        result.rendered_variables = list(dict.fromkeys(result.rendered_variables))

        if result.missing_variables and not result.errors:
            result.warnings.append(
                f"以下变量未提供值，保留为占位符：{', '.join(result.missing_variables)}"
            )

        return result

    def mock_render(
        self,
        system_template: str,
        user_template: str,
        variable_schemas: Optional[Dict[str, VariableSchema]] = None,
    ) -> RenderResult:
        """沙盒渲染：用 Schema 默认值或 mock 值进行预检。

        用于提示词广场的"保存前校验"，确保模板语法正确且变量都能匹配。

        Args:
            system_template: system prompt 模板
            user_template: user prompt 模板
            variable_schemas: 变量 Schema 字典

        Returns:
            RenderResult 包含校验报告
        """
        # 从 Schema 生成 mock 变量
        mock_vars: Dict[str, Any] = {}
        if variable_schemas:
            for name, schema in variable_schemas.items():
                if schema.default is not None:
                    mock_vars[name] = schema.default
                elif schema.type == VariableType.STRING:
                    mock_vars[name] = f"[{schema.display_name}]"
                elif schema.type == VariableType.INTEGER:
                    mock_vars[name] = 0
                elif schema.type == VariableType.FLOAT:
                    mock_vars[name] = 0.0
                elif schema.type == VariableType.BOOLEAN:
                    mock_vars[name] = False
                elif schema.type == VariableType.ENUM and schema.enum_values:
                    mock_vars[name] = schema.enum_values[0]
                elif schema.type == VariableType.LIST:
                    mock_vars[name] = []
                elif schema.type == VariableType.OBJECT:
                    mock_vars[name] = {}
                else:
                    mock_vars[name] = f"[{name}]"

        result = self.render(system_template, user_template, mock_vars, variable_schemas)

        # 提取模板中声明的变量，检查是否都在 Schema 中
        declared_system = self.extract_variables(system_template)
        declared_user = self.extract_variables(user_template)
        all_declared = declared_system | declared_user

        if variable_schemas:
            unregistered = all_declared - set(variable_schemas.keys())
            if unregistered:
                result.warnings.append(
                    f"以下变量在模板中使用但未在 Schema 中注册：{', '.join(sorted(unregistered))}"
                )

        return result

    def validate(
        self,
        variables: Dict[str, Any],
        variable_schemas: Dict[str, VariableSchema],
    ) -> ValidationResult:
        """校验变量值是否符合 Schema 定义。

        Args:
            variables: 实际提供的变量字典
            variable_schemas: 变量 Schema 字典

        Returns:
            ValidationResult 包含校验结果和错误信息
        """
        result = ValidationResult()

        for name, schema in variable_schemas.items():
            value = variables.get(name)
            is_valid, error_msg = schema.validate_value(value)
            if not is_valid:
                result.is_valid = False
                result.errors.append(error_msg)
                if "缺失" in error_msg:
                    result.missing_required.append(name)
                else:
                    result.type_mismatches.append(error_msg)

        return result

    def extract_variables(self, template: str) -> Set[str]:
        """从模板中提取所有变量名。

        支持旧版 {variable} 和 Jinja2 {{ variable }} 两种格式。

        Returns:
            变量名集合
        """
        if not template:
            return set()

        variables = set()

        # 提取 Jinja2 {{ variable }} 格式
        jinja2_pattern = re.compile(r'\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}')
        variables.update(jinja2_pattern.findall(template))

        # 提取旧版 {variable} 格式（排除已匹配的 Jinja2）
        legacy_matches = _LEGACY_VAR_PATTERN.findall(template)
        variables.update(legacy_matches)

        return variables

    # ─── 内部方法 ───

    def _render_template(
        self,
        template: str,
        variables: Dict[str, Any],
    ) -> Tuple[str, List[str], List[str]]:
        """渲染单个模板。

        Returns:
            (rendered_text, missing_variables, rendered_variables)
        """
        if not template:
            return "", [], []

        missing = []
        rendered = []

        if self._use_jinja2 and self._jinja2_env is not None:
            # 转换旧版格式
            jinja2_template = _legacy_to_jinja2(template)

            # 🔥 预处理：用 {% raw %}...{% endraw %} 包裹 JSON 示例块
            # 模板中大量使用 {{ "key": "value" }} 作为 JSON 输出示例，
            # 这些不是 Jinja2 变量而是字面文本。用 {% raw %} 块包裹后
            # Jinja2 会原样输出，不做任何解析。
            safe_template = _escape_json_blocks(jinja2_template)

            try:
                tmpl = self._jinja2_env.from_string(safe_template)
                rendered_text = tmpl.render(**variables)

                # 检测哪些变量被渲染（不在输出中保留 {{ name }} 形式）
                all_vars = self.extract_variables(template)
                for var in all_vars:
                    if var in variables and variables[var] is not None:
                        rendered.append(var)
                    else:
                        # 检查输出中是否仍有 {{ var }} 占位符
                        if f"{{{{ {var} }}}}" in rendered_text:
                            missing.append(var)
                        else:
                            rendered.append(var)

            except Exception as exc:
                logger.error("Jinja2 渲染失败: %s，回退到 format_map", exc)
                rendered_text = self._fallback_render(template, variables)
        else:
            rendered_text = self._fallback_render(template, variables)

        return rendered_text, missing, rendered

    @staticmethod
    def _fallback_render(template: str, variables: Dict[str, Any]) -> str:
        """回退渲染：使用 format_map（兼容模式）。"""
        if not template:
            return ""

        class SafeDict(dict):
            def __missing__(self, key: str) -> str:
                return "{" + key + "}"

        try:
            return template.format_map(SafeDict(variables))
        except (KeyError, ValueError, IndexError):
            return template


# ─── 全局单例 ───

_engine_instance: Optional[PromptTemplateEngine] = None


def get_template_engine() -> PromptTemplateEngine:
    """获取全局 PromptTemplateEngine 单例。"""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = PromptTemplateEngine()
    return _engine_instance
