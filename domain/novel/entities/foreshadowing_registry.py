# domain/novel/entities/foreshadowing_registry.py
from __future__ import annotations

import logging
from typing import List, Optional
from dataclasses import replace

from domain.shared.base_entity import BaseEntity
from domain.novel.value_objects.chapter_renumber_spec import ChapterRenumberSpec

logger = logging.getLogger(__name__)
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.foreshadowing import (
    Foreshadowing,
    ForeshadowingStatus
)
from domain.novel.entities.subtext_ledger_entry import SubtextLedgerEntry
from domain.shared.exceptions import InvalidOperationError


class ForeshadowingRegistry(BaseEntity):
    """伏笔注册表实体"""

    def __init__(self, id: str, novel_id: NovelId):
        super().__init__(id)
        self.novel_id = novel_id
        self._foreshadowings: List[Foreshadowing] = []
        self._subtext_entries: List[SubtextLedgerEntry] = []

    @property
    def foreshadowings(self) -> List[Foreshadowing]:
        """返回伏笔列表的副本"""
        return self._foreshadowings.copy()

    def register(self, foreshadowing: Foreshadowing) -> None:
        """注册新伏笔，检查重复"""
        if any(f.id == foreshadowing.id for f in self._foreshadowings):
            raise InvalidOperationError(
                f"Foreshadowing with id '{foreshadowing.id}' already exists"
            )
        self._foreshadowings.append(foreshadowing)

    def mark_resolved(self, foreshadowing_id: str, resolved_in_chapter: int) -> None:
        """标记伏笔为已解决，创建新的不可变对象"""
        for i, foreshadowing in enumerate(self._foreshadowings):
            if foreshadowing.id == foreshadowing_id:
                # 创建新的不可变 Foreshadowing 对象
                resolved_foreshadowing = replace(
                    foreshadowing,
                    status=ForeshadowingStatus.RESOLVED,
                    resolved_in_chapter=resolved_in_chapter
                )
                self._foreshadowings[i] = resolved_foreshadowing
                return

        raise InvalidOperationError(
            f"Foreshadowing with id '{foreshadowing_id}' not found"
        )

    def get_by_id(self, foreshadowing_id: str) -> Optional[Foreshadowing]:
        """通过 ID 获取伏笔"""
        for foreshadowing in self._foreshadowings:
            if foreshadowing.id == foreshadowing_id:
                return foreshadowing
        return None

    def get_unresolved(self) -> List[Foreshadowing]:
        """获取所有未解决的伏笔（PLANTED 状态）"""
        return [
            f for f in self._foreshadowings
            if f.status == ForeshadowingStatus.PLANTED
        ]

    def get_ready_to_resolve(self, current_chapter: int) -> List[Foreshadowing]:
        """获取准备解决的伏笔"""
        return [
            f for f in self._foreshadowings
            if f.status == ForeshadowingStatus.PLANTED
            and f.suggested_resolve_chapter is not None
            and f.suggested_resolve_chapter <= current_chapter
        ]

    @property
    def subtext_entries(self) -> List[SubtextLedgerEntry]:
        """返回潜台词账本条目列表的副本"""
        return self._subtext_entries.copy()

    def add_subtext_entry(self, entry: SubtextLedgerEntry) -> None:
        """添加潜台词账本条目，检查重复"""
        if any(e.id == entry.id for e in self._subtext_entries):
            raise InvalidOperationError(
                f"SubtextLedgerEntry with id '{entry.id}' already exists"
            )
        self._subtext_entries.append(entry)

    def update_subtext_entry(self, entry_id: str, updated_entry: SubtextLedgerEntry) -> None:
        """更新潜台词账本条目"""
        for i, entry in enumerate(self._subtext_entries):
            if entry.id == entry_id:
                self._subtext_entries[i] = updated_entry
                return

        raise InvalidOperationError(
            f"SubtextLedgerEntry with id '{entry_id}' not found"
        )

    def remove_subtext_entry(self, entry_id: str) -> None:
        """删除潜台词账本条目"""
        for i, entry in enumerate(self._subtext_entries):
            if entry.id == entry_id:
                self._subtext_entries.pop(i)
                return

        raise InvalidOperationError(
            f"SubtextLedgerEntry with id '{entry_id}' not found"
        )

    def get_subtext_entry_by_id(self, entry_id: str) -> Optional[SubtextLedgerEntry]:
        """通过 ID 获取潜台词账本条目"""
        for entry in self._subtext_entries:
            if entry.id == entry_id:
                return entry
        return None

    def get_pending_subtext_entries(self) -> List[SubtextLedgerEntry]:
        """获取所有待消费的潜台词账本条目"""
        return [
            e for e in self._subtext_entries
            if e.status == "pending"
        ]

    def get_overdue_foreshadowings(self, current_chapter: int) -> List[Foreshadowing]:
        """获取已过期的伏笔（预期回收章节已过但尚未回收）"""
        return [
            f for f in self._foreshadowings
            if f.status == ForeshadowingStatus.PLANTED
            and f.suggested_resolve_chapter is not None
            and f.suggested_resolve_chapter < current_chapter
        ]

    def get_upcoming_foreshadowings(self, current_chapter: int, window: int = 3) -> List[Foreshadowing]:
        """获取即将到期的伏笔（在指定窗口内预期回收）"""
        return [
            f for f in self._foreshadowings
            if f.status == ForeshadowingStatus.PLANTED
            and f.suggested_resolve_chapter is not None
            and current_chapter <= f.suggested_resolve_chapter <= current_chapter + window
        ]

    def get_overdue_subtext_entries(self, current_chapter: int) -> List[SubtextLedgerEntry]:
        """获取已过期的潜台词条目"""
        return [
            e for e in self._subtext_entries
            if e.status == "pending"
            and hasattr(e, 'suggested_resolve_chapter')
            and e.suggested_resolve_chapter is not None
            and e.suggested_resolve_chapter < current_chapter
        ]

    def get_upcoming_subtext_entries(self, current_chapter: int, window: int = 3) -> List[SubtextLedgerEntry]:
        """获取即将到期的潜台词条目"""
        return [
            e for e in self._subtext_entries
            if e.status == "pending"
            and hasattr(e, 'suggested_resolve_chapter')
            and e.suggested_resolve_chapter is not None
            and current_chapter <= e.suggested_resolve_chapter <= current_chapter + window
        ]

    @staticmethod
    def _clamp_foreshadowing_chapters(f: Foreshadowing) -> Foreshadowing:
        planted = f.planted_in_chapter
        suggested = f.suggested_resolve_chapter
        resolved = f.resolved_in_chapter
        if suggested is not None and suggested < planted:
            suggested = planted
        if resolved is not None and resolved < planted:
            resolved = planted
        if suggested is not None and resolved is not None and resolved < suggested:
            resolved = suggested
        return replace(
            f,
            suggested_resolve_chapter=suggested,
            resolved_in_chapter=resolved,
        )

    def apply_ttl_downgrade(self, current_chapter: int, ttl_chapters: int = 15) -> int:
        """★ 爽文引擎: 伏笔 TTL 自动降级机制（强效 GC）

        爽文读者追求即时刺激，对深层伏笔容忍度低。
        严格 TTL 机制从"重度记账"转向"短平快"。

        超过 ttl_chapters 章未回收的边缘伏笔自动降级或放弃，
        释放 T0 层的 Token 预算给 T2（最近章节）和 T3（向量召回近期打脸对象）。

        规则（爽文引擎强化版）：
        - 默认 TTL=15 章（原 30 章），爽文不需要长线伏笔
        - 超过 TTL：LOW importance 伏笔自动 ABANDONED
        - 超过 TTL*1.2：MEDIUM importance 伏笔也自动 ABANDONED（原 1.5x，收紧）
        - HIGH/CRITICAL 伏笔永不自动放弃（必须人工干预或 LLM 主动回收）

        Args:
            current_chapter: 当前章节号
            ttl_chapters: TTL 章节数，默认 15 章

        Returns:
            被降级的伏笔数量
        """
        from domain.novel.value_objects.foreshadowing import ImportanceLevel

        abandoned_count = 0
        new_foreshadowings: List[Foreshadowing] = []

        for f in self._foreshadowings:
            if f.status != ForeshadowingStatus.PLANTED:
                new_foreshadowings.append(f)
                continue

            # 计算伏笔"年龄"
            age = current_chapter - f.planted_in_chapter

            # HIGH 和 CRITICAL 伏笔永不自动放弃
            if f.importance.value >= ImportanceLevel.HIGH.value:
                new_foreshadowings.append(f)
                continue

            # 没有 suggested_resolve_chapter 的伏笔使用 TTL
            if f.suggested_resolve_chapter is None:
                effective_ttl = ttl_chapters
            else:
                # 有 suggested_resolve_chapter 但已过期的伏笔
                overdue = current_chapter - f.suggested_resolve_chapter
                if overdue <= 0:
                    new_foreshadowings.append(f)
                    continue
                effective_ttl = ttl_chapters + (f.suggested_resolve_chapter - f.planted_in_chapter)

            if age > effective_ttl * 1.2:
                # 超过 1.2x TTL：MEDIUM 也放弃（爽文收紧，原 1.5x）
                if f.importance.value >= ImportanceLevel.MEDIUM.value:
                    abandoned = replace(f, status=ForeshadowingStatus.ABANDONED)
                    new_foreshadowings.append(abandoned)
                    abandoned_count += 1
                    logger.info(
                        f"伏笔 TTL 降级 (1.2x): {f.description[:40]}... "
                        f"(age={age}, importance={f.importance.name})"
                    )
                    continue

            if age > effective_ttl:
                # 超过 TTL：LOW 伏笔放弃
                if f.importance.value <= ImportanceLevel.LOW.value:
                    abandoned = replace(f, status=ForeshadowingStatus.ABANDONED)
                    new_foreshadowings.append(abandoned)
                    abandoned_count += 1
                    logger.info(
                        f"伏笔 TTL 降级 (1x): {f.description[:40]}... "
                        f"(age={age}, importance={f.importance.name})"
                    )
                    continue

            new_foreshadowings.append(f)

        self._foreshadowings.clear()
        self._foreshadowings.extend(new_foreshadowings)
        return abandoned_count

    def get_t0_eligible_foreshadowings(
        self,
        current_chapter: int,
        max_items: int = 6,
    ) -> List[Foreshadowing]:
        """★ 爽文引擎: 筛选值得进入 T0 上下文预算的伏笔

        爽文引擎优化策略——从 T0 剥离冗长 pending：
        1. 已过期伏笔（suggested_resolve_chapter <= current_chapter）→ 最高优先级
        2. 即将到期伏笔（3章以内）→ 次高优先级
        3. LOW/MEDIUM 且 age > 10 章的伏笔 → 剥离到 T1/T3，不再占用 T0
        4. 总数控制在 max_items 以内，保护 T0 预算

        Args:
            current_chapter: 当前章节号
            max_items: 最大返回数量（爽文默认 6，防止 T0 膨胀）

        Returns:
            值得进入 T0 的伏笔列表（按优先级排序）
        """
        from domain.novel.value_objects.foreshadowing import ImportanceLevel

        eligible: List[Foreshadowing] = []
        deferred: List[Foreshadowing] = []  # 延迟到 T1/T3 的冗长 pending

        for f in self._foreshadowings:
            if f.status != ForeshadowingStatus.PLANTED:
                continue

            age = current_chapter - f.planted_in_chapter

            # ── 剥离规则：LOW/MEDIUM 且 age > 10 → 降级到 T1/T3 ──
            if (
                f.importance.value <= ImportanceLevel.MEDIUM.value
                and age > 10
                and (f.suggested_resolve_chapter is None
                     or f.suggested_resolve_chapter > current_chapter + 3)
            ):
                deferred.append(f)
                logger.debug(
                    f"[T0剥离] 伏笔 '{f.description[:30]}...' age={age} "
                    f"importance={f.importance.name} → 降级到 T1/T3"
                )
                continue

            eligible.append(f)

        # ── 排序：过期 > 即将到期 > HIGH > MEDIUM > LOW ──
        def sort_key(f: Foreshadowing):
            age = current_chapter - f.planted_in_chapter
            overdue = (
                f.suggested_resolve_chapter is not None
                and f.suggested_resolve_chapter <= current_chapter
            )
            imminent = (
                f.suggested_resolve_chapter is not None
                and current_chapter < f.suggested_resolve_chapter <= current_chapter + 3
            )
            return (
                0 if overdue else (1 if imminent else 2),
                -f.importance.value,
                age,  # 同优先级下，越老越先
            )

        eligible.sort(key=sort_key)

        # 截断到 max_items
        if len(eligible) > max_items:
            overflow = eligible[max_items:]
            deferred.extend(overflow)
            eligible = eligible[:max_items]
            logger.debug(
                f"[T0截断] {len(overflow)} 个低优先级伏笔被剥离到 T1/T3"
            )

        if deferred:
            logger.info(
                f"[爽文GC] T0 伏笔筛选: 保留 {len(eligible)}, "
                f"剥离 {len(deferred)} 个冗长 pending 到 T1/T3"
            )

        return eligible

    def get_deferred_foreshadowings(
        self,
        current_chapter: int,
    ) -> List[Foreshadowing]:
        """★ 爽文引擎: 获取被 T0 剥离的冗长 pending 伏笔

        这些伏笔仍需保留在 T1/T3 层级供参考，
        但不再占用宝贵的 T0 Token 预算。

        Args:
            current_chapter: 当前章节号

        Returns:
            被剥离的伏笔列表
        """
        from domain.novel.value_objects.foreshadowing import ImportanceLevel

        deferred: List[Foreshadowing] = []
        for f in self._foreshadowings:
            if f.status != ForeshadowingStatus.PLANTED:
                continue
            age = current_chapter - f.planted_in_chapter
            if (
                f.importance.value <= ImportanceLevel.MEDIUM.value
                and age > 10
                and (f.suggested_resolve_chapter is None
                     or f.suggested_resolve_chapter > current_chapter + 3)
            ):
                deferred.append(f)
        return deferred

    def apply_chapter_renumber_after_chapter_deleted(self, spec: ChapterRenumberSpec) -> None:
        """删章并重排章节号后，同步伏笔与潜台词中的章号引用（与 chapters 表一致）。"""
        new_foreshadowings: List[Foreshadowing] = []
        for f in self._foreshadowings:
            try:
                nf = replace(
                    f,
                    planted_in_chapter=spec.shift_chapter_ref(f.planted_in_chapter),
                    suggested_resolve_chapter=spec.shift_optional_chapter_ref(
                        f.suggested_resolve_chapter
                    ),
                    resolved_in_chapter=spec.shift_optional_chapter_ref(f.resolved_in_chapter),
                )
                new_foreshadowings.append(self._clamp_foreshadowing_chapters(nf))
            except (ValueError, TypeError) as e:
                logger.warning(
                    "伏笔 %s 章号重映射后校验失败，保留原条目: %s",
                    getattr(f, "id", "?"),
                    e,
                )
                new_foreshadowings.append(f)

        self._foreshadowings.clear()
        self._foreshadowings.extend(new_foreshadowings)

        new_entries: List[SubtextLedgerEntry] = []
        for e in self._subtext_entries:
            try:
                nc = spec.shift_chapter_ref(e.chapter)
                ncon = spec.shift_optional_chapter_ref(e.consumed_at_chapter)
                nsug = spec.shift_optional_chapter_ref(e.suggested_resolve_chapter)
                nwin = spec.shift_optional_chapter_ref(e.resolve_chapter_window)
                if ncon is not None and ncon < nc:
                    ncon = nc
                if nsug is not None and nsug < nc:
                    nsug = nc
                ne = replace(
                    e,
                    chapter=nc,
                    consumed_at_chapter=ncon,
                    suggested_resolve_chapter=nsug,
                    resolve_chapter_window=nwin,
                )
                new_entries.append(ne)
            except (ValueError, TypeError) as ex:
                logger.warning(
                    "潜台词条目 %s 章号重映射失败，保留原条目: %s",
                    getattr(e, "id", "?"),
                    ex,
                )
                new_entries.append(e)

        self._subtext_entries.clear()
        self._subtext_entries.extend(new_entries)

