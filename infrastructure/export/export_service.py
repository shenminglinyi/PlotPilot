import io
from typing import List
from ebooklib import epub
from domain.novel.entities.novel import Novel
from domain.novel.entities.chapter import Chapter


class ExportService:

    def __init__(self, chapter_repository):
        self.chapter_repository = chapter_repository

    def _get_chapters(self, novel: Novel) -> List[Chapter]:
        return self.chapter_repository.list_by_novel(novel.novel_id)

    def export_txt(self, novel: Novel, chapters: List[Chapter] = None) -> bytes:
        if chapters is None:
            chapters = self._get_chapters(novel)
        parts = []
        for ch in chapters:
            header = f"# 第{ch.number}章 {ch.title}"
            parts.append(f"{header}\n\n{ch.content}")
        body = "\n\n".join(parts)
        full = f"{novel.title}\n作者：{novel.author}\n\n{body}"
        return full.encode("utf-8")

    def export_markdown(self, novel: Novel, chapters: List[Chapter] = None) -> bytes:
        if chapters is None:
            chapters = self._get_chapters(novel)
        lines = [f"# {novel.title}\n"]
        lines.append(f"**作者**：{novel.author}\n")
        lines.append("## 目录\n")
        for ch in chapters:
            lines.append(f"- [第{ch.number}章 {ch.title}](#第{ch.number}章-{ch.title})")
        lines.append("")
        for ch in chapters:
            lines.append(f"## 第{ch.number}章 {ch.title}\n")
            lines.append(ch.content)
            lines.append("")
        return "\n".join(lines).encode("utf-8")

    def export_epub(self, novel: Novel, chapters: List[Chapter] = None) -> bytes:
        if chapters is None:
            chapters = self._get_chapters(novel)
        book = epub.EpubBook()
        book.set_identifier(novel.novel_id.value)
        book.set_title(novel.title)
        book.set_language("zh")
        book.add_author(novel.author)

        spine = ["nav"]
        toc = []
        for ch in chapters:
            chapter_id = f"chapter_{ch.number}"
            epub_ch = epub.EpubHtml(
                title=f"第{ch.number}章 {ch.title}",
                file_name=f"{chapter_id}.xhtml",
                lang="zh",
            )
            epub_ch.content = (
                f"<html><body><h1>第{ch.number}章 {ch.title}</h1>"
                f"<div>{self._text_to_html(ch.content)}</div>"
                f"</body></html>"
            )
            book.add_item(epub_ch)
            spine.append(epub_ch)
            toc.append(epub_ch)

        book.toc = toc
        book.spine = spine
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())

        buf = io.BytesIO()
        epub.write_epub(buf, book, {})
        return buf.getvalue()

    @staticmethod
    def _text_to_html(text: str) -> str:
        paragraphs = text.split("\n")
        html_parts = []
        for p in paragraphs:
            stripped = p.strip()
            if stripped:
                html_parts.append(f"<p>{stripped}</p>")
        return "\n".join(html_parts)
