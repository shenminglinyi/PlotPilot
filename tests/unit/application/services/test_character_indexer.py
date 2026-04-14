import pytest
from unittest.mock import Mock, AsyncMock
from domain.bible.entities.character import Character
from domain.bible.value_objects.character_id import CharacterId
from application.analyst.services.character_indexer import CharacterIndexer


@pytest.fixture
def mock_embedding_service():
    """Mock EmbeddingService"""
    service = Mock()
    service.embed = AsyncMock(return_value=[0.1, 0.2, 0.3])
    service.get_dimension = Mock(return_value=3)
    return service


@pytest.fixture
def mock_vector_store():
    """Mock VectorStore"""
    store = Mock()
    store.insert = AsyncMock()
    store.search = AsyncMock(return_value=[
        {"id": "char-1", "score": 0.99, "payload": {"name": "张三", "description": "主角"}},
        {"id": "char-2", "score": 0.95, "payload": {"name": "李四", "description": "配角"}},
        {"id": "char-3", "score": 0.85, "payload": {"name": "王五", "description": "配角"}}
    ])
    store.delete = AsyncMock()
    store.create_collection = AsyncMock()
    return store


@pytest.fixture
def character_indexer(mock_embedding_service, mock_vector_store):
    """创建 CharacterIndexer 实例"""
    return CharacterIndexer(
        embedding_service=mock_embedding_service,
        vector_store=mock_vector_store,
        collection_name="test_characters"
    )


@pytest.mark.asyncio
async def test_index_character(character_indexer, mock_embedding_service, mock_vector_store):
    """测试索引角色"""
    char = Character(
        id=CharacterId("char-1"),
        name="张三",
        description="主角，勇敢的战士"
    )

    await character_indexer.index_character(char)

    # 验证调用了 embed
    mock_embedding_service.embed.assert_called_once()
    call_args = mock_embedding_service.embed.call_args[0][0]
    assert "张三" in call_args
    assert "主角，勇敢的战士" in call_args

    # 验证调用了 insert
    mock_vector_store.insert.assert_called_once()
    insert_call = mock_vector_store.insert.call_args
    assert insert_call[1]["collection"] == "test_characters"
    assert insert_call[1]["id"] == "char-1"
    assert insert_call[1]["vector"] == [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_search_by_description(character_indexer, mock_embedding_service, mock_vector_store):
    """测试按描述搜索"""
    results = await character_indexer.search_by_description("勇敢的战士", limit=5)

    # 验证调用了 embed
    mock_embedding_service.embed.assert_called_once_with("勇敢的战士")

    # 验证调用了 search
    mock_vector_store.search.assert_called_once()
    search_call = mock_vector_store.search.call_args
    assert search_call[1]["collection"] == "test_characters"
    assert search_call[1]["limit"] == 5

    # 验证返回结果
    assert len(results) == 3
    assert results[0]["id"] == "char-1"
    assert results[0]["score"] == 0.99


@pytest.mark.asyncio
async def test_find_similar_characters(character_indexer, mock_embedding_service, mock_vector_store):
    """测试查找相似角色"""
    # 首先需要索引一个角色以获取其向量
    char = Character(
        id=CharacterId("char-1"),
        name="张三",
        description="主角，勇敢的战士"
    )
    await character_indexer.index_character(char)

    # 重置 mock
    mock_embedding_service.embed.reset_mock()
    mock_vector_store.search.reset_mock()

    # 查找相似角色
    results = await character_indexer.find_similar_characters(CharacterId("char-1"), limit=3)

    # 验证使用了缓存的向量，不需要再次调用 embed
    # 如果缓存中有，就不会调用 embed
    assert mock_embedding_service.embed.call_count == 0

    # 验证调用了 search
    mock_vector_store.search.assert_called_once()
    search_call = mock_vector_store.search.call_args
    assert search_call[1]["limit"] == 3

    # 验证返回结果（过滤掉自己）
    assert len(results) == 2


@pytest.mark.asyncio
async def test_delete_character(character_indexer, mock_vector_store):
    """测试删除角色索引"""
    await character_indexer.delete_character(CharacterId("char-1"))

    mock_vector_store.delete.assert_called_once_with(
        collection="test_characters",
        id="char-1"
    )


@pytest.mark.asyncio
async def test_initialize_collection(character_indexer, mock_embedding_service, mock_vector_store):
    """测试初始化集合"""
    await character_indexer.initialize_collection()

    mock_vector_store.create_collection.assert_called_once_with(
        collection="test_characters",
        dimension=3
    )


@pytest.mark.asyncio
async def test_batch_index_characters(character_indexer, mock_embedding_service, mock_vector_store):
    """测试批量索引角色"""
    characters = [
        Character(CharacterId(f"char-{i}"), f"角色{i}", f"描述{i}")
        for i in range(10)
    ]

    await character_indexer.batch_index_characters(characters)

    # 验证调用了多次 embed 和 insert
    assert mock_embedding_service.embed.call_count == 10
    assert mock_vector_store.insert.call_count == 10


@pytest.mark.asyncio
async def test_search_with_empty_query(character_indexer):
    """测试空查询"""
    with pytest.raises(ValueError, match="Query cannot be empty"):
        await character_indexer.search_by_description("", limit=5)


@pytest.mark.asyncio
async def test_index_character_with_empty_description(character_indexer):
    """测试索引空描述的角色"""
    char = Character(
        id=CharacterId("char-1"),
        name="张三",
        description=""
    )

    with pytest.raises(ValueError, match="Character description cannot be empty"):
        await character_indexer.index_character(char)
