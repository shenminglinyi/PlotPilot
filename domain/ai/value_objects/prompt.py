# domain/ai/value_objects/prompt.py
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass(frozen=True)
class Prompt:
    """提示词值对象"""
    system: str
    user: str
    node_key: str = ""

    def __post_init__(self):
        if not self.user or not self.user.strip():
            raise ValueError("User message cannot be empty")
        if not self.system or not self.system.strip():
            raise ValueError("System message cannot be empty")
        object.__setattr__(self, "node_key", (self.node_key or "").strip())

    def to_messages(self) -> List[Dict[str, Any]]:
        """转换为消息列表格式"""
        messages = []
        if self.system:
            messages.append({"role": "system", "content": self.system})
        messages.append({"role": "user", "content": self.user})
        return messages
