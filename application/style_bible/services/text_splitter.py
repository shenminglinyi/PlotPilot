"""写作手法知识库文本切分。"""
from __future__ import annotations

import re

from domain.style_bible.entities import StyleSampleChunk


class StyleTextSplitter:
    """把参考文本切成章节、场景和段落。"""

    CHAPTER_HEADING_RE = re.compile(
        r"^\s*(第(?P<num>[一二三四五六七八九十百千万零〇两0-9]+)章[^\n]*)\s*$"
    )
    BLANK_LINE_RE = re.compile(r"\n\s*\n+")

    def __init__(
        self,
        scene_min_chars: int = 1200,
        scene_max_chars: int = 2500,
        long_paragraph_chars: int = 900,
    ):
        self.scene_min_chars = max(1, int(scene_min_chars or 1200))
        self.scene_max_chars = max(self.scene_min_chars, int(scene_max_chars or 2500))
        self.long_paragraph_chars = max(100, int(long_paragraph_chars or 900))

    def split(self, sample_id: str, text: str) -> list[StyleSampleChunk]:
        content = (text or "").strip()
        if not content:
            return []

        chunks: list[StyleSampleChunk] = []
        sequence = 1
        for chapter_number, title, chapter_text in self._split_chapters(content):
            chapter = StyleSampleChunk(
                sample_id=sample_id,
                chunk_type="chapter",
                sequence=sequence,
                chapter_number=chapter_number,
                title=title,
                content=chapter_text,
            )
            chunks.append(chapter)
            sequence += 1

            paragraphs = self._split_paragraphs(chapter_text)
            for paragraph in paragraphs:
                chunks.append(
                    StyleSampleChunk(
                        sample_id=sample_id,
                        chunk_type="paragraph",
                        sequence=sequence,
                        chapter_number=chapter_number,
                        content=paragraph,
                    )
                )
                sequence += 1

            for scene in self._split_scenes(paragraphs):
                chunks.append(
                    StyleSampleChunk(
                        sample_id=sample_id,
                        chunk_type="scene",
                        sequence=sequence,
                        chapter_number=chapter_number,
                        content=scene,
                    )
                )
                sequence += 1

        return chunks

    def _split_chapters(self, text: str) -> list[tuple[int, str, str]]:
        lines = text.splitlines()
        headings: list[tuple[int, int, str]] = []
        for index, line in enumerate(lines):
            match = self.CHAPTER_HEADING_RE.match(line)
            if match:
                headings.append((index, self._parse_chapter_number(match.group("num")), match.group(1).strip()))

        if not headings:
            return [(1, "全文", text)]

        chapters: list[tuple[int, str, str]] = []
        for item_index, (line_index, chapter_number, title) in enumerate(headings):
            next_line_index = (
                headings[item_index + 1][0] if item_index + 1 < len(headings) else len(lines)
            )
            chapter_text = "\n".join(lines[line_index + 1 : next_line_index]).strip()
            if chapter_text:
                chapters.append((chapter_number, title, chapter_text))
        return chapters or [(1, "全文", text)]

    def _split_paragraphs(self, text: str) -> list[str]:
        paragraphs = [
            paragraph.strip()
            for paragraph in self.BLANK_LINE_RE.split(text.strip())
            if paragraph.strip()
        ]
        result: list[str] = []
        for paragraph in paragraphs or [text.strip()]:
            if len(paragraph) <= self.long_paragraph_chars:
                result.append(paragraph)
                continue
            result.extend(self._split_long_paragraph(paragraph))
        return result

    def _split_long_paragraph(self, paragraph: str) -> list[str]:
        sentences = [item.strip() for item in re.findall(r".+?[。！？!?]|.+$", paragraph) if item.strip()]
        result: list[str] = []
        buffer = ""
        for sentence in sentences:
            if buffer and len(buffer) + len(sentence) > self.long_paragraph_chars:
                result.append(buffer)
                buffer = sentence
            else:
                buffer = f"{buffer}{sentence}" if buffer else sentence
        if buffer:
            result.append(buffer)
        return result

    def _split_scenes(self, paragraphs: list[str]) -> list[str]:
        scenes: list[str] = []
        buffer: list[str] = []
        buffer_chars = 0
        for paragraph in paragraphs:
            paragraph_len = len(paragraph)
            should_flush = (
                buffer
                and buffer_chars >= self.scene_min_chars
                and buffer_chars + paragraph_len > self.scene_max_chars
            )
            if should_flush:
                scenes.append("\n\n".join(buffer))
                buffer = []
                buffer_chars = 0
            buffer.append(paragraph)
            buffer_chars += paragraph_len
        if buffer:
            scenes.append("\n\n".join(buffer))
        return scenes

    @classmethod
    def _parse_chapter_number(cls, value: str) -> int:
        text = (value or "").strip()
        if text.isdigit():
            return max(1, int(text))
        return max(1, cls._parse_chinese_number(text))

    @staticmethod
    def _parse_chinese_number(text: str) -> int:
        digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
                  "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
        units = {"十": 10, "百": 100, "千": 1000, "万": 10000}
        total = 0
        section = 0
        number = 0
        for char in text:
            if char in digits:
                number = digits[char]
            elif char in units:
                unit = units[char]
                if unit == 10000:
                    section = (section + number) * unit
                    total += section
                    section = 0
                else:
                    section += (number or 1) * unit
                number = 0
        return total + section + number
