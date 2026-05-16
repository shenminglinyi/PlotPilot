"""Engine Examples — 官方管线子类示例

演示如何继承 BaseStoryPipeline，覆写 _step_xxx() 方法，
实现垂直领域的剧情引擎。

社区看了秒懂：继承核心类，随便改写几个方法，
就能做出一个垂直行业的引擎！
"""
from engine.examples.short_drama_pipeline import ShortDramaPipeline
from engine.examples.wuxia_pipeline import WuxiaPipeline

__all__ = ["ShortDramaPipeline", "WuxiaPipeline"]
