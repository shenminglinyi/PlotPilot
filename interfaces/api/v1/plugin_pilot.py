"""Manual official plugin pilot API. No automatic model consumption."""
import asyncio
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from application.plugin_pilot.contracts import AdoptRequest, PilotError, RunRequest
from application.plugin_pilot.service import PilotService

router = APIRouter(prefix="/plugin-pilot", tags=["official-plugin-pilot"])


@lru_cache(maxsize=1)
def get_pilot_service():
    from application.engine.services.persistence_queue import get_persistence_queue
    from infrastructure.ai.plugin_pilot_model import ConfiguredPilotModel
    return PilotService(get_persistence_queue(), ConfiguredPilotModel())


Service = Annotated[PilotService, Depends(get_pilot_service)]


async def _call(awaitable):
    try:
        return await awaitable
    except PilotError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    except asyncio.TimeoutError as exc:
        raise HTTPException(504, "Writer result unknown. Query command ID or refresh candidate list; do not resubmit blindly.") from exc
    except RuntimeError as exc:
        raise HTTPException(503, "Persistence writer unavailable or busy; refresh before retrying") from exc


@router.get("/catalog")
def catalog(service: Service):
    try:
        return service.catalog()
    except (ValueError, OSError) as exc:
        raise HTTPException(503, "Official plugin validation failed") from exc


@router.get("/model")
async def model(service: Service):
    return await _call(service.model.identity())


@router.get("/projects")
async def projects(service: Service):
    return await _call(service.command("projects"))


@router.get("/projects/{project_id}/inputs")
async def inputs(project_id: str, service: Service):
    return await _call(service.command("inputs", project_id=project_id))


@router.post("/runs")
async def run(request: RunRequest, service: Service):
    return await _call(service.run(request))


@router.get("/projects/{project_id}/candidates")
async def candidates(project_id: str, service: Service):
    return await _call(service.command("candidates", project_id=project_id))


@router.post("/candidates/{candidate_id}/adopt")
async def adopt(candidate_id: str, request: AdoptRequest, service: Service):
    try:
        result = await service.command("adopt", candidate_id=candidate_id, **request.model_dump())
    except asyncio.TimeoutError:
        return {"status": "pending", "command_id": request.command_id,
                "message": "Outcome unknown; query this command ID before taking further action"}
    except PilotError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, "Writer unavailable; query command ID before retrying") from exc
    if result["status"] != "committed":
        raise HTTPException(409, result)
    return result


@router.get("/projects/{project_id}/commands/{command_id}")
async def command(project_id: str, command_id: str, service: Service):
    return await _call(service.command("command", project_id=project_id, command_id=command_id))
