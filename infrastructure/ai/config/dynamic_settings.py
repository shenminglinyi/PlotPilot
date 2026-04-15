import json
import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel

class LLMConfigDTO(BaseModel):
    # 全局默认提供商 (为了兼容老逻辑)
    provider: str = "openai"
    
    # 创作主力模型 (Default Model) 配置
    default_model_provider: str = "openai"
    default_model_api_key: Optional[str] = None
    default_model_base_url: Optional[str] = None
    default_model: str = ""

    # 分析经济模型 (Cheap Model) 配置
    cheap_model_provider: str = "openai"
    cheap_model_api_key: Optional[str] = None
    cheap_model_base_url: Optional[str] = None
    cheap_model: str = ""

    # 知识图谱模型 (Knowledge Model) 配置
    knowledge_model_provider: str = "openai"
    knowledge_model_api_key: Optional[str] = None
    knowledge_model_base_url: Optional[str] = None
    knowledge_model: str = ""

    # 深度研究模型 (Research Model) 配置
    research_model_provider: str = "openai"
    research_model_api_key: Optional[str] = None
    research_model_base_url: Optional[str] = None
    research_model: str = ""

    fact_review_model_provider: str = "openai"
    fact_review_model_api_key: Optional[str] = None
    fact_review_model_base_url: Optional[str] = None
    fact_review_model: str = ""

    genre_review_model_provider: str = "openai"
    genre_review_model_api_key: Optional[str] = None
    genre_review_model_base_url: Optional[str] = None
    genre_review_model: str = ""

    reader_review_model_provider: str = "openai"
    reader_review_model_api_key: Optional[str] = None
    reader_review_model_base_url: Optional[str] = None
    reader_review_model: str = ""

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
