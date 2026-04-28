"""Legacy file-backed storyline repository compatibility layer."""

from typing import List, Optional

from domain.novel.entities.storyline import Storyline
from domain.novel.repositories.storyline_repository import StorylineRepository
from domain.novel.value_objects.novel_id import NovelId
from infrastructure.persistence.mappers.storyline_mapper import StorylineMapper
from infrastructure.persistence.storage.file_storage import FileStorage


class FileStorylineRepository(StorylineRepository):
    def __init__(self, storage: FileStorage):
        self.storage = storage

    def _path(self, storyline: Storyline) -> str:
        return f"novels/{storyline.novel_id.value}/storylines/{storyline.id}.json"

    def save(self, storyline: Storyline) -> None:
        self.storage.write_json(self._path(storyline), StorylineMapper.to_dict(storyline))

    def get_by_id(self, storyline_id: str) -> Optional[Storyline]:
        for path in self.storage.list_files("novels/*/storylines/*.json"):
            data = self.storage.read_json(path)
            if data.get("id") == storyline_id:
                return StorylineMapper.from_dict(data)
        return None

    def get_by_novel_id(self, novel_id: NovelId) -> List[Storyline]:
        return [
            StorylineMapper.from_dict(self.storage.read_json(path))
            for path in self.storage.list_files(f"novels/{novel_id.value}/storylines/*.json")
        ]

    def delete(self, storyline_id: str) -> None:
        for path in self.storage.list_files("novels/*/storylines/*.json"):
            if self.storage.read_json(path).get("id") == storyline_id:
                self.storage.delete(path)
                return
