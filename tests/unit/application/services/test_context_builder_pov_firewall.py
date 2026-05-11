"""测试 ContextBuilder POV 防火墙功能

验证 ContextBuilder 根据 POV 和章节号过滤角色的 hidden_profile。
"""
import pytest
from unittest.mock import Mock, MagicMock
from application.engine.services.context_builder import ContextBuilder
from application.dtos.bible_dto import BibleDTO, CharacterDTO


@pytest.fixture
def mock_dependencies():
    """创建 ContextBuilder 所需的 mock 依赖"""
    storyline_manager = Mock()
    storyline_manager.repository.get_by_novel_id.return_value = []

    chapter_repository = Mock()
    chapter_repository.list_by_novel.return_value = []

    return {
        "bible_service": Mock(),
        "storyline_manager": storyline_manager,
        "relationship_engine": Mock(),
        "vector_store": None,
        "novel_repository": Mock(),
        "chapter_repository": chapter_repository,
        "plot_arc_repository": None,
        "embedding_service": None,
    }


@pytest.fixture
def context_builder(mock_dependencies):
    """创建 ContextBuilder 实例"""
    return ContextBuilder(**mock_dependencies)


def test_layer2_excludes_hidden_before_reveal(context_builder, mock_dependencies):
    """测试：reveal_chapter 之前，hidden_profile 不应出现在 layer2"""
    # Arrange
    char_with_hidden = CharacterDTO(
        id="char_001",
        name="林雪",
        description="",
        relationships=[],
        public_profile="警察，外表冷静",
        hidden_profile="实际上是卧底，潜伏在黑帮内部",
        reveal_chapter=100
    )

    bible_dto = BibleDTO(
        id="bible_001",
        novel_id="novel_001",
        characters=[char_with_hidden],
        world_settings=[],
        locations=[],
        timeline_notes=[],
        style_notes=[]
    )

    mock_dependencies["bible_service"].get_bible_by_novel.return_value = bible_dto
    mock_dependencies["novel_repository"].get_by_id.return_value = None

    # Act
    result = context_builder.build_structured_context(
        novel_id="novel_001",
        chapter_number=10,  # 远早于 reveal_chapter=100
        outline="男主与林雪见面",
        max_tokens=35000
    )

    # Assert
    layer2_text = result["layer2_text"]
    assert "林雪" in layer2_text, "角色名应该出现"
    assert "警察，外表冷静" in layer2_text, "public_profile 应该出现"
    assert "卧底" not in layer2_text, "hidden_profile 不应出现（章节 10 < reveal_chapter 100）"
    assert "潜伏在黑帮" not in layer2_text, "hidden_profile 内容不应出现"


def test_layer2_includes_hidden_after_reveal(context_builder, mock_dependencies):
    """测试：达到 reveal_chapter 后，hidden_profile 应出现在 layer2"""
    # Arrange
    char_with_hidden = CharacterDTO(
        id="char_001",
        name="林雪",
        description="",
        relationships=[],
        public_profile="警察，外表冷静",
        hidden_profile="实际上是卧底，潜伏在黑帮内部",
        reveal_chapter=100
    )

    bible_dto = BibleDTO(
        id="bible_001",
        novel_id="novel_001",
        characters=[char_with_hidden],
        world_settings=[],
        locations=[],
        timeline_notes=[],
        style_notes=[]
    )

    mock_dependencies["bible_service"].get_bible_by_novel.return_value = bible_dto
    mock_dependencies["novel_repository"].get_by_id.return_value = None

    # Act
    result = context_builder.build_structured_context(
        novel_id="novel_001",
        chapter_number=100,  # 达到 reveal_chapter
        outline="真相揭露",
        max_tokens=35000
    )

    # Assert
    layer2_text = result["layer2_text"]
    assert "林雪" in layer2_text, "角色名应该出现"
    assert "警察，外表冷静" in layer2_text, "public_profile 应该出现"
    assert "卧底" in layer2_text, "hidden_profile 应该出现（章节 100 >= reveal_chapter 100）"
    assert "潜伏在黑帮" in layer2_text, "hidden_profile 内容应该出现"


def test_layer2_includes_hidden_when_no_reveal_chapter(context_builder, mock_dependencies):
    """测试：reveal_chapter=None 时，hidden_profile 总是可见（默认行为）"""
    # Arrange
    char_always_visible = CharacterDTO(
        id="char_002",
        name="张伟",
        description="",
        relationships=[],
        public_profile="商人",
        hidden_profile="有犯罪前科",
        reveal_chapter=None  # 总是可见
    )

    bible_dto = BibleDTO(
        id="bible_001",
        novel_id="novel_001",
        characters=[char_always_visible],
        world_settings=[],
        locations=[],
        timeline_notes=[],
        style_notes=[]
    )

    mock_dependencies["bible_service"].get_bible_by_novel.return_value = bible_dto
    mock_dependencies["novel_repository"].get_by_id.return_value = None

    # Act
    result = context_builder.build_structured_context(
        novel_id="novel_001",
        chapter_number=1,  # 任意章节
        outline="初次登场",
        max_tokens=35000
    )

    # Assert
    layer2_text = result["layer2_text"]
    assert "张伟" in layer2_text, "角色名应该出现"
    assert "商人" in layer2_text, "public_profile 应该出现"
    assert "犯罪前科" in layer2_text, "hidden_profile 应该出现（reveal_chapter=None）"


