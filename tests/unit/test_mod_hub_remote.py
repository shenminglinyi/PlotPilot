from __future__ import annotations

import asyncio
import datetime
import json
import os
import ssl
import tempfile
from typing import Any, AsyncIterator, List, Sequence, Tuple
from unittest.mock import patch

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import HTTPException

from interfaces.api.v1.workbench.mod_manifest_remote import (
    ModRemoteFetchRequest,
    build_ip_pinned_url,
    fetch_remote_mod_manifest_response,
    fetch_safe_json_url,
    resolve_mod_manifest_candidates,
    resolve_validated_target,
    validate_remote_mod_url,
)


def test_resolve_github_shorthand_main_and_master() -> None:
    urls = resolve_mod_manifest_candidates("github:duoduoler/plotpilot-cold-noir")
    assert urls == [
        "https://raw.githubusercontent.com/duoduoler/plotpilot-cold-noir/main/plotpilot-mod.json",
        "https://raw.githubusercontent.com/duoduoler/plotpilot-cold-noir/main/mod.json",
        "https://raw.githubusercontent.com/duoduoler/plotpilot-cold-noir/main/manifest.json",
        "https://raw.githubusercontent.com/duoduoler/plotpilot-cold-noir/master/plotpilot-mod.json",
        "https://raw.githubusercontent.com/duoduoler/plotpilot-cold-noir/master/mod.json",
        "https://raw.githubusercontent.com/duoduoler/plotpilot-cold-noir/master/manifest.json",
    ]


def test_resolve_github_shorthand_identical_at_and_hash_including_extensionless_and_slash_refs() -> None:
    # 1. 带 .json 的嵌套路径：@ 与 # 完全等价
    at_json = resolve_mod_manifest_candidates("github:duoduoler/mods@v1.2/packs/dialogue.json")
    hash_json = resolve_mod_manifest_candidates("github:duoduoler/mods#v1.2/packs/dialogue.json")
    assert at_json == hash_json == [
        "https://raw.githubusercontent.com/duoduoler/mods/v1.2/packs/dialogue.json",
    ]

    # 2. 无扩展名的显式清单路径（B2 回归测试）：@ 与 # 必须生成完全相同的唯一候选 URL
    at_extless = resolve_mod_manifest_candidates("github:duoduoler/mods@v1/config/manifest")
    hash_extless = resolve_mod_manifest_candidates("github:duoduoler/mods#v1/config/manifest")
    assert at_extless == hash_extless == [
        "https://raw.githubusercontent.com/duoduoler/mods/v1/config/manifest",
    ]

    # 3. 路径在前、含斜杠分支在后的明确表示：owner/repo/<path>@feature/noir 与 #feature/noir 完全等价
    at_slash_ref = resolve_mod_manifest_candidates(
        "github:duoduoler/mods/config/manifest@feature/noir"
    )
    hash_slash_ref = resolve_mod_manifest_candidates(
        "github:duoduoler/mods/config/manifest#feature/noir"
    )
    assert at_slash_ref == hash_slash_ref == [
        "https://raw.githubusercontent.com/duoduoler/mods/feature/noir/config/manifest",
    ]

    # 4. 纯分支无子路径
    assert resolve_mod_manifest_candidates("github:duoduoler/mods@dev") == (
        resolve_mod_manifest_candidates("github:duoduoler/mods#dev")
    )


def test_resolve_github_blob_and_repo_urls() -> None:
    blob_urls = resolve_mod_manifest_candidates(
        "https://github.com/shenminglinyi/PlotPilot-Mods/blob/main/mods/noir.json"
    )
    assert blob_urls == [
        "https://raw.githubusercontent.com/shenminglinyi/PlotPilot-Mods/main/mods/noir.json"
    ]

    repo_urls = resolve_mod_manifest_candidates("https://github.com/shenminglinyi/PlotPilot-Mods")
    assert repo_urls[0] == (
        "https://raw.githubusercontent.com/shenminglinyi/PlotPilot-Mods/main/plotpilot-mod.json"
    )
    assert len(repo_urls) == 6


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "http://raw.githubusercontent.com/a/b/main/plotpilot-mod.json",
        "file:///etc/passwd",
        "https://localhost/plotpilot-mod.json",
        "https://127.0.0.1/plotpilot-mod.json",
        "https://10.0.0.5/plotpilot-mod.json",
        "https://192.168.1.20/plotpilot-mod.json",
        "https://169.254.169.254/latest/meta-data/",
        "https://[::1]/plotpilot-mod.json",
        "https://[::ffff:127.0.0.1]/plotpilot-mod.json",
        "https://example.com:8080/plotpilot-mod.json",
        "https://user:pass@example.com/plotpilot-mod.json",
        "https://internal.service.local/plotpilot-mod.json",
    ],
)
def test_validate_remote_mod_url_blocks_ssrf_targets(unsafe_url: str) -> None:
    with pytest.raises(HTTPException) as exc_info:
        validate_remote_mod_url(unsafe_url)
    assert exc_info.value.status_code == 400


