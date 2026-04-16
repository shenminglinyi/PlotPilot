import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from application.engine.services.rewrite_service import RewriteService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rewrite", tags=["rewrite"])


class RewriteRequest(BaseModel):
    text: str = Field(..., min_length=1, description="选中的文字")
    mode: str = Field(..., description="模式：rewrite|expand|shrink|polish|continue")
    context: str = Field("", description="前文上下文")


_service: Optional[RewriteService] = None


def _get_service() -> RewriteService:
    global _service
    if _service is None:
        _service = RewriteService()
    return _service


@router.post("")
async def rewrite_text(body: RewriteRequest):
    if body.mode not in ("rewrite", "expand", "shrink", "polish", "continue"):
        raise HTTPException(status_code=400, detail=f"Invalid mode: {body.mode}")

    service = _get_service()

    async def event_gen():
        try:
            async for chunk in service.stream_rewrite(
                text=body.text,
                mode=body.mode,
                context=body.context,
            ):
                event = {"type": "chunk", "text": chunk}
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            event = {"type": "done"}
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error("Rewrite stream error: %s", e, exc_info=True)
            event = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
