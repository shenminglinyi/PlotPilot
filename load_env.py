"""加载包根目录 `.env` 到 `os.environ`（与 CLI 行为一致，供 `serve` 使用）。

额外处理代理变量：
- 如果 `.env` 未显式声明代理，则清理继承来的系统代理，避免本地开发进程误走 SOCKS。
- 如果 `.env` 显式声明了代理，则同步写入大小写两套变量，保证 httpx / requests 行为一致。
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

_PACKAGE_ROOT = Path(__file__).resolve().parent
_ENV_PATH = _PACKAGE_ROOT / ".env"
_PROXY_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
_DEFAULT_NO_PROXY = "127.0.0.1,localhost"
_MISSING = object()


def _parse_env_file(env_file: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip()
            if "#" in v:
                v = v.split("#")[0].strip()
            if k:
                values[k] = v
    return values


def _resolve_proxy_value(values: dict[str, str], key: str):
    for candidate in (key, key.lower()):
        if candidate in values:
            value = values[candidate].strip()
            return value or None
    return _MISSING


def _set_env_pair(key: str, value: Optional[str]) -> None:
    variants = (key, key.lower())
    if value is None:
        for candidate in variants:
            os.environ.pop(candidate, None)
        return

    for candidate in variants:
        os.environ[candidate] = value


def _apply_proxy_env(values: dict[str, str]) -> None:
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        proxy_value = _resolve_proxy_value(values, key)
        _set_env_pair(key, None if proxy_value is _MISSING else proxy_value)

    no_proxy_value = _resolve_proxy_value(values, "NO_PROXY")
    if no_proxy_value is _MISSING:
        no_proxy_value = _DEFAULT_NO_PROXY
    _set_env_pair("NO_PROXY", no_proxy_value)

_QUOTED_HASH_PATTERN = re.compile(r'''(?P<in_double_quotes>"[^"]*")|(?P<in_single_quotes>'[^']*')|(?P<comment>#[^\n]*)''')


def _strip_trailing_comment(value: str) -> str:
    """移除值末尾的行内注释，但保留引号内的 # 字符。"""
    in_single = False
    in_double = False
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '#' and not in_single and not in_double:
            return value[:i].rstrip()
        i += 1
    return value


def load_env(path: Optional[Path] = None) -> Optional[Path]:
    """
    读取 KEY=VALUE 行并写入环境变量（覆盖已有键）。
    支持 # 行内注释和 # 整行注释。
    返回已加载的文件路径；未找到文件则返回 None。
    """
    env_file = path or _ENV_PATH
    if not env_file.is_file():
        return None
    values = _parse_env_file(env_file)
    for key, value in values.items():
        if key.upper() in _PROXY_KEYS:
            continue
        os.environ[key] = value

    _apply_proxy_env(values)
    return env_file
