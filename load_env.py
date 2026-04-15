"""加载包根目录 `.env` 到 `os.environ`（与 CLI 行为一致，供 `serve` 使用）。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

_PACKAGE_ROOT = Path(__file__).resolve().parent
_ENV_PATH = _PACKAGE_ROOT / ".env"


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
            # 去掉行内注释（# 后面的是注释，但不在引号内的）
            if "#" in v:
                # 简单处理：按 # 分割取第一部分
                v = v.split("#")[0].strip()
            if k:
                os.environ[k] = v
    return env_file
