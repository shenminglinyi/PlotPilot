from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import socket
import ssl
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import httpcore
import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field

MOD_MANIFEST_MAX_BYTES = 1_048_576  # 1 MiB
MOD_MAX_WIRE_HEADER_BYTES = 65_536  # 64 KiB 原始响应头上限
MOD_FETCH_TIMEOUT_SECONDS = 10.0
MOD_FETCH_OVERALL_TIMEOUT_SECONDS = 15.0
MOD_ROUTE_OVERALL_TIMEOUT_SECONDS = 30.0
MOD_MAX_REDIRECTS = 3
DEFAULT_MANIFEST_FILENAMES: Tuple[str, ...] = (
    "plotpilot-mod.json",
    "mod.json",
    "manifest.json",
)

_SAFE_REPO_ATOM_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_ASCII_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")

DnsResolver = Callable[[str, int], Sequence[Any]]


class _WireLocationControlCharError(Exception):
    """在 HTTP 解析器剥离首尾 OWS（如 HTAB）之前，检测到原始响应头含非法控制字符。"""


class _WireHeaderGuardStream(httpcore.AsyncNetworkStream):
    """包装底层 TLS 解密字节流，在 HTTP/1.1 解析器归一化头字段空白前逐行核验原始 Location 头字节。"""

    def __init__(self, inner: httpcore.AsyncNetworkStream, *, inspect_headers: bool) -> None:
        self._inner = inner
        self._inspect_headers = inspect_headers
        self._headers_done = False
        self._expect_status_line = True
        self._status_code = 0
        self._prev_was_location = False
        self._total_header_bytes = 0
        self._header_buf = bytearray()

    def _inspect_chunk(self, data: bytes) -> None:
        if not self._inspect_headers or self._headers_done or not data:
            return

        self._header_buf.extend(data)
        while not self._headers_done:
            nl_idx = self._header_buf.find(b"\n")
            if nl_idx == -1:
                if self._total_header_bytes + len(self._header_buf) > MOD_MAX_WIRE_HEADER_BYTES:
                    raise _WireLocationControlCharError("远程模组响应头超过安全长度上限")
                break

            self._total_header_bytes += nl_idx + 1
            if self._total_header_bytes > MOD_MAX_WIRE_HEADER_BYTES:
                raise _WireLocationControlCharError("远程模组响应头超过安全长度上限")

            raw_line = bytes(self._header_buf[:nl_idx])
            del self._header_buf[: nl_idx + 1]
            if raw_line.endswith(b"\r"):
                raw_line = raw_line[:-1]

            if self._expect_status_line:
                parts = raw_line.split(b" ", 2)
                status_code = 0
                if len(parts) >= 2 and parts[1].isdigit():
                    status_code = int(parts[1])
                self._status_code = status_code
                self._expect_status_line = False
                self._prev_was_location = False
                continue

            if raw_line == b"":
                if 100 <= self._status_code < 200 and self._status_code != 101:
                    self._expect_status_line = True
                    self._status_code = 0
                    self._prev_was_location = False
                    continue
                self._headers_done = True
                self._header_buf.clear()
                break

            if raw_line[:1] in (b" ", b"\t"):
                if self._prev_was_location:
                    raise _WireLocationControlCharError("远程模组重定向路径包含非法控制字符或折行头")
                continue

            name_bytes, sep, value_bytes = raw_line.partition(b":")
            if not sep:
                self._prev_was_location = False
                continue

            is_location = name_bytes.strip(b" \t").lower() == b"location"
            self._prev_was_location = is_location
            if is_location and any(b < 0x20 or b == 0x7F for b in value_bytes):
                raise _WireLocationControlCharError("远程模组重定向路径包含非法控制字符")

    async def read(self, max_bytes: int, timeout: Optional[float] = None) -> bytes:
        chunk = await self._inner.read(max_bytes, timeout=timeout)
        try:
            self._inspect_chunk(chunk)
        except _WireLocationControlCharError:
            try:
                await self._inner.aclose()
            except Exception:
                pass
            raise
        return chunk

    async def write(self, buffer: bytes, timeout: Optional[float] = None) -> None:
        await self._inner.write(buffer, timeout=timeout)

    async def aclose(self) -> None:
        await self._inner.aclose()

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> httpcore.AsyncNetworkStream:
        tls_stream = await self._inner.start_tls(
            ssl_context=ssl_context,
            server_hostname=server_hostname,
            timeout=timeout,
        )
        return _WireHeaderGuardStream(tls_stream, inspect_headers=True)

    def get_extra_info(self, info: str) -> Any:
        return self._inner.get_extra_info(info)


