"""删章并重排序号后，各层「章号引用」的统一变换规则。

与 ``SqliteChapterRepository`` 内 SQL 更新语义对齐：
大于被删章号减 1；等于被删章号收束到 ``max(1, deleted-1)``；小于不变。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ChapterRenumberSpec:
    """一次删章事件对应的章号映射说明（供 JSON / 向量等扩展点共用）。"""

    novel_id: str
    deleted_chapter_number: int

    def shift_chapter_ref(self, chapter_number: int) -> int:
        """将「仍指向旧编号体系」的章号映射到删章后的新编号。"""
        d = self.deleted_chapter_number
        n = int(chapter_number)
        if n > d:
            return n - 1
        if n == d:
            return max(1, d - 1)
        return n

    def shift_optional_chapter_ref(self, chapter_number: Optional[int]) -> Optional[int]:
        if chapter_number is None:
            return None
        return self.shift_chapter_ref(chapter_number)