@pytest.mark.parametrize(
    "traversal_input",
    [
        "github:owner/repo@main/../../secret.json",
        "github:owner/repo@../other/main/plotpilot-mod.json",
        "github:owner/repo#../other",
        "github:../owner/repo",
        "https://github.com/owner/repo/blob/..%2fother/plotpilot-mod.json",
        "https://github.com/owner/repo/tree/../other",
        "https://raw.githubusercontent.com/alice/project/../other/main/plotpilot-mod.json",
        "https://raw.githubusercontent.com/alice/project/%2e%2e/other/main/plotpilot-mod.json",
        "https://example.com/a/../mod.json",
        "https://example.com/a/%2e%2e/mod.json",
        "https://example.com/a/./mod.json",
        "https://example.com/a/..;v=1/mod.json",
    ],
)
def test_resolve_blocks_all_structural_path_traversal(traversal_input: str) -> None:
    with pytest.raises(HTTPException) as exc_info:
        resolve_mod_manifest_candidates(traversal_input)
    assert exc_info.value.status_code == 400


def test_dns_pinning_builds_ip_bound_url_and_blocks_private_dns() -> None:
    with patch("socket.getaddrinfo") as mock_dns:
        mock_dns.return_value = [
            (2, 1, 6, "", ("185.199.108.133", 443)),
        ]
        target = resolve_validated_target(
            "https://raw.githubusercontent.com/demo/mod/main/plotpilot-mod.json",
            resolve_dns=True,
        )
        assert target.host == "raw.githubusercontent.com"
        assert target.pinned_ips == ("185.199.108.133",)
        assert (
            build_ip_pinned_url(target, target.pinned_ips[0])
            == "https://185.199.108.133/demo/mod/main/plotpilot-mod.json"
        )

    with patch("socket.getaddrinfo") as mock_evil_dns:
        mock_evil_dns.return_value = [
            (2, 1, 6, "", ("185.199.108.133", 443)),
            (2, 1, 6, "", ("127.0.0.1", 443)),
        ]
        with pytest.raises(HTTPException) as exc_info:
            resolve_validated_target("https://rebind.attacker.example/mod.json", resolve_dns=True)
        assert exc_info.value.status_code == 400


class _ChunkedOversizeStream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        chunk = b"a" * (256 * 1024)
        for _ in range(5):  # 1.25 MiB total, without Content-Length header
            yield chunk