class _WireHeaderGuardBackend(httpcore.AsyncNetworkBackend):
    """注入原始 TLS 响应头字节守卫的异步网络后端。"""

    def __init__(self, inner: Optional[httpcore.AsyncNetworkBackend] = None) -> None:
        self._inner = inner or httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: Optional[float] = None,
        local_address: Optional[str] = None,
        socket_options: Optional[Iterable[Any]] = None,
    ) -> httpcore.AsyncNetworkStream:
        stream = await self._inner.connect_tcp(
            host=host,
            port=port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )
        return _WireHeaderGuardStream(stream, inspect_headers=False)

    async def connect_unix_socket(
        self,
        path: str,
        timeout: Optional[float] = None,
        socket_options: Optional[Iterable[Any]] = None,
    ) -> httpcore.AsyncNetworkStream:
        stream = await self._inner.connect_unix_socket(
            path=path,
            timeout=timeout,
            socket_options=socket_options,
        )
        return _WireHeaderGuardStream(stream, inspect_headers=False)

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class _WireHeaderGuardTransport(httpx.AsyncHTTPTransport):
    """单跳独立、无连接复用、带原始响应头字节守卫的 HTTPS 传输层。"""

    def __init__(self, *, verify: Union[bool, ssl.SSLContext], limits: httpx.Limits) -> None:
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
            network_backend=_WireHeaderGuardBackend(),
        )


def _default_dns_resolver(host: str, port: int) -> Sequence[Any]:
    return socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)


class ModRemoteFetchRequest(BaseModel):
    """请求体：从 GitHub 仓库简写或 HTTPS JSON 链接拉取模组清单。"""

    source: str = Field(..., min_length=1, max_length=1024)


@dataclass(frozen=True)
class ValidatedRemoteTarget:
    """经过协议、端口与全局公网 IP 校验的远程连接目标。"""

    url: str
    host: str
    host_header: str
    is_ip_literal: bool
    port: int
    path_and_query: str
    pinned_ips: Tuple[str, ...]


def _assert_no_control_chars(value: str, label: str = "远程模组 URL") -> None:
    if _ASCII_CONTROL_CHAR_RE.search(value):
        raise HTTPException(status_code=400, detail=f"{label}包含非法控制字符")


def _assert_global_ip(raw_ip: str) -> str:
    if "%" in raw_ip:
        raise HTTPException(status_code=400, detail="不允许包含 IPv6 作用域标识的地址")
    addr = ipaddress.ip_address(raw_ip)
    mapped = getattr(addr, "ipv4_mapped", None)
    check_targets = [addr, mapped] if mapped is not None else [addr]
    for item in check_targets:
        if (
            not item.is_global
            or item.is_loopback
            or item.is_private
            or item.is_link_local
            or item.is_reserved
            or item.is_multicast
            or item.is_unspecified
        ):
            raise HTTPException(status_code=400, detail="不允许访问内网、环回或保留地址")
    return str(addr)


def _validate_repo_atom(value: str, label: str) -> str:
    _assert_no_control_chars(value, f"GitHub {label}")
    decoded_raw = unquote(value)
    _assert_no_control_chars(decoded_raw, f"GitHub {label}")
    decoded = decoded_raw.strip(" ")
    if (
        not decoded
        or decoded != value
        or decoded in {".", ".."}
        or ".." in decoded
        or "/" in decoded
        or "\\" in decoded
        or not _SAFE_REPO_ATOM_RE.fullmatch(decoded)
    ):
        raise HTTPException(status_code=400, detail=f"GitHub {label} 字段格式非法")
    return decoded


