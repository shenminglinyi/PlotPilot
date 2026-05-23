"""
Domain entity for Worldbuilding (世界观构建)
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict


@dataclass
class Worldbuilding:
    """世界观构建实体 - 基于专业小说家的5维度框架"""

    id: str
    novel_id: str

    # 1. 核心法则与底层逻辑 (The Rules)
    power_system: str = ""           # 力量体系/科技树
    physics_rules: str = ""          # 物理规律
    magic_tech: str = ""             # 魔法/科技机制

    # 2. 地理与生态环境 (Geography & Ecology)
    terrain: str = ""                # 地形
    climate: str = ""                # 气候
    resources: str = ""              # 资源分布
    ecology: str = ""                # 生态链

    # 3. 社会结构与权力分配 (Society & Power)
    politics: str = ""               # 政治体制
    economy: str = ""                # 经济模式
    class_system: str = ""           # 阶级系统

    # 4. 历史、信仰与文化 (History & Culture)
    history: str = ""                # 关键历史事件
    religion: str = ""               # 宗教信仰
    taboos: str = ""                 # 文化禁忌

    # 5. 沉浸感细节 (Daily Life)
    food_clothing: str = ""          # 衣食住行
    language_slang: str = ""         # 俚语口音
    entertainment: str = ""          # 娱乐方式

    # V2 canonical worldbuilding document. Legacy scalar columns above remain as
    # a compatibility projection for old callers and existing databases.
    schema_version: int = 2
    dimensions: Dict[str, Dict[str, str]] = field(default_factory=dict)

    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    @property
    def core_rules(self) -> dict:
        return self._dimension_or_legacy("core_rules", {
            "power_system": self.power_system,
            "physics_rules": self.physics_rules,
            "magic_tech": self.magic_tech,
        })

    @property
    def geography(self) -> dict:
        return self._dimension_or_legacy("geography", {
            "terrain": self.terrain,
            "climate": self.climate,
            "resources": self.resources,
            "ecology": self.ecology,
        })

    @property
    def society(self) -> dict:
        return self._dimension_or_legacy("society", {
            "politics": self.politics,
            "economy": self.economy,
            "class_system": self.class_system,
        })

    @property
    def culture(self) -> dict:
        return self._dimension_or_legacy("culture", {
            "history": self.history,
            "religion": self.religion,
            "taboos": self.taboos,
        })

    @property
    def daily_life(self) -> dict:
        return self._dimension_or_legacy("daily_life", {
            "food_clothing": self.food_clothing,
            "language_slang": self.language_slang,
            "entertainment": self.entertainment,
        })

    def _dimension_or_legacy(self, key: str, legacy: Dict[str, str]) -> Dict[str, str]:
        block = self.dimensions.get(key) if isinstance(self.dimensions, dict) else None
        if isinstance(block, dict) and any(str(v).strip() for v in block.values()):
            return {str(k): str(v or "") for k, v in block.items()}
        return legacy

    def normalized_dimensions(self) -> Dict[str, Dict[str, str]]:
        return {
            "core_rules": dict(self.core_rules),
            "geography": dict(self.geography),
            "society": dict(self.society),
            "culture": dict(self.culture),
            "daily_life": dict(self.daily_life),
        }

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "novel_id": self.novel_id,
            "schema_version": self.schema_version,
            "dimensions": self.normalized_dimensions(),

            # Core Rules
            "core_rules": dict(self.core_rules),

            # Geography
            "geography": dict(self.geography),

            # Society
            "society": dict(self.society),

            # Culture
            "culture": dict(self.culture),

            # Daily Life
            "daily_life": dict(self.daily_life),

            "created_at": self.created_at.isoformat() if isinstance(self.created_at, datetime) else self.created_at,
            "updated_at": self.updated_at.isoformat() if isinstance(self.updated_at, datetime) else self.updated_at,
        }
