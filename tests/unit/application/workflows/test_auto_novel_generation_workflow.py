"""AutoNovelGenerationWorkflow 单元测试"""
import pytest
from unittest.mock import Mock, AsyncMock
from types import SimpleNamespace
from application.workflows.auto_novel_generation_workflow import (
    AutoNovelGenerationWorkflow,
    CHAPTER_GENERATION_MAX_TOKENS,
    CHAPTER_GENERATION_TEMPERATURE,
    CHAPTER_CONTEXT_LAYER2_HEADER,
    CHAPTER_CONTEXT_LAYER3_HEADER,
    assemble_chapter_bundle_context_text,
)
from application.engine.dtos.generation_result import GenerationResult
from application.engine.dtos.scene_director_dto import SceneDirectorAnalysis
from application.engine.services.context_builder import ContextBuilder
from domain.novel.services.consistency_checker import ConsistencyChecker
from domain.novel.services.storyline_manager import StorylineManager
from domain.novel.repositories.plot_arc_repository import PlotArcRepository
from domain.novel.value_objects.consistency_report import ConsistencyReport, Issue, IssueType, Severity
from domain.novel.value_objects.chapter_state import ChapterState
from domain.ai.services.llm_service import LLMService, GenerationResult as LLMResult
from domain.ai.value_objects.token_usage import TokenUsage


@pytest.fixture
def mock_context_builder():
    """Mock ContextBuilder"""
    builder = Mock(spec=ContextBuilder)
    builder.build_structured_context.return_value = {
        "layer1_text": "Layer 1 context",
        "layer2_text": "Layer 2 context",
        "layer3_text": "Layer 3 context",
        "token_usage": {
            "layer1": 1250,
            "layer2": 5500,
            "layer3": 2500,
            "total": 9250
        }
    }
    # 不再需要 estimate_tokens 方法
    return builder


@pytest.fixture
def mock_consistency_checker():
    """Mock ConsistencyChecker"""
    checker = Mock(spec=ConsistencyChecker)
    checker.check_all = Mock(return_value=ConsistencyReport(
        issues=[],
        warnings=[],
        suggestions=[]
    ))
    return checker


@pytest.fixture
def mock_storyline_manager():
    """Mock StorylineManager"""
    manager = Mock(spec=StorylineManager)
    manager.repository = Mock()
    manager.repository.get_by_novel_id.return_value = []
    manager.get_storyline_context.return_value = "Main storyline context"
    return manager


@pytest.fixture
def mock_plot_arc_repository():
    """Mock PlotArcRepository"""
    repo = Mock(spec=PlotArcRepository)
    return repo


async def _mock_stream_generate(*args, **kwargs):
    yield "Generated chapter content"


@pytest.fixture
def mock_llm_service():
    """Mock LLMService"""
    service = Mock(spec=LLMService)
    service.generate = AsyncMock(return_value=LLMResult(
        content="Generated chapter content",
        token_usage=TokenUsage(input_tokens=500, output_tokens=500)
    ))
    service.stream_generate = _mock_stream_generate
    return service


@pytest.fixture
def workflow(
    mock_context_builder,
    mock_consistency_checker,
    mock_storyline_manager,
    mock_plot_arc_repository,
    mock_llm_service
):
    """创建 AutoNovelGenerationWorkflow 实例"""
    return AutoNovelGenerationWorkflow(
        context_builder=mock_context_builder,
        consistency_checker=mock_consistency_checker,
        storyline_manager=mock_storyline_manager,
        plot_arc_repository=mock_plot_arc_repository,
        llm_service=mock_llm_service
    )


def test_assemble_chapter_bundle_context_text_uses_t2_t3_headers():
    payload = {
        "layer1_text": "L1",
        "layer2_text": "L2",
        "layer3_text": "L3",
    }
    s = assemble_chapter_bundle_context_text(payload)
    assert f"=== {CHAPTER_CONTEXT_LAYER2_HEADER} ===" in s
    assert f"=== {CHAPTER_CONTEXT_LAYER3_HEADER} ===" in s
    assert "L1" in s and "L2" in s and "L3" in s


class TestGenerateChapter:
    """测试 generate_chapter 方法"""

    @pytest.mark.asyncio
    async def test_generate_chapter_success(self, workflow, mock_context_builder, mock_llm_service):
        """测试成功生成章节"""
        result = await workflow.generate_chapter(
            novel_id="novel-1",
            chapter_number=1,
            outline="Chapter 1 outline"
        )

        # 验证返回结果
        assert isinstance(result, GenerationResult)
        assert result.content == "Generated chapter content"
        assert result.token_count == 9250
        assert "Layer 1 context" in result.context_used
        assert f"=== {CHAPTER_CONTEXT_LAYER2_HEADER} ===" in result.context_used
        assert f"=== {CHAPTER_CONTEXT_LAYER3_HEADER} ===" in result.context_used
        assert isinstance(result.consistency_report, ConsistencyReport)

        # 验证调用顺序
        mock_context_builder.build_structured_context.assert_called_once_with(
            novel_id="novel-1",
            chapter_number=1,
            outline="Chapter 1 outline",
            max_tokens=35000,
            scene_director=None
        )
        # 验证 LLM 被调用：至少一次用于生成章节，可能还有一次用于状态提取
        assert mock_llm_service.generate.call_count >= 1
        generation_config = mock_llm_service.generate.call_args_list[0].args[1]
        assert generation_config.max_tokens == CHAPTER_GENERATION_MAX_TOKENS
        assert generation_config.temperature == CHAPTER_GENERATION_TEMPERATURE

    @pytest.mark.asyncio
    async def test_generate_chapter_stream_direct_mode_skips_post_processing(
        self,
        workflow,
        mock_llm_service,
        mock_context_builder,
    ):
        """直接写作模式用于对照测试，应跳过节拍拆分、自然化后处理和章后质检。"""
        async def direct_stream(*args, **kwargs):
            yield "直接写作正文"

        mock_llm_service.stream_generate = direct_stream
        workflow.post_process_generated_chapter = AsyncMock()
        workflow._naturalize_ai_flavor_if_needed = AsyncMock(return_value="不应出现")

        events = [
            event async for event in workflow.generate_chapter_stream(
                novel_id="novel-1",
                chapter_number=1,
                outline="主角在雨夜拿到一张不该出现的票据。",
                direct_writing_mode=True,
            )
        ]

        done = next(event for event in events if event["type"] == "done")
        assert done["content"] == "直接写作正文"
        assert done["direct_writing_mode"] is True
        assert "post" not in [event.get("phase") for event in events]
        workflow.post_process_generated_chapter.assert_not_called()
        workflow._naturalize_ai_flavor_if_needed.assert_not_called()
        mock_context_builder.magnify_outline_to_beats.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_chapter_stream_direct_mode_can_light_polish(
        self,
        workflow,
        mock_llm_service,
    ):
        """直接写作轻修只调用轻修 pass，不进入完整后处理链路。"""
        async def direct_stream(*args, **kwargs):
            yield "直接写作正文"

        mock_llm_service.stream_generate = direct_stream
        workflow._apply_direct_light_polish_if_needed = AsyncMock(return_value="轻修后正文")
        workflow.post_process_generated_chapter = AsyncMock()
        workflow._naturalize_ai_flavor_if_needed = AsyncMock(return_value="不应出现")

        events = [
            event async for event in workflow.generate_chapter_stream(
                novel_id="novel-1",
                chapter_number=1,
                outline="主角在雨夜拿到一张不该出现的票据。",
                direct_writing_mode=True,
                direct_light_polish=True,
            )
        ]

        done = next(event for event in events if event["type"] == "done")
        assert done["content"] == "轻修后正文"
        assert done["direct_light_polish"] is True
        assert "polish" in [event.get("phase") for event in events]
        workflow._apply_direct_light_polish_if_needed.assert_awaited_once()
        workflow.post_process_generated_chapter.assert_not_called()
        workflow._naturalize_ai_flavor_if_needed.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_chapter_stream_passes_target_words_to_beats(
        self,
        workflow,
        mock_context_builder,
    ):
        """目标字数应传给节拍拆分器，避免固定 3000-4000 字。"""
        async def direct_stream(*args, **kwargs):
            yield "正文"

        workflow.llm_service.stream_generate = direct_stream
        mock_context_builder.magnify_outline_to_beats.return_value = []

        events = [
            event async for event in workflow.generate_chapter_stream(
                novel_id="novel-1",
                chapter_number=1,
                outline="主角核对票据时间。",
                target_word_count=2500,
            )
        ]

        assert events[-1]["type"] == "done"
        mock_context_builder.magnify_outline_to_beats.assert_called_once_with(
            1,
            "主角核对票据时间。",
            target_chapter_words=2500,
        )

    @pytest.mark.asyncio
    async def test_direct_light_polish_discards_over_smoothed_candidate(
        self,
        workflow,
        mock_llm_service,
    ):
        """轻修如果抹掉直接稿的现场余量，应保留原直接稿。"""
        draft = (
            "林默把票据往袖口里塞了半寸。\n\n"
            "“你刚才看见编号了？”\n\n"
            "周正明伸手，又缩回去，鞋底在水里磨了一下。\n\n"
            "顾知寒没接话，只把抽屉推回去，停了半秒。\n\n"
        ) * 16
        over_smoothed = (
            "林默整理好票据，众人意识到线索已经指向新的方向。\n\n"
            "周正明说明了自己的判断，顾知寒也明白事情正在发生变化。\n\n"
            "他们决定继续调查，并准备面对接下来的风险。\n\n"
        ) * 16
        mock_llm_service.generate = AsyncMock(return_value=LLMResult(
            content=over_smoothed,
            token_usage=TokenUsage(input_tokens=300, output_tokens=300),
        ))

        result = await workflow._apply_direct_light_polish_if_needed(
            content=draft,
            outline="测试大纲",
        )

        assert result == draft

    def test_human_residue_score_prefers_concrete_draft_texture(self):
        """直接写作保护需要能区分现场动作稿和顺滑概述稿。"""
        draft = (
            "林默把票据往袖口里塞了半寸。\n\n"
            "“你刚才看见编号了？”\n\n"
            "周正明伸手，又缩回去，鞋底在水里磨了一下。\n\n"
        ) * 18
        smoothed = (
            "林默保存了票据，随后说明线索的重要性。\n\n"
            "众人理解了当前情况，并决定继续调查。\n\n"
        ) * 18

        assert AutoNovelGenerationWorkflow._human_residue_score(draft) > (
            AutoNovelGenerationWorkflow._human_residue_score(smoothed) + 2
        )

    @pytest.mark.asyncio
    async def test_generate_chapter_with_scene_director(self, workflow, mock_context_builder, mock_llm_service):
        """测试使用 scene_director 参数生成章节"""
        scene_director = SceneDirectorAnalysis(
            characters=["Alice", "Bob"],
            locations=["Room A"],
            action_types=["dialogue", "action"],
            trigger_keywords=["conflict"],
            emotional_state="tense",
            pov="Alice"
        )

        result = await workflow.generate_chapter(
            novel_id="novel-1",
            chapter_number=1,
            outline="Chapter 1 outline",
            scene_director=scene_director
        )

        # 验证返回结果
        assert isinstance(result, GenerationResult)
        assert result.content == "Generated chapter content"

        # 验证 build_structured_context 被调用时传入了 scene_director
        mock_context_builder.build_structured_context.assert_called_once_with(
            novel_id="novel-1",
            chapter_number=1,
            outline="Chapter 1 outline",
            max_tokens=35000,
            scene_director=scene_director
        )

    @pytest.mark.asyncio
    async def test_generate_chapter_invalid_chapter_number(self, workflow):
        """测试无效的章节号"""
        with pytest.raises(ValueError, match="chapter_number must be positive"):
            await workflow.generate_chapter(
                novel_id="novel-1",
                chapter_number=0,
                outline="Chapter outline"
            )

    @pytest.mark.asyncio
    async def test_generate_chapter_empty_outline(self, workflow):
        """测试空大纲"""
        with pytest.raises(ValueError, match="outline cannot be empty"):
            await workflow.generate_chapter(
                novel_id="novel-1",
                chapter_number=1,
                outline=""
            )