def _validate_clean_segments(raw_value: str, label: str, *, allow_slash: bool = True) -> str:
    if not raw_value:
        raise HTTPException(status_code=400, detail=f"GitHub {label} 不能为空")
    _assert_no_control_chars(raw_value, f"GitHub {label}")
    decoded = unquote(raw_value)
    _assert_no_control_chars(decoded, f"GitHub {label}")
    if "\\" in raw_value or "\\" in decoded:
        raise HTTPException(status_code=400, detail=f"GitHub {label} 包含非法路径分隔符")
    raw_parts = raw_value.split("/")
    dec_parts = decoded.split("/")
    if not allow_slash and (len(raw_parts) != 1 or len(dec_parts) != 1):
        raise HTTPException(status_code=400, detail=f"GitHub {label} 不允许包含斜杠")
    for part in [*raw_parts, *dec_parts]:
        if not part or part in {".", ".."}:
            raise HTTPException(status_code=400, detail=f"GitHub {label} 不允许包含空段或上级目录引用")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", part):
            raise HTTPException(status_code=400, detail=f"GitHub {label} 含受限字符")
    return "/".join(dec_parts)


def _extract_validated_ips_from_addrinfo(host: str, infos: Sequence[Any]) -> Tuple[str, ...]:
    if not infos:
        raise HTTPException(status_code=502, detail=f"远程主机无可用地址：{host}")
    pinned_ips: List[str] = []
    seen = set()
    for info in infos:
        sockaddr = info[4] if len(info) > 4 else None
        if sockaddr and isinstance(sockaddr[0], str):
            checked_ip = _assert_global_ip(sockaddr[0])
            if checked_ip not in seen:
                seen.add(checked_ip)
                pinned_ips.append(checked_ip)
    if not pinned_ips:
        raise HTTPException(status_code=502, detail=f"远程主机未返回有效公网地址：{host}")
    return tuple(pinned_ips)


def _assert_no_dot_segments(raw_path: str, label: str = "远程模组 URL 路径") -> None:
    _assert_no_control_chars(raw_path, label)
    decoded_path = unquote(raw_path)
    _assert_no_control_chars(decoded_path, label)
    if "\\" in raw_path or "\\" in decoded_path:
        raise HTTPException(status_code=400, detail=f"{label}包含非法字符")
    for seg in [*raw_path.split("/"), *decoded_path.split("/")]:
        base_seg = seg.split(";", 1)[0]
        decoded_base = unquote(base_seg)
        _assert_no_control_chars(decoded_base, label)
        if seg in {".", ".."} or base_seg in {".", ".."} or decoded_base in {".", ".."}:
            raise HTTPException(status_code=400, detail=f"{label}不允许包含相对路径穿越片段")


def _parse_and_validate_url_structure(url: str) -> Tuple[str, str, str, bool, str]:
    if url is None:
        raise HTTPException(status_code=400, detail="远程模组 URL 缺少有效主机名")
    _assert_no_control_chars(url, "远程模组 URL")
    cleaned_url = url.strip(" ")
    if "\\" in cleaned_url:
        raise HTTPException(status_code=400, detail="远程模组 URL 包含非法反斜杠")
    try:
        split = urlsplit(cleaned_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="远程模组 URL 格式无效") from exc
    if split.scheme.lower() != "https":
        raise HTTPException(status_code=400, detail="仅支持 HTTPS 协议拉取远程模组清单")
    if "@" in split.netloc or split.username or split.password:
        raise HTTPException(status_code=400, detail="远程模组 URL 不允许包含认证凭据")
    try:
        port = split.port
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="远程模组 URL 端口无效") from exc
    if port not in (None, 443):
        raise HTTPException(status_code=400, detail="远程模组 URL 仅允许标准 443 端口")

    host = (split.hostname or "").strip().lower().rstrip(".")
    if not host:
        raise HTTPException(status_code=400, detail="远程模组 URL 缺少有效主机名")
    if host in {"localhost", "localhost.localdomain"} or host.endswith(
        (".local", ".internal", ".localhost")
    ):
        raise HTTPException(status_code=400, detail="不允许访问本地或内网主机")

    raw_path = split.path or "/"
    _assert_no_dot_segments(raw_path, "远程模组 URL 路径")
    canonical_url = urlunsplit(("https", split.netloc, raw_path, split.query, ""))

    try:
        ipaddress.ip_address(host)
    except ValueError:
        is_ip_literal = False
        host_header = host
    else:
        is_ip_literal = True
        _assert_global_ip(host)
        host_header = f"[{host}]" if ":" in host else host

    path_and_query = f"{raw_path}?{split.query}" if split.query else raw_path
    return canonical_url, host, host_header, is_ip_literal, path_and_query