def test_fetch_safe_json_url_ip_pinning_redirects_streamed_size_and_encoding_guards() -> None:
    manifest_payload = {
        "schema": "plotpilot-mod/v1",
        "id": "mod-test",
        "name": "测试模组",
        "overrides": [],
    }

    def fake_dns(host: str, port: int) -> Sequence[Any]:
        assert port == 443
        mapping = {
            "raw.githubusercontent.com": [(2, 1, 6, "", ("185.199.108.133", 443))],
            "example.com": [(2, 1, 6, "", ("93.184.216.34", 443))],
            "cdn.example.net": [(2, 1, 6, "", ("1.1.1.1", 443))],
            "rebind-target.example": [(2, 1, 6, "", ("10.0.0.8", 443))],
        }
        return mapping[host]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("accept-encoding") == "identity"
        assert request.headers.get("connection") == "close"

        if (
            str(request.url) == "https://185.199.108.133/demo/mod/main/plotpilot-mod.json"
            and request.headers.get("host") == "raw.githubusercontent.com"
            and request.extensions.get("sni_hostname") == "raw.githubusercontent.com"
        ):
            return httpx.Response(200, text=json.dumps(manifest_payload))

        if str(request.url) == "https://93.184.216.34/hop-to-cdn.json":
            return httpx.Response(302, headers={"Location": "https://cdn.example.net/final.json"})

        if (
            str(request.url) == "https://1.1.1.1/final.json"
            and request.headers.get("host") == "cdn.example.net"
            and request.extensions.get("sni_hostname") == "cdn.example.net"
        ):
            return httpx.Response(200, text=json.dumps(manifest_payload))

        if str(request.url) == "https://93.184.216.34/evil-redirect.json":
            return httpx.Response(
                302, headers={"Location": "https://rebind-target.example/internal.json"}
            )

        if str(request.url) == "https://93.184.216.34/streamed-oversized.json":
            # 无 Content-Length 头，专门覆盖流式读取累计字节超限分支
            return httpx.Response(200, stream=_ChunkedOversizeStream())

        if str(request.url) == "https://93.184.216.34/gzip-bomb.json":
            return httpx.Response(
                200,
                headers={"Content-Encoding": "gzip"},
                content=b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\x03\xab\xae\x05\x00\x43\xbf\xa6\xa3\x02\x00\x00\x00",
            )

        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    ok_res = asyncio.run(
        fetch_safe_json_url(
            "https://raw.githubusercontent.com/demo/mod/main/plotpilot-mod.json",
            transport=transport,
            dns_resolver=fake_dns,
        )
    )
    assert ok_res["manifest"]["id"] == "mod-test"

    hop_res = asyncio.run(
        fetch_safe_json_url(
            "https://example.com/hop-to-cdn.json",
            transport=transport,
            dns_resolver=fake_dns,
        )
    )
    assert hop_res["resolved_url"] == "https://cdn.example.net/final.json"

    with pytest.raises(HTTPException) as redirect_exc:
        asyncio.run(
            fetch_safe_json_url(
                "https://example.com/evil-redirect.json",
                transport=transport,
                dns_resolver=fake_dns,
            )
        )
    assert redirect_exc.value.status_code == 400

    with pytest.raises(HTTPException) as size_exc:
        asyncio.run(
            fetch_safe_json_url(
                "https://example.com/streamed-oversized.json",
                transport=transport,
                dns_resolver=fake_dns,
            )
        )
    assert size_exc.value.status_code == 413

    with pytest.raises(HTTPException) as enc_exc:
        asyncio.run(
            fetch_safe_json_url(
                "https://example.com/gzip-bomb.json",
                transport=transport,
                dns_resolver=fake_dns,
            )
        )
    assert enc_exc.value.status_code == 502


def test_redirect_traversal_and_semicolon_path_parameter_fidelity() -> None:
    """
    R1 & R2 回归测试：
    1. 重定向 Location 中若含相对点段（如 ../../other/main/mod.json 或 /a/%2e%2e/b.json），
       必须在 urljoin 归一化之前直接拦截为 HTTP 400（同时覆盖 GitHub Raw 与普通 HTTPS 主机）。
    2. 含 RFC 3986 路径分号参数的合法 URL（如 /manifest.json;version=2?format=json），
       钉扎请求实际发送的 raw_path 必须完整保留分号参数并与返回的 resolved_url 严格一致。
    """
    observed_raw_paths: List[bytes] = []

    def fake_dns(host: str, port: int) -> Sequence[Any]:
        assert port == 443
        mapping = {
            "raw.githubusercontent.com": [(2, 1, 6, "", ("185.199.108.133", 443))],
            "example.com": [(2, 1, 6, "", ("93.184.216.34", 443))],
        }
        return mapping[host]

    def handler(request: httpx.Request) -> httpx.Response:
        observed_raw_paths.append(request.url.raw_path)

        if str(request.url) == "https://185.199.108.133/alice/project/main/mod.json":
            return httpx.Response(302, headers={"Location": "../../other/main/mod.json"})

        if str(request.url) == "https://93.184.216.34/dir/start.json":
            return httpx.Response(302, headers={"Location": "../%2e%2e/secret.json"})

        if (
            str(request.url) == "https://93.184.216.34/manifest.json;version=2?format=json"
            and request.headers.get("host") == "example.com"
        ):
            return httpx.Response(
                200,
                text=json.dumps({"id": "param-v2", "name": "Parameterized", "overrides": []}),
            )

        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    with pytest.raises(HTTPException) as gh_redir_exc:
        asyncio.run(
            fetch_safe_json_url(
                "https://raw.githubusercontent.com/alice/project/main/mod.json",
                transport=transport,
                dns_resolver=fake_dns,
            )
        )
    assert gh_redir_exc.value.status_code == 400

    with pytest.raises(HTTPException) as https_redir_exc:
        asyncio.run(
            fetch_safe_json_url(
                "https://example.com/dir/start.json",
                transport=transport,
                dns_resolver=fake_dns,
            )
        )
    assert https_redir_exc.value.status_code == 400

    observed_raw_paths.clear()
    param_url = "https://example.com/manifest.json;version=2?format=json"
    param_res = asyncio.run(
        fetch_safe_json_url(
            param_url,
            transport=transport,
            dns_resolver=fake_dns,
        )
    )
    assert observed_raw_paths == [b"/manifest.json;version=2?format=json"]
    assert param_res["resolved_url"] == param_url
    assert param_res["manifest"]["id"] == "param-v2"


