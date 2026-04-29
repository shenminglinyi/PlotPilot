"""Legacy file-backed chapter repository compatibility layer."""

from typing import List, Optional

from domain.novel.entities.chapter import Chapter
from domain.novel.repositories.chapter_repository import ChapterRepository
from domain.novel.value_objects.chapter_id import ChapterId
from domain.novel.value_objects.novel_id import NovelId
from infrastructure.persistence.mappers.chapter_mapper import ChapterMapper
from infrastructure.persistence.storage.file_storage import FileStorage


class FileChapterRepository(ChapterRepository):
    def __init__(self, storage: FileStorage):
        self.storage = storage

    def _path(self, chapter: Chapter) -> str:
        return f"novels/{chapter.novel_id.value}/chapters/{chapter.id}.json"

    def save(self, chapter: Chapter) -> None:
        self.storage.write_json(self._path(chapter), ChapterMapper.to_dict(chapter))

    def get_by_id(self, chapter_id: ChapterId) -> Optional[Chapter]:
        target = getattr(chapter_id, "value", str(chapter_id))
        for path in self.storage.list_files("novels/*/chapters/*.json"):
            data = self.storage.read_json(path)
            if data.get("id") == target:
                return ChapterMapper.from_dict(data)
        return None

    def list_by_novel(self, novel_id: NovelId) -> List[Chapter]:
        chapters = [
            ChapterMapper.from_dict(self.storage.read_json(path))
            for path in self.storage.list_files(f"novels/{novel_id.value}/chapters/*.json")
        ]
        return sorted(chapters, key=lambda item: item.number)

    def exists(self, chapter_id: ChapterId) -> bool:
        return self.get_by_id(chapter_id) is not None

    def delete(self, chapter_id: ChapterId) -> None:
        target = getattr(chapter_id, "value", str(chapter_id))
        for path in self.storage.list_files("novels/*/chapters/*.json"):
            if self.storage.read_json(path).get("id") == target:
                self.storage.delete(path)
                return
