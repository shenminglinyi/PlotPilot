"""自动 Bible 生成器 - 从小说标题生成完整的人物、地点、风格设定和世界观"""
import logging
import json
import uuid
import sys
from typing import Dict, Any
from datetime import datetime
from domain.ai.services.llm_service import LLMService, GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from application.world.services.bible_service import BibleService
from application.world.services.worldbuilding_service import WorldbuildingService
from domain.bible.triple import Triple, SourceType
from infrastructure.persistence.database.triple_repository import TripleRepository
from domain.shared.exceptions import EntityNotFoundError

logger = logging.getLogger(__name__)


def _infer_character_importance(char_data: Dict[str, Any]) -> str:
    """与前端人物关系图 importance 一致：primary / secondary / minor。"""
    role = str(char_data.get("role") or "").strip()
    desc_head = str(char_data.get("description") or "")[:160]
    blob = f"{role}{desc_head}"
    if "主角" in blob:
        return "primary"
    if any(k in blob for k in ("导师", "师父", "宿敌", "反派", "对手", "核心", "幕后")):
        return "secondary"
    return "minor"


def _map_location_kind(raw_type: str) -> str:
    """与 KnowledgeTriple.location_type 枚举对齐。"""
    t = str(raw_type or "")
    if "城" in t:
        return "city"
    if any(k in t for k in ("区域", "域", "境", "荒", "谷", "原", "山脉")):
        return "region"
    if any(k in t for k in ("建筑", "楼", "殿", "阁", "府", "宫", "塔")):
        return "building"
    if any(k in t for k in ("势力", "宗", "门", "派", "盟", "族")):
        return "faction"
    if any(k in t for k in ("特殊", "秘境", "领域", "遗迹", "墟")):
        return "realm"
    return "region"


def _default_location_importance(_loc_data: Dict[str, Any]) -> str:
    return "normal"


