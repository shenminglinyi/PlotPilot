"""Loopback-only API route for in-memory 300-word A/B Mod Sandbox Trial."""
from __future__ import annotations

import base64
import binascii
import json
import logging
import re
from urllib.parse import (
    quote as url_quote,
    unquote as url_unquote,
    unquote_plus as url_unquote_plus,
)

from fastapi import APIRouter, Depends, HTTPException

from application.ai.mod_sandbox_trial_service import (
    ModSandboxAbTrialRequest,
    ModSandboxAbTrialResult,
    ModSandboxTrialService,
    ModSandboxValidationError,
)
from domain.ai.errors import LLMNotConfiguredError
from infrastructure.persistence.database.connection import get_database
from interfaces.api.v1.workbench.llm_control import (
    assert_loopback_request,
    get_llm_control_service_dep,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/llm-control",
    tags=["llm-control"],
    dependencies=[Depends(assert_loopback_request)],
)

_VALID_KEY_CHARS_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_SECRET_KEY_EXACT_RE = re.compile(
    r"^(?:api[-_]?key|key|token|access[-_]?token|refresh[-_]?token|id[-_]?token|"
    r"client[-_]?secret|secret|password|passwd|auth|authorization|"
    r"x-api-key|x-goog-api-key|proxy-authorization|cookie|set-cookie)$",
    re.IGNORECASE,
)
_SECRET_KEY_BOUNDED_SUFFIX_RE = re.compile(
    r"[._-](?:api[-_]?key|key|token|secret|password|passwd|auth|authorization|cookie)$",
    re.IGNORECASE,
)
_SAFE_COUNTER_KEYS = frozenset(
    {
        "max_tokens",
        "max-tokens",
        "prompt_tokens",
        "prompt-tokens",
        "completion_tokens",
        "completion-tokens",
        "total_tokens",
        "total-tokens",
        "input_tokens",
        "input-tokens",
        "output_tokens",
        "output-tokens",
        "cached_tokens",
        "cached-tokens",
    }
)

_AUTH_SCHEME_WORDS = frozenset({"bearer", "basic", "token", "oauth"})
_AUTH_SCHEME_WORD_RE = re.compile(r"(?:Bearer|Basic|Token|OAuth)(?=\s)", re.IGNORECASE)
_UNICODE_QUOTE_ESCAPE_RE = re.compile(
    r"\\(?:u002[27]|U0000002[27]|x2[27])",
    re.IGNORECASE,
)
_KEY_SPLIT_RE = re.compile(r"""[\s?&#,;/{}[\]()=:+'"]+""")
_URL_CREDENTIAL_RE = re.compile(
    r"((?:https?|wss?)://)[^/\s@'\"\\,;{}\[\]()<>?#]+@",
    re.IGNORECASE,
)
_QUERY_DELIMS = frozenset("?&#")
_QUERY_STOP_BASE = frozenset("&#'\"\\,;{}[]()<>")
_PERCENT_ENCODED_RE = re.compile(r"%[0-9A-Fa-f]{2}")
_NON_DELIM_TOKEN_RE = re.compile(r"[^\s'\"\\,;{}\[\]()<>?&#=]+")
_AUTH_SCHEME_RE = re.compile(
    r"\b(Bearer|Basic|Token|OAuth)\s+[^\s&,;'\"{}\[\]()<>]+",
    re.IGNORECASE,
)
_SK_PREFIX_TOKEN_RE = re.compile(
    r"\b(?:sk|rk|pk)-[A-Za-z0-9_.-]{4,}"
    r"|\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{6,}"
    r"|\bgithub_pat_[A-Za-z0-9_]{8,}"
    r"|\bya29\.[A-Za-z0-9_.-]{6,}"
    r"|\bAIza[0-9A-Za-z_-]{12,}"
)
_JWT_CANDIDATE_RUN_RE = re.compile(r"[A-Za-z0-9_.=-]+")
_B64URL_JSON_FIRST_CHARS = frozenset("eICD7")
_JOSE_HEADER_PARAM_KEYS = frozenset(
    {"alg", "enc", "typ", "cty", "kid", "jku", "jwk", "x5u", "x5c", "x5t", "crit"}
)
_MAX_JOSE_DECODE_CHARS = 16384
_MAX_JOSE_RAW_B64_CHARS = 262144
_MAX_PREFIX_SCAN_TAIL = 512
_MAX_PREFIX_BOUNDARY_CHECKS = 8

_MAX_SCRUB_DEPTH = 6
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")
_UK_PREV_BLOCKED = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-%\\=/"
)
_SCALAR_DELIMS = frozenset("&,;)]}")
_MALFORMED_CLOSE_FOLLOWERS = frozenset("&,;)]}:=")
_FALLBACK_UNESCAPE_MAP = {
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "b": "\b",
    "f": "\f",
    '"': '"',
    "'": "'",
    "\\": "\\",
    "/": "/",
}
_ESCAPE_SEQ_RE = re.compile(
    r"\\(?:u([0-9a-fA-F]{4})|U([0-9a-fA-F]{8})|x([0-9a-fA-F]{2})|(.))",
    re.DOTALL,
)
_JSON_DECODER = json.JSONDecoder()


def _is_hex_span(text: str, start: int, count: int) -> bool:
    end = start + count
    if end > len(text):
        return False
    for idx in range(start, end):
        if text[idx] not in _HEX_CHARS:
            return False
    return True


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def _unicode_quote_escape_len(text: str, slash_idx: int) -> int:
    if slash_idx + 3 >= len(text) or text[slash_idx] != "\\":
        return 0
    kind = text[slash_idx + 1]
    if kind == "x" and slash_idx + 4 <= len(text) and text[slash_idx + 2 : slash_idx + 4].lower() in ("22", "27"):
        return 4
    if kind == "u" and slash_idx + 6 <= len(text) and text[slash_idx + 2 : slash_idx + 6].lower() in ("0022", "0027"):
        return 6
    if (
        kind == "U"
        and slash_idx + 10 <= len(text)
        and text[slash_idx + 2 : slash_idx + 10].lower() in ("00000022", "00000027")
    ):
        return 10
    return 0


def _has_unescaped_quote(text: str) -> bool:
    idx = 0
    length = len(text)
    while idx < length:
        ch = text[idx]
        if ch == "\\":
            run_start = idx
            while idx < length and text[idx] == "\\":
                idx += 1
            if (idx - run_start) % 2 == 0 and idx < length and text[idx] in ('"', "'"):
                return True
            idx += 1
            continue
        if ch == '"':
            return True
        if ch == "'" and (idx == 0 or not _is_word_char(text[idx - 1])):
            return True
        idx += 1
    return False


