"""Knowledge DTOs"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ChapterSummaryDTO(BaseModel):
    """章节摘要 DTO"""
    chapter_id: int = Field(..., description="章节号")
    summary: str = Field(default="", description="章末总结")
    key_events: str = Field(default="", description="关键事件")
    open_threads: str = Field(default="", description="未解问题")
    consistency_note: str = Field(default="", description="一致性说明")
    beat_sections: List[str] = Field(default_factory=list, description="节拍列表")
    micro_beats: List[Dict[str, Any]] = Field(default_factory=list, description="微观节拍列表")
    sync_status: str = Field(default="draft", description="同步状态")


class KnowledgeTripleDTO(BaseModel):
    """知识三元组 DTO"""
    id: str = Field(..., description="三元组ID")
    subject: str = Field(default="", description="主语")
    predicate: str = Field(default="", description="谓词")
    object: str = Field(default="", description="宾语")
    chapter_id: Optional[int] = Field(default=None, description="章节号")
    note: str = Field(default="", description="备注")
    entity_type: Optional[str] = Field(default=None, description="实体类型 (character|location)")
    importance: Optional[str] = Field(default=None, description="重要程度")
    location_type: Optional[str] = Field(default=None, description="地点类型 (city|region|building|faction|realm)")
    description: Optional[str] = Field(default=None, description="实体详细描述")
    first_appearance: Optional[int] = Field(default=None, description="首次出现章节号")
    related_chapters: List[int] = Field(default_factory=list, description="相关章节列表")
    tags: List[str] = Field(default_factory=list, description="标签列表")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="额外属性")
    confidence: Optional[float] = Field(default=None, description="置信度 0~1")
    source_type: Optional[str] = Field(
        default=None,
        description="来源: manual|bible_generated|chapter_inferred|ai_generated",
    )
    subject_entity_id: Optional[str] = Field(default=None, description="主语实体 id")
    object_entity_id: Optional[str] = Field(default=None, description="宾语实体 id")
    provenance: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="服务端返回的推断溯源（PUT 时会被忽略，不由客户端持久化）",
    )


class StoryKnowledgeDTO(BaseModel):
    """故事知识 DTO"""
    version: int = Field(default=1, description="数据版本")
    premise_lock: str = Field(default="", description="梗概锁定")
    chapters: List[ChapterSummaryDTO] = Field(default_factory=list, description="章节摘要列表")
    facts: List[KnowledgeTripleDTO] = Field(default_factory=list, description="知识三元组列表")


class KnowledgeSearchHitDTO(BaseModel):
    """知识搜索结果项 DTO"""
    id: str = Field(..., description="结果ID")
    text: str = Field(..., description="文本内容")
    meta: Optional[dict] = Field(default=None, description="元数据")


class KnowledgeSearchResponseDTO(BaseModel):
    """知识搜索响应 DTO"""
    hits: List[KnowledgeSearchHitDTO] = Field(default_factory=list, description="搜索结果列表")
