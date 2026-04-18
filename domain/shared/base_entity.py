# domain/shared/base_entity.py
from datetime import datetime, timezone
from typing import Any


class BaseEntity:
    """实体基类"""

    def __init__(self, id: str):
        self.id = id
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, BaseEntity):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
