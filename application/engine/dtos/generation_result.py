"""生成结果 DTO"""
from dataclasses import dataclass
from typing import Optional, List, TYPE_CHECKING
from domain.novel.value_objects.consistency_report import ConsistencyReport
from application.audit.dtos.ghost_annotation import GhostAnnotation

if TYPE_CHECKING:
    from application.audit.services.cliche_scanner import ClicheHit


@dataclass(frozen=True)
class GenerationResult:
    """章节生成结果值对象

    包含生成的内容和相关元数据
    """
    content: str
    consistency_report: ConsistencyReport
    context_used: str
    token_count: int
    ghost_annotations: List[GhostAnnotation] = None  # 幽灵批注（冲突检测结果）
    style_warnings: List['ClicheHit'] = None  # 风格警告（俗套句式检测结果）

    def __post_init__(self):
        if not self.content or not self.content.strip():
            raise ValueError("content cannot be empty")
        if self.token_count < 0:
            raise ValueError("token_count must be non-negative")
        if not self.context_used:
            raise ValueError("context_used cannot be empty")
        # 确保 ghost_annotations 不为 None
        if self.ghost_annotations is None:
            object.__setattr__(self, 'ghost_annotations', [])
        # 确保 style_warnings 不为 None
        if self.style_warnings is None:
            object.__setattr__(self, 'style_warnings', [])