def resolve_validated_target(
    url: str,
    *,
    resolve_dns: bool = False,
    dns_resolver: Optional[DnsResolver] = None,
) -> ValidatedRemoteTarget:
    """同步校验远程模组 URL 安全性，并在需要时解析并锁定全局公网 IP 列表。"""
    cleaned_url, host, host_header, is_ip_literal, path_and_query = _parse_and_validate_url_structure(
        url
    )
    if is_ip_literal:
        pinned_ips: Tuple[str, ...] = (_assert_global_ip(host),)
    elif resolve_dns:
        resolver = dns_resolver or _default_dns_resolver
        try:
            infos = resolver(host, 443)
        except socket.gaierror as exc:
            raise HTTPException(status_code=502, detail=f"无法解析远程主机域名：{host}") from exc
        pinned_ips = _extract_validated_ips_from_addrinfo(host, infos)
    else:
        pinned_ips = ()

    return ValidatedRemoteTarget(
        url=cleaned_url,
        host=host,
        host_header=host_header,
        is_ip_literal=is_ip_literal,
        port=443,
        path_and_query=path_and_query,
        pinned_ips=pinned_ips,
    )


async def resolve_validated_target_async(
    url: str,
    *,
    dns_resolver: Optional[DnsResolver] = None,
) -> ValidatedRemoteTarget:
    """异步校验远程模组 URL 并解析、钉扎全局公网 IP（不阻塞事件循环）。"""
    cleaned_url, host, host_header, is_ip_literal, path_and_query = _parse_and_validate_url_structure(
        url
    )
    if is_ip_literal:
        pinned_ips: Tuple[str, ...] = (_assert_global_ip(host),)
    else:
        resolver = dns_resolver or _default_dns_resolver
        try:
            infos = await asyncio.to_thread(resolver, host, 443)
        except socket.gaierror as exc:
            raise HTTPException(status_code=502, detail=f"无法解析远程主机域名：{host}") from exc
        pinned_ips = _extract_validated_ips_from_addrinfo(host, infos)

    return ValidatedRemoteTarget(
        url=cleaned_url,
        host=host,
        host_header=host_header,
        is_ip_literal=is_ip_literal,
        port=443,
        path_and_query=path_and_query,
        pinned_ips=pinned_ips,
    )


def validate_remote_mod_url(url: str, *, resolve_dns: bool = False) -> str:
    """校验远程模组 URL 并返回规范化 URL 字符串。"""
    return resolve_validated_target(url, resolve_dns=resolve_dns).url


def build_ip_pinned_url(target: ValidatedRemoteTarget, ip_str: str) -> str:
    """构造直连已验证公网 IP 的 HTTPS URL（配合 Host 头与 sni_hostname 保持完整证书校验）。"""
    addr = ipaddress.ip_address(ip_str)
    netloc = f"[{addr}]" if addr.version == 6 else str(addr)
    if target.port != 443:
        netloc = f"{netloc}:{target.port}"
    return f"https://{netloc}{target.path_and_query}"


def _build_raw_github_candidates(
    owner: str,
    repo: str,
    refs: List[str],
    explicit_subpath: Optional[str],
    *,
    allow_slash_in_ref: bool = True,
) -> List[str]:
    safe_owner = _validate_repo_atom(owner, "owner")
    clean_repo_raw = repo[:-4] if repo.lower().endswith(".git") else repo
    safe_repo = _validate_repo_atom(clean_repo_raw, "repo")
    safe_refs = [_validate_clean_segments(r, "ref", allow_slash=allow_slash_in_ref) for r in refs]
    subpaths = (
        [_validate_clean_segments(explicit_subpath.lstrip("/"), "path", allow_slash=True)]
        if explicit_subpath
        else list(DEFAULT_MANIFEST_FILENAMES)
    )
    urls: List[str] = []
    for ref_item in safe_refs:
        for sp in subpaths:
            urls.append(
                validate_remote_mod_url(
                    f"https://raw.githubusercontent.com/{safe_owner}/{safe_repo}/{ref_item}/{sp}"
                )
            )
    return urls


