"""卷级摘要服务 - 轨道一：宏观摘要线

金字塔层级压缩：
- 幕摘要 (~200 tokens)：每写完一幕生成
- 卷摘要 (~500 tokens)：每写完一卷生成（Map-Reduce）
- 部摘要 (~300 tokens)：每写完一部生成

触发机制（混合）：
1. 幕完结 → 生成"幕摘要"
2. 累计达到阈值（如 20 章）→ 强制生成"检查点摘要"
3. 卷/部完结 → Map-Reduce 压缩

核心作用：
- 提供不可撼动的时空与逻辑基石
- 防止大模型出现"死人复活"、"时间倒流"等低级 Bug
"""
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

from domain.ai.services.llm_service import LLMService, GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.repositories.chapter_repository import ChapterRepository
from domain.novel.repositories.foreshadowing_repository import ForeshadowingRepository
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
from domain.structure.story_node import NodeType

logger = logging.getLogger(__name__)

# CPMS: 提示词节点 key
_VOLUME_SUMMARY_NODE_KEYS = {
    "act": "volume-summary-act",
    "volume": "volume-summary-volume",
    "part": "volume-summary-part",
    "checkpoint": "volume-summary-checkpoint",
}

# 硬编码回退（仅在 PromptRegistry 不可用时使用）
_FALLBACK_VOLUME_SUMMARY_SYSTEMS = {
    "act": "你是一位专业的小说编辑，擅长提炼故事精华。你的任务是为一幕（Act）生成简洁的摘要。\n摘要应包含：\n1. 核心事件（2-3句话）\n2. 情绪曲线（从什么状态到什么状态）\n3. 关键转折点\n\n输出格式：直接输出摘要文本，约 150-200 字。",
    "volume": "你是一位专业的小说编辑，擅长提炼长篇故事的精华。你的任务是将多个幕摘要压缩为一卷的摘要。\n摘要应包含：\n1. 卷主线进展（3-4句话）\n2. 主角状态变化\n3. 关键冲突与转折\n4. 未解决的悬念\n\n输出格式：直接输出摘要文本，约 300-500 字。",
    "part": '你是一位资深小说主编，擅长把握长篇小说的宏观脉络。你的任务是将多卷摘要压缩为"部"级别的摘要。\n摘要应包含：\n1. 整体结构定位（这一部在整个故事中的作用）\n2. 主角弧光演变\n3. 核心冲突升级脉络\n\n输出格式：直接输出摘要文本，约 200-300 字。',
    "checkpoint": "你是一位专业的小说编辑。你的任务是为最近的章节生成一个检查点摘要。\n摘要应聚焦于：\n1. 当前的故事进度\n2. 主角的状态和目标\n3. 未解决的悬念\n\n输出格式：直接输出摘要文本，约 150-200 字。",
}


def _get_volume_summary_system(summary_type: str) -> str:
    """获取卷摘要的 system prompt。

    CPMS: 优先从 PromptRegistry 获取（广场可编辑），
    如果 Registry 不可用则回退到硬编码默认值。
    """
    node_key = _VOLUME_SUMMARY_NODE_KEYS.get(summary_type, "")
    fallback = _FALLBACK_VOLUME_SUMMARY_SYSTEMS.get(summary_type, "")

    if node_key:
        try:
            from infrastructure.ai.prompt_registry import get_prompt_registry
            registry = get_prompt_registry()
            system = registry.get_system(node_key)
            if system:
                return system
        except Exception as exc:
            logger.debug("PromptRegistry 不可用 (%s): %s", node_key, exc)

    return fallback


