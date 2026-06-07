"""AI 能力契约的轻量值对象。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Type

from pydantic import BaseModel


@dataclass(frozen=True)
class PromptContract:
    """单个 AI 能力的提示词契约。

    契约只描述能力边界，不直接读取数据库或调用模型：
    - node_key 指向 CPMS / prompt_packages 节点
    - variables_schema 在渲染前做 fast-fail 校验
    - output_schema 预留给调用方做结构化输出校验
    - generation_profile / target_models 用于后续模型画像和灰度治理
    """

    node_key: str
    version: str = "1.0.0"
    variables_schema: Type[BaseModel] | None = None
    output_schema: Type[BaseModel] | None = None
    generation_profile: str = ""
    fallback_policy: str = "package_file"
    target_models: tuple[str, ...] = field(default_factory=tuple)
