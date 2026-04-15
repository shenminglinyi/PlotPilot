"""Skill-Driven Prompt Builder - 根据 Skill 构建优化的写作 Prompt（Hermes 自优化核心）"""
import logging
from typing import Dict, List, Optional, Any
from application.engine.services.skill_storage import SkillStorage, PresetSkill
from application.engine.services.skill_extractor import SkillDocument

logger = logging.getLogger(__name__)


class SkillDrivenPromptBuilder:
    """根据已提取的 Skill 构建优化的写作提示词"""

    def __init__(self, skill_storage: SkillStorage):
        self.skill_storage = skill_storage

    def build(
        self,
        novel_id: str,
        novel_title: str,
        next_chapter: int,
        scene_type: str = "",
        prev_tension: int = 0,
        act_number: int = 0,
        base_prompt: str = "",
    ) -> str:
        """
        构建写作 Prompt，优先使用预设 Skill，其次使用提取的 Skill
        
        策略：
        1. 如果有匹配的预设 Skill，优先使用
        2. 如果有提取的 Skill，作为补充
        3. 两者结合，避免屎山
        """
        # 1. 查找预设 Skill
        preset_skill = self.skill_storage.find_preset_skill(
            scene_type=scene_type,
            tension=prev_tension,
            act_number=act_number,
        )
        
        # 2. 查找提取的 Skill
        extracted_skill = self.skill_storage.get_best_matching_skill(
            novel_id=novel_id,
            scene_type=scene_type,
            prev_tension=prev_tension,
            act_number=act_number,
        )
        
        # 3. 获取最近的 Skills
        recent_skills = self._get_recent_skills(novel_id, limit=3)

        # 4. 构建 Prompt
        sections = []
        
        # 4.1 预设 Skill 部分（核心指导）
        if preset_skill:
            logger.info(f"[Hermes] Using preset skill: {preset_skill.name}")
            sections.append(preset_skill.to_prompt_section())
        
        # 4.2 提取的 Skill 部分（补充优化）
        if extracted_skill:
            logger.info(f"[Hermes] Using extracted skill from chapter {extracted_skill.chapter}")
            extracted_section = self._render_extracted_skill_section(extracted_skill)
            if extracted_section:
                sections.append(extracted_section)
        
        # 4.3 近期 Skills 统计（参考）
        if recent_skills:
            recent_section = self._render_recent_skills_section(recent_skills)
            if recent_section:
                sections.append(recent_section)

        # 5. 如果没有找到任何 Skill，使用 base prompt
        if not sections:
            logger.info(f"[Hermes] No skills found for novel={novel_id}, using base prompt")
            return base_prompt

        # 6. 组合最终 Prompt
        hermes_addition = "\n\n【Hermes 自优化指南】\n\n" + "\n\n---\n\n".join(sections)
        
        # 7. 添加控制说明，防止屎山
        hermes_addition += """

---

【重要提醒】
1. 以上指南是参考，不是束缚，根据实际剧情灵活运用
2. 优先保证故事流畅和角色一致性
3. 不要为了符合模板而牺牲剧情合理性
4. 如果本章有特殊需求，可以突破上述约束
"""

        if base_prompt:
            return base_prompt + hermes_addition
        return hermes_addition

    def _get_recent_skills(
        self, novel_id: str, limit: int = 3
    ) -> List[SkillDocument]:
        all_skills = self.skill_storage.load_l1_skills(novel_id)
        active = [s for s in all_skills if not s.deprecated]
        active.sort(key=lambda s: s.chapter, reverse=True)
        return active[:limit]

    def _render_extracted_skill_section(
        self,
        skill: SkillDocument,
    ) -> str:
        """渲染提取的 Skill 部分（简洁版）"""
        lines = ["【本章特定优化】"]
        lines.append(f"基于第{skill.chapter}章的成功模式:")
        
        if skill.structure_template:
            # 只取结构模板的前3行，避免过长
            template_lines = skill.structure_template.split("\n")[:3]
            lines.append("结构参考:")
            for line in template_lines:
                lines.append(f"  {line}")
        
        if skill.tension_score > 0:
            lines.append(f"张力控制: {skill.tension_score:.1f}/10")
        
        return "\n".join(lines)

    def _render_recent_skills_section(
        self,
        recent_skills: List[SkillDocument],
    ) -> str:
        """渲染近期 Skills 统计（参考版）"""
        if not recent_skills:
            return ""
        
        lines = ["【近期文风参考】"]
        
        # 计算平均值
        avg_tension = sum(s.tension_score for s in recent_skills) / len(recent_skills)
        avg_confidence = sum(s.confidence for s in recent_skills) / len(recent_skills)
        
        lines.append(f"近期平均张力: {avg_tension:.1f}")
        lines.append(f"模式置信度: {avg_confidence:.2f}")
        
        # 场景类型分布
        scene_types = {}
        for s in recent_skills:
            scene_types[s.scene_type] = scene_types.get(s.scene_type, 0) + 1
        
        if scene_types:
            lines.append("近期场景类型:")
            for scene_type, count in scene_types.items():
                lines.append(f"  - {scene_type}: {count}章")
        
        return "\n".join(lines)

    def _render_skill_section(
        self,
        best_skill: Optional[SkillDocument],
        recent_skills: List[SkillDocument],
    ) -> str:
        """旧方法：渲染 Skill 部分（保留用于兼容）"""
        if best_skill is None:
            return ""

        lines = ["【成功模式参考】"]

        if best_skill.structure_template:
            lines.append(f"场景类型: {best_skill.scene_type}")
            lines.append(f"结构模板:\n{best_skill.structure_template}")

        if recent_skills:
            lines.append("\n近期章节模式:")
            for skill in recent_skills:
                lines.append(
                    f"  第{skill.chapter}章: {skill.scene_type}, "
                    f"张力={skill.tension_score:.1f}, "
                    f"置信度={skill.confidence:.1f}"
                )

        return "\n".join(lines)

    def _render_style_section(
        self,
        best_skill: Optional[SkillDocument],
        recent_skills: List[SkillDocument],
    ) -> str:
        """旧方法：渲染风格部分（保留用于兼容）"""
        if best_skill is None and not recent_skills:
            return ""

        lines = ["【文风约束】"]

        if best_skill:
            lines.append(f"- 平均句长: {best_skill.avg_sentence_length:.1f}字")
            lines.append(f"- 对话占比: {best_skill.dialogue_ratio:.1f}%")
            lines.append(f"- 感官词密度: {best_skill.sensory_density:.1f}/100字")
            lines.append(f"- 情绪曲线: {best_skill.emotion_curve}")

        if recent_skills:
            avg_sent = sum(s.avg_sentence_length for s in recent_skills) / len(recent_skills)
            avg_dial = sum(s.dialogue_ratio for s in recent_skills) / len(recent_skills)
            avg_sens = sum(s.sensory_density for s in recent_skills) / len(recent_skills)

            lines.append(f"\n近期平均文风:")
            lines.append(f"- 平均句长: {avg_sent:.1f}字")
            lines.append(f"- 对话占比: {avg_dial:.1f}%")
            lines.append(f"- 感官词密度: {avg_sens:.1f}/100字")

        return "\n".join(lines)

    def _render_foreshadow_section(
        self,
        best_skill: Optional[SkillDocument],
        recent_skills: List[SkillDocument],
    ) -> str:
        """旧方法：渲染伏笔部分（保留用于兼容）"""
        unresolved = []
        for skill in recent_skills:
            if skill.new_hooks:
                unresolved.append(f"  第{skill.chapter}章埋设: {skill.new_hooks}")

        if not unresolved:
            return ""

        lines = ["【伏笔处理要求】"]
        lines.append("尚未回收的伏笔（优先在本章回收）:")
        lines.extend(unresolved)

        return "\n".join(lines)
