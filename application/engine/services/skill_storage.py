"""Skill Storage - 三级技能存储系统（L1 小说级 / L2 作者级 / L3 通用）"""
import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional
from application.engine.services.skill_extractor import SkillDocument
from application.paths import AITEXT_ROOT

logger = logging.getLogger(__name__)


class PresetSkill:
    """预设 Skill（类似 Hermes 的固定模式）"""
    
    def __init__(
        self,
        skill_id: str,
        name: str,
        version: int,
        scene_type: str,
        confidence: float,
        tension_range: List[int],
        applicable_acts: List[int],
        structure_template: str,
        style_constraints: Dict,
        writing_tips: List[str],
        common_mistakes: List[str],
        max_optimizations: int = 3,
        current_optimizations: int = 0,
        is_preset: bool = True,
    ):
        self.skill_id = skill_id
        self.name = name
        self.version = version
        self.scene_type = scene_type
        self.confidence = confidence
        self.tension_range = tension_range
        self.applicable_acts = applicable_acts
        self.structure_template = structure_template
        self.style_constraints = style_constraints
        self.writing_tips = writing_tips
        self.common_mistakes = common_mistakes
        self.max_optimizations = max_optimizations
        self.current_optimizations = current_optimizations
        self.is_preset = is_preset
    
    def can_optimize(self) -> bool:
        """检查是否还可以优化"""
        return self.current_optimizations < self.max_optimizations
    
    def to_prompt_section(self) -> str:
        """转换为 Prompt 段落"""
        lines = [f"【{self.name} 写作模式】"]
        lines.append(f"\n结构模板:\n{self.structure_template}")
        lines.append(f"\n文风约束:")
        for key, value in self.style_constraints.items():
            lines.append(f"  - {key}: {value}")
        lines.append(f"\n写作要点:")
        for tip in self.writing_tips:
            lines.append(f"  - {tip}")
        lines.append(f"\n避免错误:")
        for mistake in self.common_mistakes:
            lines.append(f"  - {mistake}")
        return "\n".join(lines)


