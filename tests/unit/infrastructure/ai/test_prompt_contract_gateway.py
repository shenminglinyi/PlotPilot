"""AI 能力契约与 prompt_packages 一致性测试。"""
from __future__ import annotations

from pathlib import Path

import pytest

from infrastructure.ai.prompt_contract import PromptContract
from infrastructure.ai.prompt_contracts.chapter_summarizer import CHAPTER_SUMMARIZER_CONTRACT
from infrastructure.ai.prompt_contracts.continuous_planning import PLANNING_ACT_CONTRACT
from infrastructure.ai.prompt_contracts.memory_extraction import MEMORY_EXTRACTION_CONTRACT
from infrastructure.ai.prompt_contracts.tension_analysis_diagnosis import (
    TENSION_ANALYSIS_DIAGNOSIS_CONTRACT,
)
from infrastructure.ai.prompt_gateway import (
    PromptGateway,
    PromptGatewayPackageMissingError,
    PromptGatewayRenderResult,
    PromptGatewayValidationError,
)
from domain.ai.value_objects.prompt import Prompt
from infrastructure.ai.prompt_keys import ALL_KEYS
from infrastructure.ai.prompt_seed.loader import NODES_DIR, load_node_dir, load_seed_bundle
from infrastructure.ai.prompt_template_engine import get_template_engine
from infrastructure.ai.variable_registry import VariableRegistry


def test_prompt_template_engine_renders_variables_inside_output_json_shape():
    """输出 JSON 结构里的 escaped braces 不能阻断内部变量渲染。"""
    engine = get_template_engine()

    rendered = engine.render(
        system_template="系统：{premise}",
        user_template='''请输出 JSON：\n{{\n  "worldbuilding": {{\n{fields_desc}\n  }}\n}}''',
        variables={
            "premise": "重生高武世界",
            "fields_desc": '    "core_rules": {\n      "power_system": "武道体系"\n    }',
        },
    )

    assert rendered.system == "系统：重生高武世界"
    assert '"worldbuilding": {' in rendered.user
    assert '"core_rules": {' in rendered.user
    assert "{{" not in rendered.user
    assert "{fields_desc}" not in rendered.user
    assert rendered.missing_variables == []


def test_all_registered_prompt_keys_have_builtin_package():
    """prompt_keys 注册的静态 key 必须存在对应内置包。"""
    _, prompts = load_seed_bundle()
    package_ids = {p.get("id") for p in prompts}
    assert ALL_KEYS - package_ids == set()


def test_prompt_package_variables_cover_template_usage():
    """模板中使用的变量必须在 package.yaml 中声明。"""
    engine = get_template_engine()
    problems: list[tuple[str, set[str]]] = []

    for node_dir in sorted(NODES_DIR.iterdir(), key=lambda p: p.name):
        if not (node_dir / "package.yaml").is_file():
            continue
        record = load_node_dir(node_dir)
        declared = {
            var.get("name")
            for var in record.get("variables") or []
            if isinstance(var, dict)
        }
        used = engine.extract_variables(
            f"{record.get('system') or ''}\n{record.get('user_template') or ''}"
        )
        missing = used - declared
        if missing:
            problems.append((record.get("id", node_dir.name), missing))

    assert problems == []


def test_bible_worldbuilding_package_exposes_split_fields():
    engine = get_template_engine()
    record = load_node_dir(NODES_DIR / "bible-worldbuilding")
    declared = {var.get("name") for var in record.get("variables") or [] if isinstance(var, dict)}
    used = engine.extract_variables(f"{record.get('system') or ''}\n{record.get('user_template') or ''}")

    assert {"premise", "novel_title", "fields_desc", "genre_opening_profile"} <= declared
    assert {"premise", "novel_title", "fields_desc", "genre_opening_profile"} <= used
    assert {"worldbuilding_full", "novel_setup", "core_rules", "geography", "society", "culture", "daily_life"}.isdisjoint(declared)
    assert {"worldbuilding_full", "novel_setup", "core_rules", "geography", "society", "culture", "daily_life"}.isdisjoint(used)


def test_prompt_gateway_fast_fails_when_registry_misses(monkeypatch):
    """Registry 未命中时，Gateway 必须阻断，不能读取本地 package 降级。"""
    gateway = PromptGateway(packages_root=NODES_DIR)
    monkeypatch.setattr(gateway, "_render_from_registry", lambda contract, variables: None)

    with pytest.raises(PromptGatewayPackageMissingError):
        gateway.render(
            MEMORY_EXTRACTION_CONTRACT,
            {
                "chapter_content": "主角推开门，第一次看见密室里的旧照片。",
                "chapter_number": 1,
                "outline": "主角发现密室",
            },
        )


def test_prompt_gateway_fast_fails_when_required_variable_missing(monkeypatch):
    gateway = PromptGateway(packages_root=NODES_DIR)
    monkeypatch.setattr(gateway, "_render_from_registry", lambda contract, variables: None)

    with pytest.raises(PromptGatewayValidationError):
        gateway.render(MEMORY_EXTRACTION_CONTRACT, {"chapter_number": 1})


