"""同章多节拍续写：将已生成正文注入后续节拍 prompt，减少重复铺垫与对白。"""


# 单章内累计正文注入上限，避免撑爆上下文；超长时保留尾部（离当前节拍最近）
_MAX_PRIOR_DRAFT_CHARS = 14_000


def format_prior_draft_for_prompt(chapter_draft_so_far: str) -> str:
    """将本章已写片段格式化为可拼入 user prompt 的正文（可能截断并加说明）。"""
    raw = (chapter_draft_so_far or "").strip()
    if not raw:
        return ""
    if len(raw) <= _MAX_PRIOR_DRAFT_CHARS:
        return raw
    tail = raw[-_MAX_PRIOR_DRAFT_CHARS:]
    omitted = len(raw) - _MAX_PRIOR_DRAFT_CHARS
    return f"…（已省略本章前段约 {omitted} 字，以下从更近情节接续）\n{tail}"
