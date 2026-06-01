import pytest
from unittest.mock import Mock, AsyncMock
from application.services.state_extractor import StateExtractionError, StateExtractor
from domain.ai.services.llm_service import LLMService, GenerationConfig, GenerationResult
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage
from domain.novel.value_objects.chapter_state import ChapterState


class TestStateExtractor:
    """测试 StateExtractor 应用服务"""

    def setup_method(self):
        """设置测试环境"""
        self.llm_service = Mock(spec=LLMService)
        self.extractor = StateExtractor(llm_service=self.llm_service)

    @pytest.mark.asyncio
    async def test_extract_chapter_state_empty_content(self):
        """测试提取空内容"""
        # Mock LLM 返回空结果
        self.llm_service.generate = AsyncMock(return_value=GenerationResult(
            content='{"new_characters": [], "character_actions": [], "relationship_changes": [], "foreshadowing_planted": [], "foreshadowing_resolved": [], "events": []}',
            token_usage=TokenUsage(input_tokens=100, output_tokens=50)
        ))

        state = await self.extractor.extract_chapter_state(content="")

        assert isinstance(state, ChapterState)
        assert len(state.new_characters) == 0
        assert len(state.character_actions) == 0
        assert len(state.relationship_changes) == 0
        assert len(state.foreshadowing_planted) == 0
        assert len(state.foreshadowing_resolved) == 0
        assert len(state.events) == 0

    @pytest.mark.asyncio
    async def test_extract_chapter_state_with_new_characters(self):
        """测试提取包含新角色的内容"""
        content = "张三是一个勇敢的战士，第一次出现在第5章。"

        # Mock LLM 返回包含新角色的结果
        self.llm_service.generate = AsyncMock(return_value=GenerationResult(
            content='{"new_characters": [{"name": "张三", "description": "勇敢的战士", "first_appearance": 5}], "character_actions": [], "relationship_changes": [], "foreshadowing_planted": [], "foreshadowing_resolved": [], "events": []}',
            token_usage=TokenUsage(input_tokens=100, output_tokens=50)
        ))

        state = await self.extractor.extract_chapter_state(content=content)

        assert len(state.new_characters) == 1
        assert state.new_characters[0]["name"] == "张三"
        assert state.new_characters[0]["description"] == "勇敢的战士"
        assert state.new_characters[0]["first_appearance"] == 5

    @pytest.mark.asyncio
    async def test_extract_chapter_state_with_character_actions(self):
        """测试提取包含角色行为的内容"""
        content = "张三做出了重要决定。"

        # Mock LLM 返回包含角色行为的结果
        self.llm_service.generate = AsyncMock(return_value=GenerationResult(
            content='{"new_characters": [], "character_actions": [{"character_id": "char-1", "action": "做出了重要决定", "chapter": 5}], "relationship_changes": [], "foreshadowing_planted": [], "foreshadowing_resolved": [], "events": []}',
            token_usage=TokenUsage(input_tokens=100, output_tokens=50)
        ))

        state = await self.extractor.extract_chapter_state(content=content)

        assert len(state.character_actions) == 1
        assert state.character_actions[0]["character_id"] == "char-1"
        assert state.character_actions[0]["action"] == "做出了重要决定"

    @pytest.mark.asyncio
    async def test_extract_chapter_state_with_relationship_changes(self):
        """测试提取包含关系变化的内容"""
        content = "张三和李四成为了朋友。"

        # Mock LLM 返回包含关系变化的结果
        self.llm_service.generate = AsyncMock(return_value=GenerationResult(
            content='{"new_characters": [], "character_actions": [], "relationship_changes": [{"char1": "char-1", "char2": "char-2", "old_type": "stranger", "new_type": "friend", "chapter": 5}], "foreshadowing_planted": [], "foreshadowing_resolved": [], "events": []}',
            token_usage=TokenUsage(input_tokens=100, output_tokens=50)
        ))

        state = await self.extractor.extract_chapter_state(content=content)

        assert len(state.relationship_changes) == 1
        assert state.relationship_changes[0]["char1"] == "char-1"
        assert state.relationship_changes[0]["char2"] == "char-2"
        assert state.relationship_changes[0]["new_type"] == "friend"

    @pytest.mark.asyncio
    async def test_extract_chapter_state_with_foreshadowing(self):
        """测试提取包含伏笔的内容"""
        content = "一个神秘的预言被提及。"

        # Mock LLM 返回包含伏笔的结果
        self.llm_service.generate = AsyncMock(return_value=GenerationResult(
            content='{"new_characters": [], "character_actions": [], "relationship_changes": [], "foreshadowing_planted": [{"description": "神秘的预言", "chapter": 5}], "foreshadowing_resolved": [], "events": []}',
            token_usage=TokenUsage(input_tokens=100, output_tokens=50)
        ))

        state = await self.extractor.extract_chapter_state(content=content)

        assert len(state.foreshadowing_planted) == 1
        assert state.foreshadowing_planted[0]["description"] == "神秘的预言"

    @pytest.mark.asyncio
    async def test_extract_chapter_state_with_events(self):
        """测试提取包含事件的内容"""
        content = "主角与反派发生了激烈的冲突。"

        # Mock LLM 返回包含事件的结果
        self.llm_service.generate = AsyncMock(return_value=GenerationResult(
            content='{"new_characters": [], "character_actions": [], "relationship_changes": [], "foreshadowing_planted": [], "foreshadowing_resolved": [], "events": [{"type": "conflict", "description": "主角与反派对峙", "involved_characters": ["char-1", "char-2"], "chapter": 5}]}',
            token_usage=TokenUsage(input_tokens=100, output_tokens=50)
        ))

        state = await self.extractor.extract_chapter_state(content=content)

        assert len(state.events) == 1
        assert state.events[0]["type"] == "conflict"
        assert state.events[0]["description"] == "主角与反派对峙"

    @pytest.mark.asyncio
    async def test_extract_chapter_state_calls_llm_service(self):
        """测试提取时调用 LLM 服务"""
        content = "测试内容"

        self.llm_service.generate = AsyncMock(return_value=GenerationResult(
            content='{"new_characters": [], "character_actions": [], "relationship_changes": [], "foreshadowing_planted": [], "foreshadowing_resolved": [], "events": []}',
            token_usage=TokenUsage(input_tokens=100, output_tokens=50)
        ))

        await self.extractor.extract_chapter_state(content=content)

        # 验证 LLM 服务被调用
        self.llm_service.generate.assert_called_once()
        call_args = self.llm_service.generate.call_args

        # 验证传入的 prompt 包含内容
        assert isinstance(call_args[1]['prompt'], Prompt)
        assert content in call_args[1]['prompt'].user

        # 验证传入的 config
        assert isinstance(call_args[1]['config'], GenerationConfig)

    @pytest.mark.asyncio
    async def test_extract_chapter_state_invalid_contract_blocks(self):
        """顶层多字段时契约拒绝，流程阻塞，不再伪造空状态。"""
        self.llm_service.generate = AsyncMock(
            return_value=GenerationResult(
                content=(
                    '{"new_characters": [], "character_actions": [], "relationship_changes": [], '
                    '"foreshadowing_planted": [], "foreshadowing_resolved": [], "events": [], "junk": 1}'
                ),
                token_usage=TokenUsage(input_tokens=10, output_tokens=10),
            )
        )
        with pytest.raises(StateExtractionError):
            await self.extractor.extract_chapter_state(content="正文")

    @pytest.mark.asyncio
    async def test_extract_chapter_state_with_complex_content(self):
        """测试提取复杂内容"""
        content = """
        第五章：新的开始

        张三是一个勇敢的战士，他做出了重要决定。
        他和李四成为了朋友。
        一个神秘的预言被提及。
        主角与反派发生了激烈的冲突。
        """

        # Mock LLM 返回复杂结果
        self.llm_service.generate = AsyncMock(return_value=GenerationResult(
            content='{"new_characters": [{"name": "张三", "description": "勇敢的战士", "first_appearance": 5}], "character_actions": [{"character_id": "char-1", "action": "做出了重要决定", "chapter": 5}], "relationship_changes": [{"char1": "char-1", "char2": "char-2", "old_type": "stranger", "new_type": "friend", "chapter": 5}], "foreshadowing_planted": [{"description": "神秘的预言", "chapter": 5}], "foreshadowing_resolved": [], "events": [{"type": "conflict", "description": "主角与反派对峙", "involved_characters": ["char-1", "char-2"], "chapter": 5}]}',
            token_usage=TokenUsage(input_tokens=200, output_tokens=150)
        ))

        state = await self.extractor.extract_chapter_state(content=content)

        assert len(state.new_characters) == 1
        assert len(state.character_actions) == 1
        assert len(state.relationship_changes) == 1
        assert len(state.foreshadowing_planted) == 1
        assert len(state.events) == 1