class TestGenerateChapterWithReview:
    """测试 generate_chapter_with_review 方法"""

    @pytest.mark.asyncio
    async def test_generate_with_review_success(self, workflow):
        """测试带审查的生成成功"""
        content, report = await workflow.generate_chapter_with_review(
            novel_id="novel-1",
            chapter_number=1,
            outline="Chapter 1 outline"
        )

        assert content == "Generated chapter content"
        assert isinstance(report, ConsistencyReport)
        assert not report.has_critical_issues()


class TestSuggestOutline:
    """测试 suggest_outline"""

    @pytest.mark.asyncio
    async def test_suggest_outline_returns_llm_text(self, workflow, mock_context_builder, mock_llm_service):
        mock_context_builder.build_context = Mock(return_value="Mock context")
        mock_llm_service.generate = AsyncMock(
            return_value=LLMResult(
                content="1. 开场\n2. 转折",
                token_usage=TokenUsage(input_tokens=10, output_tokens=20),
            )
        )
        text = await workflow.suggest_outline("novel-1", 3)
        assert "开场" in text
        mock_llm_service.generate.assert_called_once()


class TestGenerateChapterStream:
    """测试 generate_chapter_stream 流式事件"""

    @pytest.mark.asyncio
    async def test_stream_emits_phases_chunk_and_done(self, workflow):
        events = []
        async for e in workflow.generate_chapter_stream("novel-1", 1, "Chapter outline"):
            events.append(e)
        types = [x["type"] for x in events]
        assert "phase" in types
        assert "chunk" in types
        assert events[-1]["type"] == "done"
        assert events[-1]["content"] == "Generated chapter content"
        assert events[-1]["token_count"] == 9250


class TestExtractChapterState:
    """测试 _extract_chapter_state 方法"""

    @pytest.mark.asyncio
    async def test_extract_chapter_state_from_content(self, workflow):
        """测试从内容中提取章节状态"""
        content = "Chapter content with character actions"

        state = await workflow._extract_chapter_state(content, chapter_number=1)

        assert isinstance(state, ChapterState)
        # 基本实现应该返回空列表
        assert isinstance(state.new_characters, list)
        assert isinstance(state.character_actions, list)
        assert isinstance(state.relationship_changes, list)


