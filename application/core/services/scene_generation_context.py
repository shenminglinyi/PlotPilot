"""场景生成上下文装配。

把 API 层的“前置场景正文 / Bible 上下文”读取集中到可测试的应用服务，
避免路由里散落数据库细节，也避免在缺少关键上下文时静默降级。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from domain.novel.value_objects.chapter_id import ChapterId


class MissingPreviousSceneContextError(RuntimeError):
    """生成非首场景时缺少必须的前置场景正文。"""


@dataclass(frozen=True)
class SceneGenerationContext:
    """场景生成所需的外部上下文。"""

    previous_scenes: List[str]
    bible_context: Optional[Dict[str, Any]]


class SceneGenerationContextProvider:
    """从章节场景仓储、章节仓储和 Bible 服务装配场景生成上下文。"""

    def __init__(
        self,
        *,
        chapter_scene_repository=None,
        chapter_repository=None,
        bible_service=None,
    ) -> None:
        self._chapter_scene_repository = chapter_scene_repository
        self._chapter_repository = chapter_repository
        self._bible_service = bible_service

    async def build(self, chapter_id: str, scene_index: int) -> SceneGenerationContext:
        """构建场景生成上下文。

        非首场景依赖之前场景的已生成正文；若缺失则显式阻塞，避免续写
        链路在没有承接文本的情况下悄悄退化成单场景生成。
        """
        previous_scenes = await self._load_previous_scene_contents(
            chapter_id=chapter_id,
            scene_index=scene_index,
        )
        bible_context = self._load_bible_context(chapter_id)
        return SceneGenerationContext(
            previous_scenes=previous_scenes,
            bible_context=bible_context,
        )

    async def _load_previous_scene_contents(
        self,
        *,
        chapter_id: str,
        scene_index: int,
    ) -> List[str]:
        if scene_index <= 0:
            return []
        if self._chapter_scene_repository is None:
            raise MissingPreviousSceneContextError("缺少章节场景仓储，无法读取前置场景正文")

        scenes = await self._chapter_scene_repository.get_by_chapter(chapter_id)
        content_by_index: Dict[int, str] = {}
        for scene in scenes:
            content = (getattr(scene, "content", None) or "").strip()
            if content:
                content_by_index[int(getattr(scene, "order_index", -1))] = content

        missing = [idx for idx in range(scene_index) if idx not in content_by_index]
        if missing:
            labels = "、".join(str(idx) for idx in missing)
            raise MissingPreviousSceneContextError(
                f"缺少前置场景正文：索引 {labels}。请先生成并保存前置场景。"
            )

        return [content_by_index[idx] for idx in range(scene_index)]

    def _load_bible_context(self, chapter_id: str) -> Optional[Dict[str, Any]]:
        if self._chapter_repository is None or self._bible_service is None:
            return None
        chapter = self._chapter_repository.get_by_id(ChapterId(chapter_id))
        if chapter is None:
            return None
        novel_id = getattr(chapter.novel_id, "value", chapter.novel_id)
        bible = self._bible_service.get_bible_by_novel(str(novel_id))
        if bible is None:
            return None
        return asdict(bible)
