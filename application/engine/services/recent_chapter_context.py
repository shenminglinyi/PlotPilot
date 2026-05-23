"""Recent chapter excerpt policy for generation context."""
from __future__ import annotations

from typing import Any, Iterable


def excerpt_immediate_previous_chapter(
    content: str,
    *,
    head_chars: int,
    tail_chars: int,
) -> str:
    """Render the N-1 chapter as a short opening glance plus a longer ending."""
    raw = (content or "").strip()
    if not raw:
        return ""
    if len(raw) <= tail_chars:
        return f"【章末节选，供本章开头承接】\n{raw}"
    if len(raw) <= head_chars + tail_chars:
        return f"【章末节选，供本章开头承接】\n{raw}"
    head = raw[:head_chars]
    tail = raw[-tail_chars:]
    return (
        f"【章首略览】\n{head}……\n"
        f"【章末节选，供本章开头承接】\n{tail}"
    )


def build_recent_chapters_context(
    chapters: Iterable[Any],
    *,
    chapter_number: int,
    limit: int = 5,
    current_beat_index: int = 0,
    prev_head_chars: int,
    prev_tail_chars: int,
    older_head_chars: int,
) -> str:
    """Build the recent-chapter block used by dynamic T2 context."""
    all_chapters = list(chapters)
    recent = sorted(
        [chapter for chapter in all_chapters if chapter.number < chapter_number],
        key=lambda chapter: chapter.number,
        reverse=True,
    )[:limit]

    prev_num = chapter_number - 1
    prev2_num = chapter_number - 2
    lines = ["【最近章节】"]

    for chapter in reversed(recent):
        lines.append(f"\n第 {chapter.number} 章：{chapter.title}")
        body = (chapter.content or "").strip()
        if not body:
            continue
        if chapter.number == prev_num:
            excerpt = excerpt_immediate_previous_chapter(
                chapter.content or "",
                head_chars=prev_head_chars,
                tail_chars=prev_tail_chars,
            )
            if excerpt:
                lines.append(excerpt)
            continue
        if chapter.number == prev2_num:
            tail_n = prev_tail_chars // 2
            tail = body[-tail_n:] if len(body) > tail_n else body
            lines.append(f"【章末节选，供跨章一致性参考】\n{tail}")
            continue
        preview = body[:older_head_chars]
        if len(body) > older_head_chars:
            preview = f"{preview}..."
        lines.append(f"【章首预览】\n{preview}")

    if current_beat_index > 0:
        current_chapter = next(
            (chapter for chapter in all_chapters if chapter.number == chapter_number),
            None,
        )
        if current_chapter and current_chapter.content:
            current_content = current_chapter.content.strip()
            if current_content:
                continuation_preview = (
                    current_content[-2000:]
                    if len(current_content) > 2000
                    else current_content
                )
                lines.append("\n【本章已生成（断点续写上下文）】")
                lines.append(f"当前节拍索引: {current_beat_index}")
                lines.append(f"已生成 {len(current_content)} 字")
                lines.append("---")
                lines.append(continuation_preview)

    return "\n".join(lines)
