"""Character实体 — 四维动态模型 + 地质叠层

核心设计：
- 四维心理画像：core_belief / moral_taboos / voice_profile / active_wounds
- 地质叠层架构：Append-only Patch日志，不删除过去，只追加修改
- apply_trauma()：应用创伤事件，追加地质叠层
- compute_mask()：折叠所有Patch，计算当前面具快照

文学意义：
- 让角色在百万字中"成长与黑化"
- 第1章"傻白甜"→ 第100章"冷酷猎手"有完整轨迹可追溯
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import uuid


@dataclass(frozen=True)
class CharacterId:
    """角色ID值对象"""
    value: str

    @classmethod
    def generate(cls) -> CharacterId:
        return cls(value=str(uuid.uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass
class VoiceStyle:
    """语言指纹 — 决定角色的台词风格

    维度3：语言指纹（Voice Profile）
    - 第1章：话多、反问、感叹号、语速快
    - 第100章：惜字如金、陈述句、阴冷隐喻
    """
    style: str = "default"            # 话多/惜字如金/阴冷/热情
    sentence_pattern: str = "mixed"   # 反问/陈述/短句/长句
    punctuation: List[str] = field(default_factory=list)  # ！、...、。习惯
    metaphors: List[str] = field(default_factory=list)     # 阴冷的隐喻/阳光比喻
    catchphrases: List[str] = field(default_factory=list)  # 口头禅
    speech_tempo: str = "normal"      # fast/normal/slow

    def to_t0_instruction(self) -> str:
        """生成T0层语言指纹注入指令"""
        parts = [f"语言风格：{self.style}"]
        if self.sentence_pattern != "mixed":
            parts.append(f"句式偏好：{self.sentence_pattern}")
        if self.punctuation:
            parts.append(f"标点习惯：{'、'.join(self.punctuation)}")
        if self.metaphors:
            parts.append(f"隐喻偏好：{'、'.join(self.metaphors[:3])}")
        if self.catchphrases:
            parts.append(f"口头禅：{'、'.join(self.catchphrases[:2])}")
        if self.speech_tempo != "normal":
            parts.append(f"语速：{self.speech_tempo}")
        return "；".join(parts)


@dataclass(frozen=True)
class Wound:
    """未愈合的创伤 — 条件反射触发器

    维度4：未愈合的创伤（Active Wounds）
    - 左肩被恩师刺伤 → 排斥有人靠近左后方
    - 挚友惨死 → 提及"保护"眼神变冷
    """
    description: str    # 创伤描述："左肩被恩师刺伤"
    trigger: str        # 触发条件："有人靠近左后方"
    effect: str         # 后遗症："肌肉下意识紧绷"

    def to_t0_instruction(self) -> str:
        """生成T0层创伤注入指令"""
        return f"旧伤：{self.description}（触发条件：{self.trigger} → {self.effect}）"


@dataclass
class CharacterPatch:
    """角色地质叠层Patch — Append-only修改日志

    核心思想：不删除过去，只追加修改
    每个Patch记录一次重大事件对角色的改变
    """
    trigger_chapter: int       # 触发章节
    trigger_event: str         # 触发事件："导师背叛"
    changes: Dict[str, Any]    # 修改内容：{"core_belief": "信任是致命软肋"}
    created_at: Optional[str] = None


@dataclass
class Character:
    """角色实体（四维动态模型 + 地质叠层）

    四维心理画像：
    1. core_belief：核心信念（决定价值选择）
    2. moral_taboos：绝对禁忌（决定底线）
    3. voice_profile：语言指纹（决定台词风格）
    4. active_wounds：未愈合创伤（决定条件反射）

    地质叠层：
    - evolution_patches：Append-only日志
    - compute_mask()：折叠所有Patch → 当前面具快照
    """
    character_id: CharacterId
    name: str

    # 四维动态模型
    core_belief: str = ""
    moral_taboos: List[str] = field(default_factory=list)
    voice_profile: VoiceStyle = field(default_factory=VoiceStyle)
    active_wounds: List[Wound] = field(default_factory=list)

    # 地质叠层
    evolution_patches: List[CharacterPatch] = field(default_factory=list)

    # 基础属性
    description: str = ""
    public_profile: str = ""
    hidden_profile: str = ""
    reveal_chapter: Optional[int] = None

    @classmethod
    def create(cls, name: str, core_belief: str = "") -> Character:
        """工厂方法：创建角色"""
        return cls(
            character_id=CharacterId.generate(),
            name=name,
            core_belief=core_belief,
        )

    def apply_trauma(
        self,
        trigger_chapter: int,
        trigger_event: str,
        new_belief: Optional[str] = None,
        new_taboo: Optional[str] = None,
        new_wound: Optional[Wound] = None,
        voice_change: Optional[Dict[str, Any]] = None,
    ) -> CharacterPatch:
        """应用创伤事件（追加地质叠层）

        这是角色成长/黑化的核心机制：
        - 每次创伤都追加一个Patch，不删除过去的记录
        - 修改当前状态的同时记录变更轨迹
        - compute_mask()会折叠所有Patch生成当前面具
        """
        changes: Dict[str, Any] = {}

        if new_belief:
            changes['core_belief'] = new_belief
            self.core_belief = new_belief

        if new_taboo:
            changes['moral_taboos'] = new_taboo
            self.moral_taboos.append(new_taboo)

        if new_wound:
            changes['active_wounds'] = new_wound.description
            self.active_wounds.append(new_wound)

        if voice_change:
            changes['voice_profile'] = voice_change
            for key, val in voice_change.items():
                if hasattr(self.voice_profile, key):
                    setattr(self.voice_profile, key, val)

        patch = CharacterPatch(
            trigger_chapter=trigger_chapter,
            trigger_event=trigger_event,
            changes=changes,
        )
        self.evolution_patches.append(patch)
        return patch

    def compute_mask(self, up_to_chapter: Optional[int] = None) -> Dict[str, Any]:
        """折叠地质叠层 → 计算当前面具快照

        步骤：
        1. 从Base Layer开始
        2. 逐个应用Patch（按章节顺序）
        3. 返回当前面具的完整快照

        Args:
            up_to_chapter: 计算到哪个章节为止（None=全部）
        """
        mask: Dict[str, Any] = {
            "name": self.name,
            "core_belief": self.core_belief,
            "moral_taboos": list(self.moral_taboos),
            "voice_profile": {
                "style": self.voice_profile.style,
                "sentence_pattern": self.voice_profile.sentence_pattern,
                "punctuation": list(self.voice_profile.punctuation),
                "metaphors": list(self.voice_profile.metaphors),
            },
            "active_wounds": [
                {"description": w.description, "trigger": w.trigger, "effect": w.effect}
                for w in self.active_wounds
            ],
        }

        # 如果指定了章节上限，需要从Base开始重新折叠
        if up_to_chapter is not None:
            # 重置为基础层（只保留初始值）
            base_belief = ""
            base_taboos: List[str] = []
            base_wounds: List[Dict] = []
            base_voice: Dict[str, Any] = {
                "style": "default", "sentence_pattern": "mixed",
                "punctuation": [], "metaphors": [],
            }

            # 逐个应用Patch
            for patch in self.evolution_patches:
                if patch.trigger_chapter > up_to_chapter:
                    break
                if 'core_belief' in patch.changes:
                    base_belief = patch.changes['core_belief']
                if 'moral_taboos' in patch.changes:
                    base_taboos.append(patch.changes['moral_taboos'])
                if 'active_wounds' in patch.changes:
                    base_wounds.append({"description": patch.changes['active_wounds']})
                if 'voice_profile' in patch.changes:
                    base_voice.update(patch.changes['voice_profile'])

            mask.update({
                "core_belief": base_belief or self.core_belief,
                "moral_taboos": base_taboos or self.moral_taboos,
                "voice_profile": base_voice,
                "active_wounds": base_wounds or mask["active_wounds"],
            })

        return mask

    def to_t0_fact_lock(self, chapter_number: int) -> str:
        """生成T0层Fact Lock注入格式

        格式示例：
        [角色状态锁定 - 林羽（第50章当前阶段）]
        当前核心信念：只有力量能保护自己，轻信必死。
        当前语言指纹：短句为主，陈述语气，透着背叛后的阴沉。
        身上带着的旧伤：左肩曾被恩师刺伤，极其排斥别人站在他左后方。
        绝对禁忌：绝不杀手无寸铁之人。
        """
        lines = [f"[角色状态锁定 - {self.name}（第{chapter_number}章当前阶段）]"]
        lines.append(f"当前核心信念：{self.core_belief}")

        voice_instruction = self.voice_profile.to_t0_instruction()
        if voice_instruction:
            lines.append(f"当前语言指纹：{voice_instruction}")

        for wound in self.active_wounds:
            lines.append(f"身上带着的旧伤：{wound.to_t0_instruction()}")

        if self.moral_taboos:
            lines.append(f"绝对禁忌：{'、'.join(self.moral_taboos)}")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "character_id": self.character_id.value,
            "name": self.name,
            "core_belief": self.core_belief,
            "moral_taboos": self.moral_taboos,
            "voice_profile": {
                "style": self.voice_profile.style,
                "sentence_pattern": self.voice_profile.sentence_pattern,
            },
            "active_wounds": [
                {"description": w.description, "trigger": w.trigger, "effect": w.effect}
                for w in self.active_wounds
            ],
            "evolution_patches": len(self.evolution_patches),
        }