@dataclass
class SummaryResult:
    """摘要生成结果"""
    success: bool
    summary: str = ""
    tokens: int = 0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class VolumeSummaryService:
    """卷级摘要服务
    
    使用示例：
    ```python
    service = VolumeSummaryService(
        llm_service=...,
        story_node_repo=...,
        chapter_repo=...,
    )
    
    # 写完一幕后生成幕摘要
    result = await service.generate_act_summary(
        novel_id="novel-001",
        act_id="act-xxx",
    )
    
    # 写完一卷后生成卷摘要
    result = await service.generate_volume_summary(
        novel_id="novel-001",
        volume_number=1,
    )
    ```
    """
    
    # Token 目标
    ACT_SUMMARY_TARGET_TOKENS = 200      # 幕摘要
    VOLUME_SUMMARY_TARGET_TOKENS = 500   # 卷摘要
    PART_SUMMARY_TARGET_TOKENS = 300     # 部摘要
    
    # 检查点阈值
    CHECKPOINT_CHAPTER_THRESHOLD = 20    # 每 20 章强制生成检查点
    
    def __init__(
        self,
        llm_service: LLMService,
        story_node_repository: StoryNodeRepository,
        chapter_repository: Optional[ChapterRepository] = None,
        foreshadowing_repository: Optional[ForeshadowingRepository] = None,
    ):
        self.llm_service = llm_service
        self.story_node_repo = story_node_repository
        self.chapter_repo = chapter_repository
        self.foreshadowing_repo = foreshadowing_repository
    
    async def generate_act_summary(
        self,
        novel_id: str,
        act_id: str,
    ) -> SummaryResult:
        """生成幕摘要
        
        包含：
        - 核心事件
        - 情绪曲线
        - 埋下/回收的伏笔
        """
        try:
            # 获取幕节点信息
            act_node = await self.story_node_repo.get_by_id(act_id)
            if not act_node:
                return SummaryResult(success=False, error=f"幕节点不存在: {act_id}")
            
            # 获取幕下的章节
            children = self.story_node_repo.get_children_sync(act_id)
            chapter_nodes = [n for n in children if n.node_type == NodeType.CHAPTER]
            
            if not chapter_nodes:
                return SummaryResult(success=False, error="幕下无章节")
            
            # 收集章节信息
            chapter_info = []
            for ch in sorted(chapter_nodes, key=lambda x: x.number):
                content_preview = ""
                if self.chapter_repo:
                    from domain.novel.value_objects.chapter_id import ChapterId
                    chapter = self.chapter_repo.get_by_id(ChapterId(ch.id))
                    if chapter and chapter.content:
                        content_preview = chapter.content[:500]
                
                chapter_info.append({
                    "number": ch.number,
                    "title": ch.title,
                    "outline": ch.outline or ch.description or "",
                    "content_preview": content_preview,
                })
            
            # 获取该幕涉及的伏笔
            foreshadowing_info = await self._get_foreshadowing_info(novel_id, act_node.chapter_start, act_node.chapter_end)
            
            # 构建 Prompt
            prompt = self._build_act_summary_prompt(act_node, chapter_info, foreshadowing_info)
            
            # 调用 LLM
            response = await self.llm_service.generate(
                prompt,
                GenerationConfig(max_tokens=400, temperature=0.5)
            )
            
            summary = response.content.strip() if hasattr(response, 'content') else str(response).strip()
            
            # 保存摘要到节点
            act_node.metadata = act_node.metadata or {}
            act_node.metadata["summary"] = summary
            act_node.metadata["summary_generated_at"] = datetime.now().isoformat()
            await self.story_node_repo.update(act_node)
            
            logger.info(f"[VolumeSummaryService] 幕摘要生成成功: {act_node.title} ({len(summary)} 字)")
            
            return SummaryResult(
                success=True,
                summary=summary,
                tokens=len(summary) // 2,  # 粗略估算
                metadata={"act_id": act_id, "chapter_count": len(chapter_nodes)}
            )
            
        except Exception as e:
            logger.error(f"[VolumeSummaryService] 幕摘要生成失败: {e}", exc_info=True)
            return SummaryResult(success=False, error=str(e))
    
    async def generate_volume_summary(
        self,
        novel_id: str,
        volume_number: int,
    ) -> SummaryResult:
        """生成卷摘要（Map-Reduce）
        
        流程：
        1. 收集该卷所有幕摘要
        2. 拼接为上下文
        3. LLM 压缩为 ~500 tokens 的卷摘要
        """
        try:
            # 获取该卷的所有节点
            all_nodes = await self.story_node_repo.get_by_novel(novel_id)
            volume_node = next(
                (n for n in all_nodes if n.node_type == NodeType.VOLUME and n.number == volume_number),
                None
            )
            
            if not volume_node:
                return SummaryResult(success=False, error=f"卷节点不存在: volume_number={volume_number}")
            
            # 收集幕摘要
            act_nodes = sorted(
                [n for n in all_nodes if n.node_type == NodeType.ACT and n.parent_id == volume_node.id],
                key=lambda x: x.number
            )
            
            if not act_nodes:
                # 如果没有幕节点，尝试直接从章节生成
                return await self._generate_volume_summary_from_chapters(novel_id, volume_node)
            
            # Map: 收集所有幕摘要
            act_summaries = []
            for act in act_nodes:
                summary = act.metadata.get("summary", "") if act.metadata else ""
                if not summary:
                    # 尝试生成幕摘要
                    result = await self.generate_act_summary(novel_id, act.id)
                    if result.success:
                        summary = result.summary
                
                act_summaries.append({
                    "number": act.number,
                    "title": act.title,
                    "summary": summary or act.description or "",
                })
            
            # Reduce: LLM 压缩
            prompt = self._build_volume_summary_prompt(volume_node, act_summaries)
            
            response = await self.llm_service.generate(
                prompt,
                GenerationConfig(max_tokens=800, temperature=0.5)
            )
            
            summary = response.content.strip() if hasattr(response, 'content') else str(response).strip()
            
            # 保存到卷节点
            volume_node.metadata = volume_node.metadata or {}
            volume_node.metadata["summary"] = summary
            volume_node.metadata["summary_generated_at"] = datetime.now().isoformat()
            await self.story_node_repo.update(volume_node)
            
            logger.info(f"[VolumeSummaryService] 卷摘要生成成功: {volume_node.title} ({len(summary)} 字)")
            
            return SummaryResult(
                success=True,
                summary=summary,
                tokens=len(summary) // 2,
                metadata={"volume_id": volume_node.id, "act_count": len(act_nodes)}
            )
            
        except Exception as e:
            logger.error(f"[VolumeSummaryService] 卷摘要生成失败: {e}", exc_info=True)
            return SummaryResult(success=False, error=str(e))
    
    async def generate_part_summary(
        self,
        novel_id: str,
        part_number: int,
    ) -> SummaryResult:
        """生成部摘要（最高层级）
        
        包含：
        - 三部曲结构定位
        - 主角弧光总结
        - 核心冲突演变
        """
        try:
            all_nodes = await self.story_node_repo.get_by_novel(novel_id)
            part_node = next(
                (n for n in all_nodes if n.node_type == NodeType.PART and n.number == part_number),
                None
            )
            
            if not part_node:
                return SummaryResult(success=False, error=f"部节点不存在: part_number={part_number}")
            
            # 收集卷摘要
            volume_nodes = sorted(
                [n for n in all_nodes if n.node_type == NodeType.VOLUME and n.parent_id == part_node.id],
                key=lambda x: x.number
            )
            
            volume_summaries = []
            for vol in volume_nodes:
                summary = vol.metadata.get("summary", "") if vol.metadata else ""
                volume_summaries.append({
                    "number": vol.number,
                    "title": vol.title,
                    "summary": summary or vol.description or "",
                })
            
            prompt = self._build_part_summary_prompt(part_node, volume_summaries)
            
            response = await self.llm_service.generate(
                prompt,
                GenerationConfig(max_tokens=500, temperature=0.5)
            )
            
            summary = response.content.strip() if hasattr(response, 'content') else str(response).strip()
            
            # 保存
            part_node.metadata = part_node.metadata or {}
            part_node.metadata["summary"] = summary
            part_node.metadata["summary_generated_at"] = datetime.now().isoformat()
            await self.story_node_repo.update(part_node)
            
            logger.info(f"[VolumeSummaryService] 部摘要生成成功: {part_node.title}")
            
            return SummaryResult(
                success=True,
                summary=summary,
                tokens=len(summary) // 2,
                metadata={"part_id": part_node.id}
            )
            
        except Exception as e:
            logger.error(f"[VolumeSummaryService] 部摘要生成失败: {e}", exc_info=True)
            return SummaryResult(success=False, error=str(e))
    
    async def should_generate_checkpoint(
        self,
        novel_id: str,
        current_chapter: int,
    ) -> bool:
        """检查是否需要生成检查点摘要"""
        # 每 N 章强制生成一次
        return current_chapter > 0 and current_chapter % self.CHECKPOINT_CHAPTER_THRESHOLD == 0
    
    async def generate_checkpoint_summary(
        self,
        novel_id: str,
        current_chapter: int,
    ) -> SummaryResult:
        """生成检查点摘要（每 20 章）"""
        try:
            # 获取最近的 N 章
            if not self.chapter_repo:
                return SummaryResult(success=False, error="chapter_repo 未初始化")
            
            nid = NovelId(novel_id)
            all_chapters = self.chapter_repo.list_by_novel(nid)
            
            recent = sorted(
                [c for c in all_chapters if c.number <= current_chapter],
                key=lambda c: c.number,
                reverse=True
            )[:self.CHECKPOINT_CHAPTER_THRESHOLD]
            
            if not recent:
                return SummaryResult(success=False, error="无章节可摘要")
            
            # 构建检查点摘要 Prompt
            chapter_info = [
                {
                    "number": ch.number,
                    "title": ch.title,
                    "content_preview": (ch.content or "")[:300],
                }
                for ch in sorted(recent, key=lambda x: x.number)
            ]
            
            prompt = self._build_checkpoint_summary_prompt(current_chapter, chapter_info)
            
            response = await self.llm_service.generate(
                prompt,
                GenerationConfig(max_tokens=400, temperature=0.5)
            )
            
            summary = response.content.strip() if hasattr(response, 'content') else str(response).strip()
            
            logger.info(f"[VolumeSummaryService] 检查点摘要生成成功: 第 {current_chapter} 章")
            
            return SummaryResult(
                success=True,
                summary=summary,
                tokens=len(summary) // 2,
                metadata={"checkpoint_chapter": current_chapter}
            )
            
        except Exception as e:
            logger.error(f"[VolumeSummaryService] 检查点摘要生成失败: {e}", exc_info=True)
            return SummaryResult(success=False, error=str(e))
    
    def get_volume_summary(self, novel_id: str, volume_number: int) -> Optional[str]:
        """获取已生成的卷摘要"""
        try:
            all_nodes = self.story_node_repo.get_by_novel_sync(novel_id)
            volume_node = next(
                (n for n in all_nodes if n.node_type == NodeType.VOLUME and n.number == volume_number),
                None
            )
            
            if volume_node and volume_node.metadata:
                return volume_node.metadata.get("summary")
            
        except Exception as e:
            logger.warning(f"获取卷摘要失败: {e}")
        
        return None
    
    def get_act_summary(self, novel_id: str, act_number: int) -> Optional[str]:
        """获取已生成的幕摘要"""
        try:
            all_nodes = self.story_node_repo.get_by_novel_sync(novel_id)
            act_node = next(
                (n for n in all_nodes if n.node_type == NodeType.ACT and n.number == act_number),
                None
            )
            
            if act_node and act_node.metadata:
                return act_node.metadata.get("summary")
            
        except Exception as e:
            logger.warning(f"获取幕摘要失败: {e}")
        
        return None
    
    # ==================== Prompt 构建 ====================
    
    def _build_act_summary_prompt(
        self,
        act_node,
        chapter_info: List[Dict],
        foreshadowing_info: Dict,
    ) -> Prompt:
        """构建幕摘要 Prompt"""
        chapters_text = "\n".join([
            f"第{ch['number']}章《{ch['title']}》: {ch['outline'][:100]}"
            for ch in chapter_info[:10]
        ])
        
        foreshadowing_text = ""
        if foreshadowing_info.get("planted"):
            foreshadowing_text += f"\n埋下伏笔: {', '.join(foreshadowing_info['planted'][:5])}"
        if foreshadowing_info.get("resolved"):
            foreshadowing_text += f"\n回收伏笔: {', '.join(foreshadowing_info['resolved'][:5])}"
        
        system = _get_volume_summary_system("act")
        
        user = f"""幕标题：{act_node.title}
幕描述：{act_node.description or '无'}

章节概览：
{chapters_text}
{foreshadowing_text}

请生成这一幕的摘要。"""
        
        return Prompt(system=system, user=user)
    
    def _build_volume_summary_prompt(
        self,
        volume_node,
        act_summaries: List[Dict],
    ) -> Prompt:
        """构建卷摘要 Prompt（Reduce 阶段）"""
        acts_text = "\n\n".join([
            f"【第{act['number']}幕 {act['title']}】\n{act['summary']}"
            for act in act_summaries
        ])
        
        system = _get_volume_summary_system("volume")
        
        user = f"""卷标题：{volume_node.title}
卷描述：{volume_node.description or '无'}

幕摘要汇总：
{acts_text}

请生成这一卷的摘要。"""
        
        return Prompt(system=system, user=user)
    
    def _build_part_summary_prompt(
        self,
        part_node,
        volume_summaries: List[Dict],
    ) -> Prompt:
        """构建部摘要 Prompt"""
        volumes_text = "\n\n".join([
            f"【第{vol['number']}卷 {vol['title']}】\n{vol['summary']}"
            for vol in volume_summaries
        ])
        
        system = _get_volume_summary_system("part")
        
        user = f"""部标题：{part_node.title}
部描述：{part_node.description or '无'}

卷摘要汇总：
{volumes_text}

请生成这一部的摘要。"""
        
        return Prompt(system=system, user=user)
    
    def _build_checkpoint_summary_prompt(
        self,
        current_chapter: int,
        chapter_info: List[Dict],
    ) -> Prompt:
        """构建检查点摘要 Prompt"""
        chapters_text = "\n".join([
            f"第{ch['number']}章《{ch['title']}》: {ch['content_preview'][:200]}"
            for ch in chapter_info
        ])
        
        system = _get_volume_summary_system("checkpoint")
        
        user = f"""当前进度：第 {current_chapter} 章

最近章节：
{chapters_text}

请生成检查点摘要。"""
        
        return Prompt(system=system, user=user)
    
    # ==================== 辅助方法 ====================
    
    async def _get_foreshadowing_info(
        self,
        novel_id: str,
        chapter_start: Optional[int],
        chapter_end: Optional[int],
    ) -> Dict[str, List[str]]:
        """获取伏笔信息"""
        result = {"planted": [], "resolved": []}
        
        if not self.foreshadowing_repo:
            return result
        
        try:
            from domain.novel.value_objects.novel_id import NovelId
            registry = self.foreshadowing_repo.get_by_novel_id(NovelId(novel_id))
            
            if not registry:
                return result
            
            for f in registry.foreshadowings:
                if chapter_start and chapter_end:
                    if f.planted_in_chapter >= chapter_start and f.planted_in_chapter <= chapter_end:
                        result["planted"].append(f.description)
                    if f.resolved_in_chapter and f.resolved_in_chapter >= chapter_start and f.resolved_in_chapter <= chapter_end:
                        result["resolved"].append(f.description)
            
        except Exception as e:
            logger.warning(f"获取伏笔信息失败: {e}")
        
        return result
    
    async def _generate_volume_summary_from_chapters(
        self,
        novel_id: str,
        volume_node,
    ) -> SummaryResult:
        """如果没有幕节点，直接从章节生成卷摘要"""
        if not self.chapter_repo:
            return SummaryResult(success=False, error="无幕节点且 chapter_repo 未初始化")
        
        try:
            # 获取该卷范围的章节
            nid = NovelId(novel_id)
            all_chapters = self.chapter_repo.list_by_novel(nid)
            
            volume_chapters = [
                ch for ch in all_chapters
                if volume_node.chapter_start and volume_node.chapter_end
                and volume_node.chapter_start <= ch.number <= volume_node.chapter_end
            ]
            
            if not volume_chapters:
                return SummaryResult(success=False, error="卷下无章节")
            
            chapter_info = [
                {
                    "number": ch.number,
                    "title": ch.title,
                    "content_preview": (ch.content or "")[:300],
                }
                for ch in sorted(volume_chapters, key=lambda x: x.number)
            ]
            
            prompt = Prompt(
                system="你是一位专业的小说编辑，擅长提炼长篇故事的精华。请生成卷级摘要，约 300-500 字。",
                user=f"""卷标题：{volume_node.title}
卷描述：{volume_node.description or '无'}
章节范围：第 {volume_node.chapter_start} - {volume_node.chapter_end} 章

章节预览：
{chr(10).join([f"第{ch['number']}章: {ch['content_preview'][:100]}" for ch in chapter_info[:20]])}

请生成这一卷的摘要。"""
            )
            
            response = await self.llm_service.generate(
                prompt,
                GenerationConfig(max_tokens=800, temperature=0.5)
            )
            
            summary = response.content.strip() if hasattr(response, 'content') else str(response).strip()
            
            # 保存
            volume_node.metadata = volume_node.metadata or {}
            volume_node.metadata["summary"] = summary
            volume_node.metadata["summary_generated_at"] = datetime.now().isoformat()
            await self.story_node_repo.update(volume_node)
            
            return SummaryResult(
                success=True,
                summary=summary,
                tokens=len(summary) // 2,
            )
            
        except Exception as e:
            logger.error(f"从章节生成卷摘要失败: {e}", exc_info=True)
            return SummaryResult(success=False, error=str(e))
