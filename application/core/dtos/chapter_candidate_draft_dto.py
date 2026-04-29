"""Chapter candidate draft DTO."""
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class ChapterCandidateDraftDTO:
    id: str
    novel_id: str
    chapter_number: int
    branch_name: str
    source: str
    status: str
    title: str
    content: str
    rationale: str
    metadata: Dict[str, Any]
    created_at: str
    updated_at: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChapterCandidateDraftDTO":
        return cls(
            id=data["id"],
            novel_id=data["novel_id"],
            chapter_number=int(data["chapter_number"]),
            branch_name=data.get("branch_name") or "main",
            source=data["source"],
            status=data.get("status") or "draft",
            title=data.get("title") or "",
            content=data.get("content") or "",
            rationale=data.get("rationale") or "",
            metadata=data.get("metadata") or {},
            created_at=data.get("created_at") or "",
            updated_at=data.get("updated_at") or "",
        )
