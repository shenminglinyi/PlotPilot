"""ThemeSkillRegistry — 增强技能注册中心

管理所有可用的 ThemeSkill 实例。
提供按 genre 过滤、按 key 查找、自动发现内置 Skills 等能力。

使用方式：
    registry = ThemeSkillRegistry()
    registry.auto_discover()

    # 列出某题材可用的所有 skills
    skills = registry.list_for_genre("xuanhuan")

    # 按 key 获取 skill
    skill = registry.get("cultivation_system")
"""

import logging
from typing import Dict, List, Optional

from application.engine.theme.theme_agent import ThemeSkill

logger = logging.getLogger(__name__)


class ThemeSkillRegistry:
    """增强技能注册中心

    管理 skill_key → ThemeSkill 实例的映射。
    支持手动注册和自动发现两种模式。
    """

    def __init__(self):
        self._skills: Dict[str, ThemeSkill] = {}

    def register(self, skill: ThemeSkill) -> None:
        """注册一个增强技能

        Args:
            skill: ThemeSkill 实例
        """
        key = skill.skill_key
        if key in self._skills:
            logger.warning(
                f"增强技能重复注册：'{key}' "
                f"(已有: {self._skills[key].__class__.__name__}, "
                f"新增: {skill.__class__.__name__})，将覆盖旧实例"
            )
        self._skills[key] = skill
        logger.info(f"注册增强技能: {skill}")

    def unregister(self, skill_key: str) -> bool:
        """注销一个增强技能"""
        if skill_key in self._skills:
            removed = self._skills.pop(skill_key)
            logger.info(f"注销增强技能: {removed}")
            return True
        return False

    def get(self, skill_key: str) -> Optional[ThemeSkill]:
        """按 key 获取技能实例"""
        return self._skills.get(skill_key)

    def list_all(self) -> List[Dict[str, object]]:
        """列出所有已注册的技能

        Returns:
            [{"key": "cultivation_system", "name": "修炼体系",
              "description": "...", "compatible_genres": ["xuanhuan", "xianxia"]}, ...]
        """
        return [
            {
                "key": skill.skill_key,
                "name": skill.skill_name,
                "description": skill.skill_description,
                "compatible_genres": skill.compatible_genres,
            }
            for skill in self._skills.values()
        ]

    def list_for_genre(self, genre_key: str) -> List[Dict[str, object]]:
        """列出某题材可用的所有技能

        兼容两种 skill：
        - compatible_genres 为空列表 → 通用技能，适用于所有题材
        - compatible_genres 包含 genre_key → 题材专属技能

        Args:
            genre_key: 题材标识

        Returns:
            匹配的技能信息列表
        """
        result = []
        for skill in self._skills.values():
            genres = skill.compatible_genres
            if not genres or genre_key in genres:
                result.append({
                    "key": skill.skill_key,
                    "name": skill.skill_name,
                    "description": skill.skill_description,
                    "compatible_genres": genres,
                })
        return result

    def get_skills_by_keys(self, skill_keys: List[str]) -> List[ThemeSkill]:
        """批量按 key 获取技能实例（忽略不存在的 key）

        Args:
            skill_keys: 技能 key 列表

        Returns:
            匹配的 ThemeSkill 实例列表
        """
        return [
            self._skills[k]
            for k in skill_keys
            if k in self._skills
        ]

    @property
    def registered_keys(self) -> List[str]:
        """已注册的所有 skill_key 列表"""
        return list(self._skills.keys())

    def __len__(self) -> int:
        return len(self._skills)

    def __contains__(self, skill_key: str) -> bool:
        return skill_key in self._skills

    def auto_discover(self) -> int:
        """自动发现并注册 skills/ 目录下的所有内置增强技能

        Returns:
            成功注册的 Skill 数量
        """
        count = 0

        # (module_name, class_name, display_name)
        _BUILTIN_SKILLS = [
            ("cultivation_system_skill", "CultivationSystemSkill", "修炼体系"),
            ("battle_choreography_skill", "BattleChoreographySkill", "战斗编排"),
            ("deduction_logic_skill", "DeductionLogicSkill", "推理逻辑"),
            ("emotion_pacing_skill", "EmotionPacingSkill", "情感节奏"),
        ]

        import importlib
        for module_name, class_name, display_name in _BUILTIN_SKILLS:
            try:
                mod = importlib.import_module(
                    f"application.engine.theme.skills.{module_name}"
                )
                cls = getattr(mod, class_name)
                self.register(cls())
                count += 1
            except Exception as e:
                logger.warning(f"加载{display_name}增强技能失败：{e}")

        logger.info(f"增强技能自动发现完成，共注册 {count} 个技能")
        return count

    def __repr__(self) -> str:
        keys = ", ".join(self._skills.keys()) or "(empty)"
        return f"<ThemeSkillRegistry [{keys}]>"
