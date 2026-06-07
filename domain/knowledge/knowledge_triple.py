"""Knowledge Triple entity"""
from typing import Optional, Literal, List, Dict, Any
from domain.shared.base_entity import BaseEntity


class KnowledgeTriple(BaseEntity):
    """知识三元组实体

    表示一个知识事实：主语-谓词-宾语
    扩展了丰富的上下文信息以减少 AI 幻觉
    """

    def __init__(
        self,
        id: str,
        subject: str,
        predicate: str,
        object: str,
        chapter_id: Optional[int] = None,
        note: str = "",
        entity_type: Optional[Literal['character', 'location']] = None,
        importance: Optional[str] = None,
        location_type: Optional[Literal['city', 'region', 'building', 'faction', 'realm']] = None,
        description: Optional[str] = None,
        first_appearance: Optional[int] = None,
        related_chapters: Optional[List[int]] = None,
        tags: Optional[List[str]] = None,
        attributes: Optional[Dict[str, Any]] = None,
        confidence: Optional[float] = None,
        source_type: Optional[str] = None,
        subject_entity_id: Optional[str] = None,
        object_entity_id: Optional[str] = None,
        provenance: Optional[List[Dict[str, Any]]] = None,
        is_starred: bool = False,
    ):
        """初始化知识三元组

        Args:
            id: 三元组唯一标识
            subject: 主语
            predicate: 谓词/关系
            object: 宾语
            chapter_id: 关联章节号
            note: 备注说明
            entity_type: 实体类型 ('character' | 'location')
            importance: 重要程度 (人物: 'primary'|'secondary'|'minor', 地点: 'core'|'important'|'normal')
            location_type: 地点类型 ('city'|'region'|'building'|'faction'|'realm')
            description: 实体详细描述，为 AI 提供完整上下文
            first_appearance: 首次出现的章节号
            related_chapters: 相关章节列表
            tags: 标签列表，如 ['主线', '重要', '伏笔']
            attributes: 灵活键值（持久化为 triple_attr 子表，非库内 JSON 列）
            confidence: 置信度 0~1，人工可空
            source_type: manual|bible_generated|chapter_inferred|ai_generated
            subject_entity_id: 绑定设定实体 id（可选）
            object_entity_id: 绑定设定实体 id（可选）
            provenance: 推断溯源（仅服务端写入；来自 triple_provenance 表）
        """
        super().__init__(id)
        self.subject = subject
        self.predicate = predicate
        self.object = object
        self.chapter_id = chapter_id
        self.note = note
        self.entity_type = entity_type
        self.importance = importance
        self.location_type = location_type
        self.description = description
        self.first_appearance = first_appearance
        self.related_chapters = related_chapters or []
        self.tags = tags or []
        self.attributes = attributes or {}
        self.confidence = confidence
        self.source_type = source_type
        self.subject_entity_id = subject_entity_id
        self.object_entity_id = object_entity_id
        self.provenance = list(provenance or [])
        self.is_starred = is_starred

    def __repr__(self) -> str:
        type_str = f" [{self.entity_type}]" if self.entity_type else ""
        return f"<KnowledgeTriple {self.id}{type_str}: {self.subject} -> {self.predicate} -> {self.object}>"
