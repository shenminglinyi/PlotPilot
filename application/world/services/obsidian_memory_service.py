"""Obsidian long-term memory mirror for PlotPilot Knowledge.

This service does not replace SQLite Knowledge. It exports the current
chapter-level memory into a Markdown vault so Obsidian can act as a durable,
readable long-term memory surface.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from application.paths import DATA_DIR


OBSIDIAN_VAULT_ENV = "PLOTPILOT_OBSIDIAN_VAULT"


def resolve_obsidian_vault_path() -> Path:
    raw = os.getenv(OBSIDIAN_VAULT_ENV, "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return DATA_DIR / "obsidian-vault"


def _safe_segment(value: str) -> str:
    text = re.sub(r"[\\/:*?\"<>|#^\[\]]+", "-", str(value or "").strip())
    text = re.sub(r"\s+", "-", text).strip(".-")
    return text or "untitled"


def _frontmatter(data: Dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in data.items():
        if isinstance(value, list):
            rendered = "[" + ", ".join(str(item) for item in value) + "]"
        else:
            rendered = str(value).replace("\n", " ")
        lines.append(f"{key}: {rendered}")
    lines.append("---")
    return "\n".join(lines)


def _table_cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


class ObsidianMemoryService:
    """Exports existing PlotPilot Knowledge into an Obsidian-compatible vault."""

    def __init__(self, vault_root: Optional[Path], knowledge_service: Any):
        self.vault_root = Path(vault_root or resolve_obsidian_vault_path()).expanduser()
        self.knowledge_service = knowledge_service

    def sync_chapter(self, novel_id: str, chapter_number: int) -> Dict[str, Any]:
        knowledge = self.knowledge_service.get_knowledge(novel_id)
        chapter = None
        for item in getattr(knowledge, "chapters", []) or []:
            if int(getattr(item, "chapter_id", 0) or 0) == int(chapter_number):
                chapter = item
                break

        if chapter is None:
            return {
                "synced": False,
                "reason": "chapter summary not found",
                "vault_path": str(self.vault_root),
            }

        novel_dir = self.vault_root / _safe_segment(novel_id)
        (novel_dir / "02_Chapters").mkdir(parents=True, exist_ok=True)
        (novel_dir / "03_Entities").mkdir(parents=True, exist_ok=True)
        (novel_dir / "04_Timelines").mkdir(parents=True, exist_ok=True)

        self._write_index(novel_dir, novel_id, knowledge)
        self._write_fact_locks(novel_dir, knowledge)
        self._write_timeline(novel_dir, knowledge)
        chapter_path = self._write_chapter_note(novel_dir, novel_id, chapter)

        return {
            "synced": True,
            "vault_path": str(self.vault_root),
            "chapter_note": str(chapter_path),
            "fact_count": len(getattr(knowledge, "facts", []) or []),
        }

    def _write_index(self, novel_dir: Path, novel_id: str, knowledge: Any) -> None:
        chapters = sorted(getattr(knowledge, "chapters", []) or [], key=lambda item: item.chapter_id)
        lines = [
            _frontmatter(
                {
                    "type": "plotpilot-long-term-memory-index",
                    "novel_id": novel_id,
                    "updated_at": datetime.utcnow().isoformat(),
                }
            ),
            "",
            f"# PlotPilot 长期记忆：{novel_id}",
            "",
            "## 入口",
            "- [[01_Fact_Locks|事实锁 / 长期设定]]",
            "- [[04_Timelines/Timeline|时间线]]",
            "",
            "## 章节记忆",
        ]
        for chapter in chapters:
            number = int(getattr(chapter, "chapter_id", 0) or 0)
            lines.append(f"- [[02_Chapters/Chapter_{number:04d}|第 {number} 章]]")
        self._write_text(novel_dir / "00_Index.md", "\n".join(lines) + "\n")

    def _write_fact_locks(self, novel_dir: Path, knowledge: Any) -> None:
        facts = sorted(getattr(knowledge, "facts", []) or [], key=lambda item: item.id)
        lines = [
            _frontmatter(
                {
                    "type": "plotpilot-fact-locks",
                    "updated_at": datetime.utcnow().isoformat(),
                    "fact_count": len(facts),
                }
            ),
            "",
            "# 事实锁 / 长期设定",
            "",
            "## 全书基调",
            str(getattr(knowledge, "premise_lock", "") or "（暂无）"),
            "",
            "## 知识三元组",
            "| 主体 | 关系 | 客体 | 章节 | 备注 | 标签 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for fact in facts:
            lines.append(
                "| {subject} | {predicate} | {object} | {chapter} | {note} | {tags} |".format(
                    subject=_table_cell(getattr(fact, "subject", "")),
                    predicate=_table_cell(getattr(fact, "predicate", "")),
                    object=_table_cell(getattr(fact, "object", "")),
                    chapter=_table_cell(getattr(fact, "chapter_id", "") or getattr(fact, "first_appearance", "")),
                    note=_table_cell(getattr(fact, "note", "") or getattr(fact, "description", "")),
                    tags=_table_cell(", ".join(getattr(fact, "tags", []) or [])),
                )
            )
        self._write_text(novel_dir / "01_Fact_Locks.md", "\n".join(lines) + "\n")

    def _write_timeline(self, novel_dir: Path, knowledge: Any) -> None:
        chapters = sorted(getattr(knowledge, "chapters", []) or [], key=lambda item: item.chapter_id)
        lines = [
            _frontmatter(
                {
                    "type": "plotpilot-timeline-memory",
                    "updated_at": datetime.utcnow().isoformat(),
                    "chapter_count": len(chapters),
                }
            ),
            "",
            "# 时间线",
            "",
            "| 章节 | 关键事件 | 未解问题 |",
            "| --- | --- | --- |",
        ]
        for chapter in chapters:
            number = int(getattr(chapter, "chapter_id", 0) or 0)
            lines.append(
                "| 第 {number} 章 | {events} | {threads} |".format(
                    number=number,
                    events=_table_cell(getattr(chapter, "key_events", "") or getattr(chapter, "summary", "")),
                    threads=_table_cell(getattr(chapter, "open_threads", "")),
                )
            )
        self._write_text(novel_dir / "04_Timelines" / "Timeline.md", "\n".join(lines) + "\n")

    def _write_chapter_note(self, novel_dir: Path, novel_id: str, chapter: Any) -> Path:
        chapter_number = int(getattr(chapter, "chapter_id", 0) or 0)
        path = novel_dir / "02_Chapters" / f"Chapter_{chapter_number:04d}.md"
        beats = getattr(chapter, "beat_sections", []) or []
        micro_beats = getattr(chapter, "micro_beats", []) or []
        lines = [
            _frontmatter(
                {
                    "type": "plotpilot-chapter-memory",
                    "novel_id": novel_id,
                    "chapter": chapter_number,
                    "sync_status": getattr(chapter, "sync_status", "draft") or "draft",
                    "updated_at": datetime.utcnow().isoformat(),
                    "source": "PlotPilot Knowledge",
                }
            ),
            "",
            f"# 第 {chapter_number} 章长期记忆",
            "",
            "关联：[[../00_Index|长期记忆索引]] · [[01_Fact_Locks]]",
            "",
            "## 章末摘要",
            str(getattr(chapter, "summary", "") or "（暂无）"),
            "",
            "## 关键事件",
            str(getattr(chapter, "key_events", "") or "（暂无）"),
            "",
            "## 未解问题 / 伏笔",
            str(getattr(chapter, "open_threads", "") or "无"),
            "",
            "## 连续性说明",
            str(getattr(chapter, "consistency_note", "") or "（暂无）"),
            "",
            "## 节拍",
        ]
        if beats:
            lines.extend(f"- {beat}" for beat in beats)
        else:
            lines.append("- （暂无）")

        if micro_beats:
            lines.extend(["", "## 微观节拍"])
            for beat in micro_beats:
                if isinstance(beat, dict):
                    lines.append(f"- {beat.get('description', '')}（{beat.get('focus', '')}）")
                else:
                    lines.append(f"- {beat}")

        self._write_text(path, "\n".join(lines) + "\n")
        return path

    @staticmethod
    def _write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
