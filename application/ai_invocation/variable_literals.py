"""Variable value literal parsing for interactive definition inputs."""
from __future__ import annotations

from typing import Any


def parse_variable_literal(value: Any) -> Any:
    """Parse relaxed object/list literals used when defining variable values.

    Variable reads use template expressions such as ``{{ a.b }}``.
    Variable definitions use structured value literals such as ``{a: b}`` or
    ``{a: [b, c]}``. Non-structured strings remain unchanged.
    """
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "{[":
        return value
    try:
        import yaml  # type: ignore

        parsed = yaml.safe_load(text)
    except Exception:
        return value
    return value if parsed is None else parsed