class TestBuildPrompt:
    """测试 _build_prompt 方法"""

    def test_build_prompt_with_context(self, workflow):
        """测试构建提示词"""
        prompt = workflow._build_prompt(
            context="Full context",
            outline="Chapter outline"
        )

        assert "Full context" in prompt.system
        assert "Chapter outline" in prompt.user

    def test_build_prompt_includes_storyline_and_tension(self, workflow):
        """故事线与情节张力应进入 system，供模型遵守"""
        prompt = workflow._build_prompt(
            context="CTX",
            outline="OL",
            storyline_context="主线：本章需触及 X",
            plot_tension="Expected tension: HIGH",
        )
        assert "主线" in prompt.system
        assert "HIGH" in prompt.system
        assert "CTX" in prompt.system

    def test_build_prompt_includes_style_bible_overlay(self, workflow):
        """选中写作手法档案时，overlay 应进入 system。"""
        prompt = workflow._build_prompt(
            context="CTX",
            outline="OL",
            style_overlay="【写作手法库】\n使用风格包：克制悬疑\n- 不复刻样本文字",
        )

        assert "【写作手法库】" in prompt.system
        assert "克制悬疑" in prompt.system
        assert "不复刻样本文字" in prompt.system

    def test_build_prompt_includes_coc_canon_overlay(self, workflow):
        """CoC 正典 overlay 应注入章节生成 prompt。"""
        workflow._current_novel_id = "novel-1"
        workflow.coc_canon_service = Mock()
        workflow.coc_canon_service.build_overlay.return_value = {
            "prompt": "【CoC正典】\n- [absolute] 夜巡制度：每晚三更点名。",
            "entries": [
                {"title": "夜巡制度", "level": "absolute"},
            ],
        }

        prompt = workflow._build_prompt(
            context="CTX",
            outline="OL",
        )

        assert "【CoC正典】" in prompt.system
        assert "夜巡制度" in prompt.system

    def test_build_prompt_includes_coc_clue_overlay(self, workflow):
        """CoC 线索边界 overlay 应注入章节生成 prompt。"""
        workflow._current_novel_id = "novel-1"
        workflow.coc_clue_service = Mock()
        workflow.coc_clue_service.build_overlay.return_value = {
            "prompt": "【CoC线索边界】\n- clue_key: ledger_owner | visibility: author_only",
            "clues": [
                {"clue_key": "ledger_owner", "visibility": "author_only"},
            ],
        }

        prompt = workflow._build_prompt(
            context="CTX",
            outline="OL",
        )

        assert "【CoC线索边界】" in prompt.system
        assert "ledger_owner" in prompt.system

    def test_build_prompt_includes_genre_overlay_for_suspense(self, workflow):
        """章节生成应根据上下文/大纲注入类型写法规则。"""
        prompt = workflow._build_prompt(
            context="类型：悬疑调查。主角正在追查旧档案里的异常案件。",
            outline="林默在废弃研究所发现一枚被调包的门禁卡，并误判了嫌疑人的动机。",
        )

        assert "【类型写法规则】" in prompt.system
        assert "悬疑/调查" in prompt.system
        assert "线索" in prompt.system
        assert "误判" in prompt.system

    def test_build_prompt_includes_chapter_contract_and_reader_audit(self, workflow):
        """章节生成应先约束本章任务，避免空大纲时写成概念解释。"""
        prompt = workflow._build_prompt(
            context="类型：悬疑调查。前情：林默拿到旧研究所门禁卡。",
            outline="",
        )

        assert "【好看优先：章节戏剧任务】" in prompt.system
        assert "内部场景推进表" in prompt.system
        assert "场景任务" in prompt.system
        assert "检测器分数不是写作目标" in prompt.system
        assert "【追读自检】" in prompt.system
        assert "未完成问题" in prompt.system

    def test_build_prompt_includes_detector_calibration_fact_anchors(self, workflow):
        """章节生成应注入从真人检测样本提炼出的事实锚点写法。"""
        prompt = workflow._build_prompt(
            context="类型：悬疑调查。前情：林默拿到旧研究所门禁卡。",
            outline="主角核对监控日志，发现摄像头角度和票据时间对不上。",
        )

        assert "【检测器校准：事实锚点写法】" in prompt.system
        assert "门禁编号" in prompt.system
        assert "数据/物件/流程" in prompt.system

    def test_build_prompt_uses_target_word_count_range(self, workflow):
        """指定目标字数时，应给模型明确的允许区间。"""
        prompt = workflow._build_prompt(
            context="CTX",
            outline="OL",
            target_word_count=2500,
        )

        assert "本章目标 2500 字" in prompt.system
        assert "2375-2625 字" in prompt.system

    def test_build_prompt_uses_custom_word_tolerance_range(self, workflow):
        """自定义容差应改变区间。"""
        prompt = workflow._build_prompt(
            context="CTX",
            outline="OL",
            target_word_count=2500,
            word_tolerance_ratio=0.1,
        )

        assert "本章目标 2500 字" in prompt.system
        assert "2250-2750 字" in prompt.system

    def test_direct_writing_prompt_includes_detector_calibration(self, workflow):
        """直接写作对照模式也应带事实锚点，避免纯文学化顺滑稿。"""
        prompt = workflow._build_direct_writing_prompt(
            context="都市逆袭，主角手里有项目合同和会议纪要。",
            outline="主角在会议上核对合同编号，反制夺功上司。",
        )

        assert "【检测器校准：事实锚点写法】" in prompt.system
        assert "合同条款" in prompt.system
        assert "事实锚点" in prompt.system

    def test_direct_writing_prompt_uses_target_word_count_range(self, workflow):
        """直接写作也要遵守目标字数。"""
        prompt = workflow._build_direct_writing_prompt(
            context="CTX",
            outline="OL",
            target_word_count=2500,
        )

        assert "目标 2500 中文字" in prompt.system
        assert "2375-2625 字" in prompt.system

    @pytest.mark.asyncio
    async def test_enforce_chapter_word_target_trims_when_exceed_max(self, workflow):
        """目标字数存在时，应硬裁剪超长正文。"""
        long_text = ("监控屏幕闪了一下，白雨翔盯着那条时间戳。") * 220
        result = await workflow._enforce_chapter_word_target(
            content=long_text,
            outline="白雨翔在站厅核对灰卡时间戳。",
            target_word_count=2500,
        )
        assert AutoNovelGenerationWorkflow._story_text_units(result) <= 2625

    @pytest.mark.asyncio
    async def test_enforce_chapter_word_target_smooths_hard_truncated_tail(self, workflow):
        """裁剪后若停在半句，应自动收束成完整句尾。"""
        source = (
            "白雨翔贴着站台边缘走，鞋底每次落下都带起一点潮气。"
            "他没有回头，只把旧记者证压在掌心里，指节泛白。"
            "许照在后方低声提醒：监控时间戳正在回跳。"
        )
        long_tail = "他盯着门缝里的影子一步一步往前没有停下没有回头没有回答" * 180
        long_text = source + long_tail

        result = await workflow._enforce_chapter_word_target(
            content=long_text,
            outline="白雨翔在地铁站内核对灰卡与监控。",
            target_word_count=2500,
        )
        assert AutoNovelGenerationWorkflow._story_text_units(result) <= 2625
        assert AutoNovelGenerationWorkflow._is_sentence_tail_complete(result) is True

    @pytest.mark.asyncio
    async def test_enforce_chapter_word_target_soft_lands_trimmed_tail(self, workflow, mock_llm_service):
        """命中上限时应允许对尾段做软着陆改写，避免突兀硬切。"""
        long_text = (
            "白雨翔把灰卡顶在灯下，红点像一粒被烤过的盐。"
            "许照没有催，只看着门缝里那只白手套。"
            "站台风从隧道口灌进来，把警戒带吹得贴在地砖上。"
        ) + ("他盯着门缝往前走没有停下没有回头没有回答" * 220)

        mock_llm_service.generate = AsyncMock(return_value=LLMResult(
            content=(
                "门缝后的笔尖声突然停了。许照没再说话，只把掌心压在枪套外侧，指节一寸寸收紧。"
                "白雨翔把灰卡抬高，让红点正对灯光，灯管在卡面上拖出一截细长的反光。"
                "站台尽头传来列车进洞前的低频闷响，警戒带被风扯起又落下，像有人在暗处试着打拍子。"
                "白手套在门缝里停了一秒，像在确认什么，然后慢慢伸得更近。"
                "陈泊舟没有抬枪，只侧过半步挡住白雨翔的肩线，声音压得很低：“别先给，先看他要哪一面。”"
                "白雨翔指尖一紧，卡片边缘硌进掌纹，他把编号那一侧慢慢转过去，让门缝后的人先看到最后三位。"
            ),
            token_usage=TokenUsage(input_tokens=90, output_tokens=120),
        ))

        result = await workflow._enforce_chapter_word_target(
            content=long_text,
            outline="地铁站灰卡异常，章末抛出更高风险。",
            target_word_count=2500,
        )
        assert mock_llm_service.generate.await_count >= 1
        assert AutoNovelGenerationWorkflow._story_text_units(result) <= 2625
        assert AutoNovelGenerationWorkflow._is_sentence_tail_complete(result) is True

    def test_smooth_truncated_tail_falls_back_to_punctuation_boundary(self, workflow):
        """若尾段无标点，优先回退到最近完整句边界。"""
        long_sentence = "现场灯管在潮气里反复嘶鸣，白雨翔沿着站台边缘缓慢移动，脚下每一步都试探着缝隙里的回声，" * 24
        text = (
            f"{long_sentence}。"
            "第二句完整。"
            "第三句前半段没有结束一直往前拖没有句号没有停顿没有收束"
        )
        smoothed = workflow._smooth_truncated_tail(text, min_words=700)
        assert smoothed.endswith("。")
        assert "第三句前半段" not in smoothed

    def test_build_prompt_includes_visible_chapter_strategy(self, workflow):
        prompt = workflow._build_prompt(
            context="CTX",
            outline="OL",
            chapter_strategy={
                "dramatic_task": {
                    "goal": "拿到账本",
                    "obstacle": "账房先生拖延",
                    "reader_expectation": "看到主角试探出破绽",
                    "ending_hook": "账本里藏着另一人的名字",
                },
                "scene_plan": [
                    {
                        "label": "试探账房",
                        "task": "逼对方交出账本",
                        "resistance": "对方装糊涂",
                        "info_shift": "主角确认账本被换过",
                        "relationship_shift": "彼此戒心升级",
                        "anchor": "沾了墨的账页",
                        "hook": "账页角落的签名不对",
                        "target_words": 900,
                    }
                ],
                "writing_focus": ["开头立刻进场，不先解释背景。"],
            },
        )

        assert "【本章写作策略（已确认，必须执行）】" in prompt.system
        assert "拿到账本" in prompt.system
        assert "账页角落的签名不对" in prompt.system

    def test_build_strategy_prompt_requests_show_dont_tell_contract(self, workflow):
        prompt = workflow._build_strategy_prompt(
            context="CTX",
            outline="白雨翔追查灰卡。",
            target_word_count=2500,
            word_tolerance_ratio=0.05,
        )

        assert "chapter_contract" in prompt.system
        assert "show_dont_tell_rules" in prompt.system
        assert "visible_action" in prompt.system
        assert "subtext_dialogue" in prompt.system
        assert "unspoken_emotion" in prompt.system
        assert "object_or_clue_change" in prompt.system
        assert "少解释，多展示" in prompt.system

    def test_build_strategy_overlay_includes_show_dont_tell_contract(self, workflow):
        overlay = workflow._build_strategy_overlay(
            {
                "chapter_contract": {
                    "chapter_question": "灰卡是谁写入的？",
                    "protagonist_want": "白雨翔要确认写卡器来源。",
                    "opposition": "许照只给半份证据。",
                    "reader_expectation": "看到两人互相试探。",
                    "required_information_change": "伪造签名暴露。",
                    "required_relationship_change": "形成有限合作。",
                    "ending_question": "谁借用了审计流程？",
                    "show_dont_tell_rules": ["不能写他感到怀疑，只能写他扣住证物。"],
                },
                "dramatic_task": {
                    "goal": "确认写卡器来源",
                    "obstacle": "许照保留证据",
                    "reader_expectation": "看到试探",
                    "ending_hook": "审计流程异常",
                },
                "scene_plan": [],
                "writing_focus": [],
            }
        )

        assert "章节合同" in overlay
        assert "灰卡是谁写入的" in overlay
        assert "展示优先" in overlay
        assert "扣住证物" in overlay

    def test_build_scene_budget_overlay_includes_showing_fields(self, workflow):
        overlay = workflow._build_scene_budget_overlay(
            {
                "label": "核对签收单",
                "task": "确认签名真伪",
                "resistance": "许照不交原件",
                "info_shift": "签名疑点出现",
                "relationship_shift": "有限合作",
                "anchor": "证物袋",
                "visible_action": "白雨翔按住证物袋封口。",
                "subtext_dialogue": "表面问流程，实际逼许照露底。",
                "unspoken_emotion": "怀疑不能直说。",
                "object_or_clue_change": "灰卡变成伪造链条证据。",
                "hook": "审计流程异常",
                "target_words": 800,
                "min_words": 720,
                "max_words": 880,
            }
        )

        assert "白雨翔按住证物袋封口" in overlay
        assert "表面问流程" in overlay
        assert "怀疑不能直说" in overlay
        assert "灰卡变成伪造链条证据" in overlay

    def test_resolve_scene_budget_plan_matches_beat_count(self, workflow, monkeypatch):
        monkeypatch.setenv("PLOTPILOT_SCENE_BUDGET_ENFORCED", "1")
        plan = workflow._resolve_scene_budget_plan(
            chapter_strategy={
                "scene_plan": [
                    {"label": "场景1", "task": "推进", "resistance": "阻力", "info_shift": "变化", "relationship_shift": "变化", "anchor": "灰卡", "hook": "门响", "target_words": 900},
                    {"label": "场景2", "task": "推进", "resistance": "阻力", "info_shift": "变化", "relationship_shift": "变化", "anchor": "监控", "hook": "停电", "target_words": 800},
                ]
            },
            target_word_count=2500,
            word_tolerance_ratio=0.05,
            beat_count=4,
        )
        assert len(plan) == 4
        assert all(int(item["target_words"]) > 0 for item in plan)

    def test_extract_forbidden_patterns_from_style_overlay(self, workflow):
        overlay = "\n".join(
            [
                "【写作手法库】",
                "禁用项：",
                "- 经过一番交谈后",
                "- 很快达成共识",
                "",
                "执行要求：",
                "- 保留动作链",
            ]
        )
        patterns = workflow._extract_forbidden_patterns_from_style_overlay(overlay)
        assert patterns == ["经过一番交谈后", "很快达成共识"]

    def test_direct_writing_prompt_includes_visible_chapter_strategy(self, workflow):
        prompt = workflow._build_direct_writing_prompt(
            context="CTX",
            outline="OL",
            chapter_strategy={
                "dramatic_task": {
                    "goal": "确认嫌疑人身份",
                    "obstacle": "对方提前封口",
                    "reader_expectation": "看到现场误判",
                    "ending_hook": "真正目标提前离场",
                },
                "scene_plan": [],
                "writing_focus": ["对白里保留试探。"],
            },
        )

        assert "【本章写作策略（已确认，必须执行）】" in prompt.system
        assert "确认嫌疑人身份" in prompt.system

    @pytest.mark.asyncio
    async def test_generate_chapter_stream_emits_long_draft_plan(self, workflow, mock_llm_service):
        async def direct_stream(*args, **kwargs):
            yield "第一段。"
            yield "第二段。"

        mock_llm_service.stream_generate = direct_stream
        events = [
            event async for event in workflow.generate_chapter_stream(
                novel_id="novel-1",
                chapter_number=1,
                outline="主角进入旧档案室调查灰卡来源。",
                direct_writing_mode=True,
                target_word_count=2500,
                long_draft_mode=True,
                long_draft_split_count=3,
            )
        ]
        plan_event = next(event for event in events if event["type"] == "long_draft_plan")
        assert plan_event["enabled"] is True
        assert plan_event["split_count"] == 3
        assert int(plan_event["target_word_count"]) >= 7000
        done_event = next(event for event in events if event["type"] == "done")
        assert done_event["long_draft_mode"] is True
        assert done_event["long_draft_split_count"] == 3

    def test_build_prompt_includes_next_chapter_bridge_overlay(self, workflow):
        prompt = workflow._build_prompt(
            context="CTX",
            outline="OL",
            next_chapter_bridge="【下一章承接设定（长章前摄）】\n- 下一章要交付灰卡。",
        )
        assert "【下一章承接设定（长章前摄）】" in prompt.system
        assert "下一章要交付灰卡" in prompt.system

    def test_build_next_chapter_bridge_overlay_auto_reads_next_story_node(self, workflow):
        workflow.context_builder.story_node_repository = SimpleNamespace(
            get_by_novel_sync=lambda _novel_id: [
                SimpleNamespace(
                    node_type=SimpleNamespace(value="chapter"),
                    number=2,
                    title="门禁卡背面的名字",
                    outline="白雨翔确认灰卡背后组织的第一个公开代理人，并发现监控时间戳被二次篡改。",
                    description="",
                    content="",
                )
            ]
        )
        overlay = workflow._build_next_chapter_bridge_overlay(
            novel_id="novel-1",
            chapter_number=1,
            target_word_count=4500,
            chapter_strategy=None,
        )
        assert "【下一章承接设定（长章前摄）】" in overlay
        assert "第2章《门禁卡背面的名字》" in overlay
        assert "监控时间戳被二次篡改" in overlay

    def test_build_next_chapter_bridge_overlay_keeps_manual_notes_for_short_chapter(self, workflow):
        overlay = workflow._build_next_chapter_bridge_overlay(
            novel_id="novel-1",
            chapter_number=1,
            target_word_count=2500,
            chapter_strategy={
                "next_chapter_setup": "下一章主冲突是灰卡交接失败导致身份暴露。",
            },
        )
        assert "手动设定" in overlay
        assert "灰卡交接失败导致身份暴露" in overlay

    def test_normalize_strategy_payload_has_fallback_shape(self):
        payload = AutoNovelGenerationWorkflow._normalize_strategy_payload({}, outline="主角去仓库查账。", target_word_count=2500)

        assert payload["chapter_contract"]["chapter_question"]
        assert payload["dramatic_task"]["goal"]
        assert len(payload["scene_plan"]) >= 2
        assert payload["scene_plan"][0]["target_words"] >= 500
        assert payload["scene_plan"][0]["visible_action"]
        assert payload["writing_focus"]

    def test_normalize_strategy_payload_includes_chapter_contract(self, workflow):
        payload = workflow._normalize_strategy_payload(
            {
                "chapter_contract": {
                    "chapter_question": "灰卡为什么还能刷开门禁？",
                    "protagonist_want": "白雨翔要确认 774 写卡器是否被截留。",
                    "opposition": "许照只交出部分证据。",
                    "reader_expectation": "看到两个人从对抗到有限合作。",
                    "required_information_change": "签收记录从嫌疑证据变成伪造证据。",
                    "required_relationship_change": "白雨翔和许照互相保留但开始交换证据。",
                    "ending_question": "操盘者是否借用了内部审计流程？",
                    "show_dont_tell_rules": [
                        "不能写白雨翔感到怀疑，只能写他追问和扣住证物。",
                        "对白不能每句完整回答，允许反问和避重就轻。",
                    ],
                },
                "scene_plan": [
                    {
                        "label": "核对签收单",
                        "task": "逼出 774 的异常入库记录",
                        "resistance": "许照不给完整文件",
                        "info_shift": "扫描件的模糊签名变成疑点",
                        "relationship_shift": "两人从互相试探进入有限合作",
                        "anchor": "证物袋和灰卡划痕",
                        "hook": "签名不属于当前习惯",
                        "target_words": 900,
                        "visible_action": "白雨翔把证物袋封口按住，不让许照立刻收走。",
                        "subtext_dialogue": "表面问流程，实际确认许照掌握多少证据。",
                        "unspoken_emotion": "怀疑和防备不能直说。",
                        "object_or_clue_change": "灰卡从拾获物变成伪造链条证据。",
                    }
                ],
                "writing_focus": ["少解释，多用动作和证物推进。"],
            },
            outline="白雨翔追查灰卡。",
            target_word_count=2500,
            word_tolerance_ratio=0.05,
        )

        contract = payload["chapter_contract"]
        assert contract["chapter_question"] == "灰卡为什么还能刷开门禁？"
        assert "扣住证物" in contract["show_dont_tell_rules"][0]

        scene = payload["scene_plan"][0]
        assert scene["visible_action"].startswith("白雨翔把证物袋")
        assert scene["subtext_dialogue"].startswith("表面问流程")
        assert scene["unspoken_emotion"] == "怀疑和防备不能直说。"
        assert scene["object_or_clue_change"].startswith("灰卡从拾获物")

    def test_normalize_editorial_review_payload_has_fallback_shape(self):
        payload = AutoNovelGenerationWorkflow._normalize_editorial_review_payload({})

        assert payload["summary"]
        assert payload["verdict"]
        assert set(payload["scores"].keys()) == {"opening", "conflict", "character", "dialogue", "hook", "pacing", "showing"}
        assert payload["strengths"]
        assert payload["problems"]
        assert payload["actions"]

    def test_normalize_editorial_review_payload_includes_showing_score(self, workflow):
        payload = workflow._normalize_editorial_review_payload(
            {
                "summary": "对白有张力，但解释略多。",
                "scores": {
                    "opening": 88,
                    "conflict": 90,
                    "character": 86,
                    "dialogue": 84,
                    "hook": 92,
                    "pacing": 87,
                    "showing": 79,
                },
                "strengths": ["证物动作具体。"],
                "problems": ["部分情绪仍被直接命名。"],
                "actions": ["把解释改成动作。"],
                "verdict": "可优化后使用",
            }
        )

        assert payload["scores"]["showing"] == 79

    def test_coerce_llm_content_to_text_accepts_structured_payload(self):
        text = AutoNovelGenerationWorkflow._coerce_llm_content_to_text([{"goal": "拿到账本"}])
        assert "拿到账本" in text

    def test_coerce_llm_content_to_text_accepts_content_parts(self):
        text = AutoNovelGenerationWorkflow._coerce_llm_content_to_text(
            [
                {"type": "text", "text": '{"dramatic_task":{"goal":"拿到账本"}}'},
                {"type": "reasoning", "text": "思考过程"},
            ]
        )
        assert '"dramatic_task"' in text
        assert "思考过程" not in text

    def test_parse_llm_json_payload_accepts_list_root(self, workflow):
        data, errs = workflow._parse_llm_json_payload([{"goal": "拿到账本"}])
        assert data == {"goal": "拿到账本"}
        assert isinstance(errs, list)

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("都市逆袭，主角在会议上被上司夺功。", "urban"),
            ("玄幻仙侠，宗门试炼中法器失控。", "cultivation"),
            ("古言宅斗，侯府婚约牵动家族利益。", "historical_romance"),
            ("现言甜宠，豪门总裁与替身关系拉扯。", "romance"),
            ("漫画信号转小说，保留第一眼视觉冲突。", "comic_adaptation"),
        ],
    )
    def test_infer_genre_key_for_common_webnovel_types(self, text, expected):
        """常见热门网文类型应能映射到对应写法规则。"""
        assert AutoNovelGenerationWorkflow._infer_genre_key(text) == expected

    def test_build_prompt_passes_genre_overlay_to_visible_prompt(self, workflow, monkeypatch):
        """提示词广场模板可直接使用 genre_overlay 变量。"""
        class FakePromptManager:
            def ensure_seeded(self):
                return True

            def render(self, node_key, variables):
                assert node_key == "workflow-chapter-generation"
                assert "genre_overlay" in variables
                assert "都市爽文" in variables["genre_overlay"]
                return {
                    "system": "VISIBLE SYSTEM\n{genre_overlay}",
                    "user": "VISIBLE USER",
                }

        monkeypatch.setattr(
            "infrastructure.ai.prompt_manager.get_prompt_manager",
            lambda: FakePromptManager(),
        )

        prompt = workflow._build_prompt(
            context="都市逆袭，主角被上司压制，手里握着项目证据。",
            outline="主角在会议上被夺功，临场反制并留下更大对手。",
        )

        assert prompt.system.startswith("VISIBLE SYSTEM")

    def test_build_prompt_uses_visible_prompt_config(self, workflow, monkeypatch):
        """工作流章节生成应优先读取提示词广场中的可视配置。"""
        class FakePromptManager:
            def ensure_seeded(self):
                return True

            def render(self, node_key, variables):
                assert node_key == "workflow-chapter-generation"
                assert variables["context"] == "CTX"
                assert variables["outline"] == "OL"
                return {
                    "system": "VISIBLE SYSTEM {unused}",
                    "user": "VISIBLE USER",
                }

        monkeypatch.setattr(
            "infrastructure.ai.prompt_manager.get_prompt_manager",
            lambda: FakePromptManager(),
        )

        prompt = workflow._build_prompt(context="CTX", outline="OL")

        assert prompt.system == "VISIBLE SYSTEM {unused}"
        assert prompt.user == "VISIBLE USER\n\n开始撰写："

    def test_build_prompt_falls_back_when_visible_config_is_empty(self, workflow, monkeypatch):
        """提示词广场节点为空时应回退到内置模板，避免生成请求缺 System。"""
        class FakePromptManager:
            def ensure_seeded(self):
                return True

            def render(self, node_key, variables):
                return {"system": "", "user": "VISIBLE USER"}

        monkeypatch.setattr(
            "infrastructure.ai.prompt_manager.get_prompt_manager",
            lambda: FakePromptManager(),
        )

        prompt = workflow._build_prompt(context="CTX", outline="OL")

        assert "你是一位专业的网络小说作家" in prompt.system
        assert "请根据以下大纲撰写本章内容" in prompt.user