def test_prompt_gateway_missing_package_fails_explicitly(monkeypatch, tmp_path):
    """CPMS 节点缺失时必须明确失败，不能静默硬编码回退。"""
    gateway = PromptGateway(packages_root=tmp_path)
    monkeypatch.setattr(gateway, "_render_from_registry", lambda contract, variables: None)

    with pytest.raises(PromptGatewayPackageMissingError):
        gateway.render(PromptContract(node_key="missing-node"), {})


def test_prompt_gateway_output_schema_validation_is_observable():
    gateway = PromptGateway(packages_root=NODES_DIR)

    with pytest.raises(PromptGatewayValidationError):
        gateway.validate_output(
            TENSION_ANALYSIS_DIAGNOSIS_CONTRACT,
            {
                "diagnosis": "缺少 tension_level 等必填字段",
                "missing_elements": [],
                "suggestions": [],
            },
        )


def test_gateway_migrated_runtime_files_do_not_reintroduce_large_prompt_literals():
    """已迁移链路不允许再写回大段运行时 prompt 字符串。"""
    files = [
        "application/engine/services/memory_engine.py",
        "application/analyst/services/llm_voice_analysis_service.py",
        "infrastructure/ai/claude_chapter_summarizer.py",
        "application/analyst/services/tension_analyzer.py",
        "application/blueprint/services/continuous_planning_service.py",
    ]
    suspicious_terms = [
        "_FALLBACK_",
        "system_prompt =",
        "user_prompt =",
        "You are ",
        "Please summarize",
        "system_msg =",
        "user_msg =",
        "get_system(",
    ]
    hits = []
    for file in files:
        text = Path(file).read_text(encoding="utf-8")
        for term in suspicious_terms:
            if term in text:
                hits.append((file, term))

    assert hits == []


def test_chapter_summarizer_package_is_chinese():
    """摘要生产链路不再保留英文提示词。"""
    package_dir = NODES_DIR / CHAPTER_SUMMARIZER_CONTRACT.node_key
    text = "\n".join(
        (package_dir / name).read_text(encoding="utf-8")
        for name in ("system.md", "user.md")
    )
    assert "You are" not in text
    assert "Please summarize" not in text
    assert "章节摘要" in (package_dir / "package.yaml").read_text(encoding="utf-8")


def test_planning_act_contract_requires_published_cpms_node(monkeypatch):
    """连续规划的幕级规划链路必须先发布 CPMS 节点，不能从 package 运行时降级。"""
    gateway = PromptGateway(packages_root=NODES_DIR)
    monkeypatch.setattr(gateway, "_render_from_registry", lambda contract, variables: None)

    with pytest.raises(PromptGatewayPackageMissingError):
        gateway.render(
            PLANNING_ACT_CONTRACT,
            {
                "context": "幕信息：《试炼开场》",
                "chapter_count": 3,
            },
        )


def test_prompt_gateway_records_variable_sources(monkeypatch):
    gateway = PromptGateway(packages_root=NODES_DIR)

    captured: list[dict] = []

    class _Recorder:
        def record_span(self, **kwargs):
            captured.append(kwargs)
            return None

    registry = VariableRegistry()
    registry._loaded = True
    registry._schemas = {}

    class _Schema:
        source = "prompt:memory-extraction"
        required = True
        scope = type("_Scope", (), {"value": "chapter"})()
        type = type("_Type", (), {"value": "string"})()

    monkeypatch.setattr("infrastructure.ai.prompt_gateway.get_trace_recorder", lambda: _Recorder())
    monkeypatch.setattr("infrastructure.ai.prompt_gateway.get_variable_registry", lambda: registry)
    monkeypatch.setattr(
        registry,
        "get_schemas_for_node",
        lambda node_key: {"outline": _Schema(), "chapter_number": _Schema()},
    )
    monkeypatch.setattr(
        gateway,
        "_render_from_registry",
        lambda contract, variables: PromptGatewayRenderResult(
            prompt=Prompt(system="系统提示词", user="用户提示词"),
            node_key=contract.node_key,
            contract_version=contract.version,
            source="registry",
            variables=variables,
        ),
    )

    gateway.render(
        MEMORY_EXTRACTION_CONTRACT,
        {
            "chapter_content": "正文全文",
            "chapter_number": 1,
            "outline": "主角发现密室",
        },
    )

    variable_spans = [item for item in captured if item.get("phase") == "variables_validated"]
    assert variable_spans
    sources = variable_spans[0]["variable_sources"]
    assert any(item["name"] == "outline" and item["source"] == "prompt:memory-extraction" for item in sources)
    assert any(item["name"] == "chapter_content" and item["source"] == "runtime" for item in sources)
    assert variable_spans[0]["variables_full"]["chapter_content"] == "正文全文"
