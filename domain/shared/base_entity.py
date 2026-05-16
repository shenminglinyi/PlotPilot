# domain/shared/base_entity.py
from datetime import datetime, timezone
from typing import Any


class BaseEntity:
    """实体基类"""

    def __init__(self, id: str):
        self.id = id
        now = datetime.now(timezone.utc)
        self.created_at = now
        self.updated_at = now

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, BaseEntity):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
