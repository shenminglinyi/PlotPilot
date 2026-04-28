from unittest.mock import Mock

import pytest

from application.core.services.chapter_candidate_draft_service import (
    ChapterCandidateDraftService,
)
from domain.shared.exceptions import EntityNotFoundError


@pytest.fixture
def mock_repository():
    return Mock()


@pytest.fixture
def mock_chapter_service():
    return Mock()


@pytest.fixture
def service(mock_repository, mock_chapter_service):
    return ChapterCandidateDraftService(mock_repository, mock_chapter_service)


def test_create_draft_returns_created_dto(service, mock_repository):
    mock_repository.create.return_value = {
        "id": "draft-1",
        "novel_id": "novel-1",
        "chapter_number": 5,
        "branch_name": "main",
        "source": "kimi",
        "status": "draft",
        "title": "第5章候选",
        "content": "候选正文",
        "rationale": "更冷一点",
        "metadata": {"preset": "cool"},
        "created_at": "2026-04-27T12:00:00",
        "updated_at": "2026-04-27T12:00:00",
    }

    draft = service.create_draft(
        novel_id="novel-1",
        chapter_number=5,
        source="kimi",
        title="第5章候选",
        content="候选正文",
        rationale="更冷一点",
        metadata={"preset": "cool"},
    )

    assert draft.id == "draft-1"
    assert draft.status == "draft"
    assert draft.metadata["preset"] == "cool"


def test_accept_draft_as_primary_updates_chapter_and_marks_draft_accepted(
    service,
    mock_repository,
    mock_chapter_service,
):
    mock_repository.get.return_value = {
        "id": "draft-1",
        "novel_id": "novel-1",
        "chapter_number": 5,
        "branch_name": "main",
        "source": "kimi",
        "status": "draft",
        "title": "第5章候选",
        "content": "候选正文",
        "rationale": "更冷一点",
        "metadata": {},
        "created_at": "2026-04-27T12:00:00",
        "updated_at": "2026-04-27T12:00:00",
    }
    mock_chapter_service.ensure_chapter.return_value = Mock()
    mock_chapter_service.update_chapter_by_novel_and_number.return_value = Mock(
        id="chapter-novel-1-5",
        novel_id="novel-1",
        number=5,
        title="第5章",
        content="候选正文",
        word_count=4,
        status="draft",
    )
    mock_repository.update_status.return_value = {
        "id": "draft-1",
        "status": "accepted",
    }

    result = service.accept_draft_as_primary("draft-1")

    mock_chapter_service.ensure_chapter.assert_called_once_with("novel-1", 5, "第5章候选")
    mock_chapter_service.update_chapter_by_novel_and_number.assert_called_once_with(
        "novel-1",
        5,
        "候选正文",
    )
    mock_repository.update_status.assert_called_once_with("draft-1", "accepted")
    assert result["draft"].status == "accepted"
    assert result["chapter"].content == "候选正文"


def test_accept_draft_as_primary_raises_when_missing(service, mock_repository):
    mock_repository.get.return_value = None

    with pytest.raises(EntityNotFoundError, match="ChapterCandidateDraft"):
        service.accept_draft_as_primary("missing-draft")


def test_merge_branch_to_candidate_creates_main_candidate(service, mock_repository):
    mock_repository.get_latest_by_branch.return_value = {
        "id": "draft-branch",
        "novel_id": "novel-1",
        "chapter_number": 5,
        "branch_name": "exp",
        "source": "external-model",
        "status": "draft",
        "title": "实验稿",
        "content": "实验正文",
        "rationale": "试试分支",
        "metadata": {"external_model": "kimi"},
        "created_at": "2026-04-27T12:00:00",
        "updated_at": "2026-04-27T12:00:00",
    }
    mock_repository.create.return_value = {
        "id": "draft-merge",
        "novel_id": "novel-1",
        "chapter_number": 5,
        "branch_name": "main",
        "source": "branch-merge",
        "status": "draft",
        "title": "合并 exp → main：实验稿",
        "content": "实验正文",
        "rationale": "合并",
        "metadata": {
            "merge_source_branch": "exp",
            "merge_target_branch": "main",
            "merge_source_draft_id": "draft-branch",
        },
        "created_at": "2026-04-27T12:01:00",
        "updated_at": "2026-04-27T12:01:00",
    }

    draft = service.merge_branch_to_candidate(
        novel_id="novel-1",
        chapter_number=5,
        source_branch="exp",
        target_branch="main",
    )

    mock_repository.get_latest_by_branch.assert_called_once_with("novel-1", 5, "exp")
    assert draft.source == "branch-merge"
    assert draft.branch_name == "main"
    assert draft.metadata["merge_source_branch"] == "exp"


def test_branch_memory_diff_reports_external_and_relationship_risks(service, mock_repository):
    mock_repository.list_by_chapter.side_effect = [
        [
            {
                "id": "source-1",
                "content": "甲和乙关系升温，并埋下一个秘密伏笔。",
                "metadata": {"external_model": "kimi"},
                "status": "draft",
            }
        ],
        [
            {
                "id": "target-1",
                "content": "甲和乙同行。",
                "metadata": {},
                "status": "draft",
            }
        ],
    ]

    diff = service.build_branch_memory_diff(
        novel_id="novel-1",
        chapter_number=5,
        source_branch="exp",
        target_branch="main",
    )

    labels = {item["label"] for item in diff["memory_impacts"]}
    assert "外部模型稿" in labels
    assert "角色关系" in labels
    assert "伏笔状态" in labels