def _has_escaped_quote_seq(text: str) -> bool:
    if _UNICODE_QUOTE_ESCAPE_RE.search(text):
        return True
    idx = 0
    length = len(text)
    while idx < length:
        if text[idx] == "\\":
            run_start = idx
            while idx < length and text[idx] == "\\":
                idx += 1
            slash_count = idx - run_start
            if idx < length and slash_count % 2 == 1:
                q = text[idx]
                if q == '"':
                    return True
                if q == "'" and not (
                    slash_count == 1 and run_start > 0 and _is_word_char(text[run_start - 1])
                ):
                    return True
            continue
        idx += 1
    return False


def _scan_unescaped_string(text: str, quote_idx: int, quote_char: str) -> tuple[str, str, int]:
    """Deterministic single-pass O(L) scanner for `"..."` or `'...'`."""
    idx = quote_idx + 1
    length = len(text)
    while idx < length:
        ch = text[idx]
        if ch == "\\":
            idx += 2
            continue
        if ch == quote_char:
            return text[quote_idx + 1 : idx], quote_char, idx + 1
        idx += 1
    return text[quote_idx + 1 :], "", length


def _is_malformed_close_boundary(text: str, after_quote_idx: int) -> bool:
    if after_quote_idx >= len(text):
        return True
    nxt = text[after_quote_idx]
    if nxt.isspace() or nxt in _MALFORMED_CLOSE_FOLLOWERS:
        return True
    return text.startswith(("\\]", "\\}"), after_quote_idx)


def _scan_escaped_string(
    text: str,
    quote_idx: int,
    quote_char: str,
    open_slashes: int,
) -> tuple[str, str, int]:
    """Deterministic single-pass O(L) scanner for odd-backslash-escaped quotes (e.g. `\\"...\\"`)."""
    idx = quote_idx + 1
    length = len(text)
    period = 2 * (open_slashes + 1)
    well_formed_close = ("\\" * open_slashes) + quote_char
    while idx < length:
        ch = text[idx]
        if ch == "\\":
            run_start = idx
            while idx < length and text[idx] == "\\":
                idx += 1
            slash_count = idx - run_start
            if idx < length and text[idx] == quote_char:
                if slash_count % 2 == 0 or slash_count < open_slashes:
                    if _is_malformed_close_boundary(text, idx + 1):
                        return text[quote_idx + 1 : idx], quote_char, idx + 1
                    idx += 1
                    continue
                if (slash_count - open_slashes) % period == 0:
                    body_end = idx - open_slashes
                    return text[quote_idx + 1 : body_end], well_formed_close, idx + 1
                idx += 1
                continue
            continue
        if ch == quote_char:
            if _is_malformed_close_boundary(text, idx + 1):
                return text[quote_idx + 1 : idx], quote_char, idx + 1
        idx += 1
    return text[quote_idx + 1 :], "", length


def _scan_uk_end(text: str, start: int) -> int:
    """Scan an unquoted key candidate starting at `start` in strictly O(L) steps."""
    idx = start
    length = len(text)
    while idx < length:
        ch = text[idx]
        if ch.isalnum() or ch in "_.-":
            idx += 1
        elif ch == "%" and _is_hex_span(text, idx + 1, 2):
            idx += 3
        elif ch == "\\" and idx + 1 < length:
            if _unicode_quote_escape_len(text, idx) > 0:
                break
            nxt = text[idx + 1]
            if nxt == "u" and _is_hex_span(text, idx + 2, 4):
                idx += 6
            elif nxt == "U" and _is_hex_span(text, idx + 2, 8):
                idx += 10
            elif nxt == "x" and _is_hex_span(text, idx + 2, 2):
                idx += 4
            elif nxt.isalnum() or nxt in "_.-":
                idx += 2
            else:
                break
        else:
            break
    return idx


def _scan_word_with_escapes(text: str, start: int) -> int:
    """Scan a single word (`isalnum`/`_`/non-quote backslash escapes) in O(L) steps."""
    idx = start
    length = len(text)
    while idx < length:
        ch = text[idx]
        if ch.isalnum() or ch == "_":
            idx += 1
        elif ch == "\\" and idx + 1 < length:
            if _unicode_quote_escape_len(text, idx) > 0:
                break
            nxt = text[idx + 1]
            if nxt == "u" and _is_hex_span(text, idx + 2, 4):
                idx += 6
            elif nxt == "U" and _is_hex_span(text, idx + 2, 8):
                idx += 10
            elif nxt == "x" and _is_hex_span(text, idx + 2, 2):
                idx += 4
            elif nxt.isalnum() or nxt == "_":
                idx += 2
            else:
                break
        else:
            break
    return idx


def _match_trailing_auth_scheme(
    text: str,
    span_start: int,
    span_end: int,
    ws_end: int,
) -> tuple[str, int, int, tuple[str, ...]] | None:
    if ws_end <= span_end or ws_end >= len(text) or text[ws_end] in _SCALAR_DELIMS:
        return None
    word_start = span_start
    p = span_start
    while p < span_end:
        ch = text[p]
        if ch in ".-":
            p += 1
            word_start = p
        elif ch == "%" and _is_hex_span(text, p + 1, 2):
            p += 3
            word_start = p
        elif ch == "\\" and p + 1 < span_end:
            nxt = text[p + 1]
            if nxt == "u" and _is_hex_span(text, p + 2, 4):
                code = int(text[p + 2 : p + 6], 16)
                p += 6
                if not (0 <= code <= 0x10FFFF and not (0xD800 <= code <= 0xDFFF) and _is_word_char(chr(code))):
                    word_start = p
            elif nxt == "U" and _is_hex_span(text, p + 2, 8):
                code = int(text[p + 2 : p + 10], 16)
                p += 10
                if not (0 <= code <= 0x10FFFF and not (0xD800 <= code <= 0xDFFF) and _is_word_char(chr(code))):
                    word_start = p
            elif nxt == "x" and _is_hex_span(text, p + 2, 2):
                code = int(text[p + 2 : p + 4], 16)
                p += 4
                if not _is_word_char(chr(code)):
                    word_start = p
            else:
                p += 2
                if nxt in ".-nrtbf":
                    word_start = p
        else:
            p += 1
    if word_start >= span_end or (span_end - word_start) > 64:
        return None
    raw_word = text[word_start:span_end]
    candidate = _decode_escaped_text(raw_word) if "\\" in raw_word else raw_word
    if candidate.lower() not in _AUTH_SCHEME_WORDS:
        return None
    if word_start > span_start and "." in text[span_start:word_start]:
        whole_span = text[span_start:span_end]
        if _JWT_CANDIDATE_RUN_RE.fullmatch(whole_span) and _redact_jwt_in_run(whole_span) != whole_span:
            return None
    return ("auth", word_start, ws_end, (candidate, text[span_end:ws_end]))


def _is_non_secret_b64_padded_or_dotted_lhs(text: str, span_start: int, uk_end: int, ws: int) -> bool:
    if ws != uk_end or ws >= len(text) or text[ws] != "=":
        return False
    raw_uk = text[span_start:uk_end]
    if "%" in raw_uk or "\\" in raw_uk or _is_secret_key_name(raw_uk):
        return False
    if "." in raw_uk or text.startswith("==", uk_end):
        return True
    nxt_idx = uk_end + 1
    return (
        nxt_idx >= len(text)
        or text[nxt_idx] == "."
        or text[nxt_idx].isspace()
        or text[nxt_idx] in _SCALAR_DELIMS
    )


