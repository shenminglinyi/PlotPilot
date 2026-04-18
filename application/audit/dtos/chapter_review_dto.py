"""Chapter Review 数据传输对象"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class ChapterReviewDTO:
    """章节审阅 DTO"""
    status: str  # "draft", "reviewed", "approved"
    memo: str
    created_at: datetime
    updated_at: datetime

    def to_dict(self) -> dict:
        """转换为字�?""
        return {
            "status": self.status,
            "memo": self.memo,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ChapterReviewDTO':
        """从字典创�?DTO"""
        return cls(
            status=data.get("status", "draft"),
            memo=data.get("memo", ""),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(timezone.utc),
            updated_at=datetime.fromisoformat(data["updated_at"]) if "updated_at" in data else datetime.now(timezone.utc)
        )
