"""选题立项仓储接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from domain.topic.entities import TopicIdea, TopicIdeaStatus


class TopicIdeaRepository(ABC):
    """选题候选仓储。"""

    @abstractmethod
    def save(self, idea: TopicIdea) -> None:
        pass

    @abstractmethod
    def get_by_id(self, idea_id: str) -> Optional[TopicIdea]:
        pass

    @abstractmethod
    def list(self, status: TopicIdeaStatus | str | None = None) -> list[TopicIdea]:
        pass

    @abstractmethod
    def update_status(
        self,
        idea_id: str,
        status: TopicIdeaStatus | str,
        adopted_novel_id: Optional[str] = None,
    ) -> Optional[TopicIdea]:
        pass

    @abstractmethod
    def update(self, idea: TopicIdea) -> TopicIdea:
        pass