def _parse_canonical_github_shorthand(gh_short: str) -> List[str]:
    """统一确定性 GitHub 简写语法（@ 与 # 完全等价，零文件名后缀启发式）。"""
    _assert_no_control_chars(gh_short, "GitHub 简写")
    cleaned = gh_short.strip("/")
    if not cleaned:
        raise HTTPException(status_code=400, detail="GitHub 仓库格式无效，示例：github:owner/repo")

    has_at = "@" in cleaned
    has_hash = "#" in cleaned
    if has_at and has_hash:
        raise HTTPException(status_code=400, detail="请勿同时混用 @ref 与 #ref")

    sigil: Optional[str] = "@" if has_at else ("#" if has_hash else None)
    if sigil is None:
        parts = cleaned.split("/")
        if len(parts) < 2:
            raise HTTPException(status_code=400, detail="GitHub 仓库格式无效，示例：github:owner/repo")
        owner_part, repo_part = parts[0], parts[1]
        explicit_path = "/".join(parts[2:]) if len(parts) > 2 else None
        return _build_raw_github_candidates(
            owner_part,
            repo_part,
            ["main", "master"],
            explicit_path,
            allow_slash_in_ref=False,
        )

    if cleaned.count(sigil) > 1:
        raise HTTPException(status_code=400, detail=f"GitHub 简写中不允许出现多个 '{sigil}' 分隔符")

    before_sigil, sigil_tail = cleaned.split(sigil, 1)
    if not sigil_tail:
        raise HTTPException(status_code=400, detail="GitHub 分支或标签名不能为空")

    head_parts = before_sigil.split("/")
    if len(head_parts) < 2:
        raise HTTPException(status_code=400, detail="GitHub 仓库格式无效，示例：github:owner/repo")

    owner_part, repo_part = head_parts[0], head_parts[1]
    if len(head_parts) == 2:
        if "/" in sigil_tail:
            chosen_ref, explicit_path = sigil_tail.split("/", 1)
            if not chosen_ref or not explicit_path:
                raise HTTPException(status_code=400, detail="GitHub 分支或路径格式非法")
        else:
            chosen_ref = sigil_tail
            explicit_path = None
        return _build_raw_github_candidates(
            owner_part,
            repo_part,
            [chosen_ref],
            explicit_path,
            allow_slash_in_ref=False,
        )

    explicit_path = "/".join(head_parts[2:])
    return _build_raw_github_candidates(
        owner_part,
        repo_part,
        [sigil_tail],
        explicit_path,
        allow_slash_in_ref=True,
    )


def resolve_mod_manifest_candidates(source: str) -> List[str]:
    """将用户输入（github:owner/repo[@|#ref][/path]、GitHub URL 或 HTTPS JSON 直链）解析为候选 URL。"""
    if source is None:
        raise HTTPException(status_code=400, detail="请输入模组仓库地址或 JSON 链接")
    _assert_no_control_chars(source, "模组来源地址")
    raw = source.strip(" ")
    if not raw:
        raise HTTPException(status_code=400, detail="请输入模组仓库地址或 JSON 链接")

    gh_short: Optional[str] = None
    if raw.lower().startswith("github:"):
        gh_short = raw[len("github:") :].strip(" ")
    elif "://" not in raw:
        head_before_sigil = raw.split("#", 1)[0].split("@", 1)[0]
        slash_head = head_before_sigil.split("/")
        if (
            len(slash_head) >= 2
            and "." not in slash_head[0]
            and re.match(r"^[A-Za-z0-9_.-]+$", slash_head[0])
        ):
            gh_short = raw

    if gh_short is not None:
        return _parse_canonical_github_shorthand(gh_short)

    validated_raw = validate_remote_mod_url(raw)
    parsed = urlsplit(raw)
    if (parsed.hostname or "").lower() in {"github.com", "www.github.com"}:
        if "\\" in raw or "\\" in unquote(parsed.path):
            raise HTTPException(status_code=400, detail="GitHub 链接包含非法路径分隔符")
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) < 2:
            raise HTTPException(status_code=400, detail="GitHub 链接缺少 owner/repo")
        owner, repo = parts[0], parts[1]
        if len(parts) >= 4 and parts[2] == "blob":
            branch = parts[3]
            file_path = "/".join(parts[4:])
            if not file_path:
                raise HTTPException(status_code=400, detail="GitHub blob 链接缺少文件路径")
            return _build_raw_github_candidates(owner, repo, [branch], file_path)
        if len(parts) >= 4 and parts[2] == "tree":
            branch = parts[3]
            dir_path = "/".join(parts[4:]).strip("/")
            if dir_path:
                safe_dir = _validate_clean_segments(dir_path, "path", allow_slash=True)
                urls: List[str] = []
                for fname in DEFAULT_MANIFEST_FILENAMES:
                    urls.extend(
                        _build_raw_github_candidates(owner, repo, [branch], f"{safe_dir}/{fname}")
                    )
                return urls
            return _build_raw_github_candidates(owner, repo, [branch], None)
        if len(parts) == 2:
            raw_frag = parsed.fragment or ""
            _assert_no_control_chars(unquote(raw_frag), "GitHub 分支片段")
            hash_branch = raw_frag.strip(" ") or None
            refs = [hash_branch] if hash_branch else ["main", "master"]
            return _build_raw_github_candidates(owner, repo, refs, None)
        raise HTTPException(status_code=400, detail="不支持的 GitHub 路径格式，请提供仓库主页或 blob 文件链接")

    return [validated_raw]


