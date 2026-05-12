from enum import Enum

class PropCategory(str, Enum):
    WEAPON     = "WEAPON"
    ARTIFACT   = "ARTIFACT"
    TOOL       = "TOOL"
    CONSUMABLE = "CONSUMABLE"
    TOKEN      = "TOKEN"
    OTHER      = "OTHER"
