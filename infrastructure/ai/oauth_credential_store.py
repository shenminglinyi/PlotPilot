"""Atomic 0600 credential store and ephemeral flow state for LLM OAuth sessions.

OAuth access_token / refresh_token values are persisted ONLY in a kernel-local
0600 JSON file (never in SQLite llm_profiles and never in HTTP responses).
Pending PKCE and RFC 8628 Device Flow states live strictly in memory under an
RLock with automatic TTL eviction, single-flight polling slot reservation, and
strict single-use state consumption.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import tempfile
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Literal

from application.paths import resolve_runtime_data_path

logger = logging.getLogger(__name__)

OAuthProviderKey = Literal["openrouter", "github_models", "google_gemini"]
RefreshSlotAcquireState = Literal["leader", "follower", "stale"]
DevicePollAcquireState = Literal["acquired", "rate_limited", "in_flight", "expired"]
DevicePollOutcome = Literal[
    "pending",
    "slow_down",
    "timeout",
    "transient_error",
    "terminal",
]

VALID_OAUTH_PROVIDERS: tuple[OAuthProviderKey, ...] = (
    "openrouter",
    "github_models",
    "google_gemini",
)

MAX_PENDING_FLOWS = 32
DEFAULT_PKCE_TTL_SECONDS = 600


class OAuthFlowError(RuntimeError):
    """Base error for OAuth PKCE / Device Flow state or protocol violations."""


class OAuthStateError(OAuthFlowError):
    """Raised when an OAuth PKCE state is missing, mismatched, expired, or replayed."""


def generate_pkce_verifier() -> str:
    """Generate a CSPRNG RFC 7636 PKCE code_verifier (64 URL-safe ASCII chars)."""
    return secrets.token_urlsafe(48)


def compute_pkce_s256_challenge(code_verifier: str) -> str:
    """Compute RFC 7636 S256 code_challenge = BASE64URL-ENCODE(SHA256(ASCII(verifier)))."""
    if not code_verifier or not (43 <= len(code_verifier) <= 128):
        raise ValueError("PKCE code_verifier length must be between 43 and 128 characters")
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


@dataclass(frozen=True)
class OAuthSessionRecord:
    """Persisted server-side OAuth session record with monotonic generation."""

    session_id: str
    provider: OAuthProviderKey
    access_token: str
    refresh_token: str = ""
    token_type: str = "Bearer"
    expires_at: float | None = None
    scope: str = ""
    account_label: str = ""
    client_id: str = ""
    client_secret: str = ""
    connected_at: float = 0.0
    updated_at: float = 0.0
    generation: int = 1

    def is_expired(self, *, skew_seconds: float = 60.0, now: float | None = None) -> bool:
        if self.expires_at is None:
            return False
        current = time.time() if now is None else now
        return current >= (self.expires_at - skew_seconds)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "provider": self.provider,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_type": self.token_type,
            "expires_at": self.expires_at,
            "scope": self.scope,
            "account_label": self.account_label,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "connected_at": self.connected_at,
            "updated_at": self.updated_at,
            "generation": self.generation,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "OAuthSessionRecord":
        raw_provider = str(payload.get("provider") or "").strip()
        if raw_provider not in VALID_OAUTH_PROVIDERS:
            raise ValueError(f"Unsupported OAuth provider in store: {raw_provider!r}")
        raw_expires = payload.get("expires_at")
        expires_at = float(raw_expires) if raw_expires is not None else None
        raw_gen = payload.get("generation")
        generation = max(1, int(raw_gen)) if raw_gen is not None else 1
        return cls(
            session_id=str(payload.get("session_id") or raw_provider),
            provider=raw_provider,  # type: ignore[arg-type]
            access_token=str(payload.get("access_token") or ""),
            refresh_token=str(payload.get("refresh_token") or ""),
            token_type=str(payload.get("token_type") or "Bearer"),
            expires_at=expires_at,
            scope=str(payload.get("scope") or ""),
            account_label=str(payload.get("account_label") or ""),
            client_id=str(payload.get("client_id") or ""),
            client_secret=str(payload.get("client_secret") or ""),
            connected_at=float(payload.get("connected_at") or 0.0),
            updated_at=float(payload.get("updated_at") or 0.0),
            generation=generation,
        )


@dataclass
class PendingPKCEFlow:
    """In-memory single-use PKCE authorization state."""

    state: str
    provider: OAuthProviderKey
    code_verifier: str
    redirect_uri: str
    created_at: float
    expires_at: float
    client_id: str = ""
    client_secret: str = ""


@dataclass
class PendingDeviceFlow:
    """In-memory RFC 8628 Device Authorization flow state."""

    flow_id: str
    provider: OAuthProviderKey
    device_code: str
    user_code: str
    verification_uri: str
    interval: int
    next_poll_at: float
    expires_at: float
    client_id: str = ""
    created_at: float = 0.0
    poll_in_flight: bool = False


@dataclass
class RefreshSingleFlightSlot:
    """Per-session refresh single-flight coordination across sync and async callers."""

    generation: int
    done_event: threading.Event
    async_waiters: list[tuple[asyncio.AbstractEventLoop, asyncio.Future[None]]]


def _settle_waiter_future(fut: asyncio.Future[None]) -> None:
    if not fut.done():
        fut.set_result(None)


class OAuthCredentialStore:
    """Thread-safe atomic 0600 credential store + in-memory pending flow registry."""

    def __init__(
        self,
        path: Path | str | None = None,
        *,
        time_fn: Callable[[], float] = time.time,
    ) -> None:
        self.path: Path = (
            Path(path)
            if path is not None
            else resolve_runtime_data_path("data/llm-oauth-sessions.json")
        )
        self._lock = threading.RLock()
        self._refresh_coord_lock = threading.Lock()
        self._time_fn = time_fn
        self._loaded = False
        self._sessions: dict[str, OAuthSessionRecord] = {}
        self._generations: dict[str, int] = {}
        self._inflight_refreshes: dict[str, RefreshSingleFlightSlot] = {}
        self._pkce_flows: list[PendingPKCEFlow] = []
        self._device_flows: dict[str, PendingDeviceFlow] = {}

    def _ensure_loaded_locked(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        self._sessions = {}
        self._generations = {}
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                raw_gens = raw.get("generations")
                if isinstance(raw_gens, dict):
                    for gkey, gval in raw_gens.items():
                        try:
                            self._generations[str(gkey)] = max(0, int(gval))
                        except (TypeError, ValueError):
                            continue

                raw_sessions = raw.get("sessions")
                if isinstance(raw_sessions, dict):
                    for key, entry in raw_sessions.items():
                        if not isinstance(entry, dict):
                            continue
                        try:
                            record = OAuthSessionRecord.from_dict(entry)
                            if record.access_token:
                                skey = str(key)
                                eff_gen = max(
                                    self._generations.get(skey, 0),
                                    record.generation,
                                )
                                self._generations[skey] = eff_gen
                                self._sessions[skey] = replace(record, generation=eff_gen)
                        except ValueError as exc:
                            logger.warning(
                                "Skipping invalid OAuth session record %s: %s", key, exc
                            )
        except (OSError, ValueError) as exc:
            logger.warning("Failed to load OAuth credential store %s: %s", self.path, exc)
            self._sessions = {}
            self._generations = {}

    def _persist_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "generations": dict(self._generations),
            "sessions": {
                sid: record.to_dict() for sid, record in self._sessions.items()
            },
        }
        fd, tmp_name = tempfile.mkstemp(
            prefix=".llm-oauth-",
            suffix=".tmp",
            dir=str(self.path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            try:
                os.chmod(tmp_name, 0o600)
            except OSError:
                pass
            os.replace(tmp_name, str(self.path))
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
        finally:
            if os.path.exists(tmp_name):
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass

    def reload(self) -> None:
        with self._lock:
            self._loaded = False
            self._ensure_loaded_locked()

    def get_session(self, session_id: str) -> OAuthSessionRecord | None:
        key = (session_id or "").strip()
        if not key:
            return None
        with self._lock:
            self._ensure_loaded_locked()
            return self._sessions.get(key)

    def list_sessions(self) -> dict[str, OAuthSessionRecord]:
        with self._lock:
            self._ensure_loaded_locked()
            return dict(self._sessions)

    @staticmethod
    def _notify_async_waiters(
        waiters: list[tuple[asyncio.AbstractEventLoop, asyncio.Future[None]]],
    ) -> None:
        for w_loop, w_fut in waiters:
            try:
                w_loop.call_soon_threadsafe(_settle_waiter_future, w_fut)
            except RuntimeError:
                pass

    def _pop_superseded_refresh_slot_locked(
        self,
        session_id: str,
        *,
        active_generation: int | None,
    ) -> list[tuple[asyncio.AbstractEventLoop, asyncio.Future[None]]]:
        """Invalidate any inflight refresh slot superseded by a session save/CAS/delete.

        Must be called while holding ``self._lock`` (lock order: ``_lock`` -> ``_refresh_coord_lock``).
        Never removes a slot already matching ``active_generation``.
        """
        key = (session_id or "").strip()
        if not key:
            return []
        with self._refresh_coord_lock:
            slot = self._inflight_refreshes.get(key)
            if slot is None:
                return []
            if active_generation is not None and slot.generation == active_generation:
                return []
            self._inflight_refreshes.pop(key, None)
            slot.done_event.set()
            waiters = list(slot.async_waiters)
            slot.async_waiters.clear()
            return waiters

    def acquire_refresh_slot_sync(
        self, session_id: str, generation: int
    ) -> tuple[RefreshSlotAcquireState, RefreshSingleFlightSlot | None]:
        """Atomically validate ``generation`` against the current session and claim/join a slot."""
        key = (session_id or "").strip()
        if not key:
            return ("stale", None)
        with self._lock:
            self._ensure_loaded_locked()
            current = self._sessions.get(key)
            if (
                current is None
                or not current.access_token.strip()
                or current.generation != generation
            ):
                return ("stale", None)
            with self._refresh_coord_lock:
                existing = self._inflight_refreshes.get(key)
                if (
                    existing is not None
                    and existing.generation == generation
                    and not existing.done_event.is_set()
                ):
                    return ("follower", existing)
                slot = RefreshSingleFlightSlot(
                    generation=generation,
                    done_event=threading.Event(),
                    async_waiters=[],
                )
                self._inflight_refreshes[key] = slot
                return ("leader", slot)

    def acquire_refresh_slot_async(
        self,
        session_id: str,
        generation: int,
        loop: asyncio.AbstractEventLoop,
    ) -> tuple[
        RefreshSlotAcquireState,
        RefreshSingleFlightSlot | None,
        asyncio.Future[None] | None,
    ]:
        """Atomically validate ``generation`` and claim/join an async refresh single-flight slot."""
        key = (session_id or "").strip()
        if not key:
            return ("stale", None, None)
        with self._lock:
            self._ensure_loaded_locked()
            current = self._sessions.get(key)
            if (
                current is None
                or not current.access_token.strip()
                or current.generation != generation
            ):
                return ("stale", None, None)
            with self._refresh_coord_lock:
                existing = self._inflight_refreshes.get(key)
                if (
                    existing is not None
                    and existing.generation == generation
                    and not existing.done_event.is_set()
                ):
                    fut: asyncio.Future[None] = loop.create_future()
                    existing.async_waiters.append((loop, fut))
                    return ("follower", existing, fut)
                slot = RefreshSingleFlightSlot(
                    generation=generation,
                    done_event=threading.Event(),
                    async_waiters=[],
                )
                self._inflight_refreshes[key] = slot
                return ("leader", slot, None)

    def release_refresh_slot(self, session_id: str, slot: RefreshSingleFlightSlot) -> None:
        key = (session_id or "").strip()
        with self._refresh_coord_lock:
            if self._inflight_refreshes.get(key) is slot:
                self._inflight_refreshes.pop(key, None)
            slot.done_event.set()
            waiters = list(slot.async_waiters)
            slot.async_waiters.clear()
        self._notify_async_waiters(waiters)

    def save_session(self, record: OAuthSessionRecord) -> OAuthSessionRecord:
        if not record.access_token.strip():
            raise ValueError("OAuth access_token cannot be empty")
        with self._lock:
            self._ensure_loaded_locked()
            next_gen = self._generations.get(record.session_id, 0) + 1
            self._generations[record.session_id] = next_gen
            stored = replace(record, generation=next_gen)
            self._sessions[record.session_id] = stored
            self._persist_locked()
            waiters = self._pop_superseded_refresh_slot_locked(
                record.session_id,
                active_generation=next_gen,
            )
        self._notify_async_waiters(waiters)
        return stored

    def compare_and_swap_session(
        self,
        *,
        session_id: str,
        expected_generation: int,
        expected_refresh_token: str,
        updated_record: OAuthSessionRecord,
    ) -> OAuthSessionRecord | None:
        """Atomically persist a refreshed session iff it has not been deleted or replaced."""
        key = (session_id or "").strip()
        if not key or not updated_record.access_token.strip():
            return None
        waiters: list[tuple[asyncio.AbstractEventLoop, asyncio.Future[None]]] = []
        committed: OAuthSessionRecord | None = None
        with self._lock:
            self._ensure_loaded_locked()
            current = self._sessions.get(key)
            if current is None:
                return None
            if (
                current.generation != expected_generation
                or current.refresh_token != expected_refresh_token
            ):
                return None
            next_gen = max(self._generations.get(key, current.generation), current.generation) + 1
            self._generations[key] = next_gen
            committed = replace(updated_record, session_id=key, generation=next_gen)
            self._sessions[key] = committed
            self._persist_locked()
            waiters = self._pop_superseded_refresh_slot_locked(
                key,
                active_generation=next_gen,
            )
        self._notify_async_waiters(waiters)
        return committed

    def delete_session(self, session_id: str) -> bool:
        key = (session_id or "").strip()
        if not key:
            return False
        with self._lock:
            self._ensure_loaded_locked()
            self._generations[key] = self._generations.get(key, 0) + 1
            removed = self._sessions.pop(key, None) is not None
            if removed or self.path.exists():
                self._persist_locked()
            waiters = self._pop_superseded_refresh_slot_locked(
                key,
                active_generation=None,
            )
        self._notify_async_waiters(waiters)
        return removed

    # ── Ephemeral PKCE & Device Flow States ──────────────────────────────

    def _evict_expired_locked(self, now: float) -> None:
        self._pkce_flows = [f for f in self._pkce_flows if now < f.expires_at]
        if len(self._pkce_flows) > MAX_PENDING_FLOWS:
            self._pkce_flows.sort(key=lambda item: item.created_at)
            self._pkce_flows = self._pkce_flows[-MAX_PENDING_FLOWS:]

        expired_device_ids = [
            fid for fid, flow in self._device_flows.items() if now >= flow.expires_at
        ]
        for fid in expired_device_ids:
            self._device_flows.pop(fid, None)
        if len(self._device_flows) > MAX_PENDING_FLOWS:
            ordered = sorted(
                self._device_flows.values(),
                key=lambda item: item.created_at,
            )
            for stale in ordered[: len(self._device_flows) - MAX_PENDING_FLOWS]:
                self._device_flows.pop(stale.flow_id, None)

    def create_pkce_flow(
        self,
        provider: OAuthProviderKey,
        redirect_uri: str,
        *,
        ttl_seconds: int = DEFAULT_PKCE_TTL_SECONDS,
        client_id: str = "",
        client_secret: str = "",
    ) -> PendingPKCEFlow:
        if provider not in VALID_OAUTH_PROVIDERS:
            raise OAuthFlowError(f"Unsupported OAuth provider: {provider}")
        now = self._time_fn()
        flow = PendingPKCEFlow(
            state=secrets.token_urlsafe(32),
            provider=provider,
            code_verifier=generate_pkce_verifier(),
            redirect_uri=redirect_uri,
            created_at=now,
            expires_at=now + max(30, int(ttl_seconds)),
            client_id=client_id,
            client_secret=client_secret,
        )
        with self._lock:
            self._evict_expired_locked(now)
            self._pkce_flows.append(flow)
            if len(self._pkce_flows) > MAX_PENDING_FLOWS:
                self._pkce_flows = self._pkce_flows[-MAX_PENDING_FLOWS:]
        return flow

    def consume_pkce_state(self, provider: str, state: str) -> PendingPKCEFlow:
        candidate = (state or "").strip()
        if not candidate:
            raise OAuthStateError("缺少 OAuth state 参数，已拒绝回调请求")
        now = self._time_fn()
        candidate_bytes = candidate.encode("utf-8")

        with self._lock:
            matched: PendingPKCEFlow | None = None
            remaining: list[PendingPKCEFlow] = []
            for entry in self._pkce_flows:
                if (
                    matched is None
                    and entry.provider == provider
                    and hmac.compare_digest(entry.state.encode("utf-8"), candidate_bytes)
                ):
                    matched = entry
                    continue
                if now < entry.expires_at:
                    remaining.append(entry)
            self._pkce_flows = remaining

            if matched is None:
                raise OAuthStateError("OAuth state 无效或已被使用，请重新发起授权")
            if now >= matched.expires_at:
                raise OAuthStateError("OAuth 授权会话已过期，请重新发起授权")
            return matched

    def create_device_flow(
        self,
        *,
        provider: OAuthProviderKey,
        device_code: str,
        user_code: str,
        verification_uri: str,
        expires_in: int = 900,
        interval: int = 5,
        client_id: str = "",
    ) -> PendingDeviceFlow:
        now = self._time_fn()
        eff_interval = max(1, int(interval or 5))
        flow = PendingDeviceFlow(
            flow_id=secrets.token_urlsafe(24),
            provider=provider,
            device_code=device_code,
            user_code=user_code,
            verification_uri=verification_uri,
            interval=eff_interval,
            next_poll_at=now + eff_interval,
            expires_at=now + max(30, int(expires_in or 900)),
            client_id=client_id,
            created_at=now,
            poll_in_flight=False,
        )
        with self._lock:
            self._evict_expired_locked(now)
            self._device_flows[flow.flow_id] = flow
            if len(self._device_flows) > MAX_PENDING_FLOWS:
                self._evict_expired_locked(now)
        return replace(flow)

    def get_device_flow(self, flow_id: str) -> PendingDeviceFlow | None:
        fid = (flow_id or "").strip()
        if not fid:
            return None
        with self._lock:
            flow = self._device_flows.get(fid)
            return replace(flow) if flow is not None else None

    def begin_device_flow_poll(
        self, flow_id: str
    ) -> tuple[DevicePollAcquireState, PendingDeviceFlow | None]:
        """Atomically check expiry, interval, and single-flight lock before polling upstream."""
        fid = (flow_id or "").strip()
        if not fid:
            return ("expired", None)
        now = self._time_fn()
        with self._lock:
            flow = self._device_flows.get(fid)
            if flow is None:
                return ("expired", None)
            if now >= flow.expires_at:
                self._device_flows.pop(fid, None)
                return ("expired", replace(flow))
            if flow.poll_in_flight:
                return ("in_flight", replace(flow))
            if now < flow.next_poll_at:
                return ("rate_limited", replace(flow))
            flow.poll_in_flight = True
            flow.next_poll_at = now + flow.interval
            return ("acquired", replace(flow))

    def complete_device_flow_poll(
        self,
        flow_id: str,
        *,
        outcome: DevicePollOutcome,
        upstream_interval: int | None = None,
    ) -> PendingDeviceFlow | None:
        """Release the in-flight poll slot and apply RFC 8628 interval / backoff updates."""
        fid = (flow_id or "").strip()
        if not fid:
            return None
        now = self._time_fn()
        with self._lock:
            flow = self._device_flows.get(fid)
            if flow is None:
                return None
            if outcome == "terminal":
                self._device_flows.pop(fid, None)
                return None

            flow.poll_in_flight = False
            if outcome == "slow_down":
                bumped = flow.interval + 5
                if upstream_interval is not None and int(upstream_interval) > bumped:
                    bumped = int(upstream_interval)
                flow.interval = bumped
            elif outcome == "timeout":
                bumped = max(flow.interval + 5, min(flow.interval * 2, 120))
                if upstream_interval is not None and int(upstream_interval) > bumped:
                    bumped = int(upstream_interval)
                flow.interval = bumped
            elif upstream_interval is not None and int(upstream_interval) > flow.interval:
                flow.interval = int(upstream_interval)

            flow.next_poll_at = max(flow.next_poll_at, now + flow.interval)
            return replace(flow)

    def mark_device_flow_polled(
        self,
        flow_id: str,
        *,
        slow_down: bool = False,
        upstream_interval: int | None = None,
    ) -> PendingDeviceFlow | None:
        return self.complete_device_flow_poll(
            flow_id,
            outcome="slow_down" if slow_down else "pending",
            upstream_interval=upstream_interval,
        )

    def delete_device_flow(self, flow_id: str) -> bool:
        fid = (flow_id or "").strip()
        if not fid:
            return False
        with self._lock:
            return self._device_flows.pop(fid, None) is not None

    def now(self) -> float:
        return self._time_fn()


_default_store_lock = threading.Lock()
_default_oauth_credential_store: OAuthCredentialStore | None = None


def get_oauth_credential_store() -> OAuthCredentialStore:
    global _default_oauth_credential_store
    if _default_oauth_credential_store is None:
        with _default_store_lock:
            if _default_oauth_credential_store is None:
                _default_oauth_credential_store = OAuthCredentialStore()
    return _default_oauth_credential_store