def _advance_past_eq_run(text: str, ws: int) -> int:
    idx = ws
    length = len(text)
    while idx < length and text[idx] == "=":
        idx += 1
    return idx


def _next_lex_token(text: str, pos: int) -> tuple[str, int, int, tuple[str, ...]] | None:
    """Find the next lexical token (`uk`, `auth`, `dq`, `sq`, `edq`, `esq`) in a single O(N) pass."""
    idx = pos
    length = len(text)
    while idx < length:
        ch = text[idx]
        if ch == "\\":
            run_start = idx
            k = idx
            while k < length and text[k] == "\\":
                k += 1
            slash_count = k - run_start
            if k < length and text[k] in ('"', "'"):
                q = text[k]
                if slash_count % 2 == 0:
                    body, close_char, tok_end = _scan_unescaped_string(text, k, q)
                    return ("dq" if q == '"' else "sq", run_start, tok_end, (text[run_start:k], body, close_char))
                if q == "'" and slash_count == 1 and run_start > 0 and _is_word_char(text[run_start - 1]):
                    idx = k + 1
                    continue
                body, close_delim, tok_end = _scan_escaped_string(text, k, q, slash_count)
                open_delim = ("\\" * slash_count) + q
                return ("edq" if q == '"' else "esq", run_start, tok_end, (open_delim, body, close_delim))
            if slash_count % 2 == 1:
                uq_len = _unicode_quote_escape_len(text, k - 1)
                if uq_len > 0:
                    idx = (k - 1) + uq_len
                    continue
            if run_start == 0 or text[run_start - 1] not in _UK_PREV_BLOCKED:
                uk_end = _scan_uk_end(text, run_start)
                if uk_end > run_start:
                    ws = uk_end
                    while ws < length and text[ws].isspace():
                        ws += 1
                    if (
                        ws < length
                        and text[ws] in ("=", ":")
                        and not text.startswith("//", ws + 1)
                        and not _is_non_secret_b64_padded_or_dotted_lhs(text, run_start, uk_end, ws)
                    ):
                        return ("uk", run_start, uk_end, (text[run_start:uk_end],))
                    auth_tok = _match_trailing_auth_scheme(text, run_start, uk_end, ws)
                    if auth_tok is not None:
                        return auth_tok
                    idx = _advance_past_eq_run(text, ws) if ws < length and text[ws] == "=" else ws
                    continue
            elif slash_count == 1 and not _is_word_char(text[run_start - 1]):
                w_end = _scan_word_with_escapes(text, run_start)
                if w_end > run_start:
                    ws = w_end
                    while ws < length and text[ws].isspace():
                        ws += 1
                    if not (ws < length and text[ws] in ("=", ":") and not text.startswith("//", ws + 1)):
                        auth_tok = _match_trailing_auth_scheme(text, run_start, w_end, ws)
                        if auth_tok is not None:
                            return auth_tok
                    idx = ws
                    continue
            idx = k
            continue

        if ch == '"':
            body, close_char, tok_end = _scan_unescaped_string(text, idx, '"')
            return ("dq", idx, tok_end, ("", body, close_char))

        if ch == "'":
            if idx > 0 and _is_word_char(text[idx - 1]):
                idx += 1
                continue
            body, close_char, tok_end = _scan_unescaped_string(text, idx, "'")
            return ("sq", idx, tok_end, ("", body, close_char))

        if (idx == 0 or text[idx - 1] not in _UK_PREV_BLOCKED) and (
            ch.isalnum() or ch in "_.-%"
        ):
            uk_end = _scan_uk_end(text, idx)
            if uk_end > idx:
                ws = uk_end
                while ws < length and text[ws].isspace():
                    ws += 1
                if (
                    ws < length
                    and text[ws] in ("=", ":")
                    and not text.startswith("//", ws + 1)
                    and not _is_non_secret_b64_padded_or_dotted_lhs(text, idx, uk_end, ws)
                ):
                    return ("uk", idx, uk_end, (text[idx:uk_end],))
                auth_tok = _match_trailing_auth_scheme(text, idx, uk_end, ws)
                if auth_tok is not None:
                    return auth_tok
                idx = _advance_past_eq_run(text, ws) if ws < length and text[ws] == "=" else ws
                continue

        if (ch.isalnum() or ch == "_") and (idx == 0 or not _is_word_char(text[idx - 1])):
            w_end = _scan_word_with_escapes(text, idx)
            if w_end > idx:
                ws = w_end
                while ws < length and text[ws].isspace():
                    ws += 1
                if not (ws < length and text[ws] in ("=", ":") and not text.startswith("//", ws + 1)):
                    auth_tok = _match_trailing_auth_scheme(text, idx, w_end, ws)
                    if auth_tok is not None:
                        return auth_tok
                idx = ws
                continue

        idx += 1
    return None


def _is_safe_counter_key(key_lower: str) -> bool:
    if key_lower in _SAFE_COUNTER_KEYS:
        return True
    for sep in (".", "_", "-"):
        if sep in key_lower and key_lower.rsplit(sep, 1)[-1] in _SAFE_COUNTER_KEYS:
            return True
    return False


def _is_secret_key_name(raw_key: str) -> bool:
    key = raw_key.strip()
    if not key or not _VALID_KEY_CHARS_RE.fullmatch(key) or _is_safe_counter_key(key.lower()):
        return False
    if len(key) <= 32 and _SECRET_KEY_EXACT_RE.fullmatch(key):
        return True
    tail = key[-32:] if len(key) > 32 else key
    return bool(_SECRET_KEY_BOUNDED_SUFFIX_RE.search(tail))


def _decode_escape_match(match: re.Match[str]) -> str:
    hex4, hex8, hex2, single = match.groups()
    if hex4 is not None:
        code = int(hex4, 16)
        return "\ufffd" if 0xD800 <= code <= 0xDFFF else chr(code)
    if hex8 is not None:
        code = int(hex8, 16)
        return "\ufffd" if code > 0x10FFFF or (0xD800 <= code <= 0xDFFF) else chr(code)
    if hex2 is not None:
        return chr(int(hex2, 16))
    return _FALLBACK_UNESCAPE_MAP.get(single, single)


def _decode_escaped_text(raw: str) -> str:
    if "\\" not in raw:
        return raw
    trailing_backslash = raw.endswith("\\") and (len(raw) - len(raw.rstrip("\\"))) % 2 == 1
    core = raw[:-1] if trailing_backslash else raw
    decoded = _ESCAPE_SEQ_RE.sub(_decode_escape_match, core)
    return decoded + "\\" if trailing_backslash else decoded