class AutoBibleGenerator:
    """自动 Bible 生成器

    根据小说标题，使用 LLM 生成：
    - 3-5 个主要人物（主角、配角、对手、导师等）
    - 2-3 个重要地点
    - 文风公约
    - 世界观（5维度框架）
    """

    def __init__(self, llm_service: LLMService, bible_service: BibleService, worldbuilding_service: WorldbuildingService = None, triple_repository: TripleRepository = None):
        self.llm_service = llm_service
        self.bible_service = bible_service
        self.worldbuilding_service = worldbuilding_service
        self.triple_repository = triple_repository

    async def generate_and_save(
        self,
        novel_id: str,
        premise: str,
        target_chapters: int,
        stage: str = "all"
    ) -> Dict[str, Any]:
        """生成并保存 Bible（支持分阶段）

        Args:
            novel_id: 小说 ID
            premise: 故事梗概/创意
            target_chapters: 目标章节数
            stage: 生成阶段 (all/worldbuilding/characters/locations)

        Returns:
            生成的 Bible 数据
        """
        logger.info(f"Generating Bible for novel: {premise[:50]}... (stage: {stage})")

        # 1. 创建空 Bible（如果不存在）
        bible_id = f"{novel_id}-bible"
        try:
            existing_bible = self.bible_service.get_bible_by_novel(novel_id)
            if existing_bible:
                logger.info(f"Bible already exists for novel {novel_id}")
            else:
                logger.info(f"Bible not found for novel {novel_id}, creating new one")
                self.bible_service.create_bible(bible_id, novel_id)
                logger.info(f"Successfully created Bible {bible_id} for novel {novel_id}")
        except Exception as e:
            logger.error(f"Error checking/creating Bible: {e}")
            # 尝试创建
            try:
                self.bible_service.create_bible(bible_id, novel_id)
                logger.info(f"Successfully created Bible {bible_id} for novel {novel_id}")
            except Exception as create_error:
                logger.error(f"Failed to create Bible: {create_error}")
                raise

        # 2. 根据阶段生成不同内容
        if stage == "all":
            # 一次性生成所有内容（向后兼容）
            bible_data = await self._generate_bible_data(premise, target_chapters)
            await self._save_to_bible(novel_id, bible_data)
            if self.worldbuilding_service and "worldbuilding" in bible_data:
                await self._save_worldbuilding(novel_id, bible_data["worldbuilding"])

        elif stage == "worldbuilding":
            import sys
            print(f"[DEBUG] Stage worldbuilding - checking Bible record", file=sys.stderr, flush=True)
            # 确保Bible记录存在
            try:
                self.bible_service.get_bible_by_novel(novel_id)
            except EntityNotFoundError:
                bible_id = f"{novel_id}-bible"
                self.bible_service.create_bible(bible_id, novel_id)
                logger.info(f"Created Bible record: {bible_id}")

            print(f"[DEBUG] Calling _generate_worldbuilding_and_style", file=sys.stderr, flush=True)
            # 只生成世界观和文风
            bible_data = await self._generate_worldbuilding_and_style(premise, target_chapters)
            print(f"[DEBUG] _generate_worldbuilding_and_style completed", file=sys.stderr, flush=True)
            print(f"[DEBUG] bible_data keys: {bible_data.keys()}", file=sys.stderr, flush=True)
            print(f"[DEBUG] Has 'worldbuilding' key: {'worldbuilding' in bible_data}", file=sys.stderr, flush=True)
            print(f"[DEBUG] worldbuilding_service is None: {self.worldbuilding_service is None}", file=sys.stderr, flush=True)
            # 保存文风
            if "style" in bible_data:
                style_id = f"{novel_id}-style-1"
                try:
                    self.bible_service.add_style_note(
                        novel_id=novel_id,
                        note_id=style_id,
                        category="文风公约",
                        content=bible_data["style"]
                    )
                    logger.info(f"Style note saved: {style_id}")
                except Exception as e:
                    if "already exists" in str(e):
                        logger.info(f"Style note {style_id} already exists, skipping")
                    else:
                        logger.error(f"Failed to save style note: {e}")
                        raise
            # 保存世界观
            if self.worldbuilding_service and "worldbuilding" in bible_data:
                await self._save_worldbuilding(novel_id, bible_data["worldbuilding"])

        elif stage == "characters":
            # 确保Bible记录存在
            try:
                self.bible_service.get_bible_by_novel(novel_id)
            except EntityNotFoundError:
                bible_id = f"{novel_id}-bible"
                self.bible_service.create_bible(bible_id, novel_id)
                logger.info(f"Created Bible record: {bible_id}")

            # 基于已有世界观生成人物
            existing_worldbuilding = self._load_worldbuilding(novel_id)
            bible_data = await self._generate_characters(premise, target_chapters, existing_worldbuilding)
            # 保存人物
            character_ids = []
            used_char_ids = set()  # 用于跟踪已使用的人物ID
            for idx, char_data in enumerate(bible_data.get("characters", [])):
                character_id = f"{novel_id}-char-{idx+1}"
                
                # 检查并处理重复ID
                if character_id in used_char_ids:
                    logger.info(f"Character ID {character_id} already exists, generating new ID")
                    character_id = f"{novel_id}-char-{idx+1}-{len(used_char_ids)}"
                
                used_char_ids.add(character_id)
                try:
                    self.bible_service.add_character(
                        novel_id=novel_id,
                        character_id=character_id,
                        name=char_data["name"],
                        description=f"{char_data['role']} - {char_data['description']}",
                        relationships=char_data.get("relationships", [])
                    )
                    character_ids.append((character_id, char_data))
                    logger.info(f"Character saved: {character_id}")
                except Exception as e:
                    if "already exists" in str(e):
                        logger.info(f"Character {character_id} already exists, skipping")
                    else:
                        logger.error(f"Failed to save character: {e}")
                        raise

            # 从人物关系生成三元组
            if self.triple_repository:
                await self._generate_character_triples(novel_id, character_ids)

        elif stage == "locations":
            # 确保Bible记录存在
            try:
                self.bible_service.get_bible_by_novel(novel_id)
            except EntityNotFoundError:
                bible_id = f"{novel_id}-bible"
                self.bible_service.create_bible(bible_id, novel_id)
                logger.info(f"Created Bible record: {bible_id}")

            # 基于已有世界观和人物生成地点
            existing_worldbuilding = self._load_worldbuilding(novel_id)
            existing_characters = self._load_characters(novel_id)
            bible_data = await self._generate_locations(premise, target_chapters, existing_worldbuilding, existing_characters)
            # 保存地点
            location_ids = []
            used_ids = set()  # 用于跟踪已使用的ID，防止重复
            for idx, loc_data in enumerate(bible_data.get("locations", [])):
                raw_id = loc_data.get("id")
                location_id = (
                    str(raw_id).strip()
                    if isinstance(raw_id, str) and str(raw_id).strip()
                    else f"{novel_id}-loc-{idx+1}"
                )
                
                # 检查并处理重复ID
                if location_id in used_ids:
                    logger.info(f"Location ID {location_id} already exists, generating new ID")
                    location_id = f"{novel_id}-loc-{idx+1}-{len(used_ids)}"
                
                used_ids.add(location_id)
                p_raw = loc_data.get("parent_id")
                parent_id = (
                    str(p_raw).strip()
                    if isinstance(p_raw, str) and str(p_raw).strip()
                    else None
                )
                try:
                    self.bible_service.add_location(
                        novel_id=novel_id,
                        location_id=location_id,
                        name=loc_data["name"],
                        description=loc_data["description"],
                        location_type=loc_data.get("type", "场景"),
                        connections=loc_data.get("connections", []),
                        parent_id=parent_id,
                    )
                    location_ids.append((location_id, loc_data))
                    logger.info(f"Location saved: {location_id}")
                except Exception as e:
                    if "already exists" in str(e):
                        logger.info(f"Location {location_id} already exists, skipping")
                    else:
                        logger.error(f"Failed to save location: {e}")
                        raise

            # 从地点连接生成三元组
            if self.triple_repository:
                await self._generate_location_triples(novel_id, location_ids)

        else:
            raise ValueError(f"Unknown stage: {stage}")

        logger.info(f"Bible generation completed for {novel_id} (stage: {stage})")
        return bible_data

    async def _generate_bible_data(self, premise: str, target_chapters: int) -> Dict[str, Any]:
        """使用 LLM 生成 Bible 数据和世界观"""

        system_prompt = """你是资深网文策划编辑。根据用户提供的故事创意/梗概，生成完整的人物、世界设定和世界观。

**重要：只输出有效的 JSON，不要有任何其他文字。description 字段必须是单行文本，不能有换行符。**

要求：
1. 深入理解故事梗概，提取核心冲突、主题、世界观
2. 至少 3-5 个主要人物（主角、配角、对手、导师等），确保人物之间有冲突和互动
3. 每个人物：姓名、定位（主角/配角/对手/导师）、性格特点、目标动机
4. 至少 2-3 个重要地点，符合故事背景；地点须含稳定 `id`，若有层级则填 `parent_id` 指向父地点的 `id`（根为 null）
5. 明确的文风公约（叙事视角、人称、基调、节奏）
6. 完整的世界观（5维度框架）：核心法则、地理生态、社会结构、历史文化、沉浸感细节
7. 人物和地点要符合故事类型（现代都市/古代/玄幻/科幻等）
8. **所有 description 字段必须是单行文本，用逗号或分号分隔不同要点，不要使用换行符**

JSON 格式（不要有其他文字）：
{
  "characters": [
    {
      "name": "人物名",
      "role": "主角/配角/对手/导师",
      "description": "性格、背景、目标、特点，所有内容在一行内，用逗号分隔"
    }
  ],
  "locations": [
    {
      "id": "稳定id如 loc-continent-1",
      "name": "地点名",
      "type": "城市/建筑/区域",
      "description": "地点描述，单行文本",
      "parent_id": null
    }
  ],
  "style": "第三人称有限视角，以XX视角为主。基调XX，节奏XX。避免XX。营造XX氛围。",
  "worldbuilding": {
    "core_rules": {
      "power_system": "力量体系/科技树的描述",
      "physics_rules": "物理规律的特殊之处",
      "magic_tech": "魔法或科技的运作机制"
    },
    "geography": {
      "terrain": "地形特征",
      "climate": "气候特点",
      "resources": "资源分布",
      "ecology": "生态系统"
    },
    "society": {
      "politics": "政治体制",
      "economy": "经济模式",
      "class_system": "阶级系统"
    },
    "culture": {
      "history": "关键历史事件",
      "religion": "宗教信仰",
      "taboos": "文化禁忌"
    },
    "daily_life": {
      "food_clothing": "衣食住行",
      "language_slang": "俚语与口音",
      "entertainment": "娱乐方式"
    }
  }
}"""

        user_prompt = f"""故事创意：{premise}

目标章节数：{target_chapters}章

请根据这个故事创意，生成完整的人物、世界设定和世界观。注意：
1. 从故事创意中提取关键信息（主角身份、核心能力、故事背景、主要冲突）
2. 人物要有层次，不能只有主角，要有配角、对手、导师等
3. 要有明确的冲突和对立面
4. 世界观要清晰，地点要符合故事类型
5. 文风公约要具体，明确叙事视角、基调、节奏
6. 世界观5个维度都要填写，符合故事类型和背景
7. 适合网文读者，有代入感

只输出 JSON，不要有任何解释文字。"""

        prompt = Prompt(system=system_prompt, user=user_prompt)
        config = GenerationConfig(max_tokens=2048, temperature=0.7)

        result = await self.llm_service.generate(prompt, config)

        # 解析 JSON
        try:
            content = result.content.strip()

            # 移除可能的 markdown 代码块标记
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            content = content.strip()

            # 尝试找到第一个 { 和最后一个 }
            start = content.find('{')
            end = content.rfind('}')
            if start != -1 and end != -1:
                content = content[start:end+1]

            logger.info(f"Attempting to parse Bible JSON (length: {len(content)})")

            # 尝试直接解析
            try:
                bible_data = json.loads(content)
                logger.info(f"Successfully parsed Bible JSON")
                return bible_data
            except json.JSONDecodeError as e:
                # 如果失败，尝试修复常见问题
                logger.warning(f"First parse attempt failed: {e}, trying to repair JSON...")

                # 使用 json.loads 的 strict=False 模式
                import re
                # 移除字符串中的控制字符和多余的空白
                content = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', content)

                bible_data = json.loads(content, strict=False)
                logger.info(f"Successfully parsed Bible JSON after repair")
                return bible_data

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Bible JSON: {e}")
            logger.error(f"Raw content (first 1000 chars): {content[:1000]}")
            # 返回默认结构
            return {
                "characters": [
                    {
                        "name": "主角",
                        "role": "主角",
                        "description": "待补充"
                    }
                ],
                "locations": [
                    {
                        "id": "loc-default-1",
                        "name": "主要场景",
                        "type": "城市",
                        "description": "待补充",
                        "parent_id": None,
                    }
                ],
                "style": "第三人称有限视角，轻松幽默"
            }

    async def _save_to_bible(self, novel_id: str, bible_data: Dict[str, Any]) -> None:
        """保存到 Bible"""

        # 先确保 Bible 记录存在
        try:
            from domain.novel.value_objects.novel_id import NovelId
            existing_bible = self.bible_service.bible_repository.get_by_novel_id(NovelId(novel_id))
            if existing_bible is None:
                # 创建 Bible 记录
                bible_id = f"bible-{novel_id}"
                self.bible_service.create_bible(bible_id=bible_id, novel_id=novel_id)
                logger.info(f"Created Bible record for novel {novel_id}")
        except Exception as e:
            logger.error(f"Failed to ensure Bible exists: {e}")
            return

        # 添加人物
        used_character_ids = set()  # 用于跟踪已使用的人物ID
        for idx, char_data in enumerate(bible_data.get("characters", [])):
            character_id = f"{novel_id}-char-{idx+1}"
            
            # 检查并处理重复ID
            if character_id in used_character_ids:
                logger.info(f"Character ID {character_id} already exists, generating new ID")
                character_id = f"{novel_id}-char-{idx+1}-{len(used_character_ids)}"
            
            used_character_ids.add(character_id)
            try:
                self.bible_service.add_character(
                    novel_id=novel_id,
                    character_id=character_id,
                    name=char_data["name"],
                    description=f"{char_data['role']} - {char_data['description']}"
                )
                logger.info(f"Character saved: {character_id}")
            except Exception as e:
                if "already exists" in str(e):
                    logger.info(f"Character {character_id} already exists, skipping")
                else:
                    logger.error(f"Failed to save character: {e}")
                    raise

        # 添加地点
        used_location_ids = set()  # 用于跟踪已使用的位置ID
        for idx, loc_data in enumerate(bible_data.get("locations", [])):
            raw_id = loc_data.get("id")
            location_id = (
                str(raw_id).strip()
                if isinstance(raw_id, str) and str(raw_id).strip()
                else f"{novel_id}-loc-{idx+1}"
            )
            
            # 检查并处理重复ID
            if location_id in used_location_ids:
                logger.info(f"Location ID {location_id} already exists, generating new ID")
                location_id = f"{novel_id}-loc-{idx+1}-{len(used_location_ids)}"
            
            used_location_ids.add(location_id)
            p_raw = loc_data.get("parent_id")
            parent_id = (
                str(p_raw).strip()
                if isinstance(p_raw, str) and str(p_raw).strip()
                else None
            )
            try:
                self.bible_service.add_location(
                    novel_id=novel_id,
                    location_id=location_id,
                    name=loc_data["name"],
                    description=loc_data["description"],
                    location_type=loc_data.get("type", "场景"),
                    parent_id=parent_id,
                )
                logger.info(f"Location saved: {location_id}")
            except Exception as e:
                if "already exists" in str(e):
                    logger.info(f"Location {location_id} already exists, skipping")
                else:
                    logger.error(f"Failed to save location: {e}")
                    raise

        # 添加风格笔记
        style = bible_data.get("style", "")
        if style:
            style_id = f"{novel_id}-style-1"
            try:
                self.bible_service.add_style_note(
                    novel_id=novel_id,
                    note_id=style_id,
                    category="文风公约",
                    content=style
                )
                logger.info(f"Style note saved: {style_id}")
            except Exception as e:
                # 如果已存在则更新
                if "already exists" in str(e):
                    logger.info(f"Style note {style_id} already exists, skipping")
                else:
                    logger.error(f"Failed to save style note: {e}")
                    raise

    async def _save_worldbuilding(self, novel_id: str, worldbuilding_data: Dict[str, Any]) -> None:
        """保存世界观到数据库（同时保存到Worldbuilding表和Bible的world_settings）"""
        print(f"[DEBUG] _save_worldbuilding called with data: {worldbuilding_data}", file=sys.stderr, flush=True)

        # 1. 保存到Worldbuilding表（用于后续生成人物和地点时读取）
        if self.worldbuilding_service:
            try:
                print(f"[DEBUG] Calling worldbuilding_service.update_worldbuilding", file=sys.stderr, flush=True)
                self.worldbuilding_service.update_worldbuilding(
                    novel_id=novel_id,
                    core_rules=worldbuilding_data.get("core_rules"),
                    geography=worldbuilding_data.get("geography"),
                    society=worldbuilding_data.get("society"),
                    culture=worldbuilding_data.get("culture"),
                    daily_life=worldbuilding_data.get("daily_life")
                )
                print(f"[DEBUG] Worldbuilding saved to Worldbuilding table", file=sys.stderr, flush=True)
                logger.info(f"Worldbuilding saved for {novel_id}")
            except Exception as e:
                print(f"[DEBUG] Failed to save worldbuilding: {e}", file=sys.stderr, flush=True)
                logger.error(f"Failed to save worldbuilding: {e}")

        # 2. 同时保存到Bible的world_settings（用于前端显示）
        try:
            print(f"[DEBUG] Saving worldbuilding to Bible.world_settings", file=sys.stderr, flush=True)
            bible = self.bible_service.get_bible_by_novel(novel_id)
            if not bible:
                bible_id = f"{novel_id}-bible"
                self.bible_service.create_bible(bible_id, novel_id)

            # 将5维度数据转换为world_setting条目
            # WorldSetting的type只能是'rule', 'location', 'item'，所以统一使用'rule'
            import uuid
            for dimension_name, dimension_data in worldbuilding_data.items():
                if isinstance(dimension_data, dict):
                    for key, value in dimension_data.items():
                        setting_id = f"{novel_id}-ws-{uuid.uuid4().hex[:8]}"
                        self.bible_service.add_world_setting(
                            novel_id=novel_id,
                            setting_id=setting_id,
                            name=f"{dimension_name}.{key}",
                            description=value,
                            setting_type="rule"  # 统一使用'rule'类型
                        )
            logger.info("Worldbuilding saved to Bible.world_settings successfully")
        except Exception as e:
            logger.error(f"Failed to save to Bible.world_settings: {e}")

    def _load_worldbuilding(self, novel_id: str) -> Dict[str, Any]:
        """加载已有世界观"""
        if not self.worldbuilding_service:
            return {}
        try:
            wb = self.worldbuilding_service.get_worldbuilding(novel_id)
            return {
                "core_rules": wb.core_rules,
                "geography": wb.geography,
                "society": wb.society,
                "culture": wb.culture,
                "daily_life": wb.daily_life
            }
        except:
            return {}

    def _load_characters(self, novel_id: str) -> list:
        """加载已有人物"""
        try:
            bible = self.bible_service.get_bible(novel_id)
            return [{"name": c.name, "description": c.description} for c in bible.characters]
        except:
            return []

    async def _generate_worldbuilding_and_style(self, premise: str, target_chapters: int) -> Dict[str, Any]:
        """只生成世界观和文风"""
        system_prompt = """你是资深网文策划编辑。根据故事创意生成世界观和文风公约。

**重要：只输出有效的 JSON，不要有任何其他文字。**

要求：
1. 完整的世界观（5维度框架）：核心法则、地理生态、社会结构、历史文化、沉浸感细节
2. 明确的文风公约（叙事视角、人称、基调、节奏）
3. 符合故事类型（现代都市/古代/玄幻/科幻等）

JSON 格式：
{
  "style": "第三人称有限视角，以XX视角为主。基调XX，节奏XX。避免XX。营造XX氛围。",
  "worldbuilding": {
    "core_rules": {
      "power_system": "力量体系/科技树的描述",
      "physics_rules": "物理规律的特殊之处",
      "magic_tech": "魔法或科技的运作机制"
    },
    "geography": {
      "terrain": "地形特征",
      "climate": "气候特点",
      "resources": "资源分布",
      "ecology": "生态系统"
    },
    "society": {
      "politics": "政治体制",
      "economy": "经济模式",
      "class_system": "阶级系统"
    },
    "culture": {
      "history": "关键历史事件",
      "religion": "宗教信仰",
      "taboos": "文化禁忌"
    },
    "daily_life": {
      "food_clothing": "衣食住行",
      "language_slang": "俚语与口音",
      "entertainment": "娱乐方式"
    }
  }
}"""

        user_prompt = f"""故事创意：{premise}

目标章节数：{target_chapters}章

请生成世界观和文风公约。只输出 JSON，不要有任何解释文字。"""

        return await self._call_llm_and_parse(system_prompt, user_prompt)

    async def _generate_characters(self, premise: str, target_chapters: int, worldbuilding: Dict[str, Any]) -> Dict[str, Any]:
        """基于世界观生成人物"""
        wb_summary = self._summarize_worldbuilding(worldbuilding)

        system_prompt = """你是资深网文策划编辑。基于已有世界观生成主要人物。

**重要：只输出有效的 JSON，不要有任何其他文字。description 字段必须是单行文本。**

要求：
1. 至少 3-5 个主要人物（主角、配角、对手、导师等）
2. 人物要符合世界观设定
3. 确保人物之间有冲突和互动
4. 每个人物：姓名、定位、性格特点、目标动机
5. 明确定义人物之间的关系（敌对、合作、师徒、亲属、暧昧等）

JSON 格式：
{
  "characters": [
    {
      "name": "人物名",
      "role": "主角/配角/对手/导师",
      "description": "性格、背景、目标、特点，所有内容在一行内，用逗号分隔",
      "relationships": [
        {
          "target": "目标人物名",
          "relation": "关系类型（师徒/敌对/合作/亲属/暧昧等）",
          "description": "关系的详细描述"
        }
      ]
    }
  ]
}"""

        user_prompt = f"""故事创意：{premise}

已有世界观：
{wb_summary}

请基于这个世界观生成主要人物。只输出 JSON，不要有任何解释文字。"""

        return await self._call_llm_and_parse(system_prompt, user_prompt)

    async def _generate_locations(self, premise: str, target_chapters: int, worldbuilding: Dict[str, Any], characters: list) -> Dict[str, Any]:
        """基于世界观和人物生成地点"""
        wb_summary = self._summarize_worldbuilding(worldbuilding)
        char_summary = "\n".join([f"- {c['name']}: {c['description'][:50]}..." for c in characters])

        system_prompt = """你是资深网文策划编辑。基于已有世界观和人物生成完整地图。

**重要：只输出有效的 JSON，不要有任何其他文字。**

要求：
1. 至少 5-10 个重要地点，构成完整地图
2. 地点要符合世界观设定
3. 考虑人物的活动范围和故事需要
4. 包含不同类型：城市、建筑、区域、特殊场所等
5. 空间层级用 `parent_id` 表达（子地点 id 指向父地点 id）；非父子关系用 `connections`（不要用 relation=位于）

JSON 格式：
{
  "locations": [
    {
      "id": "稳定id，全书唯一",
      "name": "地点名",
      "type": "城市/建筑/区域/特殊场所",
      "description": "地点描述，单行文本",
      "parent_id": null,
      "connections": [
        {
          "target": "目标地点名",
          "relation": "连接类型（包含/相邻/通往等，勿用位于）",
          "description": "连接的详细描述"
        }
      ]
    }
  ]
}"""

        user_prompt = f"""故事创意：{premise}

已有世界观：
{wb_summary}

已有人物：
{char_summary}

请基于世界观和人物生成完整地图。只输出 JSON，不要有任何解释文字。"""

        return await self._call_llm_and_parse(system_prompt, user_prompt)

    def _summarize_worldbuilding(self, wb: Dict[str, Any]) -> str:
        """总结世界观为文本"""
        if not wb:
            return "无"

        parts = []
        for key, value in wb.items():
            if isinstance(value, dict):
                items = ", ".join([f"{k}: {v}" for k, v in value.items() if v])
                parts.append(f"{key}: {items}")
        return "\n".join(parts)

    async def _call_llm_and_parse(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """调用 LLM 并解析 JSON"""
        prompt = Prompt(system=system_prompt, user=user_prompt)
        config = GenerationConfig(max_tokens=2048, temperature=0.7)
        result = await self.llm_service.generate(prompt, config)

        try:
            content = result.content.strip()

            # 移除可能的 markdown 代码块标记
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            content = content.strip()

            # 尝试找到第一个 { 和最后一个 }
            start = content.find('{')
            end = content.rfind('}')
            if start != -1 and end != -1:
                content = content[start:end+1]

            parsed = json.loads(content)
            return parsed
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            logger.error(f"Content length: {len(content)}")
            logger.error(f"Raw content (first 1000 chars): {content[:1000]}")
            logger.error(f"Raw content (last 500 chars): {content[-500:]}")
            return {}

    async def _generate_character_triples(self, novel_id: str, character_ids: list):
        """从人物关系生成三元组"""
        logger.info(f"Generating character relationship triples for {novel_id}")

        # 创建人物名称到ID的映射
        name_to_id = {char_data["name"]: char_id for char_id, char_data in character_ids}
        id_to_char = {cid: data for cid, data in character_ids}

        for char_id, char_data in character_ids:
            relationships = char_data.get("relationships", [])
            if not relationships:
                continue

            for rel in relationships:
                # 支持两种格式：字符串或对象
                if isinstance(rel, str):
                    # 旧格式：字符串描述，尝试解析
                    target_name = None
                    predicate = "关系"
                    description = rel

                    # 简单的名称匹配
                    for other_id, other_data in character_ids:
                        if other_id != char_id and other_data["name"] in rel:
                            target_name = other_data["name"]
                            break

                    # 提取关系类型
                    if "师徒" in rel or "师从" in rel:
                        predicate = "师徒关系"
                    elif "朋友" in rel or "好友" in rel:
                        predicate = "朋友"
                    elif "敌对" in rel or "对手" in rel:
                        predicate = "敌对"
                    elif "家人" in rel or "亲属" in rel:
                        predicate = "家人"
                    elif "同事" in rel or "同僚" in rel:
                        predicate = "同事"
                else:
                    # 新格式：对象 {target, relation, description}
                    target_name = rel.get("target")
                    predicate = rel.get("relation", "关系")
                    description = rel.get("description", "")

                # 查找目标人物ID
                target_char_id = name_to_id.get(target_name)

                # 如果找到了目标人物，创建三元组
                if target_char_id:
                    target_char = id_to_char.get(target_char_id, {})
                    subj_imp = _infer_character_importance(char_data)
                    obj_imp = _infer_character_importance(target_char)
                    triple = Triple(
                        id=f"triple-{uuid.uuid4().hex[:8]}",
                        novel_id=novel_id,
                        subject_type="character",
                        subject_id=char_id,
                        predicate=predicate,
                        object_type="character",
                        object_id=target_char_id,
                        confidence=0.9,
                        source_type=SourceType.BIBLE_GENERATED,
                        description=description,
                        attributes={
                            "subject_label": char_data["name"],
                            "object_label": target_name,
                            "subject_importance": subj_imp,
                            "object_importance": obj_imp,
                        },
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    try:
                        await self.triple_repository.save(triple)
                        logger.info(f"Created triple: {char_data['name']} -{predicate}-> {target_name}")
                    except Exception as e:
                        logger.error(f"Failed to save triple: {e}")

    async def _generate_location_triples(self, novel_id: str, location_ids: list):
        """从地点连接生成三元组"""
        logger.info(f"Generating location connection triples for {novel_id}")

        # 创建地点名称到ID的映射
        name_to_id = {loc_data["name"]: loc_id for loc_id, loc_data in location_ids}
        id_to_loc = {lid: data for lid, data in location_ids}

        for loc_id, loc_data in location_ids:
            connections = loc_data.get("connections", [])
            if not connections:
                continue

            for conn in connections:
                # 支持两种格式：字符串或对象
                if isinstance(conn, str):
                    # 旧格式：字符串描述，尝试解析
                    target_name = None
                    predicate = "连接"
                    description = conn

                    # 简单的名称匹配
                    for other_id, other_data in location_ids:
                        if other_id != loc_id and other_data["name"] in conn:
                            target_name = other_data["name"]
                            break

                    # 提取连接类型
                    if "包含" in conn or "内部" in conn:
                        predicate = "包含"
                    elif "相邻" in conn or "毗邻" in conn:
                        predicate = "相邻"
                    elif "通往" in conn or "通向" in conn:
                        predicate = "通往"
                    elif "位于" in conn:
                        predicate = "位于"
                else:
                    # 新格式：对象 {target, relation, description}
                    target_name = conn.get("target")
                    predicate = conn.get("relation", "连接")
                    description = conn.get("description", "")

                pred_norm = (predicate or "").strip()
                if pred_norm == "位于":
                    continue

                # 查找目标地点ID
                target_loc_id = name_to_id.get(target_name)

                # 如果找到了目标地点，创建三元组
                if target_loc_id:
                    target_loc = id_to_loc.get(target_loc_id, {})
                    subj_lt = _map_location_kind(loc_data.get("type", ""))
                    obj_lt = _map_location_kind(target_loc.get("type", ""))
                    subj_imp = _default_location_importance(loc_data)
                    obj_imp = _default_location_importance(target_loc)
                    triple = Triple(
                        id=f"triple-{uuid.uuid4().hex[:8]}",
                        novel_id=novel_id,
                        subject_type="location",
                        subject_id=loc_id,
                        predicate=predicate,
                        object_type="location",
                        object_id=target_loc_id,
                        confidence=0.9,
                        source_type=SourceType.BIBLE_GENERATED,
                        description=description,
                        attributes={
                            "subject_label": loc_data["name"],
                            "object_label": target_name,
                            "subject_importance": subj_imp,
                            "subject_location_type": subj_lt,
                            "object_importance": obj_imp,
                            "object_location_type": obj_lt,
                        },
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    try:
                        await self.triple_repository.save(triple)
                        logger.info(f"Created triple: {loc_data['name']} -{predicate}-> {target_name}")
                    except Exception as e:
                        logger.error(f"Failed to save triple: {e}")

