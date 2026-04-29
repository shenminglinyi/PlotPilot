"""Obsidian long-term memory bridge for PlotPilot Knowledge.

PlotPilot still writes through the existing chapter/Knowledge pipeline. This
service exports PP cache into Markdown and can read supported notes back as the
primary long-term memory source.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from application.paths import DATA_DIR
from domain.knowledge.chapter_summary import ChapterSummary
from domain.knowledge.knowledge_triple import KnowledgeTriple
from domain.knowledge.story_knowledge import StoryKnowledge


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


def _parse_table_cell(value: str) -> str:
    return str(value or "").replace("\\|", "|").strip()


def _parse_tags(value: str) -> List[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _parse_chapter_number(value: str) -> Optional[int]:
    raw = str(value or "").strip()
    match = re.search(r"\d+", raw)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None


def _extract_section(markdown: str, title: str) -> str:
    pattern = re.compile(
        rf"^##\s+{re.escape(title)}\s*$\n(?P<body>.*?)(?=^##\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(markdown)
    if not match:
        return ""
    return match.group("body").strip()


def _extract_frontmatter_value(markdown: str, key: str) -> str:
    if not markdown.startswith("---"):
        return ""
    end = markdown.find("\n---", 3)
    if end < 0:
        return ""
    frontmatter = markdown[3:end]
    for line in frontmatter.splitlines():
        if line.strip().startswith(f"{key}:"):
            return line.split(":", 1)[1].strip()
    return ""


class ObsidianMemoryService:
    """Exports PP cache to Obsidian and reads supported notes back as memory."""

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
        self._write_relationship_graph(novel_dir, knowledge)
        chapter_path = self._write_chapter_note(novel_dir, novel_id, chapter)

        return {
            "synced": True,
            "vault_path": str(self.vault_root),
            "chapter_note": str(chapter_path),
            "fact_count": len(getattr(knowledge, "facts", []) or []),
        }

    def load_knowledge(self, novel_id: str) -> Optional[StoryKnowledge]:
        """Read Obsidian vault notes back as the long-term memory source."""
        novel_dir = self.vault_root / _safe_segment(novel_id)
        if not novel_dir.exists():
            return None

        premise_lock, facts = self._read_fact_locks(novel_dir / "01_Fact_Locks.md")
        chapters = self._read_chapter_notes(novel_dir / "02_Chapters")
        if not premise_lock and not facts and not chapters:
            return None

        return StoryKnowledge(
            novel_id=novel_id,
            premise_lock=premise_lock,
            chapters=chapters,
            facts=facts,
        )

    def has_memory(self, novel_id: str) -> bool:
        return self.load_knowledge(novel_id) is not None

    def get_relationship_graph_path(self, novel_id: str) -> Path:
        return self.vault_root / _safe_segment(novel_id) / "03_Entities" / "Character_Relationships.md"

    def is_vault_configured(self) -> bool:
        return bool(os.getenv(OBSIDIAN_VAULT_ENV, "").strip())

    def is_obsidian_installed(self) -> bool:
        if shutil.which("obsidian"):
            return True
        if sys.platform == "darwin":
            candidates = [
                Path("/Applications/Obsidian.app"),
                Path.home() / "Applications" / "Obsidian.app",
            ]
            return any(path.exists() for path in candidates)
        if sys.platform.startswith("win"):
            candidates = [
                Path(os.getenv("LOCALAPPDATA", "")) / "Obsidian" / "Obsidian.exe",
                Path(os.getenv("PROGRAMFILES", "")) / "Obsidian" / "Obsidian.exe",
            ]
            return any(path.exists() for path in candidates)
        return any(
            Path(path).exists()
            for path in (
                "/usr/bin/obsidian",
                "/usr/local/bin/obsidian",
                "/snap/bin/obsidian",
                "/var/lib/flatpak/exports/bin/md.obsidian.Obsidian",
            )
        )

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

    def _read_fact_locks(self, path: Path) -> tuple[str, List[KnowledgeTriple]]:
        if not path.exists():
            return "", []
        text = path.read_text(encoding="utf-8")
        premise_lock = _extract_section(text, "全书基调").strip()
        facts: List[KnowledgeTriple] = []
        for line in text.splitlines():
            if not line.startswith("|"):
                continue
            if "---" in line or "主体" in line:
                continue
            cells = [_parse_table_cell(part) for part in line.strip().strip("|").split("|")]
            if len(cells) < 3:
                continue
            subject, predicate, obj = cells[:3]
            if not subject or not predicate or not obj:
                continue
            chapter_id = _parse_chapter_number(cells[3] if len(cells) > 3 else "")
            note = cells[4] if len(cells) > 4 else ""
            tags = _parse_tags(cells[5] if len(cells) > 5 else "")
            facts.append(
                KnowledgeTriple(
                    id=f"obsidian-{len(facts) + 1:04d}-{_safe_segment(subject)}-{_safe_segment(predicate)}-{_safe_segment(obj)}",
                    subject=subject,
                    predicate=predicate,
                    object=obj,
                    chapter_id=chapter_id,
                    note=note,
                    tags=tags,
                    source_type="obsidian_primary",
                )
            )
        return premise_lock, facts

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

    def _write_relationship_graph(self, novel_dir: Path, knowledge: Any) -> None:
        facts = getattr(knowledge, "facts", []) or []
        lines = [
            _frontmatter(
                {
                    "type": "plotpilot-relationship-graph",
                    "updated_at": datetime.utcnow().isoformat(),
                    "fact_count": len(facts),
                }
            ),
            "",
            "# 角色 / 故事关系图",
            "",
            "```mermaid",
            "graph LR",
        ]
        edge_count = 0
        for fact in facts:
            subject = _safe_segment(getattr(fact, "subject", ""))
            obj = _safe_segment(getattr(fact, "object", ""))
            predicate = _table_cell(getattr(fact, "predicate", "关联"))
            if not subject or not obj:
                continue
            lines.append(
                f'  {subject}["{_table_cell(getattr(fact, "subject", ""))}"] -->|"{predicate}"| {obj}["{_table_cell(getattr(fact, "object", ""))}"]'
            )
            edge_count += 1
        if edge_count == 0:
            lines.append('  Empty["暂无结构化关系"]')
        lines.extend(["```", ""])
        self._write_text(novel_dir / "03_Entities" / "Character_Relationships.md", "\n".join(lines))

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

    def _read_chapter_notes(self, chapters_dir: Path) -> List[ChapterSummary]:
        if not chapters_dir.exists():
            return []
        chapters: List[ChapterSummary] = []
        for path in sorted(chapters_dir.glob("Chapter_*.md")):
            text = path.read_text(encoding="utf-8")
            chapter_id = _parse_chapter_number(_extract_frontmatter_value(text, "chapter"))
            if chapter_id is None:
                chapter_id = _parse_chapter_number(path.stem)
            if chapter_id is None:
                continue
            beat_lines = []
            beats_text = _extract_section(text, "节拍")
            for line in beats_text.splitlines():
                stripped = line.strip()
                if stripped.startswith("- "):
                    beat_lines.append(stripped[2:].strip())
            chapters.append(
                ChapterSummary(
                    chapter_id=chapter_id,
                    summary=_extract_section(text, "章末摘要"),
                    key_events=_extract_section(text, "关键事件"),
                    open_threads=_extract_section(text, "未解问题 / 伏笔"),
                    consistency_note=_extract_section(text, "连续性说明"),
                    beat_sections=beat_lines,
                    sync_status=_extract_frontmatter_value(text, "sync_status") or "synced",
                )
            )
        return chapters

    @staticmethod
    def _write_text(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
