"""
Service for Worldbuilding
"""
from typing import Optional
import uuid

from domain.worldbuilding.worldbuilding import Worldbuilding
from infrastructure.persistence.database.worldbuilding_repository import WorldbuildingRepository
from application.world.services.worldbuilding_field_text import normalize_dimension_fields


class WorldbuildingService:
    """世界观构建服务"""

    def __init__(self, repository: WorldbuildingRepository):
        self.repository = repository

    def get_worldbuilding(self, novel_id: str) -> Optional[Worldbuilding]:
        """获取小说的世界观"""
        return self.repository.get_by_novel_id(novel_id)

    def create_worldbuilding(self, novel_id: str) -> Worldbuilding:
        """创建空白世界观"""
        worldbuilding = Worldbuilding(
            id=f"wb-{uuid.uuid4().hex[:12]}",
            novel_id=novel_id,
        )
        self.repository.save(worldbuilding)
        return worldbuilding

    def update_worldbuilding(
        self,
        novel_id: str,
        core_rules: dict = None,
        geography: dict = None,
        society: dict = None,
        culture: dict = None,
        daily_life: dict = None,
    ) -> Worldbuilding:
        """更新世界观"""
        worldbuilding = self.repository.get_by_novel_id(novel_id)

        if not worldbuilding:
            worldbuilding = self.create_worldbuilding(novel_id)

        current_dimensions = worldbuilding.normalized_dimensions()

        # Update core rules
        if core_rules:
            core_rules = normalize_dimension_fields(core_rules, dim_key="core_rules")
            current_dimensions["core_rules"] = core_rules
            worldbuilding.power_system = core_rules.get("power_system", worldbuilding.power_system)
            worldbuilding.physics_rules = core_rules.get("physics_rules", worldbuilding.physics_rules)
            worldbuilding.magic_tech = core_rules.get("magic_tech", worldbuilding.magic_tech)

        # Update geography
        if geography:
            geography = normalize_dimension_fields(geography, dim_key="geography")
            current_dimensions["geography"] = geography
            worldbuilding.terrain = geography.get("terrain", worldbuilding.terrain)
            worldbuilding.climate = geography.get("climate", worldbuilding.climate)
            worldbuilding.resources = geography.get("resources", worldbuilding.resources)
            worldbuilding.ecology = geography.get("ecology", worldbuilding.ecology)

        # Update society
        if society:
            society = normalize_dimension_fields(society, dim_key="society")
            current_dimensions["society"] = society
            worldbuilding.politics = society.get("politics", worldbuilding.politics)
            worldbuilding.economy = society.get("economy", worldbuilding.economy)
            worldbuilding.class_system = society.get("class_system", worldbuilding.class_system)

        # Update culture
        if culture:
            culture = normalize_dimension_fields(culture, dim_key="culture")
            current_dimensions["culture"] = culture
            worldbuilding.history = culture.get("history", worldbuilding.history)
            worldbuilding.religion = culture.get("religion", worldbuilding.religion)
            worldbuilding.taboos = culture.get("taboos", worldbuilding.taboos)

        # Update daily life
        if daily_life:
            daily_life = normalize_dimension_fields(daily_life, dim_key="daily_life")
            current_dimensions["daily_life"] = daily_life
            worldbuilding.food_clothing = daily_life.get("food_clothing", worldbuilding.food_clothing)
            worldbuilding.language_slang = daily_life.get("language_slang", worldbuilding.language_slang)
            worldbuilding.entertainment = daily_life.get("entertainment", worldbuilding.entertainment)

        worldbuilding.schema_version = 2
        worldbuilding.dimensions = current_dimensions
        self.repository.save(worldbuilding)
        return worldbuilding
