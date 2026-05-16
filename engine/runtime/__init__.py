"""Engine Runtime — 运行时组件

包含：
- StoryPipelineRunner: 写作管线运行器（替代 AutopilotDaemon）
- PolicyValidator: 策略验证器（适配 QualityGuardrail）
- QualityGuardrail: 六维度质量守门人
- PlotStateMachine: 故事阶段生命周期管理
- CheckpointManager: Checkpoint 管理
- WritingOrchestrator: 写作编排器
"""
from engine.runtime.runner import StoryPipelineRunner
from engine.runtime.policy_validator import PolicyValidator

__all__ = ["StoryPipelineRunner", "PolicyValidator"]