def _make_self_signed_cert_pem(san_dns_names: List[str]) -> Tuple[bytes, bytes]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, san_dns_names[0])])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(hours=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(name) for name in san_dns_names]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return cert_pem, key_pem


def test_real_tls_redirect_same_ip_prevents_connection_reuse_cert_bypass() -> None:
    """
    B1 真实传输回归测试：
    当 first.example 与 second.example 解析到同一个钉扎 IP（共享同一 TLS 端点）时：
    1. 若服务端证书仅对 first.example 有效，即使第一跳返回 Keep-Alive 302 重定向到 second.example，
       第二跳也绝不能复用第一跳连接，必须在重新握手时因证书主机名不匹配而拒绝（ConnectError）。
    2. 若服务端证书同时覆盖两个域名，则两跳各自完成独立 TLS 握手并携带正确的 SNI 与 Host 头成功返回。
    """

    async def _run_scenario(san_hosts: List[str]) -> Tuple[Dict[str, Any], List[Tuple[str, str]]]:
        cert_pem, key_pem = _make_self_signed_cert_pem(san_hosts)
        handshakes_and_hosts: List[Tuple[str, str]] = []

        with (
            tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as cf,
            tempfile.NamedTemporaryFile(suffix=".key", delete=False) as kf,
        ):
            cf.write(cert_pem)
            cf.flush()
            kf.write(key_pem)
            kf.flush()
            cert_path, key_path = cf.name, kf.name

        server_ssl = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_ssl.load_cert_chain(certfile=cert_path, keyfile=key_path)
        observed_sni: List[str] = []

        def _sni_cb(ssl_obj: ssl.SSLObject, server_name: str, _ctx: ssl.SSLContext) -> None:
            observed_sni.append(server_name or "")

        server_ssl.sni_callback = _sni_cb

        client_ssl = ssl.create_default_context(cadata=cert_pem.decode("ascii"))

        async def _handle_client(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            conn_sni = observed_sni[-1] if observed_sni else ""
            try:
                while True:
                    raw_head = await reader.readuntil(b"\r\n\r\n")
                    head_text = raw_head.decode("latin1")
                    req_line = head_text.splitlines()[0]
                    path = req_line.split(" ")[1]
                    host_hdr = ""
                    for line in head_text.splitlines()[1:]:
                        if line.lower().startswith("host:"):
                            host_hdr = line.split(":", 1)[1].strip()
                            break
                    handshakes_and_hosts.append((conn_sni, host_hdr))

                    if path == "/start":
                        resp = (
                            "HTTP/1.1 302 Found\r\n"
                            "Location: https://second.example/mod.json\r\n"
                            "Connection: keep-alive\r\n"
                            "Content-Length: 0\r\n\r\n"
                        ).encode("ascii")
                        writer.write(resp)
                        await writer.drain()
                        # 保持同一 TLS 套接字继续等待下一请求：若客户端错误复用连接，此处将直接收到第二跳请求且 conn_sni 仍为 first.example
                        continue

                    body = json.dumps({"id": "tls-verified", "name": "TLS OK", "overrides": []}).encode(
                        "utf-8"
                    )
                    resp = (
                        b"HTTP/1.1 200 OK\r\n"
                        b"Content-Type: application/json\r\n"
                        b"Connection: close\r\n"
                        + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
                        + body
                    )
                    writer.write(resp)
                    await writer.drain()
                    break
            except Exception:
                pass
            finally:
                writer.close()

        server = await asyncio.start_server(_handle_client, "127.0.0.1", 0, ssl=server_ssl)
        bound_port = server.sockets[0].getsockname()[1]

        # 仅在测试夹具中将钉扎目标映射到本机临时 TLS 端口，真实测试 HTTPX/httpcore 连接池与 TLS 主机名校验
        def fake_shared_ip_dns(_host: str, _port: int) -> Sequence[Any]:
            return [(2, 1, 6, "", ("93.184.216.34", 443))]

        def redirect_pinned_to_local_server(target: Any, _ip_str: str) -> str:
            return f"https://127.0.0.1:{bound_port}{target.path_and_query}"

        try:
            with patch(
                "interfaces.api.v1.workbench.mod_manifest_remote.build_ip_pinned_url",
                side_effect=redirect_pinned_to_local_server,
            ):
                res = await fetch_safe_json_url(
                    "https://first.example/start",
                    dns_resolver=fake_shared_ip_dns,
                    ssl_context=client_ssl,
                )
                return res, handshakes_and_hosts
        finally:
            server.close()
            await server.wait_closed()
            for tmp_file in (cert_path, key_path):
                try:
                    os.unlink(tmp_file)
                except OSError:
                    pass

    # 场景 1：证书仅签给 first.example -> 第二跳访问同 IP 的 second.example 必须触发证书校验失败！
    with pytest.raises(httpx.ConnectError):
        asyncio.run(_run_scenario(["first.example"]))

    # 场景 2：证书同时覆盖 first.example 与 second.example -> 两跳均独立完成新握手并校验通过
    ok_payload, seen = asyncio.run(_run_scenario(["first.example", "second.example"]))
    assert ok_payload["manifest"]["id"] == "tls-verified"
    assert seen == [
        ("first.example", "first.example"),
        ("second.example", "second.example"),
    ]


def test_real_tls_redirect_rejects_wire_tab_in_location_header() -> None:
    """
    M1 真实 HTTP/1.1-over-TLS 回归测试：
    h11 在解析 HTTP 头时会剥离首尾 OWS（含水平制表符 \\t）。
    此处通过真实 TLS 套接字直接回写带前导 \\t、尾随 \\t 及双端 \\t 的原始 Location 响应字节，
    断言在线路解析归一化之前即返回 HTTP 400，且绝不会向 second.example 发起第二跳请求。
    """

    async def _run_wire_tab_case(raw_location_header_line: bytes) -> List[Tuple[str, str]]:
        cert_pem, key_pem = _make_self_signed_cert_pem(["first.example", "second.example"])
        observed_requests: List[Tuple[str, str]] = []

        with (
            tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as cf,
            tempfile.NamedTemporaryFile(suffix=".key", delete=False) as kf,
        ):
            cf.write(cert_pem)
            cf.flush()
            kf.write(key_pem)
            kf.flush()
            cert_path, key_path = cf.name, kf.name

        server_ssl = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_ssl.load_cert_chain(certfile=cert_path, keyfile=key_path)
        client_ssl = ssl.create_default_context(cadata=cert_pem.decode("ascii"))

        async def _handle_client(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            try:
                raw_head = await reader.readuntil(b"\r\n\r\n")
                lines = raw_head.decode("latin1").splitlines()
                path = lines[0].split(" ")[1]
                host_hdr = ""
                for ln in lines[1:]:
                    if ln.lower().startswith("host:"):
                        host_hdr = ln.split(":", 1)[1].strip()
                        break
                observed_requests.append((host_hdr, path))

                if path == "/start":
                    resp = (
                        b"HTTP/1.1 302 Found\r\n"
                        + raw_location_header_line
                        + b"\r\nConnection: close\r\nContent-Length: 0\r\n\r\n"
                    )
                    writer.write(resp)
                    await writer.drain()
                else:
                    body = b'{"id":"should-never-reach"}'
                    writer.write(
                        b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                        + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
                        + body
                    )
                    await writer.drain()
            except Exception:
                pass
            finally:
                writer.close()

        server = await asyncio.start_server(_handle_client, "127.0.0.1", 0, ssl=server_ssl)
        bound_port = server.sockets[0].getsockname()[1]

        def fake_dns(_host: str, _port: int) -> Sequence[Any]:
            return [(2, 1, 6, "", ("93.184.216.34", 443))]

        def redirect_pinned_to_local_server(target: Any, _ip_str: str) -> str:
            return f"https://127.0.0.1:{bound_port}{target.path_and_query}"

        try:
            with patch(
                "interfaces.api.v1.workbench.mod_manifest_remote.build_ip_pinned_url",
                side_effect=redirect_pinned_to_local_server,
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await fetch_safe_json_url(
                        "https://first.example/start",
                        dns_resolver=fake_dns,
                        ssl_context=client_ssl,
                    )
                assert exc_info.value.status_code == 400
                return observed_requests
        finally:
            server.close()
            await server.wait_closed()
            for tmp_file in (cert_path, key_path):
                try:
                    os.unlink(tmp_file)
                except OSError:
                    pass

    for wire_loc in [
        b"Location: \thttps://second.example/mod.json",
        b"Location: https://second.example/mod.json\t",
        b"Location: \thttps://second.example/mod.json\t",
    ]:
        seen_reqs = asyncio.run(_run_wire_tab_case(wire_loc))
        assert seen_reqs == [("first.example", "/start")]


def test_slowloris_drip_streaming_enforces_overall_deadline_and_closes_stream() -> None:
    """
    R1 慢速分块流回归测试：
    单个分块间隔（0.04s）小于单次读取超时，但累计流式传输耗时超过 overall_timeout（0.12s）时，
    必须按总墙钟时限主动中止，返回受控 HTTP 504，并确保底层响应流 aclose() 被调用。
    """
    stream_closed = False

    class _SlowDripStream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            for _ in range(20):
                await asyncio.sleep(0.04)
                yield b" "

        async def aclose(self) -> None:
            nonlocal stream_closed
            stream_closed = True

    def fake_dns(_host: str, _port: int) -> Sequence[Any]:
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            stream=_SlowDripStream(),
        )

    with pytest.raises(HTTPException) as timeout_exc:
        asyncio.run(
            fetch_safe_json_url(
                "https://example.com/slow.json",
                transport=httpx.MockTransport(handler),
                dns_resolver=fake_dns,
                overall_timeout=0.12,
            )
        )
    assert timeout_exc.value.status_code == 504
    assert stream_closed is True


def test_fetch_remote_mod_manifest_response_contract_and_control_char_guards() -> None:
    """验证完整路由响应包装契约 { ok, resolved_url, manifest } 及首尾/内嵌控制字符、空认证头、GitHub 路径穿越拦截。"""
    for bad in [
        "https://@example.com/mod.json",
        "https://[::1/mod.json",
        "https://example.com/a/.\t./mod.json",
        "\nhttps://example.com/mod.json",
        "https://example.com/mod.json\t",
        "\rgithub:duoduoler/demo-mod",
        "github:duoduoler/demo-mod\n",
        "https://github.com/trusted/repo/../../attacker/evil/blob/main/mod.json",
        "https://github.com/trusted/repo/%2e%2e/%2e%2e/attacker/evil/blob/main/mod.json",
    ]:
        with pytest.raises(HTTPException) as exc:
            resolve_mod_manifest_candidates(bad)
        assert exc.value.status_code == 400

    for bad_url in [
        "\nhttps://example.com/mod.json",
        "https://example.com/mod.json\t",
        "https://example.com/mod.json\r",
    ]:
        with pytest.raises(HTTPException) as url_exc:
            validate_remote_mod_url(bad_url)
        assert url_exc.value.status_code == 400

    def fake_dns(_host: str, _port: int) -> Sequence[Any]:
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    for bad_loc in [
        "\thttps://cdn.example.com/mod.json",
        "https://cdn.example.com/mod.json\t",
    ]:
        def _loc_handler(_req: httpx.Request, loc: str = bad_loc) -> httpx.Response:
            return httpx.Response(302, headers={"Location": loc})

        with pytest.raises(HTTPException) as loc_exc:
            asyncio.run(
                fetch_safe_json_url(
                    "https://example.com/start.json",
                    transport=httpx.MockTransport(_loc_handler),
                    dns_resolver=fake_dns,
                )
            )
        assert loc_exc.value.status_code == 400

    async def _fake_fetch(candidate: str) -> dict[str, Any]:
        if candidate.endswith("/plotpilot-mod.json"):
            raise FileNotFoundError(candidate)
        return {
            "resolved_url": candidate,
            "manifest": {"schema": "plotpilot-mod/v1", "pack": {"id": "demo", "name": "Demo", "overrides": []}},
        }

    with patch(
        "interfaces.api.v1.workbench.mod_manifest_remote.fetch_safe_json_url",
        side_effect=_fake_fetch,
    ):
        resp = asyncio.run(
            fetch_remote_mod_manifest_response(
                ModRemoteFetchRequest(source="github:duoduoler/demo-mod@main")
            )
        )
    assert resp["ok"] is True
    assert resp["resolved_url"] == "https://raw.githubusercontent.com/duoduoler/demo-mod/main/mod.json"
    assert resp["manifest"]["schema"] == "plotpilot-mod/v1"
