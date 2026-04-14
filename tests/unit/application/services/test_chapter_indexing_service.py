"""ChapterIndexingService 单元测试"""
import pytest
from unittest.mock import Mock, AsyncMock
from application.analyst.services.chapter_indexing_service import ChapterIndexingService


class TestChapterIndexingService:
    """ChapterIndexingService 单元测试"""

    @pytest.fixture
    def mock_vector_store(self):
        """创建 mock 向量存储"""
        mock = Mock()
        mock.insert = AsyncMock()
        mock.create_collection = AsyncMock()
        mock.list_collections = AsyncMock(return_value=[])
        return mock

    @pytest.fixture
    def mock_embedding_service(self):
        """创建 mock 嵌入服务"""
        mock = Mock()
        mock.embed = AsyncMock(return_value=[0.1] * 1536)
        mock.get_dimension = Mock(return_value=1536)
        return mock

    @pytest.fixture
    def service(self, mock_vector_store, mock_embedding_service):
        """创建服务实例"""
        return ChapterIndexingService(
            vector_store=mock_vector_store,
            embedding_service=mock_embedding_service
        )

    @pytest.mark.asyncio
    async def test_index_chapter_summary_calls_embedding(
        self, service, mock_embedding_service
    ):
        """测试索引章节摘要时调用 embedding 服务"""
        summary = "这是第一章的摘要"

        await service.index_chapter_summary(
            novel_id="novel-123",
            chapter_number=1,
            summary=summary
        )

        # 验证调用了 embedding 服务
        mock_embedding_service.embed.assert_called_once_with(summary)

    @pytest.mark.asyncio
    async def test_index_chapter_summary_writes_to_vector_store(
        self, service, mock_vector_store, mock_embedding_service
    ):
        """测试索引章节摘要时写入向量存储，验证 payload 结构"""
        novel_id = "novel-123"
        chapter_number = 1
        summary = "这是第一章的摘要"
        expected_vector = [0.1] * 1536

        await service.index_chapter_summary(
            novel_id=novel_id,
            chapter_number=chapter_number,
            summary=summary
        )

        # 验证调用了 insert
        mock_vector_store.insert.assert_called_once()

        # 验证参数
        call_args = mock_vector_store.insert.call_args
        assert call_args.kwargs["collection"] == "novel_novel-123_chunks"
        assert call_args.kwargs["id"] == "novel-123_ch1_summary"
        assert call_args.kwargs["vector"] == expected_vector

        # 验证 payload 结构
        payload = call_args.kwargs["payload"]
        assert payload["chapter_number"] == chapter_number
        assert payload["text"] == summary
        assert payload["kind"] == "chapter_summary"
        assert payload["novel_id"] == novel_id

    @pytest.mark.asyncio
    async def test_ensure_collection_creates_if_not_exists(
        self, service, mock_vector_store
    ):
        """测试 ensure_collection 在 collection 不存在时创建"""
        novel_id = "novel-123"
        mock_vector_store.list_collections.return_value = []

        await service.ensure_collection(novel_id)

        # 验证调用了 create_collection
        mock_vector_store.create_collection.assert_called_once_with(
            collection="novel_novel-123_chunks",
            dimension=1536
        )

    @pytest.mark.asyncio
    async def test_ensure_collection_skips_if_exists(
        self, service, mock_vector_store
    ):
        """测试 ensure_collection 在 collection 已存在时跳过创建"""
        novel_id = "novel-123"
        mock_vector_store.list_collections.return_value = [
            "novel_novel-123_chunks"
        ]

        await service.ensure_collection(novel_id)

        # 验证没有调用 create_collection
        mock_vector_store.create_collection.assert_not_called()

    @pytest.mark.asyncio
    async def test_index_chapter_summary_validates_novel_id(self, service):
        """测试索引章节摘要时验证 novel_id"""
        with pytest.raises(ValueError, match="novel_id cannot be empty"):
            await service.index_chapter_summary(
                novel_id="",
                chapter_number=1,
                summary="摘要"
            )

    @pytest.mark.asyncio
    async def test_index_chapter_summary_validates_chapter_number(self, service):
        """测试索引章节摘要时验证 chapter_number"""
        with pytest.raises(ValueError, match="chapter_number must be >= 1"):
            await service.index_chapter_summary(
                novel_id="novel-123",
                chapter_number=0,
                summary="摘要"
            )

    @pytest.mark.asyncio
    async def test_index_chapter_summary_validates_summary(self, service):
        """测试索引章节摘要时验证 summary"""
        with pytest.raises(ValueError, match="summary cannot be empty"):
            await service.index_chapter_summary(
                novel_id="novel-123",
                chapter_number=1,
                summary=""
            )

        with pytest.raises(ValueError, match="summary cannot be empty"):
            await service.index_chapter_summary(
                novel_id="novel-123",
                chapter_number=1,
                summary="   "
            )

    @pytest.mark.asyncio
    async def test_index_bible_snippet_writes_to_vector_store(
        self, service, mock_vector_store
    ):
        """测试索引 Bible 片段时写入向量存储"""
        novel_id = "novel-123"
        chapter_number = 5
        snippet = "这是一段 Bible 片段"

        await service.index_bible_snippet(
            novel_id=novel_id,
            chapter_number=chapter_number,
            snippet=snippet
        )

        # 验证调用了 insert
        mock_vector_store.insert.assert_called_once()

        # 验证参数
        call_args = mock_vector_store.insert.call_args
        assert call_args.kwargs["collection"] == "novel_novel-123_chunks"
        assert call_args.kwargs["id"] == "novel-123_ch5_bible"

        # 验证 payload 结构
        payload = call_args.kwargs["payload"]
        assert payload["chapter_number"] == chapter_number
        assert payload["text"] == snippet
        assert payload["kind"] == "bible_snippet"
        assert payload["novel_id"] == novel_id

    @pytest.mark.asyncio
    async def test_index_bible_snippet_with_snippet_id(
        self, service, mock_vector_store
    ):
        """测试索引 Bible 片段时使用自定义 snippet_id"""
        novel_id = "novel-123"
        chapter_number = 5
        snippet = "这是一段 Bible 片段"
        snippet_id = "location_001"

        await service.index_bible_snippet(
            novel_id=novel_id,
            chapter_number=chapter_number,
            snippet=snippet,
            snippet_id=snippet_id
        )

        # 验证 ID 包含 snippet_id
        call_args = mock_vector_store.insert.call_args
        assert call_args.kwargs["id"] == "novel-123_ch5_bible_location_001"

    @pytest.mark.asyncio
    async def test_index_bible_snippet_validates_parameters(self, service):
        """测试索引 Bible 片段时验证参数"""
        # 验证 novel_id
        with pytest.raises(ValueError, match="novel_id cannot be empty"):
            await service.index_bible_snippet(
                novel_id="",
                chapter_number=1,
                snippet="片段"
            )

        # 验证 chapter_number
        with pytest.raises(ValueError, match="chapter_number must be >= 1"):
            await service.index_bible_snippet(
                novel_id="novel-123",
                chapter_number=0,
                snippet="片段"
            )

        # 验证 snippet
        with pytest.raises(ValueError, match="snippet cannot be empty"):
            await service.index_bible_snippet(
                novel_id="novel-123",
                chapter_number=1,
                snippet=""
            )

    @pytest.mark.asyncio
    async def test_get_collection_name(self, service):
        """测试 collection 名称生成"""
        assert service._get_collection_name("novel-123") == "novel_novel-123_chunks"
        assert service._get_collection_name("abc") == "novel_abc_chunks"

    @pytest.mark.asyncio
    async def test_collection_isolation_between_novels(
        self, service, mock_vector_store
    ):
        """测试不同小说使用不同的 collection"""
        # 索引第一部小说
        await service.index_chapter_summary(
            novel_id="novel-1",
            chapter_number=1,
            summary="小说1的摘要"
        )

        # 索引第二部小说
        await service.index_chapter_summary(
            novel_id="novel-2",
            chapter_number=1,
            summary="小说2的摘要"
        )

        # 验证使用了不同的 collection
        calls = mock_vector_store.insert.call_args_list
        assert calls[0].kwargs["collection"] == "novel_novel-1_chunks"
        assert calls[1].kwargs["collection"] == "novel_novel-2_chunks"
