"""删章（并重排章节号）后的扩展编排：伏笔 JSON、快照内嵌 JSON、向量元数据等。

新增一种侧车数据时：实现 ``ChapterRenumberExtension`` 并在依赖注入处注册即可，
避免在 ``SqliteChapterRepository`` 内无限堆叠硬编码表名。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, FrozenSet, List, Optional, Protocol, Sequence

from domain.novel.chapter_renumber.json_walk import (
    DEFAULT_CHAPTER_INTEGER_JSON_KEYS,
    renumber_chapter_integers_in_json,
)
from domain.novel.value_objects.chapter_renumber_spec import ChapterRenumberSpec
from domain.novel.value_objects.novel_id import NovelId
from infrastructure.persistence.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)

VectorCollectionResolver = Callable[[str], List[str]]


def default_vector_collection_names(novel_id: str) -> List[str]:
    """默认与各 IndexingService 集合命名一致；迭代时可在 Context 中替换整个 resolver。"""
    return [
        f"novel_{novel_id}_chunks",
        f"novel_{novel_id}_triples",
        "chapters",
    ]


@dataclass
class ChapterRenumberContext:
    """扩展点共享依赖（由 DI 组装，便于单测替换）。"""

    db: DatabaseConnection
    foreshadowing_repository: Optional[Any] = None
    vector_store: Optional[Any] = None
    vector_collection_names_resolver: VectorCollectionResolver = default_vector_collection_names
    snapshot_json_keys: FrozenSet[str] = field(
        default_factory=lambda: DEFAULT_CHAPTER_INTEGER_JSON_KEYS
    )


class ChapterRenumberExtension(Protocol):
    """单种「章号侧车数据」的重排逻辑。"""

    @property
    def name(self) -> str: ...

    def apply(self, spec: ChapterRenumberSpec, ctx: ChapterRenumberContext) -> None: ...


class ForeshadowRegistryChapterRenumberExtension:
    name = "foreshadow_registry"

    def apply(self, spec: ChapterRenumberSpec, ctx: ChapterRenumberContext) -> None:
        repo = ctx.foreshadowing_repository
        if repo is None:
            return
        reg = repo.get_by_novel_id(NovelId(spec.novel_id))
        if reg is None:
            return
        reg.apply_chapter_renumber_after_chapter_deleted(spec)
        repo.save(reg)


class VectorStoreChapterRenumberExtension:
    name = "vector_store"

    def apply(self, spec: ChapterRenumberSpec, ctx: ChapterRenumberContext) -> None:
        vs = ctx.vector_store
        if vs is None:
            return
        renumber = getattr(vs, "renumber_chapter_metadata_for_novel", None)
        if not callable(renumber):
            return
        names = ctx.vector_collection_names_resolver(spec.novel_id)
        try:
            n = int(renumber(spec, names))
            logger.info(
                "向量章号元数据已处理 %s 条（含 id 重挂） novel=%s",
                n,
                spec.novel_id,
            )
        except Exception:
            logger.exception("向量章号元数据更新失败 novel=%s", spec.novel_id)


class SnapshotJsonChapterRenumberExtension:
    """修正快照中 graph_state / foreshadow_state 内嵌 JSON 的章号整型字段。

    说明：chapter_pointers 存章节主键 id，不随章号重排变化，故不修改。
    """

    name = "novel_snapshots_json"

    def apply(self, spec: ChapterRenumberSpec, ctx: ChapterRenumberContext) -> None:
        rows = ctx.db.fetch_all(
            """
            SELECT id, graph_state, foreshadow_state
            FROM novel_snapshots
            WHERE novel_id = ?
            """,
            (spec.novel_id,),
        )
        keys = ctx.snapshot_json_keys
        for row in rows:
            sid = row["id"]
            set_parts: List[str] = []
            params: List[Any] = []
            for col in ("graph_state", "foreshadow_state"):
                raw = row.get(col)
                if not raw or not str(raw).strip():
                    continue
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("快照 %s 列 %s 非 JSON，跳过章号修正", sid, col)
                    continue
                new_data = renumber_chapter_integers_in_json(data, spec, keys=keys)
                new_raw = json.dumps(new_data, ensure_ascii=False)
                if new_raw == raw:
                    continue
                set_parts.append(f"{col} = ?")
                params.append(new_raw)
            if not set_parts:
                continue
            sql = f"UPDATE novel_snapshots SET {', '.join(set_parts)} WHERE id = ?"
            params.append(sid)
            ctx.db.execute(sql, tuple(params))
        ctx.db.get_connection().commit()


class ChapterRenumberCoordinator:
    """按顺序执行已注册的扩展；单个扩展失败不影响其它扩展（记录日志）。"""

    def __init__(
        self,
        context: ChapterRenumberContext,
        extensions: Sequence[ChapterRenumberExtension],
    ):
        self._ctx = context
        self._extensions = tuple(extensions)

    def on_chapter_deleted(self, novel_id: str, deleted_chapter_number: int) -> None:
        spec = ChapterRenumberSpec(
            novel_id=novel_id,
            deleted_chapter_number=deleted_chapter_number,
        )
        for ext in self._extensions:
            try:
                ext.apply(spec, self._ctx)
            except Exception:
                logger.exception("章号重排扩展失败: %s", ext.name)


def build_default_chapter_renumber_coordinator(
    db: DatabaseConnection,
    *,
    foreshadowing_repository: Optional[Any] = None,
    vector_store: Optional[Any] = None,
    vector_collection_names_resolver: Optional[VectorCollectionResolver] = None,
    snapshot_json_keys: Optional[FrozenSet[str]] = None,
    extra_extensions: Sequence[ChapterRenumberExtension] = (),
) -> ChapterRenumberCoordinator:
    """工厂：默认扩展集 + 可选附加扩展（插件入口）。"""
    ctx = ChapterRenumberContext(
        db=db,
        foreshadowing_repository=foreshadowing_repository,
        vector_store=vector_store,
        vector_collection_names_resolver=(
            vector_collection_names_resolver or default_vector_collection_names
        ),
        snapshot_json_keys=snapshot_json_keys or DEFAULT_CHAPTER_INTEGER_JSON_KEYS,
    )
    extensions: List[ChapterRenumberExtension] = [
        ForeshadowRegistryChapterRenumberExtension(),
        VectorStoreChapterRenumberExtension(),
        SnapshotJsonChapterRenumberExtension(),
    ]
    extensions.extend(extra_extensions)
    return ChapterRenumberCoordinator(ctx, extensions)