class TestConflictDetectionIntegration:
    """测试冲突检测集成"""

    @pytest.mark.asyncio
    async def test_generate_chapter_includes_ghost_annotations(
        self,
        mock_context_builder,
        mock_consistency_checker,
        mock_storyline_manager,
        mock_plot_arc_repository,
        mock_llm_service
    ):
        """测试生成章节时包含幽灵批注"""
        from application.services.conflict_detection_service import ConflictDetectionService
        from application.dtos.ghost_annotation import GhostAnnotation
        from domain.bible.repositories.bible_repository import BibleRepository
        from domain.bible.entities.bible import Bible
        from domain.bible.entities.character import Character
        from domain.novel.value_objects.novel_id import NovelId

        # Mock ConflictDetectionService
        mock_conflict_service = Mock(spec=ConflictDetectionService)
        mock_conflict_service.detect.return_value = [
            GhostAnnotation(
                type="setting_conflict",
                severity="warning",
                message="设定库中李明为 [水系]，此处使用了 [火系]",
                entity_id="char-001",
                entity_name="李明",
                expected="水系",
                actual="火系"
            )
        ]

        # Mock BibleRepository
        mock_bible_repo = Mock(spec=BibleRepository)
        mock_bible = Mock(spec=Bible)
        mock_bible.characters = [
            Mock(spec=Character, id="char-001", name="李明", description="水系法师", attributes={})
        ]
        mock_bible.locations = []
        mock_bible_repo.get_by_novel_id.return_value = mock_bible

        # 创建带冲突检测的工作流
        workflow = AutoNovelGenerationWorkflow(
            context_builder=mock_context_builder,
            consistency_checker=mock_consistency_checker,
            storyline_manager=mock_storyline_manager,
            plot_arc_repository=mock_plot_arc_repository,
            llm_service=mock_llm_service,
            conflict_detection_service=mock_conflict_service,
            bible_repository=mock_bible_repo
        )

        result = await workflow.generate_chapter(
            novel_id="novel-1",
            chapter_number=1,
            outline="李明释放火球术攻击敌人"
        )

        # 验证返回结果包含批注
        assert isinstance(result, GenerationResult)
        assert len(result.ghost_annotations) == 1
        assert result.ghost_annotations[0].type == "setting_conflict"
        assert result.ghost_annotations[0].severity == "warning"
        assert "李明" in result.ghost_annotations[0].message
        assert "水系" in result.ghost_annotations[0].message
        assert "火系" in result.ghost_annotations[0].message

        # 验证冲突检测服务被调用
        mock_conflict_service.detect.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_chapter_no_annotations_when_no_conflicts(
        self,
        mock_context_builder,
        mock_consistency_checker,
        mock_storyline_manager,
        mock_plot_arc_repository,
        mock_llm_service
    ):
        """测试无冲突时返回空批注列表"""
        from application.services.conflict_detection_service import ConflictDetectionService

        # Mock ConflictDetectionService 返回空列表
        mock_conflict_service = Mock(spec=ConflictDetectionService)
        mock_conflict_service.detect.return_value = []

        workflow = AutoNovelGenerationWorkflow(
            context_builder=mock_context_builder,
            consistency_checker=mock_consistency_checker,
            storyline_manager=mock_storyline_manager,
            plot_arc_repository=mock_plot_arc_repository,
            llm_service=mock_llm_service,
            conflict_detection_service=mock_conflict_service
        )

        result = await workflow.generate_chapter(
            novel_id="novel-1",
            chapter_number=1,
            outline="李明与王总对话"
        )

        # 验证返回空批注列表
        assert isinstance(result, GenerationResult)
        assert len(result.ghost_annotations) == 0

    @pytest.mark.asyncio
    async def test_generate_chapter_without_conflict_service(
        self,
        workflow
    ):
        """测试没有冲突检测服务时不报错"""
        # workflow fixture 默认没有 conflict_detection_service
        result = await workflow.generate_chapter(
            novel_id="novel-1",
            chapter_number=1,
            outline="Chapter outline"
        )

        # 验证不报错，返回空批注列表
        assert isinstance(result, GenerationResult)
        assert len(result.ghost_annotations) == 0

    @pytest.mark.asyncio
    async def test_generate_chapter_stream_includes_ghost_annotations(
        self,
        mock_context_builder,
        mock_consistency_checker,
        mock_storyline_manager,
        mock_plot_arc_repository,
        mock_llm_service
    ):
        """测试流式生成时包含幽灵批注"""
        from application.services.conflict_detection_service import ConflictDetectionService
        from application.dtos.ghost_annotation import GhostAnnotation

        # Mock ConflictDetectionService
        mock_conflict_service = Mock(spec=ConflictDetectionService)
        mock_conflict_service.detect.return_value = [
            GhostAnnotation(
                type="setting_conflict",
                severity="warning",
                message="测试批注",
                entity_id="char-001",
                entity_name="测试角色"
            )
        ]

        workflow = AutoNovelGenerationWorkflow(
            context_builder=mock_context_builder,
            consistency_checker=mock_consistency_checker,
            storyline_manager=mock_storyline_manager,
            plot_arc_repository=mock_plot_arc_repository,
            llm_service=mock_llm_service,
            conflict_detection_service=mock_conflict_service
        )

        events = []
        async for event in workflow.generate_chapter_stream(
            novel_id="novel-1",
            chapter_number=1,
            outline="测试大纲"
        ):
            events.append(event)

        # 验证最后的 done 事件包含批注
        done_event = events[-1]
        assert done_event["type"] == "done"
        assert "ghost_annotations" in done_event
        assert len(done_event["ghost_annotations"]) == 1
        assert done_event["ghost_annotations"][0]["type"] == "setting_conflict"
        assert done_event["ghost_annotations"][0]["message"] == "测试批注"


