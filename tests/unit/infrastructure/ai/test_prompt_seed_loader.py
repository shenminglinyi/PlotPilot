from __future__ import annotations

from infrastructure.ai.prompt_seed.loader import _minimal_yaml_load


def test_minimal_yaml_load_parses_bundle_meta_subset():
    data = _minimal_yaml_load(
        """
version: 5.3.6-variable-center-final
name: PlotPilot 内置
author: PlotPilot Team
engine: jinja2
changelog: 'v5.3.6: sync prompt package'
"""
    )

    assert data == {
        "version": "5.3.6-variable-center-final",
        "name": "PlotPilot 内置",
        "author": "PlotPilot Team",
        "engine": "jinja2",
        "changelog": "v5.3.6: sync prompt package",
    }


def test_minimal_yaml_load_parses_package_yaml_subset():
    data = _minimal_yaml_load(
        """
name: Plot outline planning
category: planning
builtin: true
tags:
- planning
- plot-outline
output_format: json
variables:
- name: novel.title
  desc: Novel title
  type: string
- name: novel.target_chapters
  desc: Target chapter count
  type: integer
id: planning-plot-outline
sort_order: 24
"""
    )

    assert data["name"] == "Plot outline planning"
    assert data["builtin"] is True
    assert data["tags"] == ["planning", "plot-outline"]
    assert data["sort_order"] == 24
    assert data["variables"] == [
        {"name": "novel.title", "desc": "Novel title", "type": "string"},
        {"name": "novel.target_chapters", "desc": "Target chapter count", "type": "integer"},
    ]


def test_minimal_yaml_load_parses_folded_multiline_scalar():
    data = _minimal_yaml_load(
        """
variables:
- name: fact_lock
  desc: V6 记忆引擎：FACT_LOCK + COMPLETED_BEATS 组合文本块（由 MemoryEngine
    动态生成）
  type: string
"""
    )

    assert data["variables"] == [
        {
            "name": "fact_lock",
            "desc": "V6 记忆引擎：FACT_LOCK + COMPLETED_BEATS 组合文本块（由 MemoryEngine 动态生成）",
            "type": "string",
        }
    ]
