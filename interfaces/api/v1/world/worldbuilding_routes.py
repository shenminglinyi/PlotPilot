"""
API routes for Worldbuilding
"""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from application.world.services.worldbuilding_service import WorldbuildingService
from application.world.services.bible_service import BibleService
from application.ai_invocation.variable_hub import VariableWrite, compose_worldbuilding_dimensions
from infrastructure.persistence.database.worldbuilding_repository import WorldbuildingRepository
from infrastructure.persistence.database.connection import get_database
from infrastructure.persistence.database.sqlite_ai_invocation_repository import SqliteVariableHubRepository
from application.paths import get_db_path

from interfaces.api.dependencies import get_bible_service
from application.world.services.narrative_contract_loader import load_merged_worldbuilding_slices


router = APIRouter(prefix="/novels", tags=["worldbuilding"])


def _sync_worldbuilding_variable_hub(novel_id: str, slices: dict[str, dict[str, str]]) -> None:
    context_key = f"novel_id:{novel_id}"
    repo = SqliteVariableHubRepository(get_database())
    aggregate = compose_worldbuilding_dimensions(slices)
    writes: list[tuple[str, object, str, str]] = []
    if aggregate:
        writes.append(("worldbuilding.content", aggregate, "object", "世界观"))
    for key, display_name in (
        ("core_rules", "核心法则"),
        ("geography", "地理生态"),
        ("society", "社会结构"),
        ("culture", "历史文化"),
        ("daily_life", "沉浸感细节"),
    ):
        value = slices.get(key)
        if value:
            writes.append((f"worldbuilding.{key}", value, "object", display_name))
    for key, value, value_type, display_name in writes:
        repo.set_value(
            VariableWrite(
                key=key,
                value=value,
                context_key=context_key,
                source_trace_id="worldbuilding_manual_sync",
                source_node_key="worldbuilding_api",
                lineage={"source": "worldbuilding_api_manual_sync"},
                value_type=value_type,
                display_name=display_name,
                scope="global",
                stage="worldbuilding",
            )
        )


def get_worldbuilding_service() -> WorldbuildingService:
    """获取世界观服务"""
    db_path = get_db_path()
    repository = WorldbuildingRepository(db_path)
    return WorldbuildingService(repository)


class CoreRulesDTO(BaseModel):
    power_system: Optional[str] = ""
    physics_rules: Optional[str] = ""
    magic_tech: Optional[str] = ""


class GeographyDTO(BaseModel):
    terrain: Optional[str] = ""
    climate: Optional[str] = ""
    resources: Optional[str] = ""
    ecology: Optional[str] = ""


class SocietyDTO(BaseModel):
    politics: Optional[str] = ""
    economy: Optional[str] = ""
    class_system: Optional[str] = ""


class CultureDTO(BaseModel):
    history: Optional[str] = ""
    religion: Optional[str] = ""
    taboos: Optional[str] = ""


class DailyLifeDTO(BaseModel):
    food_clothing: Optional[str] = ""
    language_slang: Optional[str] = ""
    entertainment: Optional[str] = ""


class UpdateWorldbuildingRequest(BaseModel):
    core_rules: Optional[CoreRulesDTO] = None
    geography: Optional[GeographyDTO] = None
    society: Optional[SocietyDTO] = None
    culture: Optional[CultureDTO] = None
    daily_life: Optional[DailyLifeDTO] = None


@router.get("/{slug}/worldbuilding")
def get_worldbuilding(
    slug: str,
    service: WorldbuildingService = Depends(get_worldbuilding_service),
    bible_service: BibleService = Depends(get_bible_service),
):
    """获取小说的世界观。

    V2 数据以 worldbuilding.dimensions 为唯一主源；旧库缺少 V2 文档时，
    仅在仓储/loader 边界兼容读取旧列与 Bible.world_settings。
    """
    bible = bible_service.get_bible_by_novel(slug)
    wb_entity = service.get_worldbuilding(slug)
    slices = load_merged_worldbuilding_slices(bible=bible, worldbuilding=wb_entity)

    if wb_entity is None:
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        return {
            "id": f"bible-{slug}",
            "novel_id": slug,
            "schema_version": 2 if slices else 1,
            "dimensions": slices,
            **slices,
            "created_at": now,
            "updated_at": now,
        }

    dto = wb_entity.to_dict()
    dto["dimensions"] = slices
    dto["core_rules"] = slices["core_rules"]
    dto["geography"] = slices["geography"]
    dto["society"] = slices["society"]
    dto["culture"] = slices["culture"]
    dto["daily_life"] = slices["daily_life"]

    return dto


@router.post("/{slug}/worldbuilding")
def create_worldbuilding(
    slug: str,
    service: WorldbuildingService = Depends(get_worldbuilding_service)
):
    """创建空白世界观"""
    worldbuilding = service.create_worldbuilding(slug)
    return worldbuilding.to_dict()


@router.put("/{slug}/worldbuilding")
def update_worldbuilding(
    slug: str,
    request: UpdateWorldbuildingRequest,
    service: WorldbuildingService = Depends(get_worldbuilding_service)
):
    """更新世界观"""
    worldbuilding = service.update_worldbuilding(
        novel_id=slug,
        core_rules=request.core_rules.dict() if request.core_rules else None,
        geography=request.geography.dict() if request.geography else None,
        society=request.society.dict() if request.society else None,
        culture=request.culture.dict() if request.culture else None,
        daily_life=request.daily_life.dict() if request.daily_life else None,
    )
    try:
        from application.engine.services.state_bootstrap import refresh_narrative_contract_in_shared_state
        refresh_narrative_contract_in_shared_state(slug)
    except Exception:
        pass
    slices = worldbuilding.normalized_dimensions() if hasattr(worldbuilding, "normalized_dimensions") else {}
    if isinstance(slices, dict):
        _sync_worldbuilding_variable_hub(slug, slices)
    return worldbuilding.to_dict()
