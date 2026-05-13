"""通用题材树只读接口（数据源：shared/taxonomy/*.yaml）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from application.core.taxonomy.builtin_cn import load_taxonomy_bundle_dict

router = APIRouter(prefix="/taxonomy", tags=["taxonomy"])


@router.get("/bundles/builtin_cn_v1")
async def get_builtin_cn_v1_bundle():
    try:
        return load_taxonomy_bundle_dict("builtin_cn_v1")
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="taxonomy bundle builtin_cn_v1.yaml not found")
