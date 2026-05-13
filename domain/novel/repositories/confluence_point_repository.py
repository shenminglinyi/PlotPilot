from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Optional
from domain.novel.entities.confluence_point import ConfluencePoint


class ConfluencePointRepository(ABC):

    @abstractmethod
    def save(self, cp: ConfluencePoint) -> None: ...

    @abstractmethod
    def get_by_id(self, cp_id: str) -> Optional[ConfluencePoint]: ...

    @abstractmethod
    def get_by_novel_id(self, novel_id: str) -> List[ConfluencePoint]: ...

    @abstractmethod
    def get_by_source_storyline(self, storyline_id: str) -> List[ConfluencePoint]: ...

    @abstractmethod
    def delete(self, cp_id: str) -> None: ...