def _decode_key_layers(raw_key: str, depth: int) -> tuple[str, bool]:
    cur = raw_key
    layers = 0
    while "%" in cur or "\\" in cur:
        if depth + layers >= _MAX_SCRUB_DEPTH:
            if _PERCENT_ENCODED_RE.search(cur) or _ESCAPE_SEQ_RE.search(cur):
                return cur, True
            break
        nxt = cur
        if _PERCENT_ENCODED_RE.search(nxt):
            nxt = url_unquote_plus(nxt)
        if "\\" in nxt:
            nxt = _decode_escaped_text(nxt)
        if nxt == cur:
            break
        cur = nxt
        layers += 1
    return cur, False


def _decode_quoted_content(body: str, quote_char: str, close_char: str) -> str:
    if quote_char == '"' and close_char == '"':
        try:
            return json.loads(f'"{body}"')
        except ValueError:
            pass
    return _decode_escaped_text(body)


def _encode_quoted_string(content: str, quote_char: str, close_char: str) -> str:
    if quote_char == '"':
        encoded_inner = json.dumps(content, ensure_ascii=False)[1:-1]
        return f'"{encoded_inner}{close_char}'
    escaped_single = (
        content.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )
    return f"'{escaped_single}{close_char}"


def _reescape_backslash_layer(text: str, escape_double: bool, escape_single: bool) -> str:
    out = text.replace("\\", "\\\\")
    if escape_double:
        out = out.replace('"', '\\"')
    if escape_single:
        out = out.replace("'", "\\'")
    return out


def _scrub_percent_encoded_value(
    raw_val: str,
    depth: int,
    *,
    decode_plus: bool = True,
) -> str:
    layers = 0
    cur = raw_val
    while _PERCENT_ENCODED_RE.search(cur):
        if depth + layers >= _MAX_SCRUB_DEPTH:
            return "***"
        nxt = url_unquote_plus(cur) if decode_plus else url_unquote(cur)
        if nxt == cur:
            break
        cur = nxt
        layers += 1
    if layers == 0:
        return raw_val
    scrubbed = _scrub_text(cur, depth + layers)
    if scrubbed == cur:
        return raw_val
    for _ in range(layers):
        scrubbed = url_quote(scrubbed, safe="*-._~")
    return scrubbed


def _is_query_val_stop(ch: str, *, stop_on_qmark: bool) -> bool:
    return ch.isspace() or ch in _QUERY_STOP_BASE or (stop_on_qmark and ch == "?")


def _is_query_key_stop(ch: str) -> bool:
    return ch == "=" or ch == "?" or ch.isspace() or ch in _QUERY_STOP_BASE


def _scrub_non_delim_tokens(chunk: str, depth: int) -> str:
    if "%" not in chunk:
        return chunk
    return _NON_DELIM_TOKEN_RE.sub(
        lambda pm: _scrub_percent_encoded_value(pm.group(0), depth, decode_plus=False)
        if "%" in pm.group(0)
        else pm.group(0),
        chunk,
    )


def _scrub_secret_key_label(label: str) -> str:
    cleaned = (
        _JWT_CANDIDATE_RUN_RE.sub(lambda m: _redact_jwt_in_run(m.group(0)), label)
        if "." in label
        else label
    )
    return _SK_PREFIX_TOKEN_RE.sub("***", cleaned)


def _resolve_query_secret_key(
    raw_key: str,
    decoded_key: str,
    exhausted: bool,
    depth: int,
) -> str | None:
    if exhausted:
        return "***"
    if _is_secret_key_name(decoded_key):
        scrubbed = _scrub_secret_key_label(decoded_key)
        return raw_key if scrubbed == decoded_key else scrubbed
    if decoded_key and not _KEY_SPLIT_RE.search(decoded_key[-1]):
        parts = _KEY_SPLIT_RE.split(decoded_key)
        tail_key = parts[-1] if parts else ""
        if tail_key and tail_key != decoded_key and _is_secret_key_name(tail_key):
            prefix_decoded = decoded_key[: len(decoded_key) - len(tail_key)]
            prefix_scrubbed = (
                _scrub_text(prefix_decoded, depth + 1) if depth < _MAX_SCRUB_DEPTH else "***"
            )
            return f"{prefix_scrubbed}{_scrub_secret_key_label(tail_key)}"
    return None


def _scrub_query_and_percent_tokens(cleaned: str, depth: int) -> str:
    out_parts: list[str] = []
    plain_start = 0
    idx = 0
    length = len(cleaned)
    while idx < length:
        prefix = cleaned[idx]
        if prefix not in _QUERY_DELIMS:
            idx += 1
            continue
        key_start = idx + 1
        key_end = key_start
        while key_end < length and not _is_query_key_stop(cleaned[key_end]):
            key_end += 1
        if key_end == key_start or key_end >= length or cleaned[key_end] != "=":
            idx = key_end
            continue
        if idx > plain_start:
            out_parts.append(_scrub_non_delim_tokens(cleaned[plain_start:idx], depth))
        raw_key = cleaned[key_start:key_end]
        decoded_key, exhausted = _decode_key_layers(raw_key, depth)
        safe_qkey = _resolve_query_secret_key(raw_key, decoded_key, exhausted, depth)
        is_secret = safe_qkey is not None
        val_start = key_end + 1
        val_end = val_start
        while val_end < length and not _is_query_val_stop(
            cleaned[val_end], stop_on_qmark=not is_secret
        ):
            val_end += 1
        if safe_qkey is not None:
            out_parts.append(f"{prefix}{safe_qkey}=***")
        else:
            raw_val = cleaned[val_start:val_end]
            if _PERCENT_ENCODED_RE.search(raw_val):
                scrubbed_val = _scrub_percent_encoded_value(
                    raw_val, depth, decode_plus=False
                )
                out_parts.append(f"{prefix}{raw_key}={scrubbed_val}")
            else:
                out_parts.append(cleaned[idx:val_end])
        idx = val_end
        plain_start = val_end
    if plain_start < length:
        out_parts.append(_scrub_non_delim_tokens(cleaned[plain_start:], depth))
    return "".join(out_parts)


def _strip_b64_padding(seg: str) -> str | None:
    if not seg:
        return ""
    if "=" not in seg:
        return seg
    if seg.endswith("=="):
        core = seg[:-2]
    elif seg.endswith("="):
        core = seg[:-1]
    else:
        return None
    if not core or "=" in core:
        return None
    return core


