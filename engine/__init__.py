"""AIText Engine - 写作引擎内核

分层架构（洋葱模型）：
- core/: 核心领域层（实体、值对象、端口抽象）— 统一入口
- domain/: 兼容层（re-export from core）
- application/: 应用服务层（Guardrail/Checkpoint/Orchestrator）
- infrastructure/: 基础设施层（Persistence/Events/Memory）

⚠️ 优先使用 engine.core.* 导入，engine.domain.* 为兼容层。
"""
__version__ = "2.1.0"
