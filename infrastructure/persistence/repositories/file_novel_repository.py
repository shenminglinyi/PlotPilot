"""Legacy file-backed novel repository compatibility layer."""

from typing import List, Optional

from domain.novel.entities.novel import AutopilotStatus, Novel
from domain.novel.repositories.novel_repository import NovelRepository
from domain.novel.value_objects.novel_id import NovelId
from infrastructure.persistence.mappers.novel_mapper import NovelMapper
from infrastructure.persistence.storage.file_storage import FileStorage


class FileNovelRepository(NovelRepository):
    def __init__(self, storage: FileStorage):
        self.storage = storage

    def _path(self, novel_id: NovelId) -> str:
        return f"novels/{novel_id.value}/novel.json"

    def save(self, novel: Novel) -> None:
        self.storage.write_json(self._path(novel.novel_id), NovelMapper.to_dict(novel))

    async def async_save(self, novel: Novel) -> None:
        self.save(novel)

    def get_by_id(self, novel_id: NovelId) -> Optional[Novel]:
        path = self._path(novel_id)
        if not self.storage.exists(path):
            return None
        return NovelMapper.from_dict(self.storage.read_json(path))

    def list_all(self) -> List[Novel]:
        novels = []
        for path in self.storage.list_files("novels/*/novel.json"):
            novels.append(NovelMapper.from_dict(self.storage.read_json(path)))
        return novels

    def find_by_autopilot_status(self, status: AutopilotStatus) -> List[Novel]:
        return [
            novel
            for novel in self.list_all()
            if getattr(novel, "autopilot_status", AutopilotStatus.STOPPED) == status
        ]

    def delete(self, novel_id: NovelId) -> None:
        self.storage.delete(self._path(novel_id))

    def exists(self, novel_id: NovelId) -> bool:
        return self.storage.exists(self._path(novel_id))
