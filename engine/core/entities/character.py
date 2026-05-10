"""统一Character实体 — 四维动态模型 + POV防火墙 + 图谱属性

这是AIText剧情引擎的**唯一**Character定义，合并了三版精华：
1. engine/domain/entities/character.py 的四维心理画像+地质叠层
2. domain/bible/entities/character.py 的POV防火墙+行为细节
3. domain/cast/entities/character.py 的别名+图谱属性

架构定位：
- engine/core 层的纯粹领域实体，无外部依赖
- 旧 domain/bible/entities/character.py 和 domain/cast/entities/character.py
  改为从此模块导入并适配（兼容层）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import uuid


# ─── 值对象 ───


@dataclass(frozen=True)
class CharacterId:
    """角色ID值对象"""
    value: str

    @classmethod
    def generate(cls) -> CharacterId:
        return cls(value=str(uuid.uuid4()))

    def __str__(self) -> str:
        return self.value

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, CharacterId):
            return False
        return self.value == other.value

    def __hash__(self) -> int:
        return hash(self.value)


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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "style": self.style,
            "sentence_pattern": self.sentence_pattern,
            "punctuation": list(self.punctuation),
            "metaphors": list(self.metaphors),
            "catchphrases": list(self.catchphrases),
            "speech_tempo": self.speech_tempo,
        }


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

    def to_dict(self) -> Dict[str, str]:
        return {"description": self.description, "trigger": self.trigger, "effect": self.effect}


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


# ─── 聚合根 ───


@dataclass
class Character:
    """统一角色实体 — 剧情引擎的核心角色模型

    ═══ 四维心理画像（引擎内核）═══
    1. core_belief：核心信念 — 决定价值选择
    2. moral_taboos：绝对禁忌 — 决定底线
    3. voice_profile：语言指纹 — 决定台词风格
    4. active_wounds：未愈合创伤 — 决定条件反射

    ═══ 地质叠层（引擎内核）═══
    - evolution_patches：Append-only日志
    - compute_mask()：折叠所有Patch → 当前面具快照
    - apply_trauma()：追加地质叠层
    - to_t0_fact_lock()：T0层注入指令

    ═══ POV防火墙（旧Bible精华）═══
    - public_profile / hidden_profile / reveal_chapter
    - mental_state / verbal_tic / idle_behavior

    ═══ 图谱属性（旧Cast精华）═══
    - aliases：别名系统
    - role：角色定位
    - relationships：关系列表
    """
    character_id: CharacterId
    name: str

    # ─── 四维动态模型 ───
    core_belief: str = ""
    moral_taboos: List[str] = field(default_factory=list)
    voice_profile: VoiceStyle = field(default_factory=VoiceStyle)
    active_wounds: List[Wound] = field(default_factory=list)

    # ─── 地质叠层 ───
    evolution_patches: List[CharacterPatch] = field(default_factory=list)

    # ─── POV防火墙（从Bible吸收）───
    description: str = ""
    public_profile: str = ""
    hidden_profile: str = ""
    reveal_chapter: Optional[int] = None

    # ─── 行为细节（从Bible吸收）───
    mental_state: str = "NORMAL"
    verbal_tic: str = ""
    idle_behavior: str = ""

    # ─── 图谱属性（从Cast吸收）───
    aliases: List[str] = field(default_factory=list)
    role: str = ""
    relationships: List[Any] = field(default_factory=list)

    def __post_init__(self):
        if self.reveal_chapter is not None and self.reveal_chapter < 1:
            raise ValueError(f"reveal_chapter must be >= 1, got {self.reveal_chapter}")

    # ─── 工厂方法 ───

    @classmethod
    def create(cls, name: str, core_belief: str = "", description: str = "") -> Character:
        """工厂方法：创建角色"""
        return cls(
            character_id=CharacterId.generate(),
            name=name,
            core_belief=core_belief,
            description=description,
        )

    # ─── 地质叠层操作 ───

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

        角色成长/黑化的核心机制：
        - 每次创伤追加一个Patch，不删除过去
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
        """
        mask: Dict[str, Any] = {
            "name": self.name,
            "core_belief": self.core_belief,
            "moral_taboos": list(self.moral_taboos),
            "voice_profile": self.voice_profile.to_dict(),
            "active_wounds": [w.to_dict() for w in self.active_wounds],
        }

        if up_to_chapter is not None:
            base_belief = ""
            base_taboos: List[str] = []
            base_wounds: List[Dict] = []
            base_voice: Dict[str, Any] = {
                "style": "default", "sentence_pattern": "mixed",
                "punctuation": [], "metaphors": [],
            }

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

    # ─── T0层注入 ───

    def to_t0_fact_lock(self, chapter_number: int) -> str:
        """生成T0层Fact Lock注入格式"""
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

    # ─── POV防火墙 ───

    def is_profile_visible(self, current_chapter: int) -> str:
        """获取当前章节可见的角色描述（POV防火墙）

        如果当前章节 >= reveal_chapter，显示完整描述；
        否则只显示公开信息。
        """
        if self.reveal_chapter is None or current_chapter >= self.reveal_chapter:
            parts = []
            if self.public_profile:
                parts.append(self.public_profile)
            if self.hidden_profile:
                parts.append(self.hidden_profile)
            return "\n".join(parts) if parts else self.description
        return self.public_profile or self.description

    # ─── 关系管理（兼容旧Bible接口）───

    def add_relationship(self, relationship: Any) -> None:
        """添加关系"""
        if relationship in self.relationships:
            return  # 幂等
        self.relationships.append(relationship)

    def remove_relationship(self, relationship: str) -> None:
        """删除关系"""
        if relationship in self.relationships:
            self.relationships.remove(relationship)

    # ─── 序列化 ───

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "character_id": self.character_id.value,
            "name": self.name,
            "core_belief": self.core_belief,
            "moral_taboos": self.moral_taboos,
            "voice_profile": self.voice_profile.to_dict(),
            "active_wounds": [w.to_dict() for w in self.active_wounds],
            "evolution_patches": [
                {
                    "trigger_chapter": p.trigger_chapter,
                    "trigger_event": p.trigger_event,
                    "changes": p.changes,
                }
                for p in self.evolution_patches
            ],
            "description": self.description,
            "public_profile": self.public_profile,
            "hidden_profile": self.hidden_profile,
            "reveal_chapter": self.reveal_chapter,
            "mental_state": self.mental_state,
            "verbal_tic": self.verbal_tic,
            "idle_behavior": self.idle_behavior,
            "aliases": self.aliases,
            "role": self.role,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Character:
        """从字典反序列化"""
        voice_data = data.get("voice_profile", {})
        if isinstance(voice_data, dict):
            voice_profile = VoiceStyle(
                style=voice_data.get("style", "default"),
                sentence_pattern=voice_data.get("sentence_pattern", "mixed"),
                punctuation=voice_data.get("punctuation", []),
                metaphors=voice_data.get("metaphors", []),
                catchphrases=voice_data.get("catchphrases", []),
                speech_tempo=voice_data.get("speech_tempo", "normal"),
            )
        else:
            voice_profile = VoiceStyle()

        wounds_data = data.get("active_wounds", [])
        wounds = []
        for w in wounds_data:
            if isinstance(w, dict):
                wounds.append(Wound(
                    description=w.get("description", ""),
                    trigger=w.get("trigger", ""),
                    effect=w.get("effect", ""),
                ))

        patches_data = data.get("evolution_patches", [])
        patches = []
        for p in patches_data:
            if isinstance(p, dict):
                patches.append(CharacterPatch(
                    trigger_chapter=p.get("trigger_chapter", 0),
                    trigger_event=p.get("trigger_event", ""),
                    changes=p.get("changes", {}),
                ))

        return cls(
            character_id=CharacterId(data.get("character_id", str(uuid.uuid4()))),
            name=data.get("name", ""),
            core_belief=data.get("core_belief", ""),
            moral_taboos=data.get("moral_taboos", []),
            voice_profile=voice_profile,
            active_wounds=wounds,
            evolution_patches=patches,
            description=data.get("description", ""),
            public_profile=data.get("public_profile", ""),
            hidden_profile=data.get("hidden_profile", ""),
            reveal_chapter=data.get("reveal_chapter"),
            mental_state=data.get("mental_state", "NORMAL"),
            verbal_tic=data.get("verbal_tic", ""),
            idle_behavior=data.get("idle_behavior", ""),
            aliases=data.get("aliases", []),
            role=data.get("role", ""),
            relationships=data.get("relationships", []),
        )
