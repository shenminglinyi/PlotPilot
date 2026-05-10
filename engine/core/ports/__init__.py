"""引擎内核端口抽象 — 依赖倒置原则

核心思想：
- 引擎内核(engine/core)不依赖任何外部实现
- 通过Port(端口)定义抽象接口
- 外部基础设施实现Port，注入引擎
- 引擎可独立测试、替换、扩展

端口列表：
- LLMPort: LLM调用抽象
- PersistencePort: 持久化抽象
- EventPort: 事件总线抽象
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ─── LLM端口 ───


@dataclass
class PromptValue:
    """提示词值对象"""
    system: str = ""
    user: str = ""


@dataclass
class GenerationConfig:
    """生成配置值对象"""
    max_tokens: int = 4000
    temperature: float = 0.85
    top_p: float = 0.95
    stop_sequences: List[str] = field(default_factory=list)


@dataclass
class GenerationResult:
    """生成结果值对象"""
    content: str
    token_count: int = 0
    finish_reason: str = "stop"


class LLMPort(ABC):
    """LLM调用端口 — 引擎不关心底层是OpenAI/Claude/Mock"""

    @abstractmethod
    async def generate(
        self, prompt: PromptValue, config: GenerationConfig
    ) -> GenerationResult:
        """生成文本"""
        ...


# ─── 持久化端口 ───


class PersistencePort(ABC):
    """持久化端口 — 引擎不关心底层是SQLite/PostgreSQL/Memory"""

    @abstractmethod
    async def save(self, collection: str, key: str, data: Dict[str, Any]) -> str:
        """保存数据，返回key"""
        ...

    @abstractmethod
    async def load(self, collection: str, key: str) -> Optional[Dict[str, Any]]:
        """加载数据"""
        ...

    @abstractmethod
    async def list_items(
        self, collection: str, filters: Optional[Dict[str, Any]] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """列出数据"""
        ...

    @abstractmethod
    async def delete(self, collection: str, key: str) -> bool:
        """删除数据"""
        ...


# ─── 事件端口 ───


@dataclass
class DomainEvent:
    """领域事件值对象"""
    event_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    source: str = ""  # 来源节点/模块
    trace_id: str = ""  # 溯源ID


class EventPort(ABC):
    """事件总线端口 — 引擎不关心底层是进程内/Redis/Kafka"""

    @abstractmethod
    async def publish(self, event: DomainEvent) -> None:
        """发布事件"""
        ...

    @abstractmethod
    async def subscribe(
        self, event_type: str, handler: Any
    ) -> None:
        """订阅事件"""
        ...


# ─── 溯源端口 ───


@dataclass
class TraceRecord:
    """引擎操作溯源记录"""
    trace_id: str
    node_type: str           # DAG节点/Guardrail/Checkpoint
    operation: str           # check/save/load/execute
    input_summary: str       # 输入摘要(前200字)
    output_summary: str      # 输出摘要
    score: Optional[float] = None
    violations: List[str] = field(default_factory=list)
    duration_ms: int = 0
    timestamp: str = ""


class TracePort(ABC):
    """溯源端口 — 引擎操作的完整审计日志"""

    @abstractmethod
    async def record(self, trace: TraceRecord) -> None:
        """记录溯源"""
        ...

    @abstractmethod
    async def query(
        self,
        novel_id: str,
        node_type: Optional[str] = None,
        operation: Optional[str] = None,
        limit: int = 100,
    ) -> List[TraceRecord]:
        """查询溯源记录"""
        ...
