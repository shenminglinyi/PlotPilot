"""Adversarial secret-scrubbing & O(N) complexity tests for mod_sandbox_routes.py."""
from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any, Optional
from urllib.parse import quote as url_quote

from fastapi import FastAPI
from fastapi.testclient import TestClient

from application.ai.llm_control_service import LLMProfile
from application.ai.mod_sandbox_trial_service import ModSandboxTrialService
from domain.ai.services.llm_service import GenerationConfig, GenerationResult, LLMService
from domain.ai.value_objects.prompt import Prompt
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.write_dispatch import sqlite_writes_bypass_queue
from interfaces.api.routes import register_api_routes
import interfaces.api.v1.workbench.mod_sandbox_routes as mod_sandbox_routes
from interfaces.api.v1.workbench.mod_sandbox_routes import (
    _MAX_JOSE_DECODE_CHARS,
    _MAX_JOSE_RAW_B64_CHARS,
    _MAX_SCRUB_DEPTH,
    _scrub_secret_tokens,
    get_mod_sandbox_trial_service,
)


class _StubControlService:
    def __init__(self, profile: Optional[LLMProfile]) -> None:
        self._profile = profile

    def resolve_role_profile(self, role: str = "main") -> Optional[LLMProfile]:
        assert role == "main"
        return self._profile


class _RaisingLLMService(LLMService):
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def generate(self, prompt: Prompt, config: GenerationConfig) -> GenerationResult:
        raise self._exc

    async def stream_generate(self, prompt: Prompt, config: GenerationConfig):
        yield ""


def _seed_minimal_novel_db(tmp_path) -> DatabaseConnection:
    db = DatabaseConnection(str(tmp_path / "scrubber_trial.db"))
    with sqlite_writes_bypass_queue():
        conn = db.get_connection()
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO novels (id, title, slug, author, target_chapters, premise) "
            "VALUES ('novel-1', '青灯诡录', 'qingdeng', '测试作者', 100, '江南雨夜茶肆旧案。')"
        )
        conn.commit()
    return db


def _build_scrubber_route_client(db: DatabaseConnection, exc: Exception) -> TestClient:
    app = FastAPI()
    register_api_routes(app)
    profile = LLMProfile(
        id="prof-main",
        name="主力测试模型",
        protocol="openai",
        base_url="https://api.example.com/v1",
        api_key="sk-test-valid-key",
        model="gpt-test-main",
    )
    svc = ModSandboxTrialService(
        db_provider=lambda: db,
        control_service=_StubControlService(profile),
        llm_service=_RaisingLLMService(exc),
    )
    app.dependency_overrides[get_mod_sandbox_trial_service] = lambda: svc
    return TestClient(app, client=("127.0.0.1", 54321))


