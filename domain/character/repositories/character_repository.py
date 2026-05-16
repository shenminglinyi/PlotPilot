from abc import ABC, abstractmethod
from typing import List, Optional
from domain.character.entities.character import Character
from domain.character.value_objects.character_id import CharacterId

class CharacterRepository(ABC):
    @abstractmethod
    def get(self, character_id: CharacterId) -> Optional[Character]: ...
    @abstractmethod
    def list_by_novel(self, novel_id: str) -> List[Character]: ...
    @abstractmethod
    def save(self, character: Character) -> None: ...
    @abstractmethod
    def delete(self, character_id: CharacterId) -> None: ...