class TestStyleIntegration:
    """测试风格指纹和俗套扫描集成"""

    @pytest.mark.asyncio
    async def test_generate_chapter_includes_style_warnings(
        self,
        mock_context_builder,
        mock_consistency_checker,
        mock_storyline_manager,
        mock_plot_arc_repository,
        mock_llm_service
    ):
        """测试生成章节时包含风格警告"""
        from application.services.cliche_scanner import ClicheScanner, ClicheHit

        # Mock ClicheScanner
        mock_scanner = Mock(spec=ClicheScanner)
        mock_scanner.scan_cliches.return_value = [
            ClicheHit(
                pattern="熊熊系列",
                text="熊熊烈火",
                start=10,
                end=14,
                severity="warning"
            ),
            ClicheHit(
                pattern="眼神闪过系列",
                text="眼中闪过一丝",
                start=50,
                end=57,
                severity="warning"
            )
        ]

        # 创建带俗套扫描的工作流
        workflow = AutoNovelGenerationWorkflow(
            context_builder=mock_context_builder,
            consistency_checker=mock_consistency_checker,
            storyline_manager=mock_storyline_manager,
            plot_arc_repository=mock_plot_arc_repository,
            llm_service=mock_llm_service,
            cliche_scanner=mock_scanner
        )

        result = await workflow.generate_chapter(
            novel_id="novel-1",
            chapter_number=1,
            outline="测试大纲"
        )

        # 验证返回结果包含风格警告
        assert isinstance(result, GenerationResult)
        assert len(result.style_warnings) == 2
        assert result.style_warnings[0].pattern == "熊熊系列"
        assert result.style_warnings[0].text == "熊熊烈火"
        assert result.style_warnings[1].pattern == "眼神闪过系列"

        # 验证扫描器至少扫描了初稿
        mock_scanner.scan_cliches.assert_any_call("Generated chapter content")

    def test_human_texture_risk_detects_short_polished_not_structures(self):
        """短段比例过高且“不是”结构密集时，应判定为过度工整风险。"""
        text = (
            "不是同步。\n\n"
            "不是刷量。\n\n"
            "不是老周。\n\n"
            "沈铎没说话。\n\n"
            "苏晚看着屏幕。\n\n"
            "不是提示音，是屏幕右下角闪了一下。\n\n"
        ) * 10

        assert AutoNovelGenerationWorkflow._needs_human_texture_pass(text) is True

    def test_motif_repetition_detects_over_unified_generated_texture(self):
        """核心母题词过度复现时，应触发人工余量降噪。"""
        text = (
            "虹彩沿着肺泡蔓延，十七次呼吸把坐标推到墙面。\n\n"
            "周正明听见虹彩里的呼吸，肺叶按十七次收缩。\n\n"
            "拓片上的坐标、虹彩、肺和呼吸再次重合。\n\n"
        ) * 10

        terms = AutoNovelGenerationWorkflow._detector_repetition_terms(text)

        assert "虹彩" in terms
        assert "呼吸" in terms
        assert "十七" in terms
        assert AutoNovelGenerationWorkflow._needs_human_residue_pass(text) is True

    def test_detector_repetition_detects_overused_like_and_weather_texture(self):
        """普通比喻和雨水冷等场景母题过密时，也应触发降噪。"""
        text = (
            "雨水从门缝里挤进来，冷意贴着手背，像有人在桌下敲门。\n\n"
            "雨声又重了一层，水痕沿着纸角散开，冷得像旧铁片。\n\n"
            "他看着水痕，雨还在响，门禁扣裂口里有铁锈味，像没晾干的证物袋。\n\n"
        ) * 10

        terms = AutoNovelGenerationWorkflow._detector_repetition_terms(text)

        assert "像" in terms
        assert "雨" in terms
        assert "水" in terms
        assert AutoNovelGenerationWorkflow._needs_human_residue_pass(text) is True

    def test_detector_repetition_dynamically_detects_genre_motifs(self):
        """不同题材的高频意象应被动态识别，而不是依赖固定词表。"""
        text = (
            "灵气贴着丹田转了一圈，剑光从石壁上掠过去。\n\n"
            "他压住丹田里的灵气，仍看见剑光在经脉边缘发亮。\n\n"
            "经脉一跳，灵气又回到丹田，剑光却没有散。\n\n"
        ) * 12

        terms = AutoNovelGenerationWorkflow._detector_repetition_terms(text)

        assert "灵气" in terms
        assert "丹田" in terms
        assert "剑光" in terms
        assert AutoNovelGenerationWorkflow._needs_human_residue_pass(text) is True

    def test_human_texture_risk_detects_too_many_plain_like_metaphors(self):
        """大量普通“像……”比喻会制造疑似AI的统一镜头感。"""
        text = ("雨点像指节，灯光像刀背，纸页像湿掉的皮肤。\n\n") * 25

        assert AutoNovelGenerationWorkflow._needs_human_texture_pass(text) is True

    def test_soft_cap_detector_motifs_no_longer_mechanically_rewrites_numbers(self):
        """最终收尾不能再用字符串替换制造“三旧值/上一组读数”等怪词。"""
        text = ("每分钟十七次呼吸。十七。每分钟十九次呼吸。十九。\n") * 12

        capped = AutoNovelGenerationWorkflow._soft_cap_detector_motifs(text)

        assert capped == text
        for artifact in ("旧值", "上一组读数", "那个旧节拍", "刚变过的值"):
            assert artifact not in capped

    @pytest.mark.asyncio
    async def test_generate_chapter_naturalizes_ai_flavored_draft_before_returning(
        self,
        mock_context_builder,
        mock_consistency_checker,
        mock_storyline_manager,
        mock_plot_arc_repository,
        mock_llm_service
    ):
        """命中 AI 味后，应先自然化改写，再把结果返回给前端。"""
        from application.services.cliche_scanner import ClicheScanner, ClicheHit

        ai_draft = "空气仿佛凝固了，他心中五味杂陈。" * 20
        naturalized = "雨水顺着窗缝渗进来。他把杯子往里推了半寸，没接那句话。" * 20
        mock_llm_service.generate = AsyncMock(side_effect=[
            LLMResult(content=ai_draft, token_usage=TokenUsage(input_tokens=500, output_tokens=500)),
            LLMResult(content=naturalized, token_usage=TokenUsage(input_tokens=300, output_tokens=300)),
        ])

        mock_scanner = Mock(spec=ClicheScanner)
        mock_scanner.scan_cliches.side_effect = [
            [
                ClicheHit(pattern="氛围凝固系列", text="空气仿佛凝固", start=0, end=6, severity="warning"),
                ClicheHit(pattern="五味杂陈系列", text="心中五味杂陈", start=8, end=14, severity="warning"),
            ],
            [],
        ]

        workflow = AutoNovelGenerationWorkflow(
            context_builder=mock_context_builder,
            consistency_checker=mock_consistency_checker,
            storyline_manager=mock_storyline_manager,
            plot_arc_repository=mock_plot_arc_repository,
            llm_service=mock_llm_service,
            cliche_scanner=mock_scanner,
            state_extractor=Mock(extract_chapter_state=AsyncMock(return_value=ChapterState([], [], [], [], [], []))),
        )

        result = await workflow.generate_chapter(
            novel_id="novel-1",
            chapter_number=1,
            outline="测试大纲",
            enable_beats=False,
        )

        assert result.content == naturalized
        assert result.style_warnings == []
        assert mock_llm_service.generate.await_count == 2
        rewrite_prompt = mock_llm_service.generate.await_args_list[1].args[0]
        assert "AI味" in rewrite_prompt.system
        assert ai_draft in rewrite_prompt.user

    @pytest.mark.asyncio
    async def test_naturalizer_uses_prompt_plaza_node_when_available(
        self,
        mock_context_builder,
        mock_consistency_checker,
        mock_storyline_manager,
        mock_plot_arc_repository,
        mock_llm_service,
        monkeypatch
    ):
        """AI 味改写应优先读取提示词广场节点，便于用户在线调参。"""
        from application.services.cliche_scanner import ClicheScanner, ClicheHit

        ai_draft = "空气仿佛凝固了。他心中五味杂陈。" * 20
        mock_llm_service.generate = AsyncMock(return_value=LLMResult(
            content="改写后的自然正文。" * 50,
            token_usage=TokenUsage(input_tokens=300, output_tokens=300),
        ))

        class FakePromptManager:
            def ensure_seeded(self):
                return True

            def render(self, node_key, variables):
                assert node_key == "rewrite-ai-flavor-naturalizer"
                assert variables["draft"] == ai_draft
                assert "测试大纲" in variables["must_keep"]
                assert variables["rewrite_goal"] == "降低AI味，保留剧情事实，增强阅读沉浸"
                assert "不是X，是Y" in variables["taboo_phrases"]
                return {
                    "system": "来自提示词广场的去AI味系统提示",
                    "user": "来自提示词广场的去AI味用户提示：{draft}",
                }

        monkeypatch.setattr(
            "infrastructure.ai.prompt_manager.get_prompt_manager",
            lambda: FakePromptManager(),
        )
        mock_scanner = Mock(spec=ClicheScanner)
        mock_scanner.scan_cliches.return_value = [
            ClicheHit(pattern="氛围凝固系列", text="空气仿佛凝固", start=0, end=6, severity="warning")
        ]
        workflow = AutoNovelGenerationWorkflow(
            context_builder=mock_context_builder,
            consistency_checker=mock_consistency_checker,
            storyline_manager=mock_storyline_manager,
            plot_arc_repository=mock_plot_arc_repository,
            llm_service=mock_llm_service,
            cliche_scanner=mock_scanner,
        )

        await workflow._naturalize_ai_flavor_if_needed(content=ai_draft, outline="测试大纲")

        rewrite_prompt = mock_llm_service.generate.await_args.args[0]
        assert rewrite_prompt.system == "来自提示词广场的去AI味系统提示"
        assert rewrite_prompt.user.startswith("来自提示词广场的去AI味用户提示")

    @pytest.mark.asyncio
    async def test_naturalizer_applies_human_texture_pass_for_over_polished_output(
        self,
        mock_context_builder,
        mock_consistency_checker,
        mock_storyline_manager,
        mock_plot_arc_repository,
        mock_llm_service,
        monkeypatch
    ):
        """自然化后仍过度工整时，应再走句式节奏破整节点。"""
        from application.services.cliche_scanner import ClicheScanner, ClicheHit

        ai_draft = "空气仿佛凝固了，他心中五味杂陈。" * 40
        polished_but_risky = (
            "不是榜单数据，是操作日志。像某种旧证据。\n\n"
            "不是待机绿光，是读写橙光。像某种呼吸。\n\n"
            "不是逃生，是保留证据。像某种被提前埋好的路。\n\n"
        ) * 10
        textured = (
            "沈铎把日志窗口往下拖了两行。鼠标垫边缘卷起来，刮着他的手腕。\n\n"
            "第三排机柜亮了一下。他没说话，先看苏晚。苏晚也正看那盏灯。\n\n"
        ) * 10
        mock_llm_service.generate = AsyncMock(side_effect=[
            LLMResult(content=polished_but_risky, token_usage=TokenUsage(input_tokens=300, output_tokens=300)),
            LLMResult(content=textured, token_usage=TokenUsage(input_tokens=300, output_tokens=300)),
        ])

        class FakePromptManager:
            def ensure_seeded(self):
                return True

            def render(self, node_key, variables):
                if node_key == "rewrite-ai-flavor-naturalizer":
                    return {"system": "自然化", "user": variables["draft"]}
                if node_key == "rewrite-prose-irregularity":
                    assert variables["draft"] == polished_but_risky.strip()
                    assert "过度工整" in variables["rhythm_goal"]
                    return {"system": "句式节奏破整", "user": variables["draft"]}
                raise AssertionError(f"unexpected node: {node_key}")

        monkeypatch.setattr(
            "infrastructure.ai.prompt_manager.get_prompt_manager",
            lambda: FakePromptManager(),
        )
        mock_scanner = Mock(spec=ClicheScanner)
        mock_scanner.scan_cliches.return_value = [
            ClicheHit(pattern="氛围凝固系列", text="空气仿佛凝固", start=0, end=6, severity="warning")
        ]
        workflow = AutoNovelGenerationWorkflow(
            context_builder=mock_context_builder,
            consistency_checker=mock_consistency_checker,
            storyline_manager=mock_storyline_manager,
            plot_arc_repository=mock_plot_arc_repository,
            llm_service=mock_llm_service,
            cliche_scanner=mock_scanner,
        )

        result = await workflow._naturalize_ai_flavor_if_needed(content=ai_draft, outline="测试大纲")

        assert result == textured.strip()
        assert mock_llm_service.generate.await_count == 2
        rhythm_prompt = mock_llm_service.generate.await_args_list[1].args[0]
        assert rhythm_prompt.system == "句式节奏破整"

    @pytest.mark.asyncio
    async def test_human_texture_pass_discards_detector_risk_regression(
        self,
        mock_context_builder,
        mock_consistency_checker,
        mock_storyline_manager,
        mock_plot_arc_repository,
        mock_llm_service,
    ):
        """二次破整如果让检测风险升高，应保留上一轮自然化稿。"""
        naturalized = (
            "沈铎把日志窗口往下拖了两行。鼠标垫边缘卷起来，刮着他的手腕。\n\n"
            "不是榜单数据，是操作日志。\n\n"
            "第三排机柜亮了一下。他没说话，先看苏晚。\n\n"
            "苏晚也正看那盏灯。\n\n"
            "不是逃生，是保留证据。\n\n"
        ) * 12
        worse_textured = (
            "不是提示。\n\n"
            "不是同步。\n\n"
            "不是刷量。\n\n"
            "不是老周。\n\n"
            "不是绿光，是橙光。\n\n"
            "不是结束，是开始。\n\n"
        ) * 18
        mock_llm_service.generate = AsyncMock(return_value=LLMResult(
            content=worse_textured,
            token_usage=TokenUsage(input_tokens=300, output_tokens=300),
        ))
        workflow = AutoNovelGenerationWorkflow(
            context_builder=mock_context_builder,
            consistency_checker=mock_consistency_checker,
            storyline_manager=mock_storyline_manager,
            plot_arc_repository=mock_plot_arc_repository,
            llm_service=mock_llm_service,
            cliche_scanner=Mock(),
        )

        result = await workflow._apply_human_texture_pass_if_needed(
            content=naturalized,
            outline="测试大纲",
        )

        assert result == naturalized
        assert mock_llm_service.generate.await_count == 2

    @pytest.mark.asyncio
    async def test_human_texture_pass_retries_strict_signature_cleanup(
        self,
        mock_context_builder,
        mock_consistency_checker,
        mock_storyline_manager,
        mock_plot_arc_repository,
        mock_llm_service,
    ):
        """首轮破整未达标时，应再用硬约束清理检测器敏感句法。"""
        naturalized = (
            "不是周正明的。是另一种呼吸，像某种被按动的风箱。\n\n"
            "不是承重柱。是肺。或者说，是某种学会呼吸的东西。\n\n"
            "虹彩正在蔓延，顾知寒看着节点，像某种旧证据。\n\n"
        ) * 12
        still_risky = (
            "不是提示。不是同步。不是结束，是开始。像某种回声。\n\n"
        ) * 20
        strict_cleaned = (
            "顾知寒把手电压低，光贴着卷帘底部走了一圈。\n\n"
            "水渍沿着砖缝往外爬，周正明伸手去拦，又在半空停住。\n\n"
            "她没有解释，只把拓片按进内袋，听见里面轻轻撞了一下。\n\n"
        ) * 10
        mock_llm_service.generate = AsyncMock(side_effect=[
            LLMResult(content=still_risky, token_usage=TokenUsage(input_tokens=300, output_tokens=300)),
            LLMResult(content=strict_cleaned, token_usage=TokenUsage(input_tokens=300, output_tokens=300)),
        ])
        workflow = AutoNovelGenerationWorkflow(
            context_builder=mock_context_builder,
            consistency_checker=mock_consistency_checker,
            storyline_manager=mock_storyline_manager,
            plot_arc_repository=mock_plot_arc_repository,
            llm_service=mock_llm_service,
            cliche_scanner=Mock(),
        )

        result = await workflow._apply_human_texture_pass_if_needed(
            content=naturalized,
            outline="测试大纲",
        )

        assert result == strict_cleaned.strip()
        assert mock_llm_service.generate.await_count == 2

    @pytest.mark.asyncio
    async def test_human_texture_pass_continues_when_first_candidate_still_risky(
        self,
        mock_context_builder,
        mock_consistency_checker,
        mock_storyline_manager,
        mock_plot_arc_repository,
        mock_llm_service,
    ):
        """首轮已改善但仍超过风险阈值时，不能提前放行。"""
        naturalized = (
            "不是周正明的。是另一种呼吸，像某种被按动的风箱。\n\n"
            "不是承重柱。是肺。或者说，是某种学会呼吸的东西。\n\n"
            "虹彩正在蔓延，顾知寒看着节点，像某种旧证据。\n\n"
        ) * 12
        improved_but_still_risky = (
            "顾知寒压低手电，水渍往外爬。\n\n"
            "卷帘底部不是承重柱，是肺。孔洞正按十七次收缩。\n\n"
            "拓片在内袋里撞了一下，带着某种提示。\n\n"
        ) * 12
        strict_cleaned = (
            "顾知寒压低手电，水渍沿着砖缝往外爬。\n\n"
            "卷帘底部的孔洞按十七次收缩。周正明伸手，又停住。\n\n"
            "拓片在内袋里撞了一下，她把话咽回去。\n\n"
        ) * 12
        assert AutoNovelGenerationWorkflow._is_detector_signature_improved(
            improved_but_still_risky,
            naturalized,
        )
        assert AutoNovelGenerationWorkflow._needs_human_texture_pass(improved_but_still_risky)
        mock_llm_service.generate = AsyncMock(side_effect=[
            LLMResult(content=improved_but_still_risky, token_usage=TokenUsage(input_tokens=300, output_tokens=300)),
            LLMResult(content=strict_cleaned, token_usage=TokenUsage(input_tokens=300, output_tokens=300)),
        ])
        workflow = AutoNovelGenerationWorkflow(
            context_builder=mock_context_builder,
            consistency_checker=mock_consistency_checker,
            storyline_manager=mock_storyline_manager,
            plot_arc_repository=mock_plot_arc_repository,
            llm_service=mock_llm_service,
            cliche_scanner=Mock(),
        )

        result = await workflow._apply_human_texture_pass_if_needed(
            content=naturalized,
            outline="测试大纲",
        )

        assert result == strict_cleaned.strip()
        assert mock_llm_service.generate.await_count == 2

    @pytest.mark.asyncio
    async def test_naturalizer_applies_human_residue_pass_for_repeated_motifs(
        self,
        mock_context_builder,
        mock_consistency_checker,
        mock_storyline_manager,
        mock_plot_arc_repository,
        mock_llm_service,
    ):
        """句法已清理但母题词过密时，应继续做人工余量降噪。"""
        from application.services.cliche_scanner import ClicheScanner

        raw = "空气仿佛凝固了。" * 80
        signature_clean_but_repetitive = (
            "虹彩沿着肺泡蔓延，十七次呼吸把坐标推到墙面。\n\n"
            "周正明听见虹彩里的呼吸，肺叶按十七次收缩。\n\n"
            "拓片上的坐标、虹彩、肺和呼吸再次重合。\n\n"
        ) * 10
        residue_cleaned = (
            "应急灯闪了两下，墙皮从潮湿处鼓起来。\n\n"
            "周正明踩到水，先骂了一声，又把后半句吞回去。\n\n"
            "顾知寒把拓片塞回内袋，没再解释那个数字。\n\n"
        ) * 10
        mock_llm_service.generate = AsyncMock(side_effect=[
            LLMResult(content=signature_clean_but_repetitive, token_usage=TokenUsage(input_tokens=300, output_tokens=300)),
            LLMResult(content=residue_cleaned, token_usage=TokenUsage(input_tokens=300, output_tokens=300)),
        ])
        scanner = Mock(spec=ClicheScanner)
        scanner.scan_cliches.return_value = []
        workflow = AutoNovelGenerationWorkflow(
            context_builder=mock_context_builder,
            consistency_checker=mock_consistency_checker,
            storyline_manager=mock_storyline_manager,
            plot_arc_repository=mock_plot_arc_repository,
            llm_service=mock_llm_service,
            cliche_scanner=scanner,
        )

        result = await workflow._naturalize_ai_flavor_if_needed(
            content=raw,
            outline="测试大纲",
        )

        assert "虹彩" not in result
        assert "十七" not in result
        assert mock_llm_service.generate.await_count == 2

    @pytest.mark.asyncio
    async def test_naturalizer_applies_structural_audit_for_exposition_cascade(
        self,
        mock_context_builder,
        mock_consistency_checker,
        mock_storyline_manager,
        mock_plot_arc_repository,
        mock_llm_service,
    ):
        """自然化稿若仍像设定说明连发，应走结构审稿式删改。"""
        from application.services.cliche_scanner import ClicheScanner

        raw = "空气仿佛凝固了。" * 80
        exposition_cascade = (
            "周正明解释了研究所的规则，接着说明虹彩为什么会出现。\n\n"
            "林默继续解释门禁系统的历史，又补充讲述当年的项目背景。\n\n"
            "顾知寒听完后明白了整套机制，于是三人很快达成共识。\n\n"
        ) * 8
        structurally_cleaned = (
            "周正明刚开口，门禁屏幕先灭了一格。\n\n"
            "林默伸手去挡，指尖碰到读卡槽，里面传出一声迟到的滴响。\n\n"
            "顾知寒没有催他说完，只把旧卡翻到背面，看见被刮掉的编号。\n\n"
        ) * 8
        mock_llm_service.generate = AsyncMock(side_effect=[
            LLMResult(content=exposition_cascade, token_usage=TokenUsage(input_tokens=300, output_tokens=300)),
            LLMResult(content=structurally_cleaned, token_usage=TokenUsage(input_tokens=300, output_tokens=300)),
        ])
        scanner = Mock(spec=ClicheScanner)
        scanner.scan_cliches.return_value = []
        workflow = AutoNovelGenerationWorkflow(
            context_builder=mock_context_builder,
            consistency_checker=mock_consistency_checker,
            storyline_manager=mock_storyline_manager,
            plot_arc_repository=mock_plot_arc_repository,
            llm_service=mock_llm_service,
            cliche_scanner=scanner,
        )

        result = await workflow._naturalize_ai_flavor_if_needed(
            content=raw,
            outline="测试大纲",
        )

        assert result == structurally_cleaned.strip()
        assert "很快达成共识" not in result
        assert mock_llm_service.generate.await_count == 2

    @pytest.mark.asyncio
    async def test_naturalizer_applies_style_bible_after_anti_ai_rewrite(
        self,
        mock_context_builder,
        mock_consistency_checker,
        mock_storyline_manager,
        mock_plot_arc_repository,
        mock_llm_service,
        monkeypatch,
    ):
        """选中手法档案时，章后自然化也应让 Style Bible 参与收束文风。"""
        from application.services.cliche_scanner import ClicheScanner

        raw = "空气仿佛凝固了。" * 80
        naturalized = (
            "林默把门禁卡按上读卡槽，屏幕迟了半秒才亮。\n\n"
            "顾知寒没有说话，只看他拇指边缘那道新划痕。\n\n"
        ) * 12
        style_matched = (
            "林默把门禁卡贴上去。屏幕迟了半秒。\n\n"
            "顾知寒看见他拇指边缘的新划痕，没问。\n\n"
        ) * 12
        mock_llm_service.generate = AsyncMock(side_effect=[
            LLMResult(content=naturalized, token_usage=TokenUsage(input_tokens=300, output_tokens=300)),
            LLMResult(content=style_matched, token_usage=TokenUsage(input_tokens=300, output_tokens=300)),
        ])

        class FakePromptManager:
            def ensure_seeded(self):
                return True

            def render(self, node_key, variables):
                if node_key == "rewrite-ai-flavor-naturalizer":
                    return {"system": "自然化", "user": variables["draft"]}
                if node_key == "style-bible-imitation-pass":
                    assert "克制悬疑" in variables["style_overlay"]
                    assert variables["draft"] == naturalized.strip()
                    assert "测试大纲" in variables["must_keep"]
                    return {"system": "文风贴合", "user": variables["draft"]}
                raise AssertionError(f"unexpected node: {node_key}")

        monkeypatch.setattr(
            "infrastructure.ai.prompt_manager.get_prompt_manager",
            lambda: FakePromptManager(),
        )
        scanner = Mock(spec=ClicheScanner)
        scanner.scan_cliches.return_value = []
        workflow = AutoNovelGenerationWorkflow(
            context_builder=mock_context_builder,
            consistency_checker=mock_consistency_checker,
            storyline_manager=mock_storyline_manager,
            plot_arc_repository=mock_plot_arc_repository,
            llm_service=mock_llm_service,
            cliche_scanner=scanner,
        )

        result = await workflow._naturalize_ai_flavor_if_needed(
            content=raw,
            outline="测试大纲",
            style_overlay="【写作手法库】\n使用风格包：克制悬疑",
        )

        assert result == style_matched.strip()
        assert mock_llm_service.generate.await_count == 2

    @pytest.mark.asyncio
    async def test_human_residue_pass_continues_when_candidate_still_repetitive(
        self,
        mock_context_builder,
        mock_consistency_checker,
        mock_storyline_manager,
        mock_plot_arc_repository,
        mock_llm_service,
    ):
        """首轮母题降噪仍超标时，应继续按词频上限压词。"""
        draft = (
            "虹彩沿着肺泡蔓延，十七次呼吸把坐标推到墙面。\n\n"
            "周正明听见虹彩里的呼吸，肺叶按十七次收缩。\n\n"
            "拓片上的坐标、虹彩、肺和呼吸再次重合。\n\n"
        ) * 12
        improved_but_repetitive = (
            "水声沿着台阶往上爬，十七次呼吸把坐标推到墙面。\n\n"
            "周正明听见呼吸，肺叶按十七次收缩。\n\n"
            "拓片上的坐标和呼吸再次重合。\n\n"
        ) * 10
        strict_cleaned = (
            "水声沿着台阶往上爬，墙上的旧读数亮了一下。\n\n"
            "周正明退了半步，皮鞋在湿处打滑。\n\n"
            "顾知寒把拓片塞回内袋，先看门锁有没有反应。\n\n"
        ) * 10
        mock_llm_service.generate = AsyncMock(side_effect=[
            LLMResult(content=improved_but_repetitive, token_usage=TokenUsage(input_tokens=300, output_tokens=300)),
            LLMResult(content=strict_cleaned, token_usage=TokenUsage(input_tokens=300, output_tokens=300)),
        ])
        workflow = AutoNovelGenerationWorkflow(
            context_builder=mock_context_builder,
            consistency_checker=mock_consistency_checker,
            storyline_manager=mock_storyline_manager,
            plot_arc_repository=mock_plot_arc_repository,
            llm_service=mock_llm_service,
            cliche_scanner=Mock(),
        )

        result = await workflow._apply_human_residue_pass_if_needed(
            content=draft,
            outline="测试大纲",
        )

        assert result == strict_cleaned.strip()
        assert mock_llm_service.generate.await_count == 2

    @pytest.mark.asyncio
    async def test_long_streamed_chapter_is_naturalized_even_without_cliche_hits(
        self,
        mock_context_builder,
        mock_consistency_checker,
        mock_storyline_manager,
        mock_plot_arc_repository
    ):
        """长正文即使未命中正则俗套，也要走一次自然化改写。"""
        from application.services.cliche_scanner import ClicheScanner

        class FakeLLM:
            def __init__(self):
                self.generate = AsyncMock(return_value=LLMResult(
                    content="改写后的正文。" * 80,
                    token_usage=TokenUsage(input_tokens=300, output_tokens=300),
                ))

            async def stream_generate(self, prompt, config):
                yield "原始正文。" * 120

        mock_scanner = Mock(spec=ClicheScanner)
        mock_scanner.scan_cliches.return_value = []
        llm = FakeLLM()
        workflow = AutoNovelGenerationWorkflow(
            context_builder=mock_context_builder,
            consistency_checker=mock_consistency_checker,
            storyline_manager=mock_storyline_manager,
            plot_arc_repository=mock_plot_arc_repository,
            llm_service=llm,
            cliche_scanner=mock_scanner,
            state_extractor=Mock(extract_chapter_state=AsyncMock(return_value=ChapterState([], [], [], [], [], []))),
        )

        events = []
        async for event in workflow.generate_chapter_stream(
            "novel-1",
            1,
            "测试大纲",
            enable_beats=False,
        ):
            events.append(event)

        done = events[-1]
        assert done["type"] == "done"
        assert done["content"] == "改写后的正文。" * 80
        assert llm.generate.await_count == 1

    @pytest.mark.asyncio
    async def test_generate_chapter_injects_fingerprint_summary(
        self,
        mock_context_builder,
        mock_consistency_checker,
        mock_storyline_manager,
        mock_plot_arc_repository,
        mock_llm_service
    ):
        """测试生成章节时注入风格指纹摘要"""
        from application.services.voice_fingerprint_service import VoiceFingerprintService
        from domain.novel.repositories.voice_fingerprint_repository import VoiceFingerprintRepository

        # Mock VoiceFingerprintService
        mock_fingerprint_repo = Mock(spec=VoiceFingerprintRepository)
        mock_fingerprint_repo.get_by_novel.return_value = {
            "metrics": {
                "adjective_density": 0.052,
                "avg_sentence_length": 18.5,
                "sentence_count": 100
            },
            "sample_count": 10
        }

        mock_fingerprint_service = Mock(spec=VoiceFingerprintService)
        mock_fingerprint_service.fingerprint_repo = mock_fingerprint_repo

        # 创建带风格指纹的工作流
        workflow = AutoNovelGenerationWorkflow(
            context_builder=mock_context_builder,
            consistency_checker=mock_consistency_checker,
            storyline_manager=mock_storyline_manager,
            plot_arc_repository=mock_plot_arc_repository,
            llm_service=mock_llm_service,
            voice_fingerprint_service=mock_fingerprint_service
        )

        result = await workflow.generate_chapter(
            novel_id="novel-1",
            chapter_number=1,
            outline="测试大纲"
        )

        # 验证 LLM 被调用
        assert mock_llm_service.generate.called

        # 获取章节正文生成 prompt。后处理阶段也可能调用 LLM，不能依赖最后一次调用。
        prompt = next(
            call.args[0]
            for call in mock_llm_service.generate.await_args_list
            if call.args
        )

        # 验证 prompt 包含风格指纹摘要
        assert "形容词密度" in prompt.system or "平均句长" in prompt.system

        # 验证指纹仓储被调用
        mock_fingerprint_repo.get_by_novel.assert_called_once_with("novel-1", pov_character_id=None)

    @pytest.mark.asyncio
    async def test_generate_chapter_without_style_services(
        self,
        workflow
    ):
        """测试没有风格服务时不报错"""
        # workflow fixture 默认没有 voice_fingerprint_service 和 cliche_scanner
        result = await workflow.generate_chapter(
            novel_id="novel-1",
            chapter_number=1,
            outline="测试大纲"
        )

        # 验证不报错，返回空风格警告列表
        assert isinstance(result, GenerationResult)
        assert len(result.style_warnings) == 0

    @pytest.mark.asyncio
    async def test_generate_chapter_stream_includes_style_warnings(
        self,
        mock_context_builder,
        mock_consistency_checker,
        mock_storyline_manager,
        mock_plot_arc_repository,
        mock_llm_service
    ):
        """测试流式生成时包含风格警告"""
        from application.services.cliche_scanner import ClicheScanner, ClicheHit

        # Mock ClicheScanner
        mock_scanner = Mock(spec=ClicheScanner)
        mock_scanner.scan_cliches.return_value = [
            ClicheHit(
                pattern="熊熊系列",
                text="熊熊烈火",
                start=10,
                end=14,
                severity="warning"
            )
        ]

        workflow = AutoNovelGenerationWorkflow(
            context_builder=mock_context_builder,
            consistency_checker=mock_consistency_checker,
            storyline_manager=mock_storyline_manager,
            plot_arc_repository=mock_plot_arc_repository,
            llm_service=mock_llm_service,
            cliche_scanner=mock_scanner
        )

        events = []
        async for event in workflow.generate_chapter_stream(
            novel_id="novel-1",
            chapter_number=1,
            outline="测试大纲"
        ):
            events.append(event)

        # 验证最后的 done 事件包含风格警告
        done_event = events[-1]
        assert done_event["type"] == "done"
        assert "style_warnings" in done_event
        assert len(done_event["style_warnings"]) == 1
        assert done_event["style_warnings"][0]["pattern"] == "熊熊系列"
        assert done_event["style_warnings"][0]["text"] == "熊熊烈火"


