"""时间工具 — 统一时区感知的 UTC 时间戳。

所有模块使用 `utcnow_iso()` 代替已弃用的 `datetime.utcnow()`，
确保 Python 3.12+ 不触发 DeprecationWarning。
"""
from datetime import datetime, timezone


def utcnow_iso() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串（无时区后缀，与历史格式兼容）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def utcnow() -> datetime:
    """返回当前 UTC 时区感知 datetime 对象。"""
    return datetime.now(timezone.utc)
