from abc import ABC, abstractmethod
from typing import List
from domain.prop.value_objects.prop_event import PropEvent

class PropEventRepository(ABC):
    @abstractmethod
    def save(self, event: PropEvent) -> None: ...
    @abstractmethod
    def list_for_prop(self, prop_id: str) -> List[PropEvent]: ...
    @abstractmethod
    def list_for_chapter(self, novel_id: str, chapter: int) -> List[PropEvent]: ...
