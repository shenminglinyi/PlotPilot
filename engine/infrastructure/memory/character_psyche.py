"""角色心理画像引擎 — 四维模型持久化与面具计算

核心职责：
- 四维模型持久化（base_layer JSON + patches append-only）
- CharacterPatch append-only日志管理
- compute_current_mask()折叠计算
- T0层FactLock注入格式生成

命名统一：
- CharacterSoulEngine → CharacterPsycheEngine（心理画像 > 灵魂）
- character_soul → character_psyche（语义更精确，避免玄学含义）
"""
from __future__ import annotations

import json
import logging
from typing import Dict, Any, List, Optional

from engine.core.entities.character import (
    Character, CharacterId, VoiceStyle, Wound, CharacterPatch,
)
from engine.core.value_objects.character_mask import CharacterMask

logger = logging.getLogger(__name__)


# ─── 向后兼容别名 ───
# 旧代码 `from engine.infrastructure.memory.character_soul import CharacterSoulEngine` 仍然可用
# 将在 v4.0 移除


class CharacterPsycheEngine:
    """角色心理画像引擎

    四维动态模型 + 地质叠层管理

    四维：
    1. core_belief：核心信念 — 决定价值选择
    2. moral_taboos：绝对禁忌 — 决定底线
    3. voice_profile：语言指纹 — 决定台词风格
    4. active_wounds：未愈合创伤 — 决定条件反射
    """

    def __init__(self, db_pool=None):
        self._db_pool = db_pool
        self._cache: Dict[str, Character] = {}

    async def load_character(self, character_id: str) -> Optional[Character]:
        """从持久化层加载角色（含Patch历史）"""
        if character_id in self._cache:
            return self._cache[character_id]

        if not self._db_pool:
            return None

        try:
            with self._db_pool.get_connection() as conn:
                # 加载基础层
                row = conn.execute(
                    "SELECT * FROM characters WHERE id = ?",
                    (character_id,)
                ).fetchone()

                if not row:
                    return None

                data = dict(row)
                base_layer = json.loads(data.get("base_layer", "{}"))

                # 构建Character对象
                character = Character(
                    character_id=CharacterId(character_id),
                    name=base_layer.get("name", data.get("name", "")),
                    core_belief=base_layer.get("core_belief", ""),
                    moral_taboos=base_layer.get("moral_taboos", []),
                    voice_profile=VoiceStyle(**base_layer.get("voice_profile", {})),
                    description=base_layer.get("description", ""),
                    public_profile=base_layer.get("public_profile", ""),
                    hidden_profile=base_layer.get("hidden_profile", ""),
                )

                # 加载Patch历史
                patches = conn.execute(
                    """SELECT * FROM character_patches
                       WHERE character_id = ?
                       ORDER BY trigger_chapter ASC""",
                    (character_id,)
                ).fetchall()

                for patch_row in patches:
                    patch_data = dict(patch_row)
                    wound_data = patch_data.get("changes", {}).get("active_wounds")
                    new_wound = None
                    if wound_data and isinstance(wound_data, str):
                        new_wound = Wound(
                            description=wound_data,
                            trigger=patch_data.get("changes", {}).get("wound_trigger", ""),
                            effect=patch_data.get("changes", {}).get("wound_effect", ""),
                        )

                    character.apply_trauma(
                        trigger_chapter=patch_data.get("trigger_chapter", 0),
                        trigger_event=patch_data.get("trigger_event", ""),
                        new_belief=patch_data.get("changes", {}).get("core_belief"),
                        new_taboo=patch_data.get("changes", {}).get("moral_taboos"),
                        new_wound=new_wound,
                        voice_change=patch_data.get("changes", {}).get("voice_profile"),
                    )

                self._cache[character_id] = character
                return character

        except Exception as e:
            logger.error(f"加载角色失败: {character_id}, {e}")
            return None

    async def save_character(self, character: Character) -> bool:
        """保存角色（base_layer + patches）"""
        if not self._db_pool:
            self._cache[character.character_id.value] = character
            return True

        try:
            with self._db_pool.get_connection() as conn:
                base_layer = {
                    "name": character.name,
                    "core_belief": character.core_belief,
                    "moral_taboos": character.moral_taboos,
                    "voice_profile": {
                        "style": character.voice_profile.style,
                        "sentence_pattern": character.voice_profile.sentence_pattern,
                        "punctuation": character.voice_profile.punctuation,
                        "metaphors": character.voice_profile.metaphors,
                    },
                    "description": character.description,
                    "public_profile": character.public_profile,
                    "hidden_profile": character.hidden_profile,
                }

                conn.execute(
                    """INSERT OR REPLACE INTO characters
                       (id, name, base_layer)
                       VALUES (?, ?, ?)""",
                    (
                        character.character_id.value,
                        character.name,
                        json.dumps(base_layer, ensure_ascii=False),
                    )
                )

                # 保存新Patch
                for patch in character.evolution_patches:
                    conn.execute(
                        """INSERT OR IGNORE INTO character_patches
                           (character_id, trigger_chapter, trigger_event, changes, created_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (
                            character.character_id.value,
                            patch.trigger_chapter,
                            patch.trigger_event,
                            json.dumps(patch.changes, ensure_ascii=False),
                            patch.created_at,
                        )
                    )

                conn.commit()

            self._cache[character.character_id.value] = character
            return True

        except Exception as e:
            logger.error(f"保存角色失败: {e}")
            return False

    async def compute_mask(
        self,
        character_id: str,
        chapter_number: int,
    ) -> Optional[CharacterMask]:
        """计算当前面具（折叠所有Patch到指定章节）"""
        character = await self.load_character(character_id)
        if not character:
            return None

        mask_dict = character.compute_mask(up_to_chapter=chapter_number)
        return CharacterMask.from_character_dict(mask_dict, chapter_number)

    async def apply_trauma(
        self,
        character_id: str,
        trigger_chapter: int,
        trigger_event: str,
        new_belief: Optional[str] = None,
        new_taboo: Optional[str] = None,
        new_wound: Optional[Dict[str, str]] = None,
        voice_change: Optional[Dict[str, Any]] = None,
    ) -> Optional[CharacterPatch]:
        """应用创伤事件"""
        character = await self.load_character(character_id)
        if not character:
            return None

        wound_obj = None
        if new_wound:
            wound_obj = Wound(**new_wound)

        patch = character.apply_trauma(
            trigger_chapter=trigger_chapter,
            trigger_event=trigger_event,
            new_belief=new_belief,
            new_taboo=new_taboo,
            new_wound=wound_obj,
            voice_change=voice_change,
        )

        await self.save_character(character)
        return patch

    async def generate_t0_fact_lock(
        self,
        character_id: str,
        chapter_number: int,
    ) -> Optional[str]:
        """生成T0层FactLock注入格式"""
        character = await self.load_character(character_id)
        if not character:
            return None

        return character.to_t0_fact_lock(chapter_number)


# ─── 向后兼容别名（v3.x 保留，v4.0 移除） ───
CharacterSoulEngine = CharacterPsycheEngine