def _decode_b64url_json_dict(
    seg: str,
    *,
    max_b64_chars: int = _MAX_JOSE_DECODE_CHARS,
) -> dict[str, object] | None:
    core = _strip_b64_padding(seg)
    if (
        core is None
        or len(core) < 3
        or len(core) > max_b64_chars
        or len(core) % 4 == 1
        or core[0] not in _B64URL_JSON_FIRST_CHARS
    ):
        return None
    padded = core + ("=" * ((4 - (len(core) % 4)) % 4))
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (ValueError, binascii.Error):
        return None
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    stripped_bytes = raw.strip(b" \t\r\n")
    if (
        len(stripped_bytes) < 2
        or len(stripped_bytes) > _MAX_JOSE_DECODE_CHARS
        or not (stripped_bytes.startswith(b"{") and stripped_bytes.endswith(b"}"))
    ):
        return None
    try:
        parsed = json.loads(stripped_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _is_oversized_json_object_b64url(seg: str) -> bool:
    """Bounded check for oversized base64url JSON objects (including whitespace/BOM prefixes)."""
    core = _strip_b64_padding(seg)
    if (
        core is None
        or len(core) <= _MAX_JOSE_DECODE_CHARS
        or len(core) % 4 == 1
        or core[0] not in _B64URL_JSON_FIRST_CHARS
    ):
        return False
    if len(core) <= _MAX_JOSE_RAW_B64_CHARS:
        padded = core + ("=" * ((4 - (len(core) % 4)) % 4))
        try:
            raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        except (ValueError, binascii.Error):
            return False
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]
        stripped = raw.strip(b" \t\r\n")
        if not (stripped.startswith(b"{") and stripped.endswith(b"}")):
            return False
        try:
            stripped.decode("utf-8")
        except UnicodeDecodeError:
            return False
        return True
    head_chunk = core[:64]
    tail_start = max(0, (len(core) - 128) & ~3)
    tail_chunk = core[tail_start:]
    tail_padded = tail_chunk + ("=" * ((4 - (len(tail_chunk) % 4)) % 4))
    try:
        raw_head = base64.urlsafe_b64decode(head_chunk.encode("ascii"))
        raw_tail = base64.urlsafe_b64decode(tail_padded.encode("ascii"))
    except (ValueError, binascii.Error):
        return False
    if raw_head.startswith(b"\xef\xbb\xbf"):
        raw_head = raw_head[3:]
    after_ws = raw_head.lstrip(b" \t\r\n")
    if after_ws and not after_ws.startswith(b"{"):
        return False
    trimmed_tail = raw_tail.rstrip(b" \t\r\n")
    if trimmed_tail and not trimmed_tail.endswith(b"}"):
        return False
    return True


def _is_jose_header_dict(obj: dict[str, object] | None) -> bool:
    if not obj:
        return False
    for key in _JOSE_HEADER_PARAM_KEYS:
        if key not in obj:
            continue
        val = obj[key]
        if isinstance(val, str) and val.strip():
            return True
        if isinstance(val, (list, dict)) and val:
            return True
    return False


def _collect_glued_delim_positions(seg: str, min_pos: int) -> list[int]:
    upper = len(seg) - 3
    if upper <= min_pos:
        return []
    early: list[int] = []
    head_stop = min(upper, min_pos + _MAX_PREFIX_SCAN_TAIL)
    for pos in range(min_pos, head_stop):
        if seg[pos] in "-_" and seg[pos + 1] in _B64URL_JSON_FIRST_CHARS:
            early.append(pos)
            if len(early) >= 4:
                break
    late_rev: list[int] = []
    tail_start = max(head_stop, len(seg) - _MAX_PREFIX_SCAN_TAIL)
    for pos in range(upper - 1, tail_start - 1, -1):
        if seg[pos] in "-_" and seg[pos + 1] in _B64URL_JSON_FIRST_CHARS:
            late_rev.append(pos)
            if len(late_rev) >= _MAX_PREFIX_BOUNDARY_CHECKS:
                break
    early.extend(reversed(late_rev))
    return early


def _match_glued_jose_header(candidate: str) -> tuple[dict[str, object] | None, bool]:
    sub_dict = _decode_b64url_json_dict(candidate, max_b64_chars=_MAX_JOSE_RAW_B64_CHARS)
    if sub_dict and _is_jose_header_dict(sub_dict):
        return (sub_dict, True)
    if len(candidate) > _MAX_JOSE_DECODE_CHARS and _is_oversized_json_object_b64url(candidate):
        return (None, True)
    return (None, False)


def _match_header_in_segment(hdr: str) -> tuple[int, dict[str, object] | None, bool] | None:
    if len(hdr) < 3:
        return None
    pad_trim = hdr[:-2] if hdr.endswith("==") else (hdr[:-1] if hdr.endswith("=") else hdr)
    last_eq = pad_trim.rfind("=")
    base_offset = last_eq + 1 if last_eq != -1 else 0
    hdr_rest = hdr[base_offset:]
    if len(hdr_rest) < 3:
        return None

    hdr_dict = _decode_b64url_json_dict(hdr_rest, max_b64_chars=_MAX_JOSE_RAW_B64_CHARS)
    if hdr_dict:
        return (base_offset, hdr_dict, _is_jose_header_dict(hdr_dict))
    if len(hdr_rest) > _MAX_JOSE_DECODE_CHARS and _is_oversized_json_object_b64url(hdr_rest):
        return (base_offset, None, True)

    for pos in _collect_glued_delim_positions(hdr_rest, 0):
        sub_dict, matched = _match_glued_jose_header(hdr_rest[pos + 1 :])
        if matched:
            return (base_offset + pos + 1, sub_dict, True)
    return None


def _split_sig_segment(sig: str, has_two_more_segs: bool) -> tuple[str, str] | None:
    if not sig:
        return ("", "")
    stripped_full = _strip_b64_padding(sig)
    if stripped_full is None:
        eq_idx = sig.find("=")
        if eq_idx <= 0:
            return None
        end_eq = eq_idx
        while end_eq < len(sig) and sig[end_eq] == "=":
            end_eq += 1
        sep_eq = eq_idx if end_eq == len(sig) else (end_eq - 1)
        core = _strip_b64_padding(sig[:sep_eq])
        if not core:
            return None
        return (core, sig[sep_eq:])

    if has_two_more_segs and ("-" in sig or "_" in sig):
        for pos in _collect_glued_delim_positions(sig, 1):
            _, matched = _match_glued_jose_header(sig[pos + 1 :])
            if matched:
                core_before = _strip_b64_padding(sig[:pos])
                if core_before:
                    return (core_before, sig[pos:])
    return (stripped_full, "")


