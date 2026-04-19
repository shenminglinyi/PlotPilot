"""TensionAnalyzer 单元测试"""
import pytest
from unittest.mock import Mock, AsyncMock

from application.analyst.services.tension_analyzer import TensionAnalyzer
from application.workbench.dtos.writer_block_dto import TensionDiagnosis, TensionSlingshotRequest


class TestTensionAnalyzer:
    """测试 TensionAnalyzer"""

    @pytest.fixture
    def mock_event_repo(self):
        """创建 mock 事件仓储"""
        repo = Mock()
        return repo

    @pytest.fixture
    def mock_llm_client(self):
        """创建 mock LLM 客户端"""
        client = Mock()
        client.generate = AsyncMock()
        return client

    @pytest.fixture
    def analyzer(self, mock_event_repo, mock_llm_client):
        """创建 TensionAnalyzer 实例"""
        return TensionAnalyzer(
            mock_event_repo,
            mock_llm_client,
            chapter_repository=None,
            plot_arc_repository=None,
        )

    @pytest.mark.asyncio
    async def test_analyze_low_tension(self, analyzer, mock_event_repo, mock_llm_client):
        """测试分析低张力场景（无冲突标签）"""
        # 准备测试数据：无冲突标签的事件
        mock_event_repo.list_up_to_chapter.return_value = [
            {
                "event_id": "evt-001",
                "chapter_number": 1,
                "event_summary": "主角在家吃早餐",
                "tags": ["日常", "情绪:平静"],
                "mutations": []
            },
            {
                "event_id": "evt-002",
                "chapter_number": 2,
                "event_summary": "主角去上班",
                "tags": ["日常"],
                "mutations": []
            }
        ]

        # Mock LLM 响应
        mock_llm_client.generate.return_value = """{
            "diagnosis": "当前章节缺乏冲突和张力，情节过于平淡",
            "tension_level": "low",
            "missing_elements": ["conflict", "stakes"],
            "suggestions": ["引入外部冲突", "提高事件的利害关系", "增加角色内心矛盾"]
        }"""

        request = TensionSlingshotRequest(
            novel_id="novel-001",
            chapter_number=2
        )

        result = await analyzer.analyze_tension(request)

        assert result.tension_level == "low"
        assert "conflict" in result.missing_elements
        assert len(result.suggestions) > 0

    @pytest.mark.asyncio
    async def test_analyze_with_stuck_reason(self, analyzer, mock_event_repo, mock_llm_client):
        """测试提供卡文原因时的分析"""
        mock_event_repo.list_up_to_chapter.return_value = [
            {
                "event_id": "evt-001",
                "chapter_number": 1,
                "event_summary": "主角发现秘密",
                "tags": ["冲突:内心"],
                "mutations": []
            }
        ]

        # Mock LLM 响应包含对 stuck_reason 的分析
        mock_llm_client.generate.return_value = """{
            "diagnosis": "作者提到不知道如何推进情节。当前问题在于秘密发现后缺乏后续反应和行动。",
            "tension_level": "medium",
            "missing_elements": ["action", "consequence"],
            "suggestions": ["让主角对秘密做出具体反应", "引入秘密带来的直接后果", "增加时间压力"]
        }"""

        request = TensionSlingshotRequest(
            novel_id="novel-001",
            chapter_number=1,
            stuck_reason="不知道如何推进情节"
        )

        result = await analyzer.analyze_tension(request)

        assert "不知道如何推进情节" in mock_llm_client.generate.call_args[0][0] or \
               "不知道如何推进情节" in str(mock_llm_client.generate.call_args)
        assert result.diagnosis is not None
        assert len(result.diagnosis) > 0

    @pytest.mark.asyncio
    async def test_analyze_suggests_concrete_actions(self, analyzer, mock_event_repo, mock_llm_client):
        """测试建议包含可操作的具体行动"""
        mock_event_repo.list_up_to_chapter.return_value = [
            {
                "event_id": "evt-001",
                "chapter_number": 1,
                "event_summary": "主角思考人生",
                "tags": ["情绪:迷茫"],
                "mutations": []
            }
        ]

        # Mock LLM 响应包含具体可操作的建议
        mock_llm_client.generate.return_value = """{
            "diagnosis": "章节过于内省，缺乏外部行动",
            "tension_level": "low",
            "missing_elements": ["external_conflict", "action"],
            "suggestions": [
                "引入一个打断主角思考的突发事件",
                "让配角出现并提出挑战",
                "设置一个必须立即解决的问题"
            ]
        }"""

        request = TensionSlingshotRequest(
            novel_id="novel-001",
            chapter_number=1
        )

        result = await analyzer.analyze_tension(request)

        assert len(result.suggestions) > 0
        # 验证建议是动作导向的（包含动词）
        action_verbs = ["引入", "增加", "设置", "让", "创造", "提高"]
        has_action = any(
            any(verb in suggestion for verb in action_verbs)
            for suggestion in result.suggestions
        )
        assert has_action

    @pytest.mark.asyncio
    async def test_analyze_considers_context(self, analyzer, mock_event_repo, mock_llm_client):
        """测试分析考虑前后章节上下文"""
        # 准备多章节数据
        mock_event_repo.list_up_to_chapter.return_value = [
            {
                "event_id": "evt-001",
                "chapter_number": 1,
                "event_summary": "主角接受任务",
                "tags": ["冲突:外部", "情绪:紧张"],
                "mutations": []
            },
            {
                "event_id": "evt-002",
                "chapter_number": 2,
                "event_summary": "主角准备装备",
                "tags": ["日常"],
                "mutations": []
            },
            {
                "event_id": "evt-003",
                "chapter_number": 3,
                "event_summary": "主角出发",
                "tags": ["日常"],
                "mutations": []
            }
        ]

        mock_llm_client.generate.return_value = """{
            "diagnosis": "第1章建立了紧张感，但第2-3章节奏放缓，张力下降",
            "tension_level": "medium",
            "missing_elements": ["rising_tension"],
            "suggestions": ["在准备过程中加入障碍", "引入时间限制"]
        }"""

        request = TensionSlingshotRequest(
            novel_id="novel-001",
            chapter_number=3
        )

        result = await analyzer.analyze_tension(request)

        # 验证调用了 list_up_to_chapter（获取上下文）
        mock_event_repo.list_up_to_chapter.assert_called_once_with("novel-001", 3)
        assert result.tension_level in ["low", "medium", "high"]

    @pytest.mark.asyncio
    async def test_analyze_high_tension(self, analyzer, mock_event_repo, mock_llm_client):
        """测试分析高张力场景"""
        mock_event_repo.list_up_to_chapter.return_value = [
            {
                "event_id": "evt-001",
                "chapter_number": 1,
                "event_summary": "主角与敌人激烈战斗",
                "tags": ["冲突:对抗", "冲突:生死", "情绪:愤怒", "情绪:恐惧"],
                "mutations": []
            }
        ]

        mock_llm_client.generate.return_value = """{
            "diagnosis": "当前章节张力充足，冲突激烈",
            "tension_level": "high",
            "missing_elements": [],
            "suggestions": ["保持当前节奏", "注意张力的持续性"]
        }"""

        request = TensionSlingshotRequest(
            novel_id="novel-001",
            chapter_number=1
        )

        result = await analyzer.analyze_tension(request)

        assert result.tension_level == "high"
        assert len(result.missing_elements) == 0

    @pytest.mark.asyncio
    async def test_analyze_empty_events(self, analyzer, mock_event_repo, mock_llm_client):
        """测试处理空事件列表"""
        mock_event_repo.list_up_to_chapter.return_value = []

        mock_llm_client.generate.return_value = """{
            "diagnosis": "没有找到相关事件数据",
            "tension_level": "low",
            "missing_elements": ["events"],
            "suggestions": ["开始创建叙事事件"]
        }"""

        request = TensionSlingshotRequest(
            novel_id="novel-001",
            chapter_number=1
        )

        result = await analyzer.analyze_tension(request)

        assert result is not None
        assert result.tension_level == "low"

    @pytest.mark.asyncio
    async def test_analyze_parses_markdown_fenced_json(
        self, analyzer, mock_event_repo, mock_llm_client
    ):
        """LLM 用 markdown 代码块包裹 JSON 时仍能解析。"""
        mock_event_repo.list_up_to_chapter.return_value = []

        mock_llm_client.generate.return_value = """
下面是分析结果：
```json
{
    "diagnosis": "暂无事件，张力偏低。",
    "tension_level": "low",
    "missing_elements": ["events"],
    "suggestions": ["先写下本章一个具体场景"]
}
```
"""

        request = TensionSlingshotRequest(
            novel_id="novel-001",
            chapter_number=1,
        )

        result = await analyzer.analyze_tension(request)

        assert result.tension_level == "low"
        assert "暂无事件" in result.diagnosis
        assert len(result.suggestions) >= 1
