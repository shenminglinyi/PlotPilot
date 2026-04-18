"""全托管守护进程日志环：供 SSE 按书目推送真实日志行（非轮询摘要）。

线程安全；与 FileHandler 并存，不向根 logger 重复传播。
"""

from __future__ import annotations

import logging
import re
import threading
import traceback
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

_NOVEL_ID_IN_BRACKETS = re.compile(r"\[(novel-[a-zA-Z0-9]+)\]")
_NOVEL_ID_LOOSE = re.compile(r"(novel-[a-zA-Z0-9]+)")

_MAX_ENTRIES = 4000

_ring: Deque["AutopilotLogEntry"] = deque(maxlen=_MAX_ENTRIES)
_lock = threading.Lock()
_seq = 0

_handler_installed = False
_handler_lock = threading.Lock()


@dataclass(frozen=True)
class AutopilotLogEntry:
    seq: int
    timestamp_iso: str
    level: str
    message: str
    logger_name: str
    novel_id: Optional[str]


def _extract_novel_id(message: str) -> Optional[str]:
    if not message:
        return None
    m = _NOVEL_ID_IN_BRACKETS.search(message)
    if m:
        return m.group(1)
    m2 = _NOVEL_ID_LOOSE.search(message)
    if m2:
        return m2.group(1)
    return None


def _matches_novel(entry: AutopilotLogEntry, novel_id: str) -> bool:
    if entry.novel_id and entry.novel_id == novel_id:
        return True
    return novel_id in (entry.message or "")


def should_skip_autopilot_log_line(
    level: str,
    message: str,
    logger_name: str = "",
) -> bool:
    """过滤 StreamingBus 等高频 DEBUG，避免 SSE/终端刷屏。"""
    msg = message or ""
    ln = (logger_name or "").lower()
    if "streaming_bus" in ln and (level or "").upper() == "DEBUG":
        return True
    if "[StreamingBus]" in msg and "publish:" in msg:
        return True
    if "[DEBUG]" in msg and "streaming_bus" in msg.lower():
        return True
    return False


def should_skip_raw_log_file_line(line: str) -> bool:
    """文件 tail 单行过滤（无独立 logger 字段）。"""
    if "[StreamingBus]" in line and "publish:" in line:
        return True
    if "[DEBUG]" in line and "streaming_bus" in line.lower():
        return True
    return False


def shorten_log_message(text: str, max_chars: int = 88) -> str:
    """SSE / 终端展示固定上限，减轻 payload 与 DOM。"""
    t = (text or "").replace("\r\n", "\n").strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


def allocate_seq() -> int:
    """跨内存环与文件 tail 的全局单调序号（SSE 去重 / 重连）。"""
    global _seq
    with _lock:
        _seq += 1
        return _seq


def initial_snapshot_offset(log_path: str, max_bytes: int = 65536) -> int:
    """首次连接时从文件末尾附近开始读，避免整文件过大。"""
    path = Path(log_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        return 0
    size = path.stat().st_size
    return max(0, size - max_bytes)


def file_end_offset(log_path: str) -> int:
    """重连时从文件末尾起只读新追加字节（不重复历史 tail）。"""
    path = Path(log_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        return 0
    return path.stat().st_size


def read_incremental_log_file_lines(
    log_path: str,
    novel_id: str,
    cursor: int,
) -> Tuple[List[Dict], int]:
    """从独立进程写入的 LOG_FILE 增量 tail；行含 novel_id 时推送。

    返回 (行列表, 新字节偏移)。cursor 为上次读到的文件末尾位置。
    """
    path = Path(log_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        return [], cursor
    size = path.stat().st_size
    if cursor > size:
        cursor = 0
    with path.open("rb") as f:
        f.seek(cursor)
        raw = f.read()
        new_cursor = f.tell()
    if not raw:
        return [], new_cursor
    if cursor > 0 and b"\n" in raw:
        first_nl = raw.find(b"\n")
        raw = raw[first_nl + 1 :]
    text = raw.decode("utf-8", errors="replace")
    lines_out: List[Dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or novel_id not in line:
            continue
        if should_skip_raw_log_file_line(line):
            continue
        lines_out.append(
            {
                "seq": allocate_seq(),
                "message": shorten_log_message(line),
                "timestamp": datetime.now().isoformat(),
                "level": "INFO",
                "logger": "file",
            }
        )
    return lines_out, new_cursor


def append_log_line(level: str, message: str, logger_name: str, timestamp_iso: str) -> None:
    """由 Handler 调用：写入全局环。"""
    if should_skip_autopilot_log_line(level, message, logger_name):
        return
    global _seq
    novel_id = _extract_novel_id(message)
    with _lock:
        _seq += 1
        seq = _seq
        _ring.append(
            AutopilotLogEntry(
                seq=seq,
                timestamp_iso=timestamp_iso,
                level=level,
                message=message,
                logger_name=logger_name,
                novel_id=novel_id,
            )
        )


def iter_new_for_novel(novel_id: str, after_seq: int, limit: int = 500) -> List[AutopilotLogEntry]:
    """返回 seq > after_seq 且与本书相关的日志行（时间顺序）。"""
    out: List[AutopilotLogEntry] = []
    with _lock:
        for e in _ring:
            if e.seq <= after_seq:
                continue
            if should_skip_autopilot_log_line(e.level, e.message, e.logger_name):
                continue
            if _matches_novel(e, novel_id):
                out.append(e)
                if len(out) >= limit:
                    break
    return out


def snapshot_for_novel(novel_id: str, limit: int = 400) -> List[AutopilotLogEntry]:
    """初次连接：返回本书最近若干条（用于冷启动即有上下文）。"""
    out: List[AutopilotLogEntry] = []
    with _lock:
        for e in reversed(_ring):
            if should_skip_autopilot_log_line(e.level, e.message, e.logger_name):
                continue
            if _matches_novel(e, novel_id):
                out.append(e)
                if len(out) >= limit:
                    break
    out.reverse()
    return out


class AutopilotRingLogHandler(logging.Handler):
    """将指定 logger 的日志写入内存环。"""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
            if record.exc_info:
                msg = msg + "\n" + "".join(traceback.format_exception(*record.exc_info))
            ts = datetime.fromtimestamp(record.created).isoformat()
            append_log_line(record.levelname, msg, record.name, ts)
        except Exception:
            self.handleError(record)


def install_autopilot_log_ring_handler() -> None:
    """将环写入 Handler 挂到守护进程与自动驾驶 API logger（幂等）。"""
    global _handler_installed
    with _handler_lock:
        if _handler_installed:
            return
        h = AutopilotRingLogHandler()
        names = (
            "application.engine.services.autopilot_daemon",
            "interfaces.api.v1.engine.autopilot_routes",
        )
        for name in names:
            lg = logging.getLogger(name)
            if not any(isinstance(x, AutopilotRingLogHandler) for x in lg.handlers):
                lg.addHandler(h)
        _handler_installed = True