class SkillStorage:
    """三级技能存储 + 预设 Skill 管理"""

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir is None:
            base_dir = os.path.join(os.getcwd(), ".plotpilot", "skills")
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # 预设 skill 目录
        self.preset_dir = AITEXT_ROOT / ".plotpilot" / "presets" / "skills"
        self._preset_skills: List[PresetSkill] = []
        self._load_preset_skills()

    def save_to_l1(self, skill: SkillDocument) -> str:
        novel_dir = self.base_dir / f"novel-{skill.novel_id}"
        novel_dir.mkdir(parents=True, exist_ok=True)

        filename = f"chapter-{skill.chapter:03d}-skill.md"
        filepath = novel_dir / filename

        filepath.write_text(skill.to_markdown(), encoding="utf-8")

        meta_file = novel_dir / "skills-index.json"
        index = self._load_index(meta_file)
        index[str(skill.chapter)] = {
            "skill_id": skill.skill_id,
            "scene_type": skill.scene_type,
            "tension_score": skill.tension_score,
            "confidence": skill.confidence,
            "deprecated": skill.deprecated,
            "filename": filename,
        }
        self._save_index(meta_file, index)

        logger.info(
            f"[Hermes] Skill saved to L1: novel={skill.novel_id}, "
            f"chapter={skill.chapter}, file={filepath}"
        )
        return str(filepath)

    def load_l1_skills(self, novel_id: str) -> List[SkillDocument]:
        novel_dir = self.base_dir / f"novel-{novel_id}"
        if not novel_dir.exists():
            return []

        meta_file = novel_dir / "skills-index.json"
        index = self._load_index(meta_file)

        skills = []
        for chapter_key, meta in sorted(index.items(), key=lambda x: int(x[0])):
            if meta.get("deprecated", False):
                continue

            filename = meta.get("filename", f"chapter-{int(chapter_key):03d}-skill.md")
            filepath = novel_dir / filename

            if filepath.exists():
                skill = self._parse_skill_file(filepath)
                if skill is not None:
                    skills.append(skill)

        return skills

    def get_skill_by_chapter(
        self, novel_id: str, chapter_num: int
    ) -> Optional[SkillDocument]:
        novel_dir = self.base_dir / f"novel-{novel_id}"
        filepath = novel_dir / f"chapter-{chapter_num:03d}-skill.md"

        if not filepath.exists():
            return None

        return self._parse_skill_file(filepath)

    def get_best_matching_skill(
        self,
        novel_id: str,
        scene_type: str = "",
        prev_tension: int = 0,
        act_number: int = 0,
    ) -> Optional[SkillDocument]:
        skills = self.load_l1_skills(novel_id)
        if not skills:
            return None

        scored = []
        for skill in skills:
            score = skill.confidence * (1 + skill.success_count * 0.2)

            if skill.scene_type == scene_type:
                score += 3.0

            if abs(skill.prev_tension - prev_tension) <= 2:
                score += 1.0

            if skill.act_number == act_number:
                score += 0.5

            if skill.tension_score >= 7.0:
                score += 1.0

            scored.append((score, skill))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1] if scored else None

    def update_skill_confidence(
        self, novel_id: str, chapter_num: int, delta: float
    ) -> None:
        skill = self.get_skill_by_chapter(novel_id, chapter_num)
        if skill is None:
            return

        skill.confidence = max(0.1, min(2.0, skill.confidence + delta))
        if delta > 0:
            skill.success_count += 1

        novel_dir = self.base_dir / f"novel-{novel_id}"
        filepath = novel_dir / f"chapter-{chapter_num:03d}-skill.md"
        filepath.write_text(skill.to_markdown(), encoding="utf-8")

        meta_file = novel_dir / "skills-index.json"
        index = self._load_index(meta_file)
        if str(chapter_num) in index:
            index[str(chapter_num)]["confidence"] = skill.confidence
            index[str(chapter_num)]["success_count"] = skill.success_count
            self._save_index(meta_file, index)

    def deprecate_skill(self, novel_id: str, chapter_num: int) -> None:
        skill = self.get_skill_by_chapter(novel_id, chapter_num)
        if skill is None:
            return

        skill.deprecated = True
        novel_dir = self.base_dir / f"novel-{novel_id}"
        filepath = novel_dir / f"chapter-{chapter_num:03d}-skill.md"
        filepath.write_text(skill.to_markdown(), encoding="utf-8")

        meta_file = novel_dir / "skills-index.json"
        index = self._load_index(meta_file)
        if str(chapter_num) in index:
            index[str(chapter_num)]["deprecated"] = True
            self._save_index(meta_file, index)

        logger.info(
            f"[Hermes] Skill deprecated: novel={novel_id}, chapter={chapter_num}"
        )

    def _load_index(self, filepath: Path) -> Dict:
        if not filepath.exists():
            return {}
        try:
            return json.loads(filepath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_index(self, filepath: Path, index: Dict) -> None:
        try:
            filepath.write_text(
                json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as e:
            logger.error(f"[Hermes] Failed to save skill index: {e}")

    def _load_preset_skills(self) -> None:
        """加载预设 skills"""
        if not self.preset_dir.exists():
            logger.warning(f"[Hermes] Preset skills directory not found: {self.preset_dir}")
            return
        
        for filepath in self.preset_dir.glob("*.md"):
            try:
                skill = self._parse_preset_skill_file(filepath)
                if skill:
                    self._preset_skills.append(skill)
                    logger.info(f"[Hermes] Loaded preset skill: {skill.name} ({skill.scene_type})")
            except Exception as e:
                logger.error(f"[Hermes] Failed to load preset skill {filepath}: {e}")
        
        logger.info(f"[Hermes] Total preset skills loaded: {len(self._preset_skills)}")
    
    def get_preset_skills(self) -> List[PresetSkill]:
        """获取所有预设 skills"""
        return self._preset_skills
    
    def find_preset_skill(
        self,
        scene_type: str = "",
        tension: int = 0,
        act_number: int = 0,
    ) -> Optional[PresetSkill]:
        """根据条件查找最佳预设 skill"""
        candidates = []
        
        for skill in self._preset_skills:
            score = skill.confidence
            
            # 场景类型匹配
            if skill.scene_type == scene_type:
                score += 5.0
            
            # 张力范围匹配
            if skill.tension_range[0] <= tension <= skill.tension_range[1]:
                score += 2.0
            
            # 幕数匹配
            if act_number in skill.applicable_acts:
                score += 1.0
            
            candidates.append((score, skill))
        
        if not candidates:
            return None
        
        candidates.sort(key=lambda x: x[0], reverse=True)
        best_skill = candidates[0][1]
        
        logger.info(
            f"[Hermes] Found preset skill: {best_skill.name} "
            f"(scene={best_skill.scene_type}, score={candidates[0][0]:.1f})"
        )
        return best_skill

    def _parse_preset_skill_file(self, filepath: Path) -> Optional[PresetSkill]:
        """解析预设 skill 文件"""
        content = filepath.read_text(encoding="utf-8")
        
        # 解析 frontmatter
        frontmatter = {}
        body_sections = {}
        in_frontmatter = False
        current_section = None
        current_content = []
        
        lines = content.split("\n")
        i = 0
        
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Frontmatter 解析
            if stripped == "---":
                if not in_frontmatter:
                    in_frontmatter = True
                else:
                    in_frontmatter = False
                i += 1
                continue
            
            if in_frontmatter and ":" in stripped:
                key, _, value = stripped.partition(":")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                
                # 解析数组
                if value.startswith("[") and value.endswith("]"):
                    value = [int(x.strip()) for x in value[1:-1].split(",") if x.strip()]
                # 解析数字
                elif value.isdigit():
                    value = int(value)
                elif value.replace(".", "").isdigit():
                    value = float(value)
                elif value == "true":
                    value = True
                elif value == "false":
                    value = False
                
                frontmatter[key] = value
            
            # Body 部分解析
            elif not in_frontmatter and stripped.startswith("## "):
                if current_section:
                    body_sections[current_section] = "\n".join(current_content).strip()
                current_section = stripped[3:].strip()
                current_content = []
            elif not in_frontmatter and current_section:
                current_content.append(line)
            
            i += 1
        
        # 保存最后一个 section
        if current_section:
            body_sections[current_section] = "\n".join(current_content).strip()
        
        # 解析风格约束
        style_constraints = {}
        if "文风约束" in body_sections:
            for line in body_sections["文风约束"].split("\n"):
                if line.strip().startswith("-"):
                    parts = line.strip()[1:].strip().split(":", 1)
                    if len(parts) == 2:
                        style_constraints[parts[0].strip()] = parts[1].strip()
        
        # 解析写作要点
        writing_tips = []
        if "写作要点" in body_sections:
            for line in body_sections["写作要点"].split("\n"):
                if line.strip().startswith("-"):
                    writing_tips.append(line.strip()[1:].strip())
        
        # 解析常见错误
        common_mistakes = []
        if "常见错误" in body_sections:
            for line in body_sections["常见错误"].split("\n"):
                if line.strip().startswith("-"):
                    common_mistakes.append(line.strip()[1:].strip())
        
        return PresetSkill(
            skill_id=frontmatter.get("skill_id", ""),
            name=frontmatter.get("name", ""),
            version=frontmatter.get("version", 1),
            scene_type=frontmatter.get("scene_type", ""),
            confidence=frontmatter.get("confidence", 0.8),
            tension_range=frontmatter.get("tension_range", [1, 10]),
            applicable_acts=frontmatter.get("applicable_acts", list(range(1, 13))),
            structure_template=body_sections.get("结构模板", ""),
            style_constraints=style_constraints,
            writing_tips=writing_tips,
            common_mistakes=common_mistakes,
            max_optimizations=frontmatter.get("max_optimizations", 3),
            current_optimizations=frontmatter.get("current_optimizations", 0),
            is_preset=frontmatter.get("is_preset", True),
        )

    def _parse_skill_file(self, filepath: Path) -> Optional[SkillDocument]:
        try:
            content = filepath.read_text(encoding="utf-8")
            frontmatter = {}
            in_frontmatter = False

            for line in content.split("\n"):
                line = line.strip()
                if line == "---":
                    if in_frontmatter:
                        break
                    in_frontmatter = True
                    continue
                if in_frontmatter and ":" in line:
                    key, _, value = line.partition(":")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    frontmatter[key] = value

            return SkillDocument(
                skill_id=frontmatter.get("skill_id", ""),
                novel_id=frontmatter.get("novel_id", ""),
                chapter=int(frontmatter.get("chapter", 0)),
                extracted_at=frontmatter.get("extracted_at", ""),
                scene_type=frontmatter.get("scene_type", ""),
                prev_tension=int(frontmatter.get("prev_tension", 0)),
                act_number=int(frontmatter.get("act_number", 0)),
                confidence=float(frontmatter.get("confidence", 1.0)),
                success_count=int(frontmatter.get("success_count", 0)),
                deprecated=frontmatter.get("deprecated", "false") == "true",
            )
        except Exception as e:
            logger.error(f"[Hermes] Failed to parse skill file {filepath}: {e}")
            return None
