"""
API routes for Worldbuilding
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from application.world.services.worldbuilding_service import WorldbuildingService
from infrastructure.persistence.database.worldbuilding_repository import WorldbuildingRepository
from application.paths import get_db_path


router = APIRouter(prefix="/novels", tags=["worldbuilding"])


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
    service: WorldbuildingService = Depends(get_worldbuilding_service)
):
    """获取小说的世界观"""
    worldbuilding = service.get_worldbuilding(slug)

    if not worldbuilding:
        raise HTTPException(status_code=404, detail="Worldbuilding not found")

    return worldbuilding.to_dict()


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
    return worldbuilding.to_dict()
