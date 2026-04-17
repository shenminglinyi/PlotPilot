"""加载包根目录 `.env` 到 `os.environ`（与 CLI 行为一致，供 `serve` 使用）。"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

_PACKAGE_ROOT = Path(__file__).resolve().parent
_ENV_PATH = _PACKAGE_ROOT / ".env"

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
            v = _strip_trailing_comment(v)
            if k:
                os.environ[k] = v
    return env_file
