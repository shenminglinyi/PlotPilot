"""ChunkedBufferScanner — Layer 6: 分块缓冲验证扫描器。

核心机制：
- 将流式输出分为多个 chunk（如每 200 字一块）
- 对每个 chunk 进行 AC 扫描
- 检测到问题时，只回滚当前 chunk + 重新生成
- 降低回滚重生成的算力损耗

相比全章节回滚：
- 回滚量从整章 → 单个 chunk（~200字）
- 算力节省 80%+
- 用户体验更流畅
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from application.engine.rules.stream_ac_scanner import StreamACScanner, StreamScanResult

logger = logging.getLogger(__name__)


@dataclass
class ChunkResult:
    """单个 chunk 的扫描结果。"""
    chunk_index: int
    text: str
    scan_results: List[StreamScanResult] = field(default_factory=list)
    needs_rollback: bool = False
    rollback_reason: str = ""


class ChunkedBufferScanner:
    """分块缓冲验证扫描器。"""

    def __init__(
        self,
        chunk_size: int = 200,
        max_rollback_attempts: int = 3,
        scanner: Optional[StreamACScanner] = None,
    ):
        """
        Args:
            chunk_size: 每个 chunk 的字符数
            max_rollback_attempts: 单个 chunk 最大回滚重试次数
            scanner: AC 扫描器实例
        """
        self._chunk_size = chunk_size
        self._max_rollback_attempts = max_rollback_attempts
        self._scanner = scanner or StreamACScanner()
        self._chunks: List[str] = []
        self._results: List[ChunkResult] = []
        self._current_buffer: str = ""
        self._total_offset: int = 0

    def reset(self) -> None:
        """重置扫描器状态。"""
        self._chunks = []
        self._results = []
        self._current_buffer = ""
        self._total_offset = 0

    def append_text(self, text: str) -> Optional[ChunkResult]:
        """追加文本到缓冲区。

        当缓冲区积累到 chunk_size 时触发扫描。

        Args:
            text: 新到达的文本

        Returns:
            如果触发了 chunk 扫描则返回 ChunkResult，否则返回 None
        """
        self._current_buffer += text

        if len(self._current_buffer) >= self._chunk_size:
            return self._flush_chunk()

        return None

    def flush_remaining(self) -> Optional[ChunkResult]:
        """强制刷新剩余缓冲区。"""
        if self._current_buffer:
            return self._flush_chunk()
        return None

    def _flush_chunk(self) -> ChunkResult:
        """刷新当前缓冲区为一个 chunk 并扫描。"""
        chunk_text = self._current_buffer
        chunk_index = len(self._chunks)

        # 扫描
        scan_results = self._scanner.scan_chunk(chunk_text, self._total_offset)

        # 判断是否需要回滚
        needs_rollback = self._scanner.should_interrupt(scan_results)
        rollback_reason = ""
        if needs_rollback:
            critical_hits = [r for r in scan_results if r.severity == "critical"]
            if critical_hits:
                rollback_reason = f"检测到 {len(critical_hits)} 处严重AI味模式"
            else:
                rollback_reason = "检测到同类模式过多"

        # 记录
        self._chunks.append(chunk_text)
        self._total_offset += len(chunk_text)
        self._current_buffer = ""

        result = ChunkResult(
            chunk_index=chunk_index,
            text=chunk_text,
            scan_results=scan_results,
            needs_rollback=needs_rollback,
            rollback_reason=rollback_reason,
        )
        self._results.append(result)

        if needs_rollback:
            logger.warning(
                "ChunkedBufferScanner: chunk %d 需要回滚 — %s",
                chunk_index, rollback_reason,
            )

        return result

    def get_rollback_text(self, chunk_index: int) -> str:
        """获取指定 chunk 之前的所有文本（回滚后保留的部分）。"""
        return "".join(self._chunks[:chunk_index])

    @property
    def all_results(self) -> List[ChunkResult]:
        """获取所有扫描结果。"""
        return self._results

    @property
    def total_text(self) -> str:
        """获取所有已确认的文本。"""
        return "".join(self._chunks)

    @property
    def stats(self) -> Dict[str, Any]:
        """获取扫描统计。"""
        total_hits = sum(len(r.scan_results) for r in self._results)
        total_rollbacks = sum(1 for r in self._results if r.needs_rollback)
        return {
            "total_chunks": len(self._chunks),
            "total_chars": self._total_offset,
            "total_hits": total_hits,
            "total_rollbacks": total_rollbacks,
        }
