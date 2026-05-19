"""场景生成服务

为单个场景生成正文（500-1000 字）
"""

import logging
from typing import Dict, List, Optional, TYPE_CHECKING

from domain.novel.value_objects.scene import Scene
from domain.ai.services.llm_service import LLMService, GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from application.engine.services.scene_director_service import SceneDirectorService

if TYPE_CHECKING:
    from infrastructure.ai.chromadb_vector_store import ChromaDBVectorStore

logger = logging.getLogger(__name__)


class SceneGenerationService:
    """场景生成服务

    为单个场景生成正文，集成：
    1. 场记分析（SceneDirectorAnalysis）
    2. 向量检索过滤上下文（POV 防火墙）
    3. 前置场景上下文（previous_scenes）
    4. LLM 生成正文
    """

    def __init__(
        self,
        llm_service: LLMService,
        scene_director: SceneDirectorService,
        vector_store: Optional["ChromaDBVectorStore"] = None,
        embedding_service=None,
    ):
        self.llm_service = llm_service
        self.scene_director = scene_director
        self.vector_store = vector_store
        self.embedding_service = embedding_service

    async def generate_scene(
        self,
        scene: Scene,
        chapter_number: int,
        previous_scenes: List[str],
        bible_context: Optional[Dict] = None
    ) -> str:
        """生成单个场景的正文

        Args:
            scene: 场景对象
            chapter_number: 章节号
            previous_scenes: 前置场景的正文列表
            bible_context: Bible 上下文（可选）

        Returns:
            生成的场景正文
        """
        logger.info(f"Generating scene: {scene.title} (POV: {scene.pov_character})")

        # 1. 场记分析
        scene_analysis = await self.scene_director.analyze(
            chapter_number=chapter_number,
            outline=f"{scene.title}\n{scene.goal}"
        )
        logger.debug(f"Scene analysis: characters={scene_analysis.characters}, "
                    f"locations={scene_analysis.locations}, pov={scene_analysis.pov}")

        # 2. 向量检索过滤上下文（POV 防火墙）
        relevant_context = await self._retrieve_relevant_context(
            scene=scene,
            scene_analysis=scene_analysis
        )

        # 3. 构建提示词
        prompt = self._build_scene_prompt(
            scene=scene,
            scene_analysis=scene_analysis,
            relevant_context=relevant_context,
            previous_scenes=previous_scenes,
            bible_context=bible_context
        )

        # 4. 生成正文
        config = GenerationConfig(max_tokens=2048, temperature=0.8)
        response = await self.llm_service.generate(prompt, config)

        # 提取响应文本
        if hasattr(response, 'content'):
            content = response.content
        elif hasattr(response, 'text'):
            content = response.text
        else:
            content = str(response)

        logger.info(f"Scene generated: {len(content)} characters")
        return content.strip()

    async def _retrieve_relevant_context(
        self,
        scene: Scene,
        scene_analysis
    ) -> Dict:
        """向量检索：获取与场景相关的上下文

        Phase 2.1 简化版：暂时返回空上下文
        """
        # TODO: 实现向量检索
        # - 检索相关人物信息（POV 防火墙）
        # - 检索相关地点信息
        # - 检索相关伏笔
        return {
            "characters": [],
            "locations": [],
            "foreshadowings": []
        }

    @staticmethod
    def _get_system_prompt() -> str:
        """获取场景生成 system prompt（CPMS 统一入口）。"""
        from infrastructure.ai.prompt_utils import get_prompt_system
        from infrastructure.ai.prompt_keys import SCENE_GENERATION
        return get_prompt_system(SCENE_GENERATION)

    def _build_scene_prompt(
        self,
        scene: Scene,
        scene_analysis,
        relevant_context: Dict,
        previous_scenes: List[str],
        bible_context: Optional[Dict]
    ) -> Prompt:
        """构建场景生成提示词（CPMS 渲染）。"""
        from infrastructure.ai.prompt_keys import SCENE_GENERATION
        from infrastructure.ai.prompt_registry import get_prompt_registry

        # 构建变量
        analysis_parts = []
        if scene_analysis.characters:
            analysis_parts.append(f"涉及角色：{', '.join(scene_analysis.characters)}")
        if scene_analysis.locations:
            analysis_parts.append(f"涉及地点：{', '.join(scene_analysis.locations)}")
        if scene_analysis.emotional_state:
            analysis_parts.append(f"情绪状态：{scene_analysis.emotional_state}")
        analysis_block = "\n".join(analysis_parts)

        previous_scenes_parts = []
        for i, prev_scene in enumerate(previous_scenes[-2:], 1):
            summary = prev_scene[:200] + "..." if len(prev_scene) > 200 else prev_scene
            previous_scenes_parts.append(f"场景 {i}：\n{summary}")
        previous_scenes_block = "\n".join(previous_scenes_parts)

        foreshadow_parts = []
        for foreshadowing in relevant_context.get("foreshadowings", [])[:3]:
            foreshadow_parts.append(f"- {foreshadowing.get('description', 'N/A')}")
        foreshadowing_block = "\n".join(foreshadow_parts)

        variables = {
            "title": scene.title,
            "goal": scene.goal,
            "pov_character": scene.pov_character,
            "location": scene.location or "未指定",
            "tone": scene.tone or "未指定",
            "estimated_words": str(scene.estimated_words),
            "analysis_block": analysis_block,
            "previous_scenes_block": previous_scenes_block,
            "foreshadowing_block": foreshadowing_block,
        }

        # CPMS 渲染
        registry = get_prompt_registry()
        prompt = registry.render_to_prompt(SCENE_GENERATION, variables)
        if prompt:
            return prompt

        # 降级：直接拼接
        system = self._get_system_prompt()
        user = f"场景信息：\n标题：{scene.title}\n目标：{scene.goal}\nPOV 角色：{scene.pov_character}\n地点：{scene.location or '未指定'}\n情绪基调：{scene.tone or '未指定'}\n预估字数：{scene.estimated_words}\n"
        if analysis_block:
            user += f"\n{analysis_block}"
        if previous_scenes_block:
            user += f"\n\n前置场景摘要：\n{previous_scenes_block}"
        if foreshadowing_block:
            user += f"\n\n相关伏笔：\n{foreshadowing_block}"
        user += "\n\n请生成场景正文："
        return Prompt(system=system, user=user)
