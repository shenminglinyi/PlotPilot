from __future__ import annotations
from typing import List, Protocol, runtime_checkable
from domain.prop.value_objects.prop_event import PropEvent


@runtime_checkable
class PropExtractor(Protocol):
    """可插拔道具事件提取策略。
    
    任何实现此接口的类都可以注册到 PropLifecycleSyncer。
    新策略只需实现此协议并注册，无需修改核心逻辑。
    """

    async def extract(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
        active_props: List[dict],
    ) -> List[PropEvent]:
        """从章节正文中提取道具事件列表。

        active_props: [{"id": ..., "name": ..., "aliases": [...], "holder": ..., "state": ...}]
        """
        ...

    @property
    def priority(self) -> int:
        """执行优先级，数字越小越先执行。"""
        ...

    @property
    def name(self) -> str:
        """提取器名称，用于日志。"""
        ...
