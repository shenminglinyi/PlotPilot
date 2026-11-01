"""Cloud session store: kernel-side persistence for the plotpilot.xyz session.

会话凭证（access_token + refresh cookie）只存在内核服务端本地文件，
浏览器全程零凭证。写入原子（tmp+rename），权限 0600。
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class CloudSession:
    access_token: str
    refresh_cookie: str
    expires_at: float = 0.0
    username: str = ""
    display_name: str = ""
    user_id: str = ""

    def to_dict(self) -> dict:
        return {
            "access_token": self.access_token,
            "refresh_cookie": self.refresh_cookie,
            "expires_at": self.expires_at,
            "username": self.username,
            "display_name": self.display_name,
            "user_id": self.user_id,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "CloudSession":
        return cls(
            access_token=str(payload.get("access_token") or ""),
            refresh_cookie=str(payload.get("refresh_cookie") or ""),
            expires_at=float(payload.get("expires_at") or 0.0),
            username=str(payload.get("username") or ""),
            display_name=str(payload.get("display_name") or ""),
            user_id=str(payload.get("user_id") or ""),
        )


@dataclass
class CloudSessionStore:
    """单运营者会话文件（结构预留 per-user key；P0 一个会话）。"""

    path: Path
    _cache: CloudSession | None = field(default=None, init=False)
    _loaded: bool = field(default=False, init=False)

    def load(self) -> CloudSession | None:
        if self._loaded:
            return self._cache
        self._loaded = True
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and payload.get("access_token"):
                self._cache = CloudSession.from_dict(payload)
        except (OSError, ValueError):
            self._cache = None
        return self._cache

    def save(self, session: CloudSession) -> None:
        # 1. 原子落盘：先写临时文件再 rename——崩溃窗口内要么旧凭证要么新凭证，
        #    不会出现半写状态（旋转场景下旧 cookie 已作废，半写=会话死亡）
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=str(self.path.parent), prefix=".cloud-session-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(session.to_dict(), handle, ensure_ascii=False, indent=2)
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, str(self.path))
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
        self._cache = session
        self._loaded = True

    def clear(self) -> None:
        self._cache = None
        self._loaded = True
        if self.path.exists():
            self.path.unlink()
