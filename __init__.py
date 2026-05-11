"""PlotPilot（墨枢）：配置、LLM 客户端、story 域、流水线、CLI。"""

__version__ = "0.1.0"

# Export logging configuration functions
from .interfaces.api.middleware.logging_config import setup_logging, get_logger
