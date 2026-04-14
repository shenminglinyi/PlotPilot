import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from infrastructure.ai.config.dynamic_settings import DynamicSettingsManager, LLMConfigDTO

router = APIRouter(prefix="/system/llm", tags=["System LLM Config"])
manager = DynamicSettingsManager()

class VerifyRequest(BaseModel):
    provider: str
    api_key: str
    base_url: Optional[str] = None

class VerifyResponse(BaseModel):
    models: List[str]

@router.get("/config", response_model=LLMConfigDTO)
async def get_config():
    config = manager.load_config()
    if not config:
        # Return a blank default config if none exists
        return LLMConfigDTO()
    # Mask API keys for security when returning to frontend
    masked_config = config.model_copy()
    if masked_config.openai_api_key:
        masked_config.openai_api_key = "sk-..." + masked_config.openai_api_key[-4:] if len(masked_config.openai_api_key) > 4 else "***"
    if masked_config.anthropic_api_key:
        masked_config.anthropic_api_key = "sk-ant-..." + masked_config.anthropic_api_key[-4:] if len(masked_config.anthropic_api_key) > 4 else "***"
    return masked_config

@router.post("/config")
async def save_config(config: LLMConfigDTO):
    # If the user sends masked keys, we should preserve the old keys
    old_config = manager.load_config()
    if old_config:
        if config.openai_api_key and config.openai_api_key.startswith("sk-..."):
            config.openai_api_key = old_config.openai_api_key
        if config.anthropic_api_key and config.anthropic_api_key.startswith("sk-ant-..."):
            config.anthropic_api_key = old_config.anthropic_api_key
            
    manager.save_config(config)
    return {"status": "success"}

@router.post("/verify", response_model=VerifyResponse)
async def verify_and_fetch_models(req: VerifyRequest):
    if not req.api_key or req.api_key.startswith("sk-..."):
        raise HTTPException(status_code=400, detail="Invalid API Key provided for verification.")
        
    models = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if req.provider == "openai":
                base = req.base_url.rstrip('/') if req.base_url else "https://api.openai.com/v1"
                headers = {"Authorization": f"Bearer {req.api_key}"}
                resp = await client.get(f"{base}/models", headers=headers)
                resp.raise_for_status()
                data = resp.json()
                models = [m["id"] for m in data.get("data", [])]
            elif req.provider == "anthropic":
                # Anthropic doesn't have a standard public /v1/models endpoint that lists all models for all accounts reliably in standard format.
                # We return standard hardcoded models for Anthropic to let the UI populate.
                models = ["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"]
            else:
                raise HTTPException(status_code=400, detail="Unsupported provider")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connection failed: {str(e)}")
        
    return VerifyResponse(models=models)