def _redact_jwt_in_run(run: str) -> str:
    if "." not in run:
        return run
    segs = run.split(".")
    if len(segs) < 3:
        return run
    kept: list[str] = []
    cur_prefix_parts: list[str] = []
    idx = 0
    total = len(segs)
    while idx < total:
        if idx + 2 < total:
            hdr = segs[idx]
            hdr_match = _match_header_in_segment(hdr)
            if hdr_match is not None:
                hdr_jwt_start, hdr_dict, is_jose_hdr = hdr_match
                is_jwe_candidate = (
                    (
                        hdr_dict is not None
                        and isinstance(hdr_dict.get("enc"), str)
                        and bool(str(hdr_dict["enc"]).strip())
                    )
                    or (hdr_dict is None and is_jose_hdr)
                )
                if idx + 4 < total and is_jwe_candidate:
                    ekey_core = _strip_b64_padding(segs[idx + 1])
                    iv_split = _split_sig_segment(segs[idx + 2], True)
                    ct_split = _split_sig_segment(segs[idx + 3], idx + 5 < total)
                    tag_split = _split_sig_segment(segs[idx + 4], idx + 6 < total)
                    if (
                        ekey_core is not None
                        and len(ekey_core) % 4 != 1
                        and iv_split is not None
                        and not iv_split[1]
                        and len(iv_split[0]) >= 2
                        and len(iv_split[0]) % 4 != 1
                        and ct_split is not None
                        and not ct_split[1]
                        and len(ct_split[0]) >= 2
                        and len(ct_split[0]) % 4 != 1
                        and tag_split is not None
                        and len(tag_split[0]) >= 2
                    ):
                        _, tag_tail = tag_split
                        if tag_tail and idx + 6 < total:
                            cur_prefix_parts.append(f"{hdr[:hdr_jwt_start]}***{tag_tail[0]}")
                            segs[idx + 4] = tag_tail[1:]
                            idx += 4
                        else:
                            cur_prefix_parts.append(f"{hdr[:hdr_jwt_start]}***{tag_tail}")
                            kept.append("".join(cur_prefix_parts))
                            cur_prefix_parts = []
                            idx += 5
                        continue

                mid_raw = segs[idx + 1]
                sig_raw = segs[idx + 2]
                mid_core = _strip_b64_padding(mid_raw)
                sig_split = _split_sig_segment(sig_raw, idx + 4 < total)
                if mid_core is not None and len(mid_core) % 4 != 1 and sig_split is not None:
                    sig_core, sig_tail = sig_split
                    alg_none = bool(
                        hdr_dict is not None
                        and isinstance(hdr_dict.get("alg"), str)
                        and str(hdr_dict["alg"]).strip().lower() == "none"
                    )
                    allow_empty_sig = alg_none or (hdr_dict is None and is_jose_hdr)
                    sig_ok = len(sig_core) >= 1 or (
                        sig_core == "" and not sig_tail and allow_empty_sig and len(mid_core) >= 2
                    )
                    if sig_ok:
                        if is_jose_hdr:
                            mid_ok = len(mid_core) >= 2 or (mid_core == "" and len(sig_core) >= 4)
                        else:
                            mid_ok = (
                                _decode_b64url_json_dict(mid_raw) is not None
                                or _is_oversized_json_object_b64url(mid_raw)
                            )
                        if mid_ok:
                            if sig_tail and idx + 4 < total:
                                cur_prefix_parts.append(f"{hdr[:hdr_jwt_start]}***{sig_tail[0]}")
                                segs[idx + 2] = sig_tail[1:]
                                idx += 2
                            else:
                                cur_prefix_parts.append(f"{hdr[:hdr_jwt_start]}***{sig_tail}")
                                kept.append("".join(cur_prefix_parts))
                                cur_prefix_parts = []
                                idx += 3
                            continue
        if cur_prefix_parts:
            cur_prefix_parts.append(segs[idx])
            kept.append("".join(cur_prefix_parts))
            cur_prefix_parts = []
        else:
            kept.append(segs[idx])
        idx += 1
    return ".".join(kept)


def _scrub_unquoted_segment(segment: str, depth: int = 0) -> str:
    if not segment:
        return ""
    if _UNICODE_QUOTE_ESCAPE_RE.search(segment):
        if depth >= _MAX_SCRUB_DEPTH:
            return "***"
        unescaped_layer = _decode_escaped_text(segment)
        if unescaped_layer != segment:
            return _scrub_text(unescaped_layer, depth + 1)

    cleaned = _URL_CREDENTIAL_RE.sub(r"\1***:***@", segment)
    cleaned = _scrub_query_and_percent_tokens(cleaned, depth)
    if "." in cleaned:
        cleaned = _JWT_CANDIDATE_RUN_RE.sub(lambda m: _redact_jwt_in_run(m.group(0)), cleaned)
    cleaned = _AUTH_SCHEME_RE.sub(r"\1 ***", cleaned)
    cleaned = _SK_PREFIX_TOKEN_RE.sub("***", cleaned)
    return cleaned


def _scrub_quoted_non_secret(
    body: str,
    decoded: str,
    quote_char: str,
    close_char: str,
    depth: int,
) -> str:
    if depth >= _MAX_SCRUB_DEPTH:
        if not body:
            return f"{quote_char}{close_char}"
        eff_close = close_char or quote_char
        return f"{quote_char}***{eff_close}"

    scrubbed_inner = _scrub_text(decoded, depth + 1)
    return _encode_quoted_string(scrubbed_inner, quote_char, close_char)


def _scrub_escaped_quoted_non_secret(
    body: str,
    open_delim: str,
    close_delim: str,
    depth: int,
) -> str:
    base_quote = open_delim[-1]
    eff_close = open_delim if (not close_delim or close_delim == base_quote) else close_delim
    open_slashes = len(open_delim) - 1
    if depth >= _MAX_SCRUB_DEPTH or open_slashes > (1 << (_MAX_SCRUB_DEPTH - depth)) - 1:
        if not body:
            return f"{open_delim}{close_delim}"
        return f"{open_delim}***{eff_close}"

    cur = body
    peeled = 0
    while peeled < open_slashes:
        if depth + peeled >= _MAX_SCRUB_DEPTH:
            return f"{open_delim}***{eff_close}"
        nxt = _decode_escaped_text(cur)
        if nxt == cur:
            break
        cur = nxt
        peeled += 1
    scrubbed_inner = _scrub_text(cur, depth + max(1, peeled))
    for _ in range(peeled):
        scrubbed_inner = _reescape_backslash_layer(
            scrubbed_inner,
            escape_double=(base_quote == '"'),
            escape_single=(base_quote == "'"),
        )
    return f"{open_delim}{scrubbed_inner}{eff_close}"


def _redact_secret_container(value: object, depth: int = 0) -> object:
    if depth >= _MAX_SCRUB_DEPTH:
        return "***"
    if isinstance(value, list):
        return [_redact_secret_container(item, depth + 1) for item in value]
    if isinstance(value, dict):
        return {
            _scrub_text(str(k), depth + 1): _redact_secret_container(v, depth + 1)
            for k, v in value.items()
        }
    return "***"


def _step_backslash_or_quote(text: str, idx: int) -> tuple[str, int]:
    """Single-pass step returning ('string', end_idx), ('slashes', run_end), or ('none', idx)."""
    length = len(text)
    if idx >= length:
        return ("none", idx)
    ch = text[idx]
    if ch == '"':
        _, _, end_idx = _scan_unescaped_string(text, idx, '"')
        return ("string", end_idx)
    if ch == "'" and (idx == 0 or not _is_word_char(text[idx - 1])):
        _, _, end_idx = _scan_unescaped_string(text, idx, "'")
        return ("string", end_idx)
    if ch == "\\":
        k = idx
        while k < length and text[k] == "\\":
            k += 1
        slash_count = k - idx
        if k < length and text[k] in ('"', "'"):
            q = text[k]
            if slash_count % 2 == 0:
                _, _, end_idx = _scan_unescaped_string(text, k, q)
                return ("string", end_idx)
            if q == "'" and slash_count == 1 and idx > 0 and _is_word_char(text[idx - 1]):
                return ("slashes", k + 1)
            _, _, end_idx = _scan_escaped_string(text, k, q, slash_count)
            return ("string", end_idx)
        return ("slashes", k)
    return ("none", idx)


