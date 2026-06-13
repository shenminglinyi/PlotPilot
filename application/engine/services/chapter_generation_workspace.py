"""Temporary workspace for StoryPipeline chapter generation previews.

The workspace is intentionally outside the formal ``chapters`` table. A
preview written here is useful for streaming/UI/debugging, but it is never a
resume source for the next StoryPipeline run.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def new_pipeline_run_id() -> str:
    return uuid.uuid4().hex


def _workspace_dir() -> Path:
    from application.paths import DATA_DIR

    root = DATA_DIR / "chapter_generation_workspaces"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_novel_id(novel_id: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(novel_id))


def _preview_path(novel_id: str, chapter_number: int, run_id: str) -> Path:
    return _workspace_dir() / f"{_safe_novel_id(novel_id)}_ch{int(chapter_number)}_{run_id}.preview"


def _meta_path(novel_id: str, chapter_number: int, run_id: str) -> Path:
    return _workspace_dir() / f"{_safe_novel_id(novel_id)}_ch{int(chapter_number)}_{run_id}.json"


def _glob_paths(novel_id: str, chapter_number: int) -> list[Path]:
    prefix = f"{_safe_novel_id(novel_id)}_ch{int(chapter_number)}_"
    return [p for p in _workspace_dir().glob(f"{prefix}*") if p.is_file()]


@dataclass(frozen=True)
class ChapterGenerationWorkspaceRef:
    novel_id: str
    chapter_number: int
    run_id: str


class ChapterGenerationWorkspace:
    """File-backed transient preview store for one chapter generation step."""

    def begin(
        self,
        novel_id: str,
        chapter_number: int,
        run_id: Optional[str] = None,
    ) -> ChapterGenerationWorkspaceRef:
        run_id = str(run_id or new_pipeline_run_id())
        ref = ChapterGenerationWorkspaceRef(
            novel_id=str(novel_id),
            chapter_number=int(chapter_number),
            run_id=run_id,
        )
        self._write_meta(ref, {"status": "running"})
        return ref

    def append_preview(
        self,
        novel_id: str,
        chapter_number: int,
        run_id: str,
        content: str,
    ) -> None:
        """Persist the latest full preview snapshot atomically."""
        if not content:
            return
        ref = ChapterGenerationWorkspaceRef(str(novel_id), int(chapter_number), str(run_id))
        path = _preview_path(ref.novel_id, ref.chapter_number, ref.run_id)
        tmp_fd = -1
        tmp_name = ""
        try:
            tmp_fd, tmp_name = tempfile.mkstemp(
                prefix=path.name,
                suffix=".tmp",
                dir=str(path.parent),
                text=True,
            )
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                tmp_fd = -1
                fh.write(str(content))
                fh.flush()
            os.replace(tmp_name, path)
            self._write_meta(ref, {"status": "running", "preview_chars": len(str(content))})
        except Exception as exc:
            logger.debug(
                "[ChapterGenerationWorkspace] preview write failed novel=%s ch=%s run=%s: %s",
                novel_id,
                chapter_number,
                run_id,
                exc,
            )
            if tmp_fd >= 0:
                try:
                    os.close(tmp_fd)
                except Exception:
                    pass
            if tmp_name:
                try:
                    Path(tmp_name).unlink(missing_ok=True)
                except Exception:
                    pass

    def read_latest_preview(
        self,
        novel_id: str,
        chapter_number: int,
        run_id: Optional[str] = None,
    ) -> Optional[str]:
        if run_id:
            path = _preview_path(str(novel_id), int(chapter_number), str(run_id))
            if not path.exists():
                return None
            return path.read_text(encoding="utf-8")

        previews = sorted(
            [p for p in _glob_paths(novel_id, chapter_number) if p.suffix == ".preview"],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not previews:
            return None
        return previews[0].read_text(encoding="utf-8")

    def discard(
        self,
        novel_id: str,
        chapter_number: int,
        run_id: Optional[str] = None,
    ) -> int:
        """Remove transient previews for a chapter.

        When ``run_id`` is omitted, every preview run for this chapter is
        discarded. That is the StoryPipeline retry behavior after interruption.
        """
        paths = (
            [_preview_path(str(novel_id), int(chapter_number), str(run_id)), _meta_path(str(novel_id), int(chapter_number), str(run_id))]
            if run_id
            else _glob_paths(str(novel_id), int(chapter_number))
        )
        removed = 0
        for path in paths:
            try:
                if path.exists():
                    path.unlink()
                    removed += 1
            except Exception as exc:
                logger.debug("[ChapterGenerationWorkspace] discard failed path=%s: %s", path, exc)
        return removed

    def commit_to_chapter(
        self,
        *,
        novel_id: str,
        chapter_number: int,
        content: str,
        status: str = "completed",
        chapter_repository: Any = None,
    ) -> None:
        """Commit complete content to the formal chapter store.

        This method is provided for callers that want the workspace to own the
        final write. The current StoryPipeline still uses its existing save
        step and calls ``discard`` after the save succeeds.
        """
        if not str(content or "").strip():
            raise ValueError("cannot commit empty chapter content")
        if chapter_repository is None:
            raise ValueError("chapter_repository is required")

        from domain.novel.entities.chapter import Chapter, ChapterStatus
        from domain.novel.value_objects.novel_id import NovelId

        novel_id_obj = NovelId(str(novel_id))
        existing = chapter_repository.get_by_novel_and_number(novel_id_obj, int(chapter_number))
        if existing is not None:
            existing.update_content(str(content))
            try:
                existing.status = ChapterStatus(status)
            except ValueError:
                existing.status = status
            chapter_repository.save(existing)
            return

        chapter = Chapter(
            id=f"autopilot:{novel_id}:{int(chapter_number)}",
            novel_id=novel_id_obj,
            number=int(chapter_number),
            title=f"第{int(chapter_number)}章",
            content=str(content),
            status=ChapterStatus.COMPLETED if status == "completed" else ChapterStatus.DRAFT,
        )
        chapter_repository.save(chapter)

    def _write_meta(self, ref: ChapterGenerationWorkspaceRef, fields: dict[str, Any]) -> None:
        path = _meta_path(ref.novel_id, ref.chapter_number, ref.run_id)
        payload = {
            "novel_id": ref.novel_id,
            "chapter_number": ref.chapter_number,
            "run_id": ref.run_id,
            **dict(fields or {}),
        }
        try:
            path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        except Exception as exc:
            logger.debug("[ChapterGenerationWorkspace] meta write failed path=%s: %s", path, exc)