def test_layer2_uses_public_profile_always(context_builder, mock_dependencies):
    """测试：public_profile 总是包含在 layer2，无论章节号"""
    # Arrange
    char_with_public = CharacterDTO(
        id="char_003",
        name="李明",
        description="",
        relationships=[],
        public_profile="大学教授，温文尔雅",
        hidden_profile="秘密组织成员",
        reveal_chapter=50
    )

    bible_dto = BibleDTO(
        id="bible_001",
        novel_id="novel_001",
        characters=[char_with_public],
        world_settings=[],
        locations=[],
        timeline_notes=[],
        style_notes=[]
    )

    mock_dependencies["bible_service"].get_bible_by_novel.return_value = bible_dto
    mock_dependencies["novel_repository"].get_by_id.return_value = None

    # Act - 测试多个章节
    for chapter_num in [1, 25, 49, 50, 100]:
        result = context_builder.build_structured_context(
            novel_id="novel_001",
            chapter_number=chapter_num,
            outline="测试章节",
            max_tokens=35000
        )

        # Assert
        layer2_text = result["layer2_text"]
        assert "李明" in layer2_text, f"角色名应该在章节 {chapter_num} 出现"
        assert "大学教授，温文尔雅" in layer2_text, f"public_profile 应该在章节 {chapter_num} 出现"


def test_layer2_backward_compatible_with_old_data(context_builder, mock_dependencies):
    """测试：向后兼容 - 旧数据无 public_profile/hidden_profile 时使用 description"""
    # Arrange - 模拟旧数据结构（只有 description）
    char_old_format = CharacterDTO(
        id="char_004",
        name="王芳",
        description="资深记者，善于调查",
        relationships=[]
    )

    bible_dto = BibleDTO(
        id="bible_001",
        novel_id="novel_001",
        characters=[char_old_format],
        world_settings=[],
        locations=[],
        timeline_notes=[],
        style_notes=[]
    )

    mock_dependencies["bible_service"].get_bible_by_novel.return_value = bible_dto
    mock_dependencies["novel_repository"].get_by_id.return_value = None

    # Act
    result = context_builder.build_structured_context(
        novel_id="novel_001",
        chapter_number=10,
        outline="记者采访",
        max_tokens=35000
    )

    # Assert
    layer2_text = result["layer2_text"]
    assert "王芳" in layer2_text, "角色名应该出现"
    assert "资深记者，善于调查" in layer2_text, "description 应该作为后备出现"


def test_layer2_multiple_characters_with_different_reveal_chapters(context_builder, mock_dependencies):
    """测试：多个角色各自的 reveal_chapter 独立工作"""
    # Arrange
    char1 = CharacterDTO(
        id="char_001",
        name="角色A",
        description="",
        relationships=[],
        public_profile="表面身份A",
        hidden_profile="秘密A",
        reveal_chapter=50
    )

    char2 = CharacterDTO(
        id="char_002",
        name="角色B",
        description="",
        relationships=[],
        public_profile="表面身份B",
        hidden_profile="秘密B",
        reveal_chapter=100
    )

    char3 = CharacterDTO(
        id="char_003",
        name="角色C",
        description="",
        relationships=[],
        public_profile="表面身份C",
        hidden_profile="秘密C",
        reveal_chapter=None  # 总是可见
    )

    bible_dto = BibleDTO(
        id="bible_001",
        novel_id="novel_001",
        characters=[char1, char2, char3],
        world_settings=[],
        locations=[],
        timeline_notes=[],
        style_notes=[]
    )

    mock_dependencies["bible_service"].get_bible_by_novel.return_value = bible_dto
    mock_dependencies["novel_repository"].get_by_id.return_value = None

    # Act - 章节 75（在 char1 reveal 之后，char2 reveal 之前）
    result = context_builder.build_structured_context(
        novel_id="novel_001",
        chapter_number=75,
        outline="中期章节",
        max_tokens=35000
    )

    # Assert
    layer2_text = result["layer2_text"]

    # char1: 应该显示 hidden（75 >= 50）
    assert "角色A" in layer2_text
    assert "表面身份A" in layer2_text
    assert "秘密A" in layer2_text

    # char2: 不应显示 hidden（75 < 100）
    assert "角色B" in layer2_text
    assert "表面身份B" in layer2_text
    assert "秘密B" not in layer2_text

    # char3: 应该显示 hidden（reveal_chapter=None）
    assert "角色C" in layer2_text
    assert "表面身份C" in layer2_text
    assert "秘密C" in layer2_text