def _find_balanced_container_end(
    text: str,
    start_idx: int,
    *,
    escaped_brackets: bool = False,
) -> int:
    depth = 0
    idx = start_idx
    length = len(text)
    while idx < length:
        step_kind, step_end = _step_backslash_or_quote(text, idx)
        if step_kind == "string":
            idx = step_end
            continue
        if step_kind == "slashes":
            if escaped_brackets and (step_end - idx) % 2 == 1 and step_end < length:
                esc_ch = text[step_end]
                if esc_ch in "[{":
                    depth += 1
                    idx = step_end + 1
                    continue
                if esc_ch in "]}":
                    depth -= 1
                    idx = step_end + 1
                    if depth <= 0:
                        return idx
                    continue
            idx = step_end
            continue
        if not escaped_brackets:
            ch = text[idx]
            if ch in "[{(":
                depth += 1
            elif ch in "]})":
                depth -= 1
                if depth <= 0:
                    return idx + 1
        idx += 1
    return length


def _consume_attached_value_tail(text: str, pos: int) -> int:
    length = len(text)
    p = pos
    while p < length and not text[p].isspace() and text[p] not in _SCALAR_DELIMS:
        if text.startswith(("\\]", "\\}"), p):
            break
        step_kind, step_end = _step_backslash_or_quote(text, p)
        if step_kind == "string":
            p = step_end
            continue
        if step_kind == "slashes":
            if (step_end - p) % 2 == 1 and step_end < length and text[step_end] in "]}":
                p = step_end - 1
                break
            p = step_end
            continue
        if text[p] in "[{(":
            p = _find_balanced_container_end(text, p, escaped_brackets=False)
            continue
        p += 1
    return p


def _has_assoc_delimiter_ahead(text: str, pos: int) -> bool:
    length = len(text)
    idx = pos
    while idx < length and text[idx].isspace():
        idx += 1
    return idx < length and text[idx] in ("=", ":") and not text.startswith("//", idx + 1)


def _consume_secret_value(
    text: str,
    idx: int,
    prefix: str,
    scalar_quote: str,
    depth: int,
    *,
    bare_container_fallback: bool = False,
) -> tuple[str, int] | None:
    length = len(text)
    if idx >= length:
        return None

    scheme_words: list[str] = []
    scan_pos = idx
    while len(scheme_words) < 4 and scan_pos < length:
        sm = _AUTH_SCHEME_WORD_RE.match(text, scan_pos)
        if sm is None:
            break
        after_scheme = sm.end()
        while after_scheme < length and text[after_scheme].isspace():
            after_scheme += 1
        if after_scheme >= length or text[after_scheme] in _SCALAR_DELIMS:
            break
        scheme_words.append(sm.group(0))
        scan_pos = after_scheme
    val_start = scan_pos
    scheme_prefix = f"{' '.join(scheme_words)} " if (scheme_words and not scalar_quote) else ""

    ch = text[val_start]
    if ch in ('"', "'"):
        _, _, end_pos = _scan_unescaped_string(text, val_start, ch)
        end_pos = _consume_attached_value_tail(text, end_pos)
        return f"{prefix}{scheme_prefix}{ch}***{ch}", end_pos

    slash_after = val_start
    if ch == "\\":
        k = val_start
        while k < length and text[k] == "\\":
            k += 1
        slash_count = k - val_start
        if k < length and text[k] in ('"', "'"):
            q = text[k]
            if slash_count % 2 == 1:
                _, _, end_pos = _scan_escaped_string(text, k, q, slash_count)
                end_pos = _consume_attached_value_tail(text, end_pos)
                open_delim = ("\\" * slash_count) + q
                return f"{prefix}{scheme_prefix}{open_delim}***{open_delim}", end_pos
            _, _, end_pos = _scan_unescaped_string(text, k, q)
            end_pos = _consume_attached_value_tail(text, end_pos)
            return f"{prefix}{scheme_prefix}{q}***{q}", end_pos
        if slash_count % 2 == 1 and k < length and text[k] in "[{":
            container_end = _find_balanced_container_end(
                text,
                val_start,
                escaped_brackets=True,
            )
            container_end = _consume_attached_value_tail(text, container_end)
            esc_fallback = "***" if bare_container_fallback else r'\"***\"'
            return f"{prefix}{scheme_prefix}{esc_fallback}", container_end
        slash_after = k

    if ch in "[{":
        fallback_token = (
            f"{scalar_quote}***{scalar_quote}"
            if scalar_quote
            else ("***" if bare_container_fallback else '"***"')
        )
        try:
            parsed_container, container_end = _JSON_DECODER.raw_decode(text, val_start)
        except (ValueError, RecursionError):
            container_end = _find_balanced_container_end(
                text,
                val_start,
                escaped_brackets=False,
            )
            container_end = _consume_attached_value_tail(text, container_end)
            return f"{prefix}{scheme_prefix}{fallback_token}", container_end
        tail_end = _consume_attached_value_tail(text, container_end)
        if tail_end > container_end:
            return f"{prefix}{scheme_prefix}{fallback_token}", tail_end
        redacted_container = json.dumps(
            _redact_secret_container(parsed_container, depth + 1),
            ensure_ascii=False,
        )
        return f"{prefix}{scheme_prefix}{redacted_container}", container_end

    if ch.isspace() or ch in _SCALAR_DELIMS:
        return None

    p = _consume_attached_value_tail(text, slash_after)
    if scheme_prefix or bare_container_fallback:
        return f"{prefix}{scheme_prefix}***", p
    if scalar_quote:
        return f"{prefix}{scalar_quote}***{scalar_quote}", p
    return f"{prefix}***", p


def _try_consume_secret_assoc(
    text: str,
    key_end: int,
    rendered_key: str,
    scalar_quote: str,
    depth: int,
) -> tuple[str, int] | None:
    length = len(text)
    idx = key_end
    while idx < length and text[idx].isspace():
        idx += 1
    if idx >= length or text[idx] not in ("=", ":") or text.startswith("//", idx + 1):
        return None
    idx += 1
    while idx < length and text[idx].isspace():
        idx += 1
    sep = text[key_end:idx]
    if idx >= length:
        return None
    return _consume_secret_value(
        text,
        idx,
        f"{rendered_key}{sep}",
        scalar_quote,
        depth,
    )


