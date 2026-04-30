"""写作手法知识库领域模型。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional
from uuid import uuid4


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean_text(value: Optional[str]) -> str:
    return (value or "").strip()


def _clean_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _clean_list(values: Optional[Iterable[Any] | str]) -> list[Any]:
    if not values:
        return []
    if isinstance(values, str):
        text = _clean_text(values)
        return [text] if text else []
    result: list[Any] = []
    for value in values:
        if isinstance(value, str):
            item = _clean_text(value)
        else:
            item = value
        if item and item not in result:
            result.append(item)
    return result


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass
class StyleSample:
    """用户提供的参考样本文本。"""

    title: str
    content: str
    source_type: str = "reference"
    genre: str = ""
    scene_type: str = ""
    pov: str = ""
    allowed_for_generation: bool = False
    novel_id: str = ""
    profile_id: str = ""
    content_hash: str = ""
    char_count: int = 0
    id: str = field(default_factory=lambda: f"style-sample-{uuid4().hex}")
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        self.id = _clean_text(self.id) or f"style-sample-{uuid4().hex}"
        self.title = _clean_text(self.title)
        self.content = _clean_text(self.content)
        if not self.title:
            raise ValueError("Style sample title cannot be empty")
        if not self.content:
            raise ValueError("Style sample content cannot be empty")
        self.source_type = _clean_text(self.source_type) or "reference"
        self.genre = _clean_text(self.genre)
        self.scene_type = _clean_text(self.scene_type)
        self.pov = _clean_text(self.pov)
        self.novel_id = _clean_text(self.novel_id)
        self.profile_id = _clean_text(self.profile_id)
        self.allowed_for_generation = bool(self.allowed_for_generation)
        self.char_count = len(self.content)
        self.content_hash = _clean_text(self.content_hash) or _content_hash(self.content)


@dataclass
class StyleSampleChunk:
    """样本文本切片。"""

    sample_id: str
    chunk_type: str
    sequence: int
    content: str
    chapter_number: int = 0
    title: str = ""
    char_count: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: f"style-chunk-{uuid4().hex}")
    created_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        self.id = _clean_text(self.id) or f"style-chunk-{uuid4().hex}"
        self.sample_id = _clean_text(self.sample_id)
        self.chunk_type = _clean_text(self.chunk_type)
        self.title = _clean_text(self.title)
        self.content = _clean_text(self.content)
        if not self.sample_id:
            raise ValueError("Style sample chunk sample_id cannot be empty")
        if self.chunk_type not in {"chapter", "scene", "paragraph"}:
            raise ValueError(f"Invalid style sample chunk type: {self.chunk_type}")
        if not self.content:
            raise ValueError("Style sample chunk content cannot be empty")
        self.sequence = max(0, int(self.sequence or 0))
        self.chapter_number = max(0, int(self.chapter_number or 0))
        self.char_count = len(self.content)
        self.metrics = _clean_dict(self.metrics)


@dataclass
class StyleRule:
    """可复用写作规则。"""

    title: str
    instruction: str
    category: str = ""
    weight: float = 1.0

    def __post_init__(self) -> None:
        self.title = _clean_text(self.title)
        self.instruction = _clean_text(self.instruction)
        self.category = _clean_text(self.category)
        if not self.title:
            raise ValueError("Style rule title cannot be empty")
        if not self.instruction:
            raise ValueError("Style rule instruction cannot be empty")
        try:
            self.weight = float(self.weight)
        except (TypeError, ValueError):
            self.weight = 1.0


@dataclass
class StyleProfile:
    """可被章节生成引用的写作风格包。"""

    name: str
    description: str = ""
    status: str = "active"
    novel_id: str = ""
    profile: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    rules: list[Any] = field(default_factory=list)
    forbidden_patterns: list[str] = field(default_factory=list)
    version: int = 1
    id: str = field(default_factory=lambda: f"style-profile-{uuid4().hex}")
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        self.id = _clean_text(self.id) or f"style-profile-{uuid4().hex}"
        self.name = _clean_text(self.name)
        if not self.name:
            raise ValueError("Style profile name cannot be empty")
        self.description = _clean_text(self.description)
        self.status = _clean_text(self.status) or "active"
        if self.status not in {"active", "archived"}:
            raise ValueError(f"Invalid style profile status: {self.status}")
        self.novel_id = _clean_text(self.novel_id)
        self.profile = _clean_dict(self.profile)
        self.metrics = _clean_dict(self.metrics)
        self.rules = _clean_list(self.rules)
        self.forbidden_patterns = [str(v) for v in _clean_list(self.forbidden_patterns)]
        self.version = max(1, int(self.version or 1))


@dataclass
class StyleTechniqueCard:
    """从样本中抽取的可执行写作技法卡。"""

    profile_id: str
    title: str
    rule_text: str
    prompt_instruction: str
    category: str = ""
    scene_type: str = ""
    example_summary: str = ""
    enabled: bool = True
    weight: float = 1.0
    id: str = field(default_factory=lambda: f"style-card-{uuid4().hex}")
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        self.id = _clean_text(self.id) or f"style-card-{uuid4().hex}"
        self.profile_id = _clean_text(self.profile_id)
        self.title = _clean_text(self.title)
        self.category = _clean_text(self.category)
        self.scene_type = _clean_text(self.scene_type)
        self.rule_text = _clean_text(self.rule_text)
        self.example_summary = _clean_text(self.example_summary)
        self.prompt_instruction = _clean_text(self.prompt_instruction)
        if not self.profile_id:
            raise ValueError("Style technique card profile_id cannot be empty")
        if not self.title:
            raise ValueError("Style technique card title cannot be empty")
        if not self.rule_text:
            raise ValueError("Style technique card rule_text cannot be empty")
        if not self.prompt_instruction:
            raise ValueError("Style technique card prompt_instruction cannot be empty")
        self.enabled = bool(self.enabled)
        try:
            self.weight = float(self.weight)
        except (TypeError, ValueError):
            self.weight = 1.0

    def disable(self) -> None:
        """禁用卡片但保留历史。"""
        self.enabled = False
        self.updated_at = _now()

    def enable(self) -> None:
        """重新启用卡片。"""
        self.enabled = True
        self.updated_at = _now()