async def _stream_validated_response(
    client: httpx.AsyncClient,
    request_url: str,
    logical_url: str,
    host_header: str,
    sni_hostname: Optional[str],
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    headers = {
        "Accept": "application/json, text/plain;q=0.9",
        "Accept-Encoding": "identity",
        "Connection": "close",
        "Host": host_header,
    }
    extensions = {"sni_hostname": sni_hostname} if sni_hostname else None
    request = client.build_request("GET", request_url, headers=headers, extensions=extensions)
    try:
        response = await client.send(request, stream=True)
    except _WireLocationControlCharError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.RemoteProtocolError as exc:
        if "location" in str(exc).lower():
            raise HTTPException(status_code=400, detail="远程模组重定向路径包含非法控制字符或格式无效") from exc
        raise
    try:
        if response.status_code in {301, 302, 303, 307, 308}:
            raw_location = response.headers.get("location")
            if raw_location is None:
                raise HTTPException(status_code=502, detail="远程模组重定向缺少目标地址")
            _assert_no_control_chars(raw_location, "远程模组重定向路径")
            location = raw_location.strip(" ")
            if not location:
                raise HTTPException(status_code=502, detail="远程模组重定向缺少目标地址")
            if "\\" in location:
                raise HTTPException(status_code=400, detail="远程模组重定向路径包含非法反斜杠")
            try:
                loc_split = urlsplit(location)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="远程模组重定向地址格式无效") from exc
            _assert_no_dot_segments(loc_split.path, "远程模组重定向路径")
            return urljoin(logical_url, location), None

        if response.status_code == 404:
            raise FileNotFoundError(logical_url)
        response.raise_for_status()

        content_encoding = (response.headers.get("content-encoding") or "").strip().lower()
        if content_encoding not in {"", "identity"}:
            raise HTTPException(
                status_code=502,
                detail=f"远程模组响应包含未授权的压缩编码（{content_encoding}），已拒绝读取",
            )

        raw_cl = (response.headers.get("content-length") or "").strip()
        if raw_cl:
            try:
                parsed_cl = int(raw_cl)
            except ValueError as exc:
                raise HTTPException(status_code=502, detail="远程模组响应 Content-Length 非法") from exc
            if parsed_cl < 0:
                raise HTTPException(status_code=502, detail="远程模组响应 Content-Length 非法")
            if parsed_cl > MOD_MANIFEST_MAX_BYTES:
                raise HTTPException(status_code=413, detail="远程模组清单超过 1MB 安全上限")

        chunks: List[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > MOD_MANIFEST_MAX_BYTES:
                raise HTTPException(status_code=413, detail="远程模组清单超过 1MB 安全上限")
            chunks.append(chunk)

        try:
            raw_text = b"".join(chunks).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=502, detail="远程模组清单必须为合法 UTF-8 编码") from exc

        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=502, detail="远程返回内容不是合法 JSON 清单") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=502, detail="远程模组清单根节点必须为 JSON 对象")
        return None, {"resolved_url": logical_url, "manifest": parsed}
    finally:
        await response.aclose()


