"""Integration tests for IndexingService"""
import pytest
from unittest.mock import AsyncMock, Mock
from application.analyst.services.indexing_service import IndexingService


@pytest.fixture
def mock_embedding_service():
    """Mock EmbeddingService"""
    service = Mock()
    service.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])
    return service


@pytest.fixture
def mock_vector_store():
    """Mock VectorStore"""
    store = Mock()
    store.insert = AsyncMock()
    store.search = AsyncMock(return_value=[
        {
            "id": "novel1_1",
            "score": 0.95,
            "payload": {
                "novel_id": "novel1",
                "chapter_number": 1,
                "summary": "Chapter 1 summary"
            }
        }
    ])
    store.delete = AsyncMock()
    return store


@pytest.fixture
def mock_summarizer():
    """Mock ChapterSummarizer"""
    summarizer = Mock()
    summarizer.summarize = AsyncMock(return_value="This is a summary of the chapter content.")
    return summarizer


@pytest.fixture
def indexing_service(mock_embedding_service, mock_vector_store, mock_summarizer):
    """Create IndexingService with mocked dependencies"""
    return IndexingService(
        embedding_service=mock_embedding_service,
        vector_store=mock_vector_store,
        summarizer=mock_summarizer
    )


@pytest.mark.asyncio
async def test_index_chapter_flow(indexing_service, mock_summarizer, mock_embedding_service, mock_vector_store):
    """Test the complete flow of indexing a chapter"""
    # Arrange
    novel_id = "novel123"
    chapter_number = 5
    content = "This is the full chapter content with many paragraphs..."

    # Act
    await indexing_service.index_chapter(novel_id, chapter_number, content)

    # Assert
    # 1. Content should be summarized
    mock_summarizer.summarize.assert_called_once_with(content)

    # 2. Summary should be embedded
    mock_embedding_service.embed.assert_called_once_with("This is a summary of the chapter content.")

    # 3. Vector should be stored with correct format
    mock_vector_store.insert.assert_called_once_with(
        collection="chapters",
        id="novel123_5",
        vector=[0.1, 0.2, 0.3],
        payload={
            "novel_id": "novel123",
            "chapter_number": 5,
            "summary": "This is a summary of the chapter content."
        }
    )


@pytest.mark.asyncio
async def test_search_chapters(indexing_service, mock_embedding_service, mock_vector_store):
    """Test searching chapters by semantic similarity"""
    # Arrange
    query = "What happened in the battle scene?"
    limit = 5

    # Act
    results = await indexing_service.search_chapters(query, limit)

    # Assert
    # 1. Query should be embedded
    mock_embedding_service.embed.assert_called_once_with(query)

    # 2. Vector store should be searched
    mock_vector_store.search.assert_called_once_with(
        collection="chapters",
        query_vector=[0.1, 0.2, 0.3],
        limit=5
    )

    # 3. Results should be returned
    assert len(results) == 1
    assert results[0]["id"] == "novel1_1"
    assert results[0]["score"] == 0.95
    assert results[0]["payload"]["novel_id"] == "novel1"
    assert results[0]["payload"]["chapter_number"] == 1


@pytest.mark.asyncio
async def test_search_chapters_default_limit(indexing_service, mock_embedding_service, mock_vector_store):
    """Test searching chapters with default limit"""
    # Arrange
    query = "What happened?"

    # Act
    results = await indexing_service.search_chapters(query)

    # Assert
    mock_vector_store.search.assert_called_once_with(
        collection="chapters",
        query_vector=[0.1, 0.2, 0.3],
        limit=5
    )


@pytest.mark.asyncio
async def test_delete_chapter(indexing_service, mock_vector_store):
    """Test deleting a chapter from the index"""
    # Arrange
    novel_id = "novel456"
    chapter_number = 10

    # Act
    await indexing_service.delete_chapter(novel_id, chapter_number)

    # Assert
    mock_vector_store.delete.assert_called_once_with(
        collection="chapters",
        id="novel456_10"
    )


@pytest.mark.asyncio
async def test_index_chapter_with_special_characters_in_id(indexing_service, mock_summarizer, mock_embedding_service, mock_vector_store):
    """Test indexing with special characters in novel_id"""
    # Arrange
    novel_id = "novel-abc-123"
    chapter_number = 1
    content = "Content"

    # Act
    await indexing_service.index_chapter(novel_id, chapter_number, content)

    # Assert
    mock_vector_store.insert.assert_called_once()
    call_args = mock_vector_store.insert.call_args
    assert call_args.kwargs["id"] == "novel-abc-123_1"


@pytest.mark.asyncio
async def test_search_chapters_empty_results(indexing_service, mock_embedding_service, mock_vector_store):
    """Test searching when no results are found"""
    # Arrange
    mock_vector_store.search = AsyncMock(return_value=[])
    query = "Non-existent content"

    # Act
    results = await indexing_service.search_chapters(query)

    # Assert
    assert results == []