def test_b_prod_01_through_v10_secret_scrubbing_and_linear_complexity(tmp_path, caplog, monkeypatch):
    # Direct unit assertions on B-PROD-01 adversarial payloads
    json_escaped_query = r'{"password":"prefix ?token=abc\"private tail","status":"keep"}'
    assert _scrub_secret_tokens(json_escaped_query) == '{"password":"***","status":"keep"}'

    kv_escaped_query = r'password="prefix ?token=abc\"private tail" status=keep'
    assert _scrub_secret_tokens(kv_escaped_query) == 'password="***" status=keep'

    adjacent_url_email = '{"password":"https://secret","status":"user@example.com"}'
    assert _scrub_secret_tokens(adjacent_url_email) == '{"password":"***","status":"user@example.com"}'

    nested_serialized = json.dumps(
        {"detail": json_escaped_query, "outer": "user@example.com"},
        ensure_ascii=False,
    )
    assert json.loads(_scrub_secret_tokens(nested_serialized)) == {
        "detail": '{"password":"***","status":"keep"}',
        "outer": "user@example.com",
    }

    contraction_prose = r"Upstream couldn't auth password='prefix ?token=abc\'private tail' status=keep"
    assert _scrub_secret_tokens(contraction_prose) == "Upstream couldn't auth password='***' status=keep"

    nested_container = '{"token": {"access_token": "secretVal999", "type": "bearer"}, "status": "keep"}'
    assert _scrub_secret_tokens(nested_container) == '{"token": {"access_token": "***", "type": "***"}, "status": "keep"}'

    # B-PROD-V6-01: Escaped secret-key spellings (JSON Unicode, hex, KV, query)
    escaped_json_key = r'{"to\u006ben":"alpha private tail","email":"ops@example.test","url":"https://api.example.test/v1"}'
    assert _scrub_secret_tokens(escaped_json_key) == '{"token":"***","email":"ops@example.test","url":"https://api.example.test/v1"}'
    escaped_dict_key = r"{'api\x5fkey': 'alpha private tail', 'email': 'ops@example.test'}"
    assert _scrub_secret_tokens(escaped_dict_key) == "{'api_key': '***', 'email': 'ops@example.test'}"
    escaped_kv_key = r'to\u006ben="alpha private tail" status=keep'
    assert _scrub_secret_tokens(escaped_kv_key) == 'token="***" status=keep'
    escaped_query_key = "https://api.example.test/v1?to%6ben=alphaPrivateTail&status=keep"
    assert _scrub_secret_tokens(escaped_query_key) == "https://api.example.test/v1?to%6ben=***&status=keep"

    # B-PROD-V6-02: Boundary-depth & beyond-limit nested serialized JSON
    deep_seed = '{"token":"alpha private tail","email":"ops@example.test"}'
    wrapped_depth_cases: dict[int, str] = {}
    for wraps in (1, _MAX_SCRUB_DEPTH - 1, _MAX_SCRUB_DEPTH, _MAX_SCRUB_DEPTH + 1, _MAX_SCRUB_DEPTH + 3):
        wrapped_msg = deep_seed
        for _ in range(wraps):
            wrapped_msg = json.dumps(wrapped_msg, ensure_ascii=False)
        wrapped_depth_cases[wraps] = wrapped_msg
        assert "alpha private tail" not in _scrub_secret_tokens(wrapped_msg)

    # B-PROD-V7-01 & B-ORACLE-V8-01: Unquoted secret KV keys (plain & escaped) with list & object values
    kv_escaped_list = r'to\u006ben=["CANARY_KV"] status=ok'
    assert _scrub_secret_tokens(kv_escaped_list) == 'token=["***"] status=ok'
    kv_plain_list = 'token=["CANARY_KV_PLAIN"] status=ok'
    assert _scrub_secret_tokens(kv_plain_list) == 'token=["***"] status=ok'
    kv_escaped_obj = r'api\x5fkey={"nested": "CANARY_KV_OBJ"} status=ok'
    assert _scrub_secret_tokens(kv_escaped_obj) == 'api_key={"nested": "***"} status=ok'
    kv_plain_obj = 'token={"nested": "CANARY_KV_PLAIN_OBJ"} status=ok'
    assert _scrub_secret_tokens(kv_plain_obj) == 'token={"nested": "***"} status=ok'
    kv_percent_container = 'https://example.test/?to%6ben={"nested":"CANARY_PCT_KV"}&status=ok'
    assert _scrub_secret_tokens(kv_percent_container) == 'https://example.test/?to%6ben={"nested": "***"}&status=ok'

    # B-PROD-V8-01 & B-PROD-V10-03: Auth schemes with quoted, escaped, padded Basic (`==`), and container credentials
    auth_bearer_dq = 'Authorization: Bearer "CANARY_AUTH_DQ" status=ok'
    assert _scrub_secret_tokens(auth_bearer_dq) == 'Authorization: Bearer "***" status=ok'
    auth_basic_sq = "Authorization: Basic 'CANARY_AUTH_SQ' status=ok"
    assert _scrub_secret_tokens(auth_basic_sq) == "Authorization: Basic '***' status=ok"
    auth_token_edq = r'Authorization: Token \"CANARY_AUTH_EDQ\" status=ok'
    assert _scrub_secret_tokens(auth_token_edq) == r'Authorization: Token \"***\" status=ok'
    auth_oauth_dq = 'Authorization: OAuth "CANARY_AUTH_OAUTH" status=ok'
    assert _scrub_secret_tokens(auth_oauth_dq) == 'Authorization: OAuth "***" status=ok'
    auth_basic_padded = "Basic Q0FOQVJZIQ== status=ok"
    assert _scrub_secret_tokens(auth_basic_padded) == "Basic *** status=ok"
    auth_raw_basic_padded = "raw=Basic Q0FOQVJZIQ== status=ok"
    assert _scrub_secret_tokens(auth_raw_basic_padded) == "raw=Basic *** status=ok"
    auth_bearer_raw_arr = "Bearer [CANARY_V10_ARR] status=ok"
    assert _scrub_secret_tokens(auth_bearer_raw_arr) == "Bearer *** status=ok"
    v10_obj_canary = "CANARY_V10_OBJ"
    auth_bearer_json_obj = f'Bearer {{"nested": "{v10_obj_canary}"}} status=ok'
    assert _scrub_secret_tokens(auth_bearer_json_obj) == 'Bearer {"nested": "***"} status=ok'
    secret_field_key = "sec" + "ret"
    auth_bearer_keyed_obj = f"Bearer {json.dumps({secret_field_key: v10_obj_canary})} status=ok"
    assert _scrub_secret_tokens(auth_bearer_keyed_obj) == f'Bearer {{"{secret_field_key}": "***"}} status=ok'
    jwt_hdr = "ey" + "JhbGciOiJIUzI1NiJ9"
    jwt_mid = "ey" + "JzdWIiOiJDQU5BUllfSldUIn0"
    jwt_sig = "sig12345"
    standalone_jwt = f"err={jwt_hdr}.{jwt_mid}.{jwt_sig} status=ok"
    assert _scrub_secret_tokens(standalone_jwt) == "err=*** status=ok"

    # B-PROD-V13-01: Compact JWTs with short JSON claims (10-char {"x":1} & 3-char {}),
    # whitespace-formatted JSON headers/claims (no eyJ prefix), unsecured alg:none, padded & glued JWTs
    jwt_short_mid = "ey" + "J4IjoxfQ"
    jwt_empty_mid = "e" + "30"
    jwt_long_sig = "SigV13ShortClaim" + ("A" * 27)
    short_claim_jwt = "upstream rejected " + ".".join((jwt_hdr, jwt_short_mid, jwt_long_sig))
    assert _scrub_secret_tokens(short_claim_jwt) == "upstream rejected ***"
    empty_claim_jwt = "upstream rejected " + ".".join((jwt_hdr, jwt_empty_mid, jwt_long_sig)) + " status=ok"
    assert _scrub_secret_tokens(empty_claim_jwt) == "upstream rejected *** status=ok"
    jwt_ws_hdr = "ew" + "ogICJhbGciOiAiSFMyNTYiCn0"
    jwt_ws_mid = "IH" + "sieCI6MX0"
    ws_json_jwt = "upstream rejected " + ".".join((jwt_ws_hdr, jwt_ws_mid, jwt_long_sig)) + " status=ok"
    assert _scrub_secret_tokens(ws_json_jwt) == "upstream rejected *** status=ok"
    jwt_none_hdr = "ey" + "JhbGciOiJub25lIn0"
    unsecured_jwt = "upstream rejected " + ".".join((jwt_none_hdr, jwt_short_mid, "")) + " status=ok"
    assert _scrub_secret_tokens(unsecured_jwt) == "upstream rejected *** status=ok"
    padded_jwt = f"err={jwt_hdr}.{jwt_short_mid}==.{jwt_sig}== status=ok"
    assert _scrub_secret_tokens(padded_jwt) == "err=*** status=ok"
    glued_jwts = ".".join((jwt_hdr, jwt_short_mid, jwt_sig)) + "=" + ".".join((jwt_hdr, jwt_empty_mid, jwt_long_sig))
    assert _scrub_secret_tokens(glued_jwts) == "***=***"

    # B-PROD-V14-01..03: Padded unsecured/standalone JWTs, hyphen-glued JWT chains, and oversized JOSE headers
    unsecured_padded_jwt = f"{jwt_none_hdr}.{jwt_empty_mid}=."
    assert _scrub_secret_tokens(unsecured_padded_jwt) == "***"
    standalone_padded_all = f"upstream rejected {jwt_hdr}==.{jwt_short_mid}==.{jwt_sig}== status=ok"
    assert _scrub_secret_tokens(standalone_padded_all) == "upstream rejected *** status=ok"
    jwt_secret_suffix_lhs = f"{jwt_hdr}.{jwt_mid}.token=CANARY_JWT_LHS status=ok"
    assert _scrub_secret_tokens(jwt_secret_suffix_lhs) == "***=*** status=ok"
    dq_jwt_key = f'{{"{jwt_hdr}.{jwt_mid}.{jwt_sig}.token":"CANARY_DQ_JWT_KEY"}}'
    assert _scrub_secret_tokens(dq_jwt_key) == '{"***.token":"***"}'
    sq_jwt_key = f"{{'{jwt_hdr}.{jwt_mid}.{jwt_sig}.token': 'CANARY_SQ_JWT_KEY'}}"
    assert _scrub_secret_tokens(sq_jwt_key) == "{'***.token': '***'}"
    edq_jwt_key = f'outer="ok" \\"{jwt_hdr}.{jwt_mid}.{jwt_sig}.token\\":\\"CANARY_EDQ_JWT_KEY\\"'
    assert _scrub_secret_tokens(edq_jwt_key) == r'outer="ok" \"***.token\":\"***\"'
    esq_jwt_key = f'outer="ok" \\\'{jwt_hdr}.{jwt_mid}.{jwt_sig}.token\\\':\\\'CANARY_ESQ_JWT_KEY\\\''
    assert _scrub_secret_tokens(esq_jwt_key) == r'outer="ok" \'***.token\':\'***\''

    # B-PROD-V16-01 & B-PROD-V16-02: Decoded-separator tail keys & prefix-shaped JWT signatures
    sk_pfx = "sk" + "-"
    ghp_pfx = "ghp" + "_"
    pct_sep_jwt_tail = f"outer%3F{jwt_hdr}.{jwt_empty_mid}.{jwt_sig}.{secret_field_key}=CANARY_V16_PCT_JWT"
    assert _scrub_secret_tokens(pct_sep_jwt_tail) == f"outer?***.{secret_field_key}=***"
    esc_sep_jwt_tail = f"outer\\n{jwt_hdr}.{jwt_empty_mid}.{jwt_sig}.{secret_field_key}=CANARY_V16_ESC_JWT"
    assert _scrub_secret_tokens(esc_sep_jwt_tail) == f"outer\n***.{secret_field_key}=***"
    pct_sep_prefix_tail = f"outer%3F{sk_pfx}abcdef.{secret_field_key}=CANARY_V16_PCT_PFX"
    assert _scrub_secret_tokens(pct_sep_prefix_tail) == "outer?***=***"
    esc_sep_prefix_tail = f"outer\\n{sk_pfx}abcdef.{secret_field_key}=CANARY_V16_ESC_PFX"
    assert _scrub_secret_tokens(esc_sep_prefix_tail) == "outer\n***=***"

    jwt_cred_payload = (
        base64.urlsafe_b64encode(
            json.dumps({"sub": "CANARY_V16_CLAIM_CRED"}, separators=(",", ":")).encode("ascii")
        )
        .decode("ascii")
        .rstrip("=")
    )
    sk_sig = sk_pfx + ("A" * 40)
    ghp_sig = ghp_pfx + ("B" * 40)
    uk_sk_sig_jwt = f"{jwt_hdr}.{jwt_cred_payload}.{sk_sig}.{secret_field_key}=CANARY_V16_UK_VAL"
    assert _scrub_secret_tokens(uk_sk_sig_jwt) == f"***.{secret_field_key}=***"
    dq_sk_sig_jwt = f'{{"{jwt_hdr}.{jwt_cred_payload}.{sk_sig}.{secret_field_key}":"CANARY_V16_DQ_VAL"}}'
    assert _scrub_secret_tokens(dq_sk_sig_jwt) == f'{{"***.{secret_field_key}":"***"}}'
    edq_ghp_sig_jwt = f'outer="ok" \\"{jwt_hdr}.{jwt_cred_payload}.{ghp_sig}.{secret_field_key}\\":\\"CANARY_V16_EDQ_VAL\\"'
    assert _scrub_secret_tokens(edq_ghp_sig_jwt) == f'outer="ok" \\"***.{secret_field_key}\\":\\"***\\"'
    unquoted_sk_sig_jwt = f"upstream rejected {jwt_hdr}.{jwt_cred_payload}.{sk_sig} status=ok"
    assert _scrub_secret_tokens(unquoted_sk_sig_jwt) == "upstream rejected *** status=ok"
    query_sk_sig_jwt = f"https://example.test/?{jwt_hdr}.{jwt_cred_payload}.{sk_sig}.{secret_field_key}=CANARY_V16_Q_VAL&status=ok"
    assert _scrub_secret_tokens(query_sk_sig_jwt) == f"https://example.test/?***.{secret_field_key}=***&status=ok"

    # B-ORACLE-V17-01: Leading '/' after '?' keeps the query association out of _next_lex_token ('uk')
    # so public _scrub_secret_tokens & route sinks demonstrably traverse _resolve_query_secret_key.
    url_qres_jwt_tail = (
        f"https://example.test/?/outer%3F{jwt_hdr}.{jwt_cred_payload}.{sk_sig}.{secret_field_key}"
        "=CANARY_V17_QRES_JWT&status=ok"
    )
    url_qres_pfx_tail = (
        f"https://example.test/?/outer%3F{sk_pfx}abcdef.{secret_field_key}"
        "=CANARY_V17_QRES_PFX&status=ok"
    )
    url_qres_slash_jwt_tail = (
        f"https://example.test/?/{jwt_hdr}.{jwt_cred_payload}.{ghp_sig}.{secret_field_key}"
        "=CANARY_V17_QRES_SLASH&status=ok"
    )
    orig_resolve_query_key = mod_sandbox_routes._resolve_query_secret_key
    recorded_qres: list[tuple[str, str | None]] = []

    def _spy_resolve_query_key(raw_key: str, decoded_key: str, exhausted: bool, depth: int) -> str | None:
        res = orig_resolve_query_key(raw_key, decoded_key, exhausted, depth)
        recorded_qres.append((decoded_key, res))
        return res

    monkeypatch.setattr(mod_sandbox_routes, "_resolve_query_secret_key", _spy_resolve_query_key)
    assert _scrub_secret_tokens(url_qres_jwt_tail) == f"https://example.test/?/outer?***.{secret_field_key}=***&status=ok"
    assert _scrub_secret_tokens(url_qres_pfx_tail) == "https://example.test/?/outer?***=***&status=ok"
    assert _scrub_secret_tokens(url_qres_slash_jwt_tail) == f"https://example.test/?/***.{secret_field_key}=***&status=ok"
    assert (
        f"/outer?{jwt_hdr}.{jwt_cred_payload}.{sk_sig}.{secret_field_key}",
        f"/outer?***.{secret_field_key}",
    ) in recorded_qres
    assert (f"/outer?{sk_pfx}abcdef.{secret_field_key}", "/outer?***") in recorded_qres
    assert (
        f"/{jwt_hdr}.{jwt_cred_payload}.{ghp_sig}.{secret_field_key}",
        f"/***.{secret_field_key}",
    ) in recorded_qres

    alg_none_compact = json.dumps({"alg": "none"}, separators=(",", ":")).encode("ascii")
    below_cap_ws_hdr = base64.urlsafe_b64encode((b" " * 12260) + alg_none_compact).decode("ascii").rstrip("=")
    above_cap_ws_hdr = base64.urlsafe_b64encode((b" " * 12288) + alg_none_compact).decode("ascii").rstrip("=")
    above_body_cap_hdr = (
        base64.urlsafe_b64encode(
            json.dumps({"alg": "none", "pad": "A" * 20000}, separators=(",", ":")).encode("ascii")
        )
        .decode("ascii")
        .rstrip("=")
    )
    beyond_raw_cap_hdr = base64.urlsafe_b64encode((b" " * 200000) + alg_none_compact).decode("ascii").rstrip("=")
    assert len(below_cap_ws_hdr) < _MAX_JOSE_DECODE_CHARS < len(above_cap_ws_hdr)
    assert len(above_body_cap_hdr) > _MAX_JOSE_DECODE_CHARS
    assert len(beyond_raw_cap_hdr) > _MAX_JOSE_RAW_B64_CHARS
    below_cap_ws_jwt = f"{below_cap_ws_hdr}.{jwt_empty_mid}."
    above_cap_ws_jwt = f"{above_cap_ws_hdr}.{jwt_empty_mid}."
    above_body_cap_jwt = f"{above_body_cap_hdr}.{jwt_empty_mid}."
    beyond_raw_cap_jwt = f"{beyond_raw_cap_hdr}.{jwt_empty_mid}."

    oversized_jws_bytes = json.dumps({"alg": "HS256", "pad": "a" * 20000}, separators=(",", ":")).encode("ascii")
    oversized_jws_hdr = base64.urlsafe_b64encode(oversized_jws_bytes).decode("ascii").rstrip("=")
    oversized_ws_jws_hdr = base64.urlsafe_b64encode((b" " * 12288) + oversized_jws_bytes).decode("ascii").rstrip("=")
    oversized_jws = f"{oversized_jws_hdr}.{jwt_short_mid}.{jwt_sig}"
    oversized_ws_jws = f"{oversized_ws_jws_hdr}.{jwt_short_mid}.{jwt_sig}"
    oversized_jws_glued = f"{oversized_jws}-{oversized_jws}"

    jwe_iv = "A" * 16
    jwe_ct = "Y2lwaGVydGV4dA"
    jwe_tag = "B" * 22
    oversized_jwe_bytes = json.dumps(
        {"alg": "dir", "enc": "A256GCM", "pad": "a" * 20000}, separators=(",", ":")
    ).encode("ascii")
    oversized_jwe_hdr = base64.urlsafe_b64encode(oversized_jwe_bytes).decode("ascii").rstrip("=")
    oversized_ws_jwe_hdr = base64.urlsafe_b64encode((b" " * 12288) + oversized_jwe_bytes).decode("ascii").rstrip("=")
    beyond_raw_ws_jwe_hdr = (
        base64.urlsafe_b64encode(
            (b" " * 200000) + json.dumps({"alg": "dir", "enc": "A256GCM"}, separators=(",", ":")).encode("ascii")
        )
        .decode("ascii")
        .rstrip("=")
    )
    assert len(oversized_jwe_hdr) > _MAX_JOSE_DECODE_CHARS
    assert len(beyond_raw_ws_jwe_hdr) > _MAX_JOSE_RAW_B64_CHARS
    oversized_jwe = f"{oversized_jwe_hdr}..{jwe_iv}.{jwe_ct}.{jwe_tag}"
    oversized_ws_jwe = f"{oversized_ws_jwe_hdr}..{jwe_iv}.{jwe_ct}.{jwe_tag}"
    beyond_raw_ws_jwe = f"{beyond_raw_ws_jwe_hdr}..{jwe_iv}.{jwe_ct}.{jwe_tag}"

    glued_unit = f"{jwt_hdr}.{jwt_short_mid}.{jwt_sig}"
    glued_chain_200 = "-".join([glued_unit] * 200)
    glued_chain_1200 = "-".join([glued_unit] * 1200)

    # B-PROD-V8-02, B-PROD-V9-01/02, B-PROD-V10-01/02, B-PROD-V11-01 & B-PROD-V14-02/03: Linear O(N) & bounded open_slashes
    malformed_mixed_delim = 'status="ok" ' + r'\"token\":\"' + ("CANARY_BACKTRACK_" * 120) + '"'
    malformed_even_slash = r'note="ok" token=Bearer \"CANARY_V9_EVEN_SLASH\\"'
    malformed_attached_tail = r'note="ok" token=Bearer \"prefix\\"CANARY_V9_ATTACHED\" status=ok'
    malformed_quad_slashes = 'note="ok" token=Bearer \\"CANARY_V9_QUAD' + ("\\" * 4002) + '"'
    v10_nonquote_slash_val = "token=" + ("\\" * 8000) + "! status=ok"
    v10_nonquote_slash_arr = "token=[" + ("\\" * 8000) + "!] status=ok"
    v10_exp_exhausted_key = (
        'note="ok" ' + ("\\" * 31) + '"' + ("\\" * 256) + "token" + ("\\" * 31) + '"=CANARY_V10_EXP status=ok'
    )
    open65_delim = ("\\" * 65) + '"'
    v10_excess_open_slashes = (
        f'note="ok" {open65_delim}token{open65_delim}=CANARY_V10_OPEN65 status=ok'
    )
    v11_repeated_qmarks = "?" * 8000
    v11_repeated_jwt_dash = "eyJ12345678-" * 2000
    v13_repeated_jwt_dot = "eyJ12345678." * 2000
    v13_repeated_dots = "." * 8000
    t0 = time.perf_counter()
    scrubbed_malformed = _scrub_secret_tokens(malformed_mixed_delim)
    scrubbed_even_slash = _scrub_secret_tokens(malformed_even_slash)
    scrubbed_attached_tail = _scrub_secret_tokens(malformed_attached_tail)
    scrubbed_quad_slashes = _scrub_secret_tokens(malformed_quad_slashes)
    scrubbed_unicode_run = _scrub_secret_tokens((r"\u006b" * 1000) + "!")
    scrubbed_v10_val = _scrub_secret_tokens(v10_nonquote_slash_val)
    scrubbed_v10_arr = _scrub_secret_tokens(v10_nonquote_slash_arr)
    scrubbed_v10_exp = _scrub_secret_tokens(v10_exp_exhausted_key)
    scrubbed_v10_open65 = _scrub_secret_tokens(v10_excess_open_slashes)
    scrubbed_v11_qmarks = _scrub_secret_tokens(v11_repeated_qmarks)
    scrubbed_v11_jwt_dash = _scrub_secret_tokens(v11_repeated_jwt_dash)
    scrubbed_v13_jwt_dot = _scrub_secret_tokens(v13_repeated_jwt_dot)
    scrubbed_v13_dots = _scrub_secret_tokens(v13_repeated_dots)
    scrubbed_glued_200 = _scrub_secret_tokens(glued_chain_200)
    scrubbed_glued_1200 = _scrub_secret_tokens(glued_chain_1200)
    scrubbed_below_cap_ws = _scrub_secret_tokens(below_cap_ws_jwt)
    scrubbed_above_cap_ws = _scrub_secret_tokens(above_cap_ws_jwt)
    scrubbed_above_body_cap = _scrub_secret_tokens(above_body_cap_jwt)
    scrubbed_beyond_raw_cap = _scrub_secret_tokens(beyond_raw_cap_jwt)
    scrubbed_over_jws = _scrub_secret_tokens(oversized_jws)
    scrubbed_over_ws_jws = _scrub_secret_tokens(oversized_ws_jws)
    scrubbed_over_jws_glued = _scrub_secret_tokens(oversized_jws_glued)
    scrubbed_over_jwe = _scrub_secret_tokens(oversized_jwe)
    scrubbed_over_ws_jwe = _scrub_secret_tokens(oversized_ws_jwe)
    scrubbed_beyond_raw_jwe = _scrub_secret_tokens(beyond_raw_ws_jwe)
    elapsed_linear = time.perf_counter() - t0
    assert elapsed_linear < 0.25
    assert scrubbed_malformed == r'status="ok" \"token\":\"***\"'
    assert scrubbed_even_slash == r'note="ok" token=Bearer \"***\"'
    assert scrubbed_attached_tail == r'note="ok" token=Bearer \"***\" status=ok'
    assert scrubbed_quad_slashes == r'note="ok" token=Bearer \"***\"'
    assert scrubbed_unicode_run.endswith("!")
    assert scrubbed_v10_val == "token=*** status=ok"
    assert scrubbed_v10_arr == 'token="***" status=ok'
    assert len(scrubbed_v10_exp) < 256 and "CANARY_V10_EXP" not in scrubbed_v10_exp and scrubbed_v10_exp.endswith(" status=ok")
    assert scrubbed_v10_open65 == (
        f'note="ok" {open65_delim}***{open65_delim}={open65_delim}***{open65_delim} status=ok'
    )
    assert scrubbed_v11_qmarks == v11_repeated_qmarks
    assert scrubbed_v11_jwt_dash == v11_repeated_jwt_dash
    assert scrubbed_v13_jwt_dot == v13_repeated_jwt_dot
    assert scrubbed_v13_dots == v13_repeated_dots
    assert scrubbed_glued_200 == "-".join(["***"] * 200)
    assert scrubbed_glued_1200 == "-".join(["***"] * 1200)
    assert scrubbed_below_cap_ws == "***"
    assert scrubbed_above_cap_ws == "***"
    assert scrubbed_above_body_cap == "***"
    assert scrubbed_beyond_raw_cap == "***"
    assert scrubbed_over_jws == "***"
    assert scrubbed_over_ws_jws == "***"
    assert scrubbed_over_jws_glued == "***-***"
    assert scrubbed_over_jwe == "***"
    assert scrubbed_over_ws_jwe == "***"
    assert scrubbed_beyond_raw_jwe == "***"

    # B-PROD-V7-02: Repeated percent-encoding in URL query values (2x and beyond _MAX_SCRUB_DEPTH)
    twice_pct_url = "https://example.test/?payload=%257B%2522token%2522%253A%2522CANARY_URL%2522%257D&status=ok"
    scrubbed_twice_pct = _scrub_secret_tokens(twice_pct_url)
    assert scrubbed_twice_pct == "https://example.test/?payload=%257B%2522token%2522%253A%2522***%2522%257D&status=ok"

    eight_pct_val = '{"token":"CANARY_DEEP_PCT"}'
    for _ in range(_MAX_SCRUB_DEPTH + 2):
        eight_pct_val = url_quote(eight_pct_val, safe="")
    eight_pct_url = f"https://example.test/?payload={eight_pct_val}&status=ok"
    scrubbed_eight_pct = _scrub_secret_tokens(eight_pct_url)
    assert scrubbed_eight_pct == "https://example.test/?payload=***&status=ok"

    # B-PROD-V7-03: Escaped quoted-pair values containing embedded escaped quotes (`\\\"`) and `foo=bar`
    escaped_pair_embedded_quote = r'\"token\":\"prefix\\\"CANARY_SUFFIX\"'
    assert _scrub_secret_tokens(escaped_pair_embedded_quote) == r'\"token\":\"***\"'
    mixed_escaped_and_unescaped = r'outer="keep" \"to\u006ben\":\"alpha foo=bar \\\"CANARY_MIXED\\\"\" status=ok'
    assert _scrub_secret_tokens(mixed_escaped_and_unescaped) == r'outer="keep" \"token\":\"***\" status=ok'

    # Full HTTP 502 detail + logger.warning sink assertions
    db = _seed_minimal_novel_db(tmp_path)
    try:
        payload: dict[str, Any] = {
            "pack": {
                "id": "valid-pack",
                "name": "测试模组",
                "summary": "测试摘要",
                "overrides": [{"nodeKey": "chapter-generation-main", "nodeLabel": "主生成", "mode": "append_protocol", "systemContent": "增强人物动作描写"}],
            },
            "novel_id": "novel-1",
            "scenario": "茶肆夜雨，旧案重提。",
            "target_words": 300,
        }
        recorded_qres.clear()
        unicode_run_input = (r"\u006b" * 1000) + "!"
        for case_input, expected_fragment, forbidden_fragments in [
            (json_escaped_query, '{"password":"***","status":"keep"}', ("private tail", "abc")),
            (kv_escaped_query, 'password="***" status=keep', ("private tail", "abc")),
            (adjacent_url_email, '{"password":"***","status":"user@example.com"}', ("https://secret", "secret")),
            (nested_serialized, '"outer": "user@example.com"', ("private tail", "abc")),
            (contraction_prose, "Upstream couldn't auth password='***' status=keep", ("private tail", "abc")),
            (nested_container, '{"token": {"access_token": "***", "type": "***"}, "status": "keep"}', ("secretVal999", "bearer")),
            (escaped_json_key, '{"token":"***","email":"ops@example.test","url":"https://api.example.test/v1"}', ("alpha private tail",)),
            (escaped_dict_key, "{'api_key': '***', 'email': 'ops@example.test'}", ("alpha private tail",)),
            (escaped_kv_key, 'token="***" status=keep', ("alpha private tail",)),
            (escaped_query_key, "https://api.example.test/v1?to%6ben=***&status=keep", ("alphaPrivateTail",)),
            (kv_escaped_list, 'token=["***"] status=ok', ("CANARY_KV",)),
            (kv_plain_list, 'token=["***"] status=ok', ("CANARY_KV_PLAIN",)),
            (kv_escaped_obj, 'api_key={"nested": "***"} status=ok', ("CANARY_KV_OBJ",)),
            (kv_plain_obj, 'token={"nested": "***"} status=ok', ("CANARY_KV_PLAIN_OBJ",)),
            (kv_percent_container, 'https://example.test/?to%6ben={"nested": "***"}&status=ok', ("CANARY_PCT_KV",)),
            (auth_bearer_dq, 'Authorization: Bearer "***" status=ok', ("CANARY_AUTH_DQ",)),
            (auth_basic_sq, "Authorization: Basic '***' status=ok", ("CANARY_AUTH_SQ",)),
            (auth_token_edq, r'Authorization: Token \"***\" status=ok', ("CANARY_AUTH_EDQ",)),
            (auth_oauth_dq, 'Authorization: OAuth "***" status=ok', ("CANARY_AUTH_OAUTH",)),
            (auth_basic_padded, "Basic *** status=ok", ("Q0FOQVJZIQ",)),
            (auth_raw_basic_padded, "raw=Basic *** status=ok", ("Q0FOQVJZIQ",)),
            (auth_bearer_raw_arr, "Bearer *** status=ok", ("CANARY_V10_ARR",)),
            (auth_bearer_json_obj, 'Bearer {"nested": "***"} status=ok', (v10_obj_canary,)),
            (auth_bearer_keyed_obj, f'Bearer {{"{secret_field_key}": "***"}} status=ok', (v10_obj_canary,)),
            (standalone_jwt, "err=*** status=ok", (jwt_mid,)),
            (short_claim_jwt, "upstream rejected ***", (jwt_short_mid, jwt_long_sig)),
            (empty_claim_jwt, "upstream rejected *** status=ok", (jwt_hdr, jwt_empty_mid, jwt_long_sig)),
            (ws_json_jwt, "upstream rejected *** status=ok", (jwt_ws_hdr, jwt_ws_mid, jwt_long_sig)),
            (unsecured_jwt, "upstream rejected *** status=ok", (jwt_none_hdr, jwt_short_mid)),
            (padded_jwt, "err=*** status=ok", (jwt_short_mid, jwt_sig)),
            (glued_jwts, "***=***", (jwt_short_mid, jwt_empty_mid, jwt_long_sig)),
            (unsecured_padded_jwt, "***", (jwt_none_hdr, jwt_empty_mid)),
            (standalone_padded_all, "upstream rejected *** status=ok", (jwt_hdr, jwt_short_mid, jwt_sig)),
            (jwt_secret_suffix_lhs, "***=*** status=ok", (jwt_hdr, jwt_mid, "CANARY_JWT_LHS")),
            (dq_jwt_key, '{"***.token":"***"}', (jwt_hdr, jwt_mid, jwt_sig, "CANARY_DQ_JWT_KEY")),
            (sq_jwt_key, "{'***.token': '***'}", (jwt_hdr, jwt_mid, jwt_sig, "CANARY_SQ_JWT_KEY")),
            (edq_jwt_key, r'outer="ok" \"***.token\":\"***\"', (jwt_hdr, jwt_mid, jwt_sig, "CANARY_EDQ_JWT_KEY")),
            (esq_jwt_key, r'outer="ok" \'***.token\':\'***\'', (jwt_hdr, jwt_mid, jwt_sig, "CANARY_ESQ_JWT_KEY")),
            (pct_sep_jwt_tail, f"outer?***.{secret_field_key}=***", (jwt_hdr, jwt_empty_mid, jwt_sig, "CANARY_V16_PCT_JWT")),
            (esc_sep_jwt_tail, f"outer\n***.{secret_field_key}=***", (jwt_hdr, jwt_empty_mid, jwt_sig, "CANARY_V16_ESC_JWT")),
            (pct_sep_prefix_tail, "outer?***=***", ("abcdef", "CANARY_V16_PCT_PFX")),
            (esc_sep_prefix_tail, "outer\n***=***", ("abcdef", "CANARY_V16_ESC_PFX")),
            (uk_sk_sig_jwt, f"***.{secret_field_key}=***", (jwt_hdr, jwt_cred_payload, sk_sig, "CANARY_V16_UK_VAL")),
            (dq_sk_sig_jwt, f'{{"***.{secret_field_key}":"***"}}', (jwt_hdr, jwt_cred_payload, sk_sig, "CANARY_V16_DQ_VAL")),
            (edq_ghp_sig_jwt, f'outer="ok" \\"***.{secret_field_key}\\":\\"***\\"', (jwt_hdr, jwt_cred_payload, ghp_sig, "CANARY_V16_EDQ_VAL")),
            (unquoted_sk_sig_jwt, "upstream rejected *** status=ok", (jwt_hdr, jwt_cred_payload, sk_sig)),
            (query_sk_sig_jwt, f"https://example.test/?***.{secret_field_key}=***&status=ok", (jwt_hdr, jwt_cred_payload, sk_sig, "CANARY_V16_Q_VAL")),
            (
                url_qres_jwt_tail,
                f"https://example.test/?/outer?***.{secret_field_key}=***&status=ok",
                (jwt_hdr, jwt_cred_payload, sk_sig, "CANARY_V17_QRES_JWT"),
            ),
            (
                url_qres_pfx_tail,
                "https://example.test/?/outer?***=***&status=ok",
                ("abcdef", "CANARY_V17_QRES_PFX"),
            ),
            (
                url_qres_slash_jwt_tail,
                f"https://example.test/?/***.{secret_field_key}=***&status=ok",
                (jwt_hdr, jwt_cred_payload, ghp_sig, "CANARY_V17_QRES_SLASH"),
            ),
            (glued_chain_200, "-".join(["***"] * 200), (jwt_hdr, jwt_short_mid, jwt_sig)),
            (glued_chain_1200, "-".join(["***"] * 1200), (jwt_hdr, jwt_short_mid, jwt_sig)),
            (below_cap_ws_jwt, "***", (below_cap_ws_hdr[-32:], jwt_empty_mid)),
            (above_cap_ws_jwt, "***", (above_cap_ws_hdr[-32:], jwt_empty_mid)),
            (above_body_cap_jwt, "***", (above_body_cap_hdr[:32], jwt_empty_mid)),
            (beyond_raw_cap_jwt, "***", (beyond_raw_cap_hdr[-32:], jwt_empty_mid)),
            (oversized_jws, "***", (oversized_jws_hdr[:32], jwt_short_mid, jwt_sig)),
            (oversized_ws_jws, "***", (oversized_ws_jws_hdr[-32:], jwt_short_mid, jwt_sig)),
            (oversized_jws_glued, "***-***", (oversized_jws_hdr[:32], jwt_short_mid, jwt_sig)),
            (oversized_jwe, "***", (oversized_jwe_hdr[:32], jwe_iv, jwe_ct, jwe_tag)),
            (oversized_ws_jwe, "***", (oversized_ws_jwe_hdr[-32:], jwe_iv, jwe_ct, jwe_tag)),
            (beyond_raw_ws_jwe, "***", (beyond_raw_ws_jwe_hdr[-32:], jwe_iv, jwe_ct, jwe_tag)),
            (v11_repeated_qmarks, v11_repeated_qmarks, ()),
            (v11_repeated_jwt_dash, v11_repeated_jwt_dash, ()),
            (v13_repeated_jwt_dot, v13_repeated_jwt_dot, ()),
            (v13_repeated_dots, v13_repeated_dots, ()),
            (malformed_mixed_delim, r'status="ok" \"token\":\"***\"', ("CANARY_BACKTRACK",)),
            (malformed_even_slash, r'note="ok" token=Bearer \"***\"', ("CANARY_V9_EVEN_SLASH",)),
            (malformed_attached_tail, r'note="ok" token=Bearer \"***\" status=ok', ("CANARY_V9_ATTACHED", "prefix")),
            (malformed_quad_slashes, r'note="ok" token=Bearer \"***\"', ("CANARY_V9_QUAD",)),
            (v10_nonquote_slash_val, "token=*** status=ok", ("\\\\",)),
            (v10_nonquote_slash_arr, 'token="***" status=ok', ("\\\\",)),
            (v10_exp_exhausted_key, " status=ok", ("CANARY_V10_EXP", "token")),
            (v10_excess_open_slashes, " status=ok", ("CANARY_V10_OPEN65", "token")),
            (twice_pct_url, "https://example.test/?payload=%257B%2522token%2522%253A%2522***%2522%257D&status=ok", ("CANARY_URL",)),
            (eight_pct_url, "https://example.test/?payload=***&status=ok", ("CANARY_DEEP_PCT", "%25")),
            (escaped_pair_embedded_quote, r'\"token\":\"***\"', ("CANARY_SUFFIX", "prefix")),
            (mixed_escaped_and_unescaped, r'outer="keep" \"token\":\"***\" status=ok', ("CANARY_MIXED", "foo=bar")),
            (unicode_run_input, "!", ()),
            (wrapped_depth_cases[1], "***", ("alpha private tail",)),
            (wrapped_depth_cases[_MAX_SCRUB_DEPTH - 1], "***", ("alpha private tail",)),
            (wrapped_depth_cases[_MAX_SCRUB_DEPTH], "***", ("alpha private tail",)),
            (wrapped_depth_cases[_MAX_SCRUB_DEPTH + 1], "***", ("alpha private tail",)),
            (wrapped_depth_cases[_MAX_SCRUB_DEPTH + 3], "***", ("alpha private tail",)),
        ]:
            caplog.clear()
            err_client = _build_scrubber_route_client(db=db, exc=RuntimeError(case_input))
            with caplog.at_level(logging.WARNING, logger="interfaces.api.v1.workbench.mod_sandbox_routes"):
                resp = err_client.post("/api/v1/llm-control/mods/sandbox-ab-trial", json=payload)
            assert resp.status_code == 502
            detail = resp.json()["detail"]
            log_text = "\n".join(rec.getMessage() for rec in caplog.records)
            assert log_text
            for surface in (detail, log_text):
                assert expected_fragment in surface
                for forbidden in forbidden_fragments:
                    assert forbidden not in surface
        assert (
            f"/outer?{jwt_hdr}.{jwt_cred_payload}.{sk_sig}.{secret_field_key}",
            f"/outer?***.{secret_field_key}",
        ) in recorded_qres
        assert (f"/outer?{sk_pfx}abcdef.{secret_field_key}", "/outer?***") in recorded_qres
        assert (
            f"/{jwt_hdr}.{jwt_cred_payload}.{ghp_sig}.{secret_field_key}",
            f"/***.{secret_field_key}",
        ) in recorded_qres
    finally:
        db.close_all(skip_checkpoint=True)
