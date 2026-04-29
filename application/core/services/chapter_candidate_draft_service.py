"""Chapter candidate draft service."""
from __future__ import annotations

from difflib import SequenceMatcher
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

    def compare_with_primary(self, draft_id: str) -> Dict[str, Any]:
        draft = self.repository.get(draft_id)
        if not draft:
            raise EntityNotFoundError("ChapterCandidateDraft", draft_id)

        chapter = self.chapter_service.get_chapter_by_novel_and_number(
            draft["novel_id"],
            int(draft["chapter_number"]),
        )
        primary_content = getattr(chapter, "content", "") if chapter else ""
        candidate_content = str(draft.get("content") or "")
        primary_paragraphs = self._split_paragraphs(primary_content)
        candidate_paragraphs = self._split_paragraphs(candidate_content)

        return {
            "draft": ChapterCandidateDraftDTO.from_dict(draft),
            "primary_word_count": len(primary_content.strip()),
            "candidate_word_count": len(candidate_content.strip()),
            "similarity": round(SequenceMatcher(None, primary_content, candidate_content).ratio(), 3)
            if primary_content or candidate_content
            else 1.0,
            "paragraphs": self._build_paragraph_compare(primary_paragraphs, candidate_paragraphs),
        }

    def list_branch_summaries(self, novel_id: str, chapter_number: int) -> List[Dict[str, Any]]:
        return [
            {
                "branch_name": row.get("branch_name") or "main",
                "draft_count": int(row.get("draft_count") or 0),
                "accepted_count": int(row.get("accepted_count") or 0),
                "updated_at": row.get("updated_at") or "",
            }
            for row in self.repository.list_branches(novel_id, chapter_number)
        ]

    def merge_branch_to_candidate(
        self,
        *,
        novel_id: str,
        chapter_number: int,
        source_branch: str,
        target_branch: str = "main",
        rule: str = "latest_candidate",
    ) -> ChapterCandidateDraftDTO:
        source_branch = (source_branch or "").strip()
        target_branch = (target_branch or "main").strip() or "main"
        if not source_branch:
            raise ValueError("source_branch is required")
        if source_branch == target_branch:
            raise ValueError("source_branch and target_branch must be different")

        source = self.repository.get_latest_by_branch(novel_id, chapter_number, source_branch)
        if not source:
            raise EntityNotFoundError("BranchCandidateDraft", source_branch)

        merged = self.repository.create(
            novel_id=novel_id,
            chapter_number=chapter_number,
            source="branch-merge",
            title=f"合并 {source_branch} → {target_branch}：{source.get('title') or f'第{chapter_number}章'}",
            content=source.get("content") or "",
            rationale=(
                f"按规则「{rule}」从分支「{source_branch}」合并到「{target_branch}」。"
                "合并结果仍作为候选稿，需要作者采纳后才进入主稿。"
            ),
            metadata={
                **(source.get("metadata") or {}),
                "merge_rule": rule,
                "merge_source_branch": source_branch,
                "merge_target_branch": target_branch,
                "merge_source_draft_id": source.get("id") or "",
            },
            branch_name=target_branch,
        )
        return ChapterCandidateDraftDTO.from_dict(merged)

    def build_branch_memory_diff(
        self,
        *,
        novel_id: str,
        chapter_number: int,
        source_branch: str,
        target_branch: str = "main",
    ) -> Dict[str, Any]:
        source_drafts = self.repository.list_by_chapter(
            novel_id,
            chapter_number,
            branch_name=source_branch,
        )
        target_drafts = self.repository.list_by_chapter(
            novel_id,
            chapter_number,
            branch_name=target_branch,
        )
        source_latest = source_drafts[0] if source_drafts else None
        target_latest = target_drafts[0] if target_drafts else None
        source_content = str((source_latest or {}).get("content") or "")
        target_content = str((target_latest or {}).get("content") or "")

        return {
            "novel_id": novel_id,
            "chapter_number": chapter_number,
            "source_branch": source_branch,
            "target_branch": target_branch,
            "source_draft_count": len(source_drafts),
            "target_draft_count": len(target_drafts),
            "source_latest_draft_id": (source_latest or {}).get("id") or "",
            "target_latest_draft_id": (target_latest or {}).get("id") or "",
            "similarity": round(SequenceMatcher(None, source_content, target_content).ratio(), 3)
            if source_content or target_content
            else 1.0,
            "memory_impacts": self._infer_memory_impacts(source_drafts, source_content, target_content),
        }

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

    @staticmethod
    def _split_paragraphs(content: str) -> List[str]:
        return [part.strip() for part in str(content or "").split("\n\n") if part.strip()]

    @staticmethod
    def _build_paragraph_compare(primary: List[str], candidate: List[str]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        max_len = max(len(primary), len(candidate))
        for index in range(max_len):
            left = primary[index] if index < len(primary) else ""
            right = candidate[index] if index < len(candidate) else ""
            if left and right:
                similarity = round(SequenceMatcher(None, left, right).ratio(), 3)
                change_type = "unchanged" if similarity >= 0.98 else "modified"
            elif right:
                similarity = 0.0
                change_type = "added"
            else:
                similarity = 0.0
                change_type = "removed"
            items.append(
                {
                    "index": index,
                    "type": change_type,
                    "primary": left,
                    "candidate": right,
                    "similarity": similarity,
                }
            )
        return items

    @staticmethod
    def _infer_memory_impacts(
        drafts: List[Dict[str, Any]],
        source_content: str,
        target_content: str,
    ) -> List[Dict[str, str]]:
        metadata_keys = {
            str(key)
            for draft in drafts
            for key in (draft.get("metadata") or {}).keys()
        }
        text = f"{source_content}\n{target_content}"
        impacts: List[Dict[str, str]] = []

        def add(label: str, level: str, detail: str) -> None:
            impacts.append({"label": label, "level": level, "detail": detail})

        if "external_model" in metadata_keys or "external_prompt" in metadata_keys:
            add("外部模型稿", "info", "该分支包含外部/直连模型产出的候选稿，需要确认事实与口吻。")
        if "partial_source_draft_id" in metadata_keys:
            add("部分采纳", "warning", "该分支包含部分采纳稿，建议确认段落衔接和上下文连续。")
        if "rewrite_task_id" in metadata_keys:
            add("改稿任务结果", "info", "该分支包含按任务生成的改稿结果，建议核对任务约束是否完整落实。")
        if any(token in text for token in ("关系", "和解", "决裂", "信任", "背叛", "暧昧")):
            add("角色关系", "warning", "文本疑似涉及关系变化，合并前建议检查连续性关系事件。")
        if any(token in text for token in ("伏笔", "秘密", "真相", "线索", "预言")):
            add("伏笔状态", "warning", "文本疑似涉及伏笔或线索，合并前建议检查伏笔账本。")
        if any(token in text for token in ("突破", "升级", "境界", "战力", "技能")):
            add("战力状态", "warning", "文本疑似涉及战力变化，合并前建议检查战力系统。")
        if not impacts:
            add("正文事实", "info", "未检测到显著结构化风险，仍建议按候选稿 diff 逐段确认。")
        return impacts
