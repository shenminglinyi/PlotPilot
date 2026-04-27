"""Chapter candidate draft service."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from application.core.dtos.chapter_candidate_draft_dto import ChapterCandidateDraftDTO
from domain.shared.exceptions import EntityNotFoundError


class ChapterCandidateDraftService:
    def __init__(self, repository, chapter_service):
        self.repository = repository
        self.chapter_service = chapter_service

    def create_draft(
        self,
        *,
        novel_id: str,
        chapter_number: int,
        source: str,
        title: str,
        content: str,
        rationale: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        branch_name: str = "main",
    ) -> ChapterCandidateDraftDTO:
        draft = self.repository.create(
            novel_id=novel_id,
            chapter_number=chapter_number,
            source=source,
            title=title,
            content=content,
            rationale=rationale,
            metadata=metadata or {},
            branch_name=branch_name,
        )
        return ChapterCandidateDraftDTO.from_dict(draft)

    def list_drafts(
        self,
        novel_id: str,
        chapter_number: int,
        *,
        branch_name: Optional[str] = None,
    ) -> List[ChapterCandidateDraftDTO]:
        return [
            ChapterCandidateDraftDTO.from_dict(item)
            for item in self.repository.list_by_chapter(
                novel_id,
                chapter_number,
                branch_name=branch_name,
            )
        ]

    def get_draft(self, draft_id: str) -> ChapterCandidateDraftDTO:
        draft = self.repository.get(draft_id)
        if not draft:
            raise EntityNotFoundError("ChapterCandidateDraft", draft_id)
        return ChapterCandidateDraftDTO.from_dict(draft)

    def reject_draft(self, draft_id: str) -> ChapterCandidateDraftDTO:
        draft = self.repository.get(draft_id)
        if not draft:
            raise EntityNotFoundError("ChapterCandidateDraft", draft_id)
        updated = self.repository.update_status(draft_id, "rejected")
        return ChapterCandidateDraftDTO.from_dict(updated)

    def accept_draft_as_primary(self, draft_id: str) -> Dict[str, Any]:
        draft = self.repository.get(draft_id)
        if not draft:
            raise EntityNotFoundError("ChapterCandidateDraft", draft_id)

        chapter_title = (draft.get("title") or "").strip() or f"第{draft['chapter_number']}章"
        self.chapter_service.ensure_chapter(
            draft["novel_id"],
            int(draft["chapter_number"]),
            chapter_title,
        )
        chapter = self.chapter_service.update_chapter_by_novel_and_number(
            draft["novel_id"],
            int(draft["chapter_number"]),
            draft["content"],
        )
        updated_draft = self.repository.update_status(draft_id, "accepted") or {}
        merged_draft = {**draft, **updated_draft}
        return {
            "draft": ChapterCandidateDraftDTO.from_dict(merged_draft),
            "chapter": chapter,
        }
