"""章号重排：删章后与关系库一致的引用变换（JSON 遍历、伏笔注册表等）。"""

from domain.novel.chapter_renumber.json_walk import (
    DEFAULT_CHAPTER_INTEGER_JSON_KEYS,
    renumber_chapter_integers_in_json,
)

__all__ = [
    "DEFAULT_CHAPTER_INTEGER_JSON_KEYS",
    "renumber_chapter_integers_in_json",
]
