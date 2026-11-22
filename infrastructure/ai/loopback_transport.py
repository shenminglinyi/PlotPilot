"""Connection-time loopback-only HTTP/HTTPS transport & DNS-rebinding defense.

Guarantees:
1. Every TCP connection opened through LoopbackOnlyAsyncTransport / LoopbackOnlySyncTransport
   connects strictly to a validated numeric loopback IP literal (e.g. 127.0.0.1 or ::1) on an
   allowed port (1024..65535, excluding PlotPilot's own backend port 8005).
2. When pinned_ips are bound from URL validation (e.g. LocalGatewayProbeService), connect_tcp
   uses those exact validated numeric loopback IPs and NEVER performs a second DNS lookup.
3. For long-lived saved local_gateway profiles (including https://localhost:PORT), every new
   connection resolves localhost through resolve_loopback_host_ips, rejects the connection
   before TCP SYN if ANY returned record is non-loopback, connects TCP to the numeric loopback
   IP literal, and preserves httpcore's TLS server_hostname='localhost' SNI/cert verification.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
import ssl
from typing import Any, Callable, Iterable, Optional, Sequence, Tuple, Union

import httpcore
import httpx

ALLOWED_LOOPBACK_HOSTNAMES: frozenset[str] = frozenset({"127.0.0.1", "::1", "localhost"})
DEFAULT_BLOCKED_PORTS: frozenset[int] = frozenset({8005})

LoopbackDnsResolver = Callable[[str, int], Sequence[Any]]


def _default_dns_resolver(host: str, port: int) -> Sequence[Any]:
    return socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)


def assert_strict_loopback_ip(raw_ip: str) -> str:
    """Validate that raw_ip is a strict numeric loopback address (blocking mapped/unspecified)."""
    candidate = (raw_ip or "").strip()
    if "%" in candidate:
        raise ValueError("不允许包含 IPv6 作用域标识的本地网关地址")
    try:
        addr = ipaddress.ip_address(candidate)
    except ValueError as exc:
        raise ValueError("无效的本地回环 IP 地址") from exc

    mapped = getattr(addr, "ipv4_mapped", None)
    targets = (addr, mapped) if mapped is not None else (addr,)
    for item in targets:
        if (
            not item.is_loopback
            or item.is_unspecified
            or item.is_multicast
            or item.is_link_local
        ):
            raise ValueError("localhost 解析到了非回环地址，已拒绝连接")
    return str(addr)


def resolve_loopback_host_ips(
    hostname: str,
    port: int,
    *,
    resolver: Optional[LoopbackDnsResolver] = None,
) -> Tuple[str, ...]:
    """Resolve a loopback hostname and verify EVERY returned address is strict loopback."""
    clean_host = (hostname or "").strip().strip("[]").lower()
    if clean_host not in ALLOWED_LOOPBACK_HOSTNAMES:
        raise ValueError(
            "本地订阅网关仅允许回环地址（127.0.0.1、::1 或 localhost），拒绝访问局域网或公网地址"
        )

    if clean_host != "localhost":
        return (assert_strict_loopback_ip(clean_host),)

    dns_fn = resolver or _default_dns_resolver
    try:
        addr_infos = dns_fn(clean_host, port)
    except OSError as exc:
        raise ValueError("无法解析 localhost 回环地址") from exc

    if not addr_infos:
        raise ValueError("无法解析 localhost 回环地址")

    v4_ips: list[str] = []
    v6_ips: list[str] = []
    seen: set[str] = set()
    for info in addr_infos:
        sockaddr = info[4]
        raw_addr = str(sockaddr[0])
        validated = assert_strict_loopback_ip(raw_addr)
        if validated in seen:
            continue
        seen.add(validated)
        if ":" in validated:
            v6_ips.append(validated)
        else:
            v4_ips.append(validated)

    ordered = tuple(v4_ips + v6_ips)
    if not ordered:
        raise ValueError("无法解析 localhost 回环地址")
    return ordered


def _validate_connect_port(
    port: int,
    *,
    blocked_ports: frozenset[int],
    allowed_port: Optional[int],
) -> None:
    if not (1024 <= int(port) <= 65535):
        raise httpcore.ConnectError("本地网关端口超出 1024..65535 安全范围")
    if int(port) in blocked_ports:
        raise httpcore.ConnectError(f"端口 {port} 为系统保留端口，已阻断连接")
    if allowed_port is not None and int(port) != int(allowed_port):
        raise httpcore.ConnectError("本地网关实际连接端口与校验端口不一致，已阻断连接")


class LoopbackOnlyAsyncBackend(httpcore.AsyncNetworkBackend):
    """Async network backend that connects strictly to validated numeric loopback IPs."""

    def __init__(
        self,
        *,
        pinned_ips: Optional[Sequence[str]] = None,
        allowed_port: Optional[int] = None,
        blocked_ports: frozenset[int] = DEFAULT_BLOCKED_PORTS,
        resolver: Optional[LoopbackDnsResolver] = None,
        inner: Optional[httpcore.AsyncNetworkBackend] = None,
    ) -> None:
        self._inner = inner or httpcore.AnyIOBackend()
        self._pinned_ips: Optional[Tuple[str, ...]] = (
            tuple(assert_strict_loopback_ip(ip) for ip in pinned_ips)
            if pinned_ips
            else None
        )
        self._allowed_port = allowed_port
        self._blocked_ports = blocked_ports
        self._resolver = resolver

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: Optional[float] = None,
        local_address: Optional[str] = None,
        socket_options: Optional[Iterable[Any]] = None,
    ) -> httpcore.AsyncNetworkStream:
        _validate_connect_port(
            port,
            blocked_ports=self._blocked_ports,
            allowed_port=self._allowed_port,
        )
        clean_host = (host or "").strip().strip("[]").lower()
        if clean_host not in ALLOWED_LOOPBACK_HOSTNAMES:
            raise httpcore.ConnectError("拒绝向非回环主机发起本地网关连接")

        if self._pinned_ips is not None:
            candidate_ips = self._pinned_ips
        elif clean_host != "localhost":
            try:
                candidate_ips = (assert_strict_loopback_ip(clean_host),)
            except ValueError as exc:
                raise httpcore.ConnectError(str(exc)) from exc
        else:
            try:
                candidate_ips = await asyncio.to_thread(
                    resolve_loopback_host_ips,
                    clean_host,
                    port,
                    resolver=self._resolver,
                )
            except ValueError as exc:
                raise httpcore.ConnectError(str(exc)) from exc

        last_exc: Optional[ BaseException ] = None
        for numeric_ip in candidate_ips:
            try:
                checked_ip = assert_strict_loopback_ip(numeric_ip)
            except ValueError as exc:
                raise httpcore.ConnectError(str(exc)) from exc
            try:
                return await self._inner.connect_tcp(
                    host=checked_ip,
                    port=port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except Exception as exc:
                last_exc = exc

        if last_exc is not None:
            raise last_exc
        raise httpcore.ConnectError("无可用回环地址")

    async def connect_unix_socket(
        self,
        path: str,
        timeout: Optional[float] = None,
        socket_options: Optional[Iterable[Any]] = None,
    ) -> httpcore.AsyncNetworkStream:
        raise httpcore.ConnectError("本地回环网关传输层禁止 Unix Socket 连接")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class LoopbackOnlySyncBackend(httpcore.NetworkBackend):
    """Sync network backend that connects strictly to validated numeric loopback IPs."""

    def __init__(
        self,
        *,
        pinned_ips: Optional[Sequence[str]] = None,
        allowed_port: Optional[int] = None,
        blocked_ports: frozenset[int] = DEFAULT_BLOCKED_PORTS,
        resolver: Optional[LoopbackDnsResolver] = None,
        inner: Optional[httpcore.NetworkBackend] = None,
    ) -> None:
        self._inner = inner or httpcore.SyncBackend()
        self._pinned_ips: Optional[Tuple[str, ...]] = (
            tuple(assert_strict_loopback_ip(ip) for ip in pinned_ips)
            if pinned_ips
            else None
        )
        self._allowed_port = allowed_port
        self._blocked_ports = blocked_ports
        self._resolver = resolver

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: Optional[float] = None,
        local_address: Optional[str] = None,
        socket_options: Optional[Iterable[Any]] = None,
    ) -> httpcore.NetworkStream:
        _validate_connect_port(
            port,
            blocked_ports=self._blocked_ports,
            allowed_port=self._allowed_port,
        )
        clean_host = (host or "").strip().strip("[]").lower()
        if clean_host not in ALLOWED_LOOPBACK_HOSTNAMES:
            raise httpcore.ConnectError("拒绝向非回环主机发起本地网关连接")

        if self._pinned_ips is not None:
            candidate_ips = self._pinned_ips
        else:
            try:
                candidate_ips = resolve_loopback_host_ips(
                    clean_host,
                    port,
                    resolver=self._resolver,
                )
            except ValueError as exc:
                raise httpcore.ConnectError(str(exc)) from exc

        last_exc: Optional[BaseException] = None
        for numeric_ip in candidate_ips:
            try:
                checked_ip = assert_strict_loopback_ip(numeric_ip)
            except ValueError as exc:
                raise httpcore.ConnectError(str(exc)) from exc
            try:
                return self._inner.connect_tcp(
                    host=checked_ip,
                    port=port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except Exception as exc:
                last_exc = exc

        if last_exc is not None:
            raise last_exc
        raise httpcore.ConnectError("无可用回环地址")

    def connect_unix_socket(
        self,
        path: str,
        timeout: Optional[float] = None,
        socket_options: Optional[Iterable[Any]] = None,
    ) -> httpcore.NetworkStream:
        raise httpcore.ConnectError("本地回环网关传输层禁止 Unix Socket 连接")

    def sleep(self, seconds: float) -> None:
        self._inner.sleep(seconds)


class LoopbackOnlyAsyncTransport(httpx.AsyncHTTPTransport):
    """HTTPX AsyncHTTPTransport backed by LoopbackOnlyAsyncBackend."""

    def __init__(
        self,
        *,
        pinned_ips: Optional[Sequence[str]] = None,
        allowed_port: Optional[int] = None,
        blocked_ports: frozenset[int] = DEFAULT_BLOCKED_PORTS,
        resolver: Optional[LoopbackDnsResolver] = None,
        verify: Union[bool, ssl.SSLContext] = True,
        limits: httpx.Limits = httpx.Limits(max_connections=20, max_keepalive_connections=10),
    ) -> None:
        super().__init__(
            verify=verify,
            trust_env=False,
            http1=True,
            http2=False,
            limits=limits,
        )
        ssl_ctx = httpx.create_ssl_context(verify=verify, trust_env=False)
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl_ctx,
            max_connections=limits.max_connections,
            max_keepalive_connections=limits.max_keepalive_connections,
            keepalive_expiry=limits.keepalive_expiry,
            http1=True,
            http2=False,
            retries=0,
            network_backend=LoopbackOnlyAsyncBackend(
                pinned_ips=pinned_ips,
                allowed_port=allowed_port,
                blocked_ports=blocked_ports,
                resolver=resolver,
            ),
        )


class LoopbackOnlySyncTransport(httpx.HTTPTransport):
    """HTTPX HTTPTransport backed by LoopbackOnlySyncBackend."""

    def __init__(
        self,
        *,
        pinned_ips: Optional[Sequence[str]] = None,
        allowed_port: Optional[int] = None,
        blocked_ports: frozenset[int] = DEFAULT_BLOCKED_PORTS,
        resolver: Optional[LoopbackDnsResolver] = None,
        verify: Union[bool, ssl.SSLContext] = True,
        limits: httpx.Limits = httpx.Limits(max_connections=20, max_keepalive_connections=10),
    ) -> None:
        super().__init__(
            verify=verify,
            trust_env=False,
            http1=True,
            http2=False,
            limits=limits,
        )
        ssl_ctx = httpx.create_ssl_context(verify=verify, trust_env=False)
        self._pool = httpcore.ConnectionPool(
            ssl_context=ssl_ctx,
            max_connections=limits.max_connections,
            max_keepalive_connections=limits.max_keepalive_connections,
            keepalive_expiry=limits.keepalive_expiry,
            http1=True,
            http2=False,
            retries=0,
            network_backend=LoopbackOnlySyncBackend(
                pinned_ips=pinned_ips,
                allowed_port=allowed_port,
                blocked_ports=blocked_ports,
                resolver=resolver,
            ),
        )
