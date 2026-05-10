"""节点注册表 — 所有节点类型的工厂与元数据仓库

使用装饰器模式注册节点实现类，运行时按 node_type 查找。
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Set, Type

from application.engine.dag.models import (
    NodeCategory,
    NodeConfig,
    NodeMeta,
    NodePort,
    NodeResult,
    NodeStatus,
    PortDataType,
)

logger = logging.getLogger(__name__)


# ─── 节点基类 ───


class BaseNode(ABC):
    """节点抽象基类 — 所有 DAG 节点必须继承此"""

    # 子类必须定义类级别 meta
    meta: NodeMeta = None  # type: ignore

    def __init__(self, config: Optional[NodeConfig] = None):
        self._config = config or NodeConfig()

    @abstractmethod
    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        """执行节点逻辑

        Args:
            inputs: 上游节点传入的数据，key 对应 input_ports.name
            context: 运行上下文（novel_id, chapter_number, dag_run_id, shared_state, config_overrides）

        Returns:
            NodeResult: 执行结果，outputs 的 key 对应 output_ports.name
        """
        ...

    @abstractmethod
    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        """校验输入数据是否满足要求"""
        ...

    def build_prompt(self, variables: Dict[str, str]) -> str:
        """根据模板和变量构建 Prompt（可被子类覆盖）"""
        template = self.get_prompt_template()
        if not template:
            return ""
        for key, value in variables.items():
            template = template.replace(f"{{{{{key}}}}}", str(value))
        return template

    def get_effective_prompt(self) -> Dict[str, str]:
        """获取生效的提示词（三级降级：CPMS → Config → Meta）

        Returns:
            {"system": str, "user_template": str, "source": str}
            source: "cpms" | "config" | "meta" | "none"
        """
        cpms_key = self.meta.cpms_node_key if self.meta else ""

        # 1. CPMS 优先
        if cpms_key:
            try:
                from infrastructure.ai.prompt_registry import get_prompt_registry
                registry = get_prompt_registry()
                system = registry.get_system(cpms_key)
                user_template = registry.get_user_template(cpms_key)
                if system or user_template:
                    return {
                        "system": system or "",
                        "user_template": user_template or "",
                        "source": "cpms",
                    }
            except Exception:
                pass

        # 2. Config 覆盖
        if self._config and self._config.prompt_template:
            return {
                "system": self._config.prompt_template,
                "user_template": "",
                "source": "config",
            }

        # 3. Meta 默认
        if self.meta and self.meta.prompt_template:
            return {
                "system": self.meta.prompt_template,
                "user_template": "",
                "source": "meta",
            }

        return {"system": "", "user_template": "", "source": "none"}

    def get_prompt_template(self) -> str:
        """获取生效的 Prompt 模板（向后兼容，内部走 get_effective_prompt）"""
        return self.get_effective_prompt()["system"]

    def get_timeout(self) -> float:
        """获取超时时间（秒），支持配置覆盖"""
        base = self.meta.default_timeout_seconds if self.meta else 60
        if self._config and self._config.timeout_seconds:
            return self._config.timeout_seconds
        return base

    def get_max_retries(self) -> int:
        """获取最大重试次数，支持配置覆盖"""
        base = self.meta.default_max_retries if self.meta else 1
        if self._config and self._config.max_retries is not None:
            return self._config.max_retries
        return base


# ─── 节点注册表 ───


class NodeRegistry:
    """节点注册表 — 所有节点类型的工厂"""

    _registry: Dict[str, Type[BaseNode]] = {}
    _meta_registry: Dict[str, NodeMeta] = {}

    @classmethod
    def register(cls, node_type: str):
        """装饰器：注册节点类型

        用法：
            @NodeRegistry.register("val_style")
            class StyleCheckNode(BaseNode):
                meta = NodeMeta(node_type="val_style", ...)
                ...
        """
        def decorator(node_cls: Type[BaseNode]):
            if node_type in cls._registry:
                logger.warning(f"节点类型 '{node_type}' 被重复注册，覆盖为 {node_cls.__name__}")
            cls._registry[node_type] = node_cls
            # 自动提取类级别 meta
            if hasattr(node_cls, 'meta') and node_cls.meta is not None:
                cls._meta_registry[node_type] = node_cls.meta
            logger.debug(f"注册节点类型: {node_type} → {node_cls.__name__}")
            return node_cls
        return decorator

    @classmethod
    def get(cls, node_type: str) -> Type[BaseNode]:
        """获取节点类"""
        if node_type not in cls._registry:
            raise KeyError(f"未注册的节点类型: '{node_type}'，已注册: {list(cls._registry.keys())}")
        return cls._registry[node_type]

    @classmethod
    def get_meta(cls, node_type: str) -> NodeMeta:
        """获取节点元数据"""
        if node_type not in cls._meta_registry:
            raise KeyError(f"未注册的节点类型元数据: '{node_type}'")
        return cls._meta_registry[node_type]

    @classmethod
    def has(cls, node_type: str) -> bool:
        """检查节点类型是否已注册"""
        return node_type in cls._registry

    @classmethod
    def all_types(cls) -> Set[str]:
        """获取所有已注册的节点类型"""
        return set(cls._registry.keys())

    @classmethod
    def all_meta(cls) -> Dict[str, NodeMeta]:
        """获取所有节点元数据"""
        return dict(cls._meta_registry)

    @classmethod
    def create_instance(cls, node_type: str, config: Optional[NodeConfig] = None) -> BaseNode:
        """创建节点实例"""
        node_cls = cls.get(node_type)
        return node_cls(config=config)

    @classmethod
    def create_executor(cls, node_type: str, node_id: str, config: Optional[NodeConfig] = None):
        """创建 LangGraph 可用的执行函数

        Args:
            node_type: 节点类型标识
            node_id: 节点实例 ID
            config: 节点配置

        Returns:
            async executor function，签名: (state: dict) -> dict
        """
        instance = cls.create_instance(node_type, config)
        meta = cls.get_meta(node_type)

        async def executor(state: dict) -> dict:
            # 跳过禁用节点
            disabled_nodes = state.get("disabled_nodes", [])
            if node_id in disabled_nodes:
                logger.info(f"节点 {node_id} 已禁用，跳过 (bypass)")
                return {"status": "bypassed"}

            # 收集输入
            inputs = _collect_inputs(state, meta.input_ports, node_id)

            # 校验输入
            if not instance.validate_inputs(inputs):
                return {
                    "status": "error",
                    "error": f"节点 {node_id} 输入校验失败",
                }

            # 应用用户配置覆盖
            node_configs = state.get("node_configs", {})
            config_overrides = node_configs.get(node_id, {})

            # 构建上下文
            context = {
                "novel_id": state.get("novel_id", ""),
                "chapter_number": state.get("chapter_number", 0),
                "dag_run_id": state.get("dag_run_id", ""),
                "shared_state": state,
                "config_overrides": config_overrides,
            }

            # 执行
            result = await instance.execute(inputs, context)

            # 返回输出（扁平化到 state）
            return result.outputs

        executor.__name__ = f"executor_{node_id}"
        executor.__qualname__ = f"executor_{node_id}"
        return executor


def _collect_inputs(state: dict, input_ports: List[NodePort], node_id: str) -> Dict[str, Any]:
    """从全局状态中收集节点所需的输入数据"""
    inputs = {}
    for port in input_ports:
        value = state.get(port.name)
        if value is not None:
            inputs[port.name] = value
        elif port.default is not None:
            inputs[port.name] = port.default
        elif port.required:
            logger.warning(f"节点 {node_id} 缺少必填输入端口: {port.name}")
    return inputs