class TestCocCanonWarnings:
    """测试 CoC 正典轻告警。"""

    def test_build_coc_overlay_extracts_absolute_titles_from_string(self, workflow):
        workflow._current_novel_id = "novel-1"
        workflow.coc_canon_service = Mock()
        workflow.coc_canon_service.build_overlay.return_value = (
            "【CoC正典（必须保持一致）】\n"
            "- [world_rule] 夜巡制度（锁定：absolute）\n"
            "  公共事实：每晚三更点名。"
        )

        overlay = workflow._build_coc_canon_overlay()
        assert "【CoC正典（必须保持一致）】" in overlay
        assert "夜巡制度" in workflow._current_coc_absolute_titles

    @pytest.mark.asyncio
    async def test_post_process_adds_warning_when_absolute_canon_is_rewritten(
        self,
        workflow,
    ):
        workflow._coc_hard_guard_enabled = False
        workflow._current_coc_absolute_titles = ["夜巡制度"]
        workflow._extract_chapter_state = AsyncMock(return_value=ChapterState([], [], [], [], [], []))
        workflow._check_consistency = Mock(return_value=ConsistencyReport(issues=[], warnings=[], suggestions=[]))
        workflow._detect_conflicts = Mock(return_value=[])

        post = await workflow.post_process_generated_chapter(
            novel_id="novel-1",
            chapter_number=3,
            outline="测试大纲",
            content="他翻着旧档案低声说，夜巡制度并非祖制，而是两年前临时改的。",
            scene_director=None,
        )

        warnings = post["consistency_report"].warnings
        assert len(warnings) == 1
        assert "CoC正典疑似冲突" in warnings[0].description
        assert "夜巡制度" in warnings[0].description

    @pytest.mark.asyncio
    async def test_post_process_adds_warning_when_author_truth_is_directly_exposed(
        self,
        workflow,
    ):
        workflow._coc_hard_guard_enabled = False
        workflow._current_coc_author_truth_snippets = ["信号其实是旧教团的召集暗号"]
        workflow._extract_chapter_state = AsyncMock(return_value=ChapterState([], [], [], [], [], []))
        workflow._check_consistency = Mock(return_value=ConsistencyReport(issues=[], warnings=[], suggestions=[]))
        workflow._detect_conflicts = Mock(return_value=[])

        post = await workflow.post_process_generated_chapter(
            novel_id="novel-1",
            chapter_number=6,
            outline="测试大纲",
            content="他低声说出真相：信号其实是旧教团的召集暗号，今晚就会动手。",
            scene_director=None,
        )

        warnings = post["consistency_report"].warnings
        assert len(warnings) == 1
        assert "CoC作者真相疑似直出" in warnings[0].description


