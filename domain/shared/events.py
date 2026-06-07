# domain/shared/events.py
from typing import Any, Dict
import uuid

from domain.shared.time_utils import utcnow


class AggregateDomainEvent:
    """聚合根领域事件基类（Novel/Bible 等 DDD 聚合使用）"""

    def __init__(self, aggregate_id: str):
        self.event_id = str(uuid.uuid4())
        self.aggregate_id = aggregate_id
        self.occurred_at = utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "aggregate_id": self.aggregate_id,
            "occurred_at": self.occurred_at.isoformat(),
            "event_type": self.__class__.__name__
        }


# 向后兼容别名（旧测试/代码）
DomainEvent = AggregateDomainEvent
