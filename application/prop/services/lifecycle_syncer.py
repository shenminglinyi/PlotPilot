"""PropLifecycleSyncer — 章节收稿后编排道具生命周期同步。

设计原则：
- 依赖注入：仓储 + 提取器列表 + 事件处理器列表 全部从外部注入
- 不依赖具体 LLM / DB 实现，只依赖 Protocol / 抽象仓储
- 失败隔离：单个提取器失败不影响其他提取器
"""
from __future__ import annotations
import asyncio
import logging
from typing import Any, Dict, List, Optional

from domain.prop.entities.prop import Prop
from domain.prop.repositories.prop_repository import PropRepository
from domain.prop.repositories.prop_event_repository import PropEventRepository
from domain.prop.value_objects.lifecycle_state import LifecycleTransitionError
from domain.prop.value_objects.prop_event import PropEvent
from application.prop.ports.extractor_port import PropExtractor
from application.prop.ports.event_handler_port import PropEventHandler

logger = logging.getLogger(__name__)


class PropLifecycleSyncer:
    """道具生命周期编排器。

    注册多个 PropExtractor（按 priority 升序执行），
    将提取的事件应用到 Prop 聚合根，持久化，并触发 PropEventHandler 副作用。
    """

    def __init__(
        self,
        prop_repo: PropRepository,
        event_repo: PropEventRepository,
        extractors: Optional[List[PropExtractor]] = None,
        handlers: Optional[List[PropEventHandler]] = None,
    ) -> None:
        self._prop_repo = prop_repo
        self._event_repo = event_repo
        self._extractors: List[PropExtractor] = sorted(
            extractors or [], key=lambda e: e.priority
        )
        self._handlers: List[PropEventHandler] = handlers or []

    def register_extractor(self, extractor: PropExtractor) -> None:
        """运行时注册新提取器（热插拔）。"""
        self._extractors.append(extractor)
        self._extractors.sort(key=lambda e: e.priority)

    def register_handler(self, handler: PropEventHandler) -> None:
        self._handlers.append(handler)

    async def sync(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
    ) -> Dict[str, Any]:
        """执行完整同步流程，返回执行摘要。"""
        active_props = self._prop_repo.list_active(novel_id, chapter_number)
        all_props = self._prop_repo.list_by_novel(novel_id)
        if not active_props and not all_props:
            return {"skipped": True, "reason": "no_props"}

        props_input = [
            {
                "id": p.id.value,
                "name": p.name,
                "aliases": p.aliases,
                "holder": p.holder_character_id,
                "state": p.lifecycle_state.value,
            }
            for p in active_props
        ]

        all_events: List[PropEvent] = []
        tasks = [
            self._safe_extract(ext, novel_id, chapter_number, content, props_input)
            for ext in self._extractors
        ]
        results = await asyncio.gather(*tasks)
        for evts in results:
            all_events.extend(evts)

        deduped = self._deduplicate(all_events)

        prop_map: Dict[str, Prop] = {p.id.value: p for p in active_props}
        applied = 0
        for event in deduped:
            prop = prop_map.get(event.prop_id)
            if not prop:
                continue
            try:
                prop.apply_event(event)
                self._prop_repo.save(prop)
                self._event_repo.save(event)
                applied += 1
                for handler in self._handlers:
                    try:
                        await handler.handle(prop, event)
                    except Exception as he:
                        logger.debug(
                            "[PropSync] handler %s 失败: %s", type(handler).__name__, he
                        )
            except LifecycleTransitionError as lte:
                logger.warning(
                    "[PropSync] 状态转换被拒绝 prop=%s: %s", event.prop_id, lte
                )
            except Exception as e:
                logger.warning(
                    "[PropSync] 事件应用失败 prop=%s: %s", event.prop_id, e
                )

        return {
            "novel_id": novel_id,
            "chapter": chapter_number,
            "props_checked": len(active_props),
            "events_extracted": len(all_events),
            "events_applied": applied,
        }

    async def _safe_extract(
        self,
        extractor: PropExtractor,
        *args,
    ) -> List[PropEvent]:
        try:
            return await extractor.extract(*args)
        except Exception as e:
            logger.warning("[PropSync] 提取器 %s 失败: %s", extractor.name, e)
            return []

    @staticmethod
    def _deduplicate(events: List[PropEvent]) -> List[PropEvent]:
        """同一道具同类事件只保留第一个（来自优先级更高的提取器）。"""
        seen: set = set()
        result: List[PropEvent] = []
        for ev in events:
            key = (ev.prop_id, ev.event_type.value)
            if key not in seen:
                seen.add(key)
                result.append(ev)
        return result
