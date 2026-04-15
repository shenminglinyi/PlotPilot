"""Self-Improvement Monitor - 监控 Skill 效果并持续优化（Hermes 自优化核心）"""
import logging
from typing import Dict, Optional, Any
from application.engine.services.skill_extractor import SkillDocument
from application.engine.services.skill_storage import SkillStorage

logger = logging.getLogger(__name__)


class SelfImprovementMonitor:
    """监控 Skill 效果，持续优化"""

    def __init__(self, skill_storage: SkillStorage):
        self.skill_storage = skill_storage

    def evaluate_chapter(
        self,
        novel_id: str,
        chapter_num: int,
        actual_tension: float,
        actual_quality: float,
        applied_skill_chapter: Optional[int] = None,
    ) -> Dict[str, Any]:
        result = {
            "novel_id": novel_id,
            "chapter": chapter_num,
            "action": "none",
            "reason": "",
        }

        if applied_skill_chapter is None:
            result["action"] = "skip"
            result["reason"] = "no_skill_applied"
            return result

        skill = self.skill_storage.get_skill_by_chapter(novel_id, applied_skill_chapter)
        if skill is None:
            result["action"] = "skip"
            result["reason"] = "skill_not_found"
            return result

        predicted_quality = skill.tension_score / 10.0 * 100
        quality_ratio = actual_quality / predicted_quality if predicted_quality > 0 else 1.0

        if quality_ratio > 1.1:
            self.skill_storage.update_skill_confidence(
                novel_id, applied_skill_chapter, delta=0.1
            )
            result["action"] = "reinforce"
            result["reason"] = (
                f"quality_ratio={quality_ratio:.2f} > 1.1, "
                f"actual={actual_quality:.1f}, predicted={predicted_quality:.1f}"
            )
            logger.info(
                f"[Hermes] Skill reinforced: novel={novel_id}, "
                f"skill_chapter={applied_skill_chapter}, ratio={quality_ratio:.2f}"
            )

        elif quality_ratio < 0.9:
            self.skill_storage.update_skill_confidence(
                novel_id, applied_skill_chapter, delta=-0.05
            )
            result["action"] = "patch"
            result["reason"] = (
                f"quality_ratio={quality_ratio:.2f} < 0.9, "
                f"actual={actual_quality:.1f}, predicted={predicted_quality:.1f}"
            )
            logger.warning(
                f"[Hermes] Skill underperforming: novel={novel_id}, "
                f"skill_chapter={applied_skill_chapter}, ratio={quality_ratio:.2f}"
            )

            skill_check = self.skill_storage.get_skill_by_chapter(
                novel_id, applied_skill_chapter
            )
            if skill_check and skill_check.confidence < 0.3:
                self.skill_storage.deprecate_skill(novel_id, applied_skill_chapter)
                result["action"] = "deprecate"
                result["reason"] += ", confidence too low, deprecated"
                logger.warning(
                    f"[Hermes] Skill deprecated: novel={novel_id}, "
                    f"skill_chapter={applied_skill_chapter}"
                )
        else:
            result["action"] = "keep"
            result["reason"] = (
                f"quality_ratio={quality_ratio:.2f}, within acceptable range"
            )

        return result