class TestCocClueWarnings:
    """测试 CoC 线索边界轻告警。"""

    def test_direct_writing_prompt_includes_coc_clue_overlay(self, workflow):
        workflow._current_novel_id = "novel-1"
        workflow.coc_clue_service = Mock()
        workflow.coc_clue_service.build_overlay.return_value = {
            "prompt": "【CoC线索边界】\n- clue_key: ledger_owner | visibility: author_only",
            "clues": [
                {"clue_key": "ledger_owner", "visibility": "author_only"},
            ],
        }

        prompt = workflow._build_direct_writing_prompt(
            context="CTX",
            outline="OL",
        )

        assert "【CoC线索边界】" in prompt.system
        assert "ledger_owner" in prompt.system

    @pytest.mark.asyncio
    async def test_post_process_adds_warning_when_author_only_clue_leaks(
        self,
        workflow,
    ):
        workflow._coc_hard_guard_enabled = False
        workflow._current_novel_id = "novel-1"
        workflow.coc_clue_service = Mock()
        workflow.coc_clue_service.build_overlay.return_value = {
            "prompt": "【CoC线索边界】\n- clue_key: ledger_owner | visibility: author_only",
            "clues": [
                {"clue_key": "ledger_owner", "visibility": "author_only"},
            ],
        }
        workflow._build_coc_clue_overlay()
        workflow._extract_chapter_state = AsyncMock(return_value=ChapterState([], [], [], [], [], []))
        workflow._check_consistency = Mock(return_value=ConsistencyReport(issues=[], warnings=[], suggestions=[]))
        workflow._detect_conflicts = Mock(return_value=[])

        post = await workflow.post_process_generated_chapter(
            novel_id="novel-1",
            chapter_number=5,
            outline="测试大纲",
            content="他在账页背面写下 ledger_owner，再把纸条塞回抽屉。",
            scene_director=None,
        )

        warnings = post["consistency_report"].warnings
        assert len(warnings) == 1
        assert "CoC线索疑似越级" in warnings[0].description
        assert "ledger_owner" in warnings[0].description


