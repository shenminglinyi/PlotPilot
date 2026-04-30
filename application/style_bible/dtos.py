"""写作手法知识库 DTO。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class StyleSampleImportRequestDTO:
    title: str
    content: str
    source_type: str = "reference"
    genre: str = ""
    scene_type: str = ""
    pov: str = ""
    allowed_for_generation: bool = False
    novel_id: str = ""
    profile_id: str = ""
    create_profile: bool = False
    profile_name: str = ""


@dataclass
class StyleProfileGenerateRequestDTO:
    novel_id: str = ""
    name: str = "写作手法档案"
    description: str = ""
    sample_ids: list[str] = field(default_factory=list)
    use_llm: bool = False
    llm_profile_id: str = ""


@dataclass
class StyleSampleDTO:
    id: str
    title: str
    content: str
    source_type: str
    genre: str
    scene_type: str
    pov: str
    allowed_for_generation: bool
    novel_id: str
    profile_id: str
    content_hash: str
    char_count: int


@dataclass
class StyleChunkDTO:
    id: str
    sample_id: str
    chunk_type: str
    sequence: int
    chapter_number: int
    title: str
    content: str
    char_count: int
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class StyleTechniqueCardDTO:
    id: str
    profile_id: str
    title: str
    category: str
    scene_type: str
    rule_text: str
    example_summary: str
    prompt_instruction: str
    enabled: bool
    weight: float


@dataclass
class StyleProfileDTO:
    id: str
    name: str
    description: str
    status: str
    novel_id: str
    profile: dict[str, Any]
    metrics: dict[str, Any]
    rules: list[Any]
    forbidden_patterns: list[str]
    version: int


@dataclass
class StyleSampleImportResultDTO:
    sample: StyleSampleDTO
    chunks: list[StyleChunkDTO]
    profile: Optional[StyleProfileDTO] = None
    cards: list[StyleTechniqueCardDTO] = field(default_factory=list)


@dataclass
class StyleProfileGenerateResultDTO:
    profile: StyleProfileDTO
    cards: list[StyleTechniqueCardDTO]


@dataclass
class StyleProfileMatchReportDTO:
    profile_id: str
    score: float
    metrics: dict[str, Any] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)


@dataclass
class StylePromptOverlayDTO:
    prompt: str
    profile_id: str = ""
    profile_name: str = ""
    card_ids: list[str] = field(default_factory=list)
