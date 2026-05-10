"""兼容层 — engine.domain.entities.foreshadow

⚠️ 已废弃，请使用: from engine.core.entities.foreshadow import ...
"""
from engine.core.entities.foreshadow import (
    Foreshadow, ForeshadowId, ForeshadowStatus, ForeshadowBinding,
)

__all__ = ["Foreshadow", "ForeshadowId", "ForeshadowStatus", "ForeshadowBinding"]
