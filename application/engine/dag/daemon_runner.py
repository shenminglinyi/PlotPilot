"""DAG 守护进程运行器 -- 替代 AutopilotDaemon 的隐式状态机

核心原则：
1. 复用现有 IPC 通道（StreamingBus、SharedState、PersistenceQueue）
2. LangGraph StateGraph 运行在守护进程的 asyncio 事件循环中
3. Checkpoint 使用独立 SQLite 文件
4. 每个 novel 一个 thread_id，支持并行多本小说
5. Feature Flag 控制新旧引擎切换
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, Optional

from application.engine.dag.engine import DAGEngine, DAGExecutionError
from application.engine.dag.event_aggregator import NodeEventAggregator
from application.engine.dag.ipc_adapter import IPCAdapter
from application.engine.dag.models import DAGDefinition, DAGRunResult
from application.engine.dag.validator import DAGValidator
from application.engine.dag.version_manager import DAGVersionManager

logger = logging.getLogger(__name__)


class DAGDaemonRunner:
    """DAG 编排守护进程运行器"""

    def __init__(
        self,
        streaming_bus=None,
        state_publisher=None,
        persistence_queue=None,
        circuit_breaker=None,
        data_root: Optional[str] = None,
    ):
        self._bus = streaming_bus
        self._publisher = state_publisher
        self._pq = persistence_queue
        self._breaker = circuit_breaker

        # DAG 版本管理器
        self._version_mgr = DAGVersionManager(data_root=data_root)

        # 事件聚合器
        self._aggregator = NodeEventAggregator(flush_interval=0.5)

        # IPC 适配器
        self._ipc = IPCAdapter(
            streaming_bus=streaming_bus,
            state_publisher=state_publisher,
            persistence_queue=persistence_queue,
            event_aggregator=self._aggregator,
        )

        # DAG 执行引擎
        self._engine = DAGEngine()

        # DAG 验证器
        self._validator = DAGValidator()

        # 编译缓存：novel_id -> {"fingerprint": str, "engine": DAGEngine}
        self._compiled_graphs: Dict[str, Dict[str, Any]] = {}

        # 运行中的任务
        self._running_tasks: Dict[str, asyncio.Task] = {}

    async def run_novel(self, novel_id: str, dag: Optional[DAGDefinition] = None):
        """执行单本小说的 DAG 工作流

        Args:
            novel_id: 小说 ID
            dag: DAG 定义，如果为 None 则加载已保存的定义
        """
        # 加载 DAG 定义
        if dag is None:
            dag = self._version_mgr.load_latest(novel_id)
        if dag is None:
            dag = self._version_mgr.init_default_dag(novel_id)

        # 验证 DAG
        result = self._validator.validate(dag)
        if not result.is_valid:
            logger.error(f"DAG 验证失败: {result.errors}")
            if self._publisher:
                self._publisher.update_novel_state(
                    novel_id,
                    autopilot_status="error",
                    error_message=f"DAG 验证失败: {'; '.join(result.errors)}",
                )
            return

        # 构建初始状态
        initial_state = await self._build_initial_state(novel_id)

        # 构建线程 ID
        thread_id = f"novel_{novel_id}"

        try:
            # 执行 DAG
            dag_result = await self._engine.run(dag, initial_state, thread_id)

            if dag_result.status == "completed":
                logger.info(f"DAG 运行完成: novel={novel_id}, 耗时={dag_result.total_duration_ms}ms")
                if self._publisher:
                    self._publisher.set_autopilot_status(novel_id, "completed")
            else:
                logger.error(f"DAG 运行失败: novel={novel_id}")
                if self._breaker:
                    self._breaker.record_failure()
                if self._publisher:
                    self._publisher.update_novel_state(
                        novel_id,
                        autopilot_status="error",
                        error_message="DAG 运行失败",
                    )

        except DAGExecutionError as e:
            logger.error(f"DAG 执行错误: novel={novel_id}, {e}")
            if self._breaker:
                self._breaker.record_failure()
            if self._publisher:
                self._publisher.update_novel_state(
                    novel_id,
                    autopilot_status="error",
                    error_message=str(e),
                )

        except Exception as e:
            logger.error(f"DAG 执行异常: novel={novel_id}, {e}", exc_info=True)
            if self._breaker:
                self._breaker.record_failure()

    async def resume_novel(self, novel_id: str):
        """从 checkpoint 恢复执行（断点续写）"""
        dag = self._version_mgr.load_latest(novel_id)
        if not dag:
            raise ValueError(f"小说 {novel_id} 无已保存的 DAG 定义")

        initial_state = await self._build_initial_state(novel_id)
        thread_id = f"novel_{novel_id}"

        # 使用 engine 的 run_from_node 语义
        # 实际断点续写由 LangGraph Checkpointer 处理
        dag_result = await self._engine.run(dag, initial_state, thread_id)
        logger.info(f"DAG 断点续写完成: novel={novel_id}")

    async def _build_initial_state(self, novel_id: str) -> Dict[str, Any]:
        """构建初始运行状态"""
        return {
            "novel_id": novel_id,
            "chapter_number": 0,
            "dag_run_id": f"run_{int(time.time()*1000)}",
            "disabled_nodes": [],
            "node_configs": {},
        }

    # ─── 节点操作 ───

    async def toggle_node(self, novel_id: str, node_id: str) -> DAGDefinition:
        """切换节点启用/禁用"""
        dag = self._version_mgr.load_latest(novel_id)
        if not dag:
            raise ValueError(f"小说 {novel_id} 无 DAG 定义")

        node = dag.get_node(node_id)
        if not node:
            raise ValueError(f"节点 '{node_id}' 不存在")

        # 检查是否可禁用
        from application.engine.dag.registry import NodeRegistry
        try:
            meta = NodeRegistry.get_meta(node.type)
            if not meta.can_disable and node.enabled:
                raise ValueError(f"节点 '{node_id}' 不可禁用（核心节点）")
        except KeyError:
            pass

        node.enabled = not node.enabled
        self._version_mgr.save_version(novel_id, dag)
        return dag

    async def update_node_config(
        self, novel_id: str, node_id: str, config: Dict[str, Any]
    ) -> DAGDefinition:
        """更新节点配置"""
        dag = self._version_mgr.load_latest(novel_id)
        if not dag:
            raise ValueError(f"小说 {novel_id} 无 DAG 定义")

        node = dag.get_node(node_id)
        if not node:
            raise ValueError(f"节点 '{node_id}' 不存在")

        # 更新配置
        for key, value in config.items():
            if hasattr(node.config, key):
                setattr(node.config, key, value)

        self._version_mgr.save_version(novel_id, dag)
        return dag


class EngineSelector:
    """引擎选择器 -- 根据 Feature Flag 决定使用旧守护进程或 DAG 引擎"""

    def __init__(self):
        self.dag_enabled = os.getenv(
            "ENABLE_DAG_ENGINE", "false"
        ).lower() in ("1", "true", "yes")
        self._novel_flags: Dict[str, bool] = {}

    def should_use_dag(self, novel_id: str) -> bool:
        if novel_id in self._novel_flags:
            return self._novel_flags[novel_id]
        return self.dag_enabled

    def set_novel_flag(self, novel_id: str, use_dag: bool):
        self._novel_flags[novel_id] = use_dag
