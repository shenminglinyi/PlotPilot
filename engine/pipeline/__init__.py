"""Engine Pipeline — Opinionated Fat Framework 的核心基类

AIText 不搞微内核、不搞 SPI、不搞适配器。
我们只提供一件事：一个继承即用的写作管线基类。

设计哲学：
- Batteries-Included：所有高级能力（反AI味、俗套扫描、声线追踪、
  叙事同步、伏笔管理、KG推断）全部内置，开箱即用。
- Schema-First：数据库表结构是生态的数据标准，引擎直接查库。
- 继承即扩展：把管线切成 _step_xxx() 方法，子类覆写对应步骤即可。

扩展方式（按复杂度递增）：
1. 调参：修改 prompt 模板、阈值、权重
2. 覆写步骤：继承 BaseStoryPipeline，重写 _step_build_context() 等
3. 替换管线：继承并重写 run_chapter()，完全自定义流程

示例——短剧引擎：
    class ShortDramaPipeline(BaseStoryPipeline):
        def _step_magnify_beats(self, ...):
            beats = super()._step_magnify_beats(...)
            for b in beats:
                b.target_words = 500  # 短剧每拍500字
            return beats

        def _step_build_context(self, ...):
            ctx = super()._step_build_context(...)
            ctx += "\\n【强制规则】每3分钟必须有一个反转。"
            return ctx
"""
from engine.pipeline.base import BaseStoryPipeline
from engine.pipeline.context import PipelineContext, PipelineResult
from engine.pipeline.steps import StepResult

__all__ = [
    "BaseStoryPipeline",
    "PipelineContext",
    "PipelineResult",
    "StepResult",
]
