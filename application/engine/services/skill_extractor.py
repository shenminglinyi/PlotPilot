"""Skill Extractor - 每章完成后自动提取写作模式（Hermes 自优化核心）"""
import logging
import re
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class SkillDocument:
    skill_id: str
    novel_id: str
    chapter: int
    extracted_at: str
    scene_type: str = ""
    prev_tension: int = 0
    act_number: int = 0
    character_emotions: str = ""
    structure_template: str = ""
    avg_sentence_length: float = 0.0
    dialogue_ratio: float = 0.0
    sensory_density: float = 0.0
    emotion_curve: str = ""
    resolved_hooks: str = ""
    new_hooks: str = ""
    tension_score: float = 0.0
    retention_prediction: float = 0.0
    ai_score: float = 0.0
    applicable_scenarios: str = ""
    confidence: float = 1.0
    success_count: int = 0
    deprecated: bool = False

    def to_markdown(self) -> str:
        return f"""---
skill_id: "{self.skill_id}"
novel_id: "{self.novel_id}"
chapter: {self.chapter}
extracted_at: "{self.extracted_at}"
confidence: {self.confidence}
success_count: {self.success_count}
deprecated: {str(self.deprecated).lower()}
---

## 触发条件
- 场景类型: {self.scene_type}
- 前章张力值: {self.prev_tension}/10
- 当前幕: 第{self.act_number}幕
- 角色情绪: {self.character_emotions}

## 成功模式

### 结构模板
{self.structure_template}

### 文风指纹
- 平均句长: {self.avg_sentence_length:.1f}字
- 对话占比: {self.dialogue_ratio:.1f}%
- 感官词密度: {self.sensory_density:.1f}/100字
- 情绪曲线: {self.emotion_curve}

### 伏笔处理
- 本章回收伏笔: {self.resolved_hooks or '无'}
- 本章新埋伏笔: {self.new_hooks or '无'}

## 质量指标
- 张力评分: {self.tension_score:.1f}/10
- 读者留存预测: {self.retention_prediction:.0f}%
- AI检测分数: {self.ai_score:.2f}

## 适用场景
{self.applicable_scenarios}
"""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SkillExtractor:
    """每章完成后自动提取写作模式"""

    SENSORY_WORDS = [
        "看", "听", "闻", "摸", "尝", "望", "瞧", "瞥", "瞪", "盯",
        "响", "鸣", "吼", "喊", "叫", "吟", "唱", "嘶", "嗡", "轰",
        "香", "臭", "腥", "酸", "甜", "苦", "辣", "咸",
        "冷", "热", "凉", "暖", "冰", "烫", "湿", "干",
        "光滑", "粗糙", "柔软", "坚硬", "尖锐", "沉重", "轻盈",
        "刺鼻", "芬芳", "清新", "浑浊",
        "光芒", "阴影", "色彩", "轮廓", "闪烁", "耀眼",
    ]

    SCENE_PATTERNS = {
        "conflict_escalation": [
            r"[争斗打杀冲撞推搡]", r"怒[吼叫骂视]", r"剑[指拔出]",
            r"对峙", r"冲突", r"矛盾", r"激化",
        ],
        "emotional_climax": [
            r"[哭笑泪]", r"心[碎痛颤动]", r"颤抖",
            r"绝望", r"崩溃", r"释然", r"感动",
        ],
        "daily_transition": [
            r"[吃喝睡歇]", r"闲聊", r"散步", r"修炼",
            r"平静", r"安宁", r"日常",
        ],
        "suspense_setup": [
            r"神秘", r"未知", r"暗[示藏藏]", r"线索",
            r"疑[惑问惑]", r"蹊跷", r"不对劲",
        ],
        "revelation": [
            r"真相", r"揭开", r"暴露", r"发现",
            r"原来", r"竟[然是]", r"身份",
        ],
    }

    def extract(
        self,
        chapter_content: str,
        chapter_number: int,
        novel_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> SkillDocument:
        context = context or {}

        structure = self._analyze_structure(chapter_content)
        fingerprint = self._extract_fingerprint(chapter_content)
        scene_type = self._identify_scene_type(chapter_content)
        emotion_curve = self._analyze_emotion(chapter_content)
        tension = self._score_tension(chapter_content)
        foreshadowing = self._analyze_foreshadowing(chapter_content, context)

        from datetime import datetime, timezone
        extracted_at = datetime.now(timezone.utc).isoformat()

        skill = SkillDocument(
            skill_id=f"{scene_type}-{novel_id}-{chapter_number}",
            novel_id=novel_id,
            chapter=chapter_number,
            extracted_at=extracted_at,
            scene_type=scene_type,
            prev_tension=context.get("prev_tension", 0),
            act_number=context.get("act_number", 0),
            character_emotions=context.get("character_emotions", ""),
            structure_template=structure,
            avg_sentence_length=fingerprint["avg_sentence_length"],
            dialogue_ratio=fingerprint["dialogue_ratio"],
            sensory_density=fingerprint["sensory_density"],
            emotion_curve=emotion_curve,
            resolved_hooks=foreshadowing["resolved"],
            new_hooks=foreshadowing["new"],
            tension_score=tension,
            retention_prediction=self._predict_retention(tension, fingerprint),
            ai_score=self._estimate_ai_score(fingerprint),
            applicable_scenarios=self._infer_applicable_scenes(scene_type, context),
        )

        logger.info(
            f"[Hermes] Skill extracted: novel={novel_id}, chapter={chapter_number}, "
            f"scene={scene_type}, tension={tension:.1f}"
        )
        return skill

    def _analyze_structure(self, content: str) -> str:
        paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
        if not paragraphs:
            return "空章节"

        total = len(paragraphs)
        setup_end = max(1, total // 5)
        trigger_end = setup_end + max(1, total // 5)
        climax_end = trigger_end + max(1, total * 2 // 5)
        twist_end = climax_end + max(1, total // 5)

        parts = []
        if setup_end > 0:
            parts.append(f"1. 铺设({setup_end}段): 氛围营造与角色引入")
        if trigger_end > setup_end:
            parts.append(f"2. 触发({trigger_end - setup_end}段): 事件触发与矛盾初现")
        if climax_end > trigger_end:
            parts.append(f"3. 高潮({climax_end - trigger_end}段): 冲突爆发与情绪顶点")
        if twist_end > climax_end:
            parts.append(f"4. 转折({twist_end - climax_end}段): 局势变化与意外因素")
        if total > twist_end:
            parts.append(f"5. 余波({total - twist_end}段): 心理变化与伏笔埋设")

        return "\n".join(parts)

    def _extract_fingerprint(self, content: str) -> Dict[str, float]:
        sentences = re.split(r'[。！？；\n]', content)
        sentences = [s.strip() for s in sentences if s.strip()]

        avg_len = 0.0
        if sentences:
            avg_len = sum(len(s) for s in sentences) / len(sentences)

        dialogue_chars = 0
        in_dialogue = False
        for ch in content:
            if ch in '「"':
                in_dialogue = True
            elif ch in '」"':
                in_dialogue = False
            elif in_dialogue:
                dialogue_chars += 1

        dialogue_ratio = (dialogue_chars / len(content) * 100) if content else 0.0

        sensory_count = sum(
            1 for w in self.SENSORY_WORDS if w in content
        )
        sensory_density = (sensory_count / len(content) * 100) if content else 0.0

        return {
            "avg_sentence_length": round(avg_len, 1),
            "dialogue_ratio": round(dialogue_ratio, 1),
            "sensory_density": round(sensory_density, 1),
        }

    def _identify_scene_type(self, content: str) -> str:
        scores = {}
        for scene_type, patterns in self.SCENE_PATTERNS.items():
            score = 0
            for pattern in patterns:
                matches = re.findall(pattern, content)
                score += len(matches)
            scores[scene_type] = score

        if not scores or max(scores.values()) == 0:
            return "general"

        return max(scores, key=scores.get)

    def _analyze_emotion(self, content: str) -> str:
        positive_words = ["笑", "喜", "乐", "欢", "暖", "爱", "希望", "光明", "释然", "感动"]
        negative_words = ["怒", "恨", "悲", "哭", "痛", "惧", "绝望", "黑暗", "崩溃", "恐惧"]
        tension_words = ["紧张", "危险", "急", "快", "冲", "战", "杀", "血", "死", "险"]

        pos = sum(content.count(w) for w in positive_words)
        neg = sum(content.count(w) for w in negative_words)
        ten = sum(content.count(w) for w in tension_words)

        if ten > pos and ten > neg:
            return "紧张→释放"
        elif neg > pos:
            return "压抑→低谷"
        elif pos > neg:
            return "平缓→上升"
        else:
            return "平稳过渡"

    def _score_tension(self, content: str) -> float:
        high_tension = ["战", "杀", "死", "血", "怒", "吼", "冲", "爆", "危", "险"]
        mid_tension = ["争", "斗", "抗", "拒", "疑", "惧", "紧", "急", "逼", "压"]
        low_tension = ["静", "安", "闲", "歇", "聊", "笑", "暖", "和", "平", "宁"]

        high = sum(content.count(w) for w in high_tension)
        mid = sum(content.count(w) for w in mid_tension)
        low = sum(content.count(w) for w in low_tension)

        total = high + mid + low
        if total == 0:
            return 5.0

        score = (high * 10 + mid * 6 + low * 2) / total
        return min(10.0, max(1.0, round(score, 1)))

    def _analyze_foreshadowing(
        self, content: str, context: Dict[str, Any]
    ) -> Dict[str, str]:
        resolved = context.get("resolved_hooks", "")
        new_hooks_patterns = [
            r"神秘.{0,10}(?=[，。！？])",
            r"似乎.{0,10}(?=[，。！？])",
            r"暗自.{0,10}(?=[，。！？])",
            r"不知.{0,10}(?=[，。！？])",
        ]

        new_found = []
        for pattern in new_hooks_patterns:
            matches = re.findall(pattern, content)
            new_found.extend(matches[:2])

        return {
            "resolved": str(resolved) if resolved else "",
            "new": "；".join(new_found[:3]) if new_found else "",
        }

    def _predict_retention(self, tension: float, fingerprint: Dict[str, float]) -> float:
        base = 70.0
        if 6 <= tension <= 9:
            base += 15
        elif tension >= 9:
            base += 10
        else:
            base += 5

        if 30 <= fingerprint["dialogue_ratio"] <= 60:
            base += 5
        if fingerprint["sensory_density"] >= 2.0:
            base += 3

        return min(98.0, base)

    def _estimate_ai_score(self, fingerprint: Dict[str, float]) -> float:
        score = 0.5
        if 15 <= fingerprint["avg_sentence_length"] <= 25:
            score -= 0.1
        if fingerprint["dialogue_ratio"] >= 25:
            score -= 0.1
        if fingerprint["sensory_density"] >= 1.5:
            score -= 0.05
        return max(0.1, round(score, 2))

    def _infer_applicable_scenes(
        self, scene_type: str, context: Dict[str, Any]
    ) -> str:
        act = context.get("act_number", 0)
        scenarios = []

        if scene_type == "conflict_escalation":
            scenarios.append("幕中段冲突升级")
            scenarios.append("多角色对峙场景")
        elif scene_type == "emotional_climax":
            scenarios.append("情感爆发转折点")
            scenarios.append("角色心理变化场景")
        elif scene_type == "daily_transition":
            scenarios.append("高潮后的缓冲过渡")
            scenarios.append("日常修炼/生活场景")
        elif scene_type == "suspense_setup":
            scenarios.append("新线索/伏笔埋设")
            scenarios.append("悬念设置场景")
        elif scene_type == "revelation":
            scenarios.append("真相揭露场景")
            scenarios.append("身份曝光/反转场景")
        else:
            scenarios.append("通用叙事场景")

        if act > 0:
            scenarios.append(f"第{act}幕及后续幕的类似场景")

        return "；".join(scenarios)