def _scrub_text(text: str, depth: int = 0) -> str:
    if not text:
        return ""
    if not _has_unescaped_quote(text) and _has_escaped_quote_seq(text):
        has_escaped_dq = '\\"' in text
        has_escaped_sq = "\\'" in text
        if depth >= _MAX_SCRUB_DEPTH:
            return "***"
        unescaped_layer = _decode_escaped_text(text)
        if unescaped_layer != text:
            scrubbed_layer = _scrub_text(unescaped_layer, depth + 1)
            if has_escaped_dq or has_escaped_sq:
                return _reescape_backslash_layer(
                    scrubbed_layer,
                    escape_double=has_escaped_dq,
                    escape_single=has_escaped_sq,
                )
            return scrubbed_layer

    out: list[str] = []
    pos = 0
    length = len(text)
    while pos < length:
        tok = _next_lex_token(text, pos)
        if tok is None:
            out.append(_scrub_unquoted_segment(text[pos:], depth))
            break
        kind, start, end, meta = tok
        gap = text[pos:start]
        if start > pos:
            out.append(_scrub_unquoted_segment(gap, depth))

        if kind == "uk":
            raw_key = meta[0]
            decoded_key, key_exhausted = _decode_key_layers(raw_key, depth)
            if key_exhausted:
                consumed = _try_consume_secret_assoc(text, end, "***", "", depth)
                if consumed is not None:
                    redacted_pair, next_pos = consumed
                    out.append(redacted_pair)
                    pos = next_pos
                    continue
            if _is_secret_key_name(decoded_key):
                stripped_uk = decoded_key.strip()
                scrubbed_uk = _scrub_secret_key_label(stripped_uk)
                rendered_uk = raw_key if ("%" in raw_key and scrubbed_uk == stripped_uk) else scrubbed_uk
                consumed = _try_consume_secret_assoc(text, end, rendered_uk, "", depth)
                if consumed is not None:
                    redacted_pair, next_pos = consumed
                    out.append(redacted_pair)
                    pos = next_pos
                    continue
            if decoded_key and not _KEY_SPLIT_RE.search(decoded_key[-1]):
                parts = _KEY_SPLIT_RE.split(decoded_key)
                tail_key = parts[-1] if parts else ""
                if tail_key and tail_key != decoded_key and _is_secret_key_name(tail_key):
                    prefix_decoded = decoded_key[: len(decoded_key) - len(tail_key)]
                    prefix_scrubbed = (
                        _scrub_text(prefix_decoded, depth + 1)
                        if depth < _MAX_SCRUB_DEPTH
                        else "***"
                    )
                    consumed = _try_consume_secret_assoc(
                        text, end, f"{prefix_scrubbed}{_scrub_secret_key_label(tail_key)}", "", depth
                    )
                    if consumed is not None:
                        redacted_pair, next_pos = consumed
                        out.append(redacted_pair)
                        pos = next_pos
                        continue
            out.append(_scrub_unquoted_segment(raw_key, depth))
            pos = end
            continue

        if kind == "auth":
            scheme_word, ws_sep = meta
            consumed_auth = _consume_secret_value(
                text, end, f"{scheme_word}{ws_sep}", "", depth, bare_container_fallback=True
            )
            if consumed_auth is not None:
                redacted_auth, next_pos = consumed_auth
                out.append(redacted_auth)
                pos = next_pos
                continue
            out.append(f"{scheme_word}{ws_sep}")
            pos = end
            continue

        if kind in ("edq", "esq"):
            open_delim, body, close_delim = meta
            base_quote = open_delim[-1]
            eff_close = open_delim if (not close_delim or close_delim == base_quote) else close_delim
            open_slashes = len(open_delim) - 1
            if close_delim and _has_assoc_delimiter_ahead(text, end):
                if depth >= _MAX_SCRUB_DEPTH or open_slashes > (1 << (_MAX_SCRUB_DEPTH - depth)) - 1:
                    semantic_key, key_exhausted = "", True
                else:
                    semantic_key, key_exhausted = _decode_key_layers(
                        _decode_quoted_content(_decode_escaped_text(body), base_quote, base_quote),
                        depth + 1,
                    )
                if key_exhausted or _is_secret_key_name(semantic_key):
                    rendered_ekey = (
                        f"{open_delim}***{eff_close}"
                        if key_exhausted
                        else f"{open_delim}{_scrub_secret_key_label(semantic_key.strip())}{eff_close}"
                    )
                    consumed = _try_consume_secret_assoc(
                        text, end, rendered_ekey, open_delim, depth
                    )
                    if consumed is not None:
                        redacted_pair, next_pos = consumed
                        out.append(redacted_pair)
                        pos = next_pos
                        continue

            out.append(_scrub_escaped_quoted_non_secret(body, open_delim, close_delim, depth))
            pos = end
            continue

        lead_slashes, body, close_char = meta
        quote_char = '"' if kind == "dq" else "'"
        if lead_slashes:
            out.append(lead_slashes)

        decoded_str = _decode_quoted_content(body, quote_char, close_char)
        if close_char and _has_assoc_delimiter_ahead(text, end):
            semantic_qkey, qkey_exhausted = _decode_key_layers(decoded_str, depth + 1)
            if qkey_exhausted or _is_secret_key_name(semantic_qkey):
                rendered_key = (
                    f"{quote_char}***{close_char}"
                    if qkey_exhausted
                    else _encode_quoted_string(_scrub_secret_key_label(semantic_qkey), quote_char, close_char)
                )
                consumed = _try_consume_secret_assoc(
                    text, end, rendered_key, quote_char, depth
                )
                if consumed is not None:
                    redacted_pair, next_pos = consumed
                    out.append(redacted_pair)
                    pos = next_pos
                    continue

        out.append(_scrub_quoted_non_secret(body, decoded_str, quote_char, close_char, depth))
        pos = end
    return "".join(out)


def _scrub_secret_tokens(message: str) -> str:
    """Redact credentials, quoted JSON/KV secret fields (including escaped keys/values & deep nesting), API keys, OAuth tokens, and URL userinfo."""
    if not message:
        return "上游返回未知错误"
    return _scrub_text(message, depth=0)


def get_mod_sandbox_trial_service() -> ModSandboxTrialService:
    return ModSandboxTrialService(
        db_provider=get_database,
        control_service=get_llm_control_service_dep(),
    )


@router.post("/mods/sandbox-ab-trial", response_model=ModSandboxAbTrialResult)
async def run_mod_sandbox_ab_trial(
    payload: ModSandboxAbTrialRequest,
    service: ModSandboxTrialService = Depends(get_mod_sandbox_trial_service),
) -> ModSandboxAbTrialResult:
    """Execute a side-effect-free in-memory 300-word A/B trial for a candidate Mod pack."""
    try:
        return await service.run_ab_trial(payload)
    except ModSandboxValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LLMNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        scrubbed = _scrub_secret_tokens(str(exc))
        logger.warning("Mod sandbox A/B trial failed: %s", scrubbed)
        raise HTTPException(
            status_code=502,
            detail=f"模组沙盒试写调用失败：{scrubbed}",
        ) from exc
