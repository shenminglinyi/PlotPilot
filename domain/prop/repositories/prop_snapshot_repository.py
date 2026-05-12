from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

class PropSnapshotRepository(ABC):
    @abstractmethod
    def save_snapshot(
        self,
        prop_id: str,
        chapter_number: int,
        holder_character_id: Optional[str],
        lifecycle_state: str,
        attributes_snapshot: Dict[str, Any],
    ) -> None: ...

    @abstractmethod
    def get_snapshot(self, prop_id: str, chapter_number: int) -> Optional[Dict[str, Any]]: ...
