import json
import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel

class LLMConfigDTO(BaseModel):
    provider: str = "openai"
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    anthropic_base_url: Optional[str] = None
    default_model: str = ""
    cheap_model: str = ""

class DynamicSettingsManager:
    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            # Default to data/llm_config.json in the project root
            root_dir = Path(__file__).parent.parent.parent.parent
            self.config_path = root_dir / "data" / "llm_config.json"
        else:
            self.config_path = config_path

    def load_config(self) -> Optional[LLMConfigDTO]:
        if not self.config_path.exists():
            return None
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return LLMConfigDTO(**data)
        except Exception:
            return None

    def save_config(self, config: LLMConfigDTO) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config.model_dump(), f, indent=2)
