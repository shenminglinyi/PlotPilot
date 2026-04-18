# domain/shared/events.py
from datetime import datetime, timezone
from typing import Any, Dict
import uuid


class DomainEvent:
    """领域事件基类"""

    def __init__(self, aggregate_id: str):
        self.event_id = str(uuid.uuid4())
        self.aggregate_id = aggregate_id
        self.occurred_at = datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "aggregate_id": self.aggregate_id,
            "occurred_at": self.occurred_at.isoformat(),
            "event_type": self.__class__.__name__
        }