class TestCocCognitionPrecheck:
    """测试 CoC 认知边界生成前预检。"""

    def test_precheck_returns_not_checked_when_services_missing(self, workflow):
        result = workflow.precheck_coc_cognition_boundary(
            novel_id="novel-1",
            chapter_number=1,
            outline="主角在雨夜追查旧案。",
        )
        assert result["checked"] is False
        assert result["allow_generate"] is True

    def test_precheck_blocks_author_truth_or_author_only_leak(self, workflow):
        workflow.coc_canon_service = Mock()
        workflow.coc_canon_service.get_cognition_layers.return_value = {
            "author_truth": ["灯塔信号：信号其实是旧教团的召集暗号。"],
            "author_truth_snippets": ["信号其实是旧教团的召集暗号"],
            "reader_known": [],
        }
        workflow.coc_clue_service = Mock()
        workflow.coc_clue_service.get_cognition_layers.return_value = {
            "author_truth": ["ledger_owner：账本真正持有人是裴家管家（已知角色：未记录）"],
            "character_known": [],
            "reader_known": [],
        }

        result = workflow.precheck_coc_cognition_boundary(
            novel_id="novel-1",
            chapter_number=3,
            outline="这一章明确写出：信号其实是旧教团的召集暗号，且 ledger_owner 就是裴家管家。",
        )
        assert result["checked"] is True
        assert result["allow_generate"] is False
        assert result["risk_level"] == "block"
        assert any("author_only" in item for item in result["blocking_issues"])

    def test_precheck_warns_character_known_visibility(self, workflow):
        workflow.coc_canon_service = Mock()
        workflow.coc_canon_service.get_cognition_layers.return_value = {
            "author_truth": [],
            "author_truth_snippets": [],
            "reader_known": [],
        }
        workflow.coc_clue_service = Mock()
        workflow.coc_clue_service.get_cognition_layers.return_value = {
            "author_truth": [],
            "character_known": ["archive_code：档案室门禁码 11473（已知角色：林岚）"],
            "reader_known": [],
        }

        result = workflow.precheck_coc_cognition_boundary(
            novel_id="novel-1",
            chapter_number=4,
            outline="林岚盯着 archive_code 这串数字，迟迟不敢输入门禁。",
        )
        assert result["checked"] is True
        assert result["allow_generate"] is True
        assert result["risk_level"] == "warning"
        assert len(result["warnings"]) >= 1

    def test_rewrite_outline_for_coc_boundary_replaces_blocking_tokens(self, workflow):
        workflow.coc_canon_service = Mock()
        workflow.coc_canon_service.get_cognition_layers.return_value = {
            "author_truth": ["灯塔信号：信号其实是旧教团的召集暗号。"],
            "author_truth_snippets": ["信号其实是旧教团的召集暗号"],
            "reader_known": [],
        }
        workflow.coc_clue_service = Mock()
        workflow.coc_clue_service.get_cognition_layers.return_value = {
            "author_truth": ["ledger_owner：账本真正持有人是裴家管家（已知角色：未记录）"],
            "character_known": [],
            "reader_known": [],
        }

        result = workflow.rewrite_outline_for_coc_boundary(
            novel_id="novel-1",
            chapter_number=5,
            outline="这一章明确写出：信号其实是旧教团的召集暗号，ledger_owner 已确认是裴家管家。",
        )
        assert result["changed"] is True
        assert result["rewrite_mode"] == "conservative"
        assert result["rewrite_style"] == "generic"
        assert "未公开线索" in result["rewritten_outline"]
        assert result["precheck_before"]["allow_generate"] is False

    def test_rewrite_outline_for_coc_boundary_no_change_when_safe(self, workflow):
        workflow.coc_canon_service = Mock()
        workflow.coc_canon_service.get_cognition_layers.return_value = {
            "author_truth": [],
            "author_truth_snippets": [],
            "reader_known": [],
        }
        workflow.coc_clue_service = Mock()
        workflow.coc_clue_service.get_cognition_layers.return_value = {
            "author_truth": [],
            "character_known": [],
            "reader_known": ["archive_code：档案室里有一串旧编号（已知角色：林岚）"],
        }
        outline = "主角在档案室找到旧编号并继续追查。"
        result = workflow.rewrite_outline_for_coc_boundary(
            novel_id="novel-1",
            chapter_number=2,
            outline=outline,
        )
        assert result["changed"] is False
        assert result["rewrite_mode"] == "conservative"
        assert result["rewrite_style"] == "generic"
        assert result["rewritten_outline"] == outline

    def test_rewrite_outline_for_coc_boundary_aggressive_mode(self, workflow):
        workflow.coc_canon_service = Mock()
        workflow.coc_canon_service.get_cognition_layers.return_value = {
            "author_truth": [],
            "author_truth_snippets": [],
            "reader_known": [],
        }
        workflow.coc_clue_service = Mock()
        workflow.coc_clue_service.get_cognition_layers.return_value = {
            "author_truth": ["ledger_owner：账本主人暂未公开（已知角色：未记录）"],
            "character_known": [],
            "reader_known": [],
        }
        result = workflow.rewrite_outline_for_coc_boundary(
            novel_id="novel-1",
            chapter_number=7,
            outline="主角揭露 ledger_owner，并一口气说出全部真相。",
            rewrite_mode="aggressive",
            rewrite_style="suspense",
        )
        assert result["rewrite_mode"] == "aggressive"
        assert result["rewrite_style"] == "suspense"
        assert result["changed"] is True
        assert "侧面触发" in result["rewritten_outline"] or "话到嘴边又收住" in result["rewritten_outline"]

    def test_rewrite_outline_for_coc_boundary_coc_style(self, workflow):
        workflow.coc_canon_service = Mock()
        workflow.coc_canon_service.get_cognition_layers.return_value = {
            "author_truth": [],
            "author_truth_snippets": [],
            "reader_known": [],
        }
        workflow.coc_clue_service = Mock()
        workflow.coc_clue_service.get_cognition_layers.return_value = {
            "author_truth": ["ledger_owner：账本主人暂未公开（已知角色：未记录）"],
            "character_known": [],
            "reader_known": [],
        }
        result = workflow.rewrite_outline_for_coc_boundary(
            novel_id="novel-1",
            chapter_number=8,
            outline="主角揭示邪神仪式成功，并完全理解神明意志。",
            rewrite_mode="aggressive",
            rewrite_style="coc",
        )
        assert result["rewrite_mode"] == "aggressive"
        assert result["rewrite_style"] == "coc"


class TestCocContentBoundaryValidation:
    """测试 CoC 正文级硬约束校验。"""

    def test_content_boundary_blocks_author_only_key(self, workflow):
        workflow.coc_canon_service = Mock()
        workflow.coc_canon_service.build_overlay.return_value = {"prompt": "【CoC正典】"}
        workflow.coc_canon_service.get_cognition_layers.return_value = {}
        workflow.coc_canon_service.get_overview.return_value = {"entries": []}

        workflow.coc_clue_service = Mock()
        workflow.coc_clue_service.build_overlay.return_value = {
            "prompt": "【CoC线索边界】\n- clue_key: clue-zhou-origin | visibility: author_only",
            "clues": [{"clue_key": "clue-zhou-origin", "visibility": "author_only"}],
        }
        workflow.coc_clue_service.get_cognition_layers.return_value = {
            "author_truth": [],
            "character_known": [],
            "reader_known": [],
        }

        result = workflow.validate_coc_content_boundary(
            novel_id="novel-1",
            chapter_number=6,
            content="主角终于确认 clue-zhou-origin 的来源。",
        )
        assert result["checked"] is True
        assert result["allow_save"] is False
        assert result["risk_level"] == "block"
        assert any("author_only" in item for item in result["blocking_issues"])

    def test_content_boundary_blocks_strict_entry_negation(self, workflow):
        workflow.coc_canon_service = Mock()
        workflow.coc_canon_service.build_overlay.return_value = {"prompt": "【CoC正典】"}
        workflow.coc_canon_service.get_cognition_layers.return_value = {}
        workflow.coc_canon_service.get_overview.return_value = {
            "entries": [
                {
                    "title": "第七次熄灯与十七分钟窗口",
                    "lock_level": "strict",
                }
            ]
        }
        workflow.coc_clue_service = Mock()
        workflow.coc_clue_service.build_overlay.return_value = {"prompt": "【CoC线索】"}
        workflow.coc_clue_service.get_cognition_layers.return_value = {}

        result = workflow.validate_coc_content_boundary(
            novel_id="novel-1",
            chapter_number=7,
            content="所有人都说第七次熄灯与十七分钟窗口并非关键，只是误传。",
        )
        assert result["allow_save"] is False
        assert any("硬约束冲突" in item for item in result["blocking_issues"])