async def fetch_safe_json_url(
    url: str,
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
    dns_resolver: Optional[DnsResolver] = None,
    ssl_context: Optional[ssl.SSLContext] = None,
    overall_timeout: float = MOD_FETCH_OVERALL_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """
    每一跳均执行：
    1. 公网 IP 钉扎（防 DNS 重绑定）
    2. 单次请求独立生命周期的 AsyncClient（禁止跨重定向跳复用连接池）
    3. 1MB 无压缩字节流硬上限 + 端到端总墙钟超时（防慢速滴灌连接占用 R1）
    """
    if overall_timeout <= 0:
        raise ValueError("overall_timeout must be positive")
    if ssl_context is not None and (
        ssl_context.verify_mode == ssl.CERT_NONE or not ssl_context.check_hostname
    ):
        raise ValueError("ssl_context must enforce certificate and hostname verification")
    verify_arg: Union[bool, ssl.SSLContext] = ssl_context if ssl_context is not None else True
    per_op_timeout = min(MOD_FETCH_TIMEOUT_SECONDS, overall_timeout)

    try:
        async with asyncio.timeout(overall_timeout):
            current_url = url
            for _ in range(MOD_MAX_REDIRECTS + 1):
                target = await resolve_validated_target_async(
                    current_url,
                    dns_resolver=dns_resolver,
                )
                redirect_url: Optional[str] = None
                payload: Optional[Dict[str, Any]] = None
                last_connect_err: Optional[Exception] = None
                sni_host = None if target.is_ip_literal else target.host

                for pinned_ip in target.pinned_ips:
                    pinned_url = build_ip_pinned_url(target, pinned_ip)
                    hop_limits = httpx.Limits(max_keepalive_connections=0, max_connections=1)
                    hop_transport: httpx.AsyncBaseTransport = (
                        transport
                        if transport is not None
                        else _WireHeaderGuardTransport(verify=verify_arg, limits=hop_limits)
                    )
                    async with httpx.AsyncClient(
                        timeout=per_op_timeout,
                        follow_redirects=False,
                        trust_env=False,
                        verify=verify_arg,
                        limits=hop_limits,
                        transport=hop_transport,
                    ) as hop_client:
                        try:
                            redirect_url, payload = await _stream_validated_response(
                                hop_client,
                                request_url=pinned_url,
                                logical_url=target.url,
                                host_header=target.host_header,
                                sni_hostname=sni_host,
                            )
                            last_connect_err = None
                            break
                        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                            last_connect_err = exc
                            continue

                if last_connect_err is not None and payload is None and redirect_url is None:
                    raise last_connect_err

                if payload is not None:
                    return payload
                if redirect_url is not None:
                    current_url = redirect_url
                    continue

            raise HTTPException(status_code=502, detail="远程模组链接重定向次数过多")
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=f"拉取远程模组清单超时（已超过 {overall_timeout:g}s 总时限）",
        ) from exc


async def fetch_remote_mod_manifest_response(
    payload: ModRemoteFetchRequest,
    *,
    route_overall_timeout: float = MOD_ROUTE_OVERALL_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """安全拉取远程 plotpilot-mod.json 清单并返回前端契约响应 { ok, resolved_url, manifest }。"""
    candidates = resolve_mod_manifest_candidates(payload.source)
    last_error: Optional[Exception] = None

    try:
        async with asyncio.timeout(route_overall_timeout):
            for candidate in candidates:
                try:
                    fetched = await fetch_safe_json_url(candidate)
                    return {
                        "ok": True,
                        "resolved_url": fetched["resolved_url"],
                        "manifest": fetched["manifest"],
                    }
                except FileNotFoundError as exc:
                    last_error = exc
                    continue
                except HTTPException:
                    raise
                except httpx.HTTPStatusError as exc:
                    raise HTTPException(
                        status_code=502,
                        detail=f"拉取远程模组失败（HTTP {exc.response.status_code}）",
                    ) from exc
                except httpx.RequestError as exc:
                    raise HTTPException(
                        status_code=502,
                        detail=f"连接远程模组源失败：{exc}",
                    ) from exc
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=f"拉取远程模组清单总耗时超时（已超过 {route_overall_timeout:g}s）",
        ) from exc

    raise HTTPException(
        status_code=404,
        detail=f"未在目标仓库或地址找到 plotpilot-mod.json（已尝试 {len(candidates)} 个路径）",
    ) from last_error
