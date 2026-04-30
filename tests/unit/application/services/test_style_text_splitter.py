"""写作手法知识库文本切分测试。"""

from application.style_bible.services.text_splitter import StyleTextSplitter


def test_style_text_splitter_recognizes_chapter_headings():
    text = """
第十二章 雨夜来客

雨落在窗外。

“谁？”

第十三章 门后的人

灯光亮了一下。
""".strip()

    chunks = StyleTextSplitter().split("sample-1", text)
    chapters = [chunk for chunk in chunks if chunk.chunk_type == "chapter"]

    assert [chapter.chapter_number for chapter in chapters] == [12, 13]
    assert [chapter.title for chapter in chapters] == ["第十二章 雨夜来客", "第十三章 门后的人"]
    assert "雨落在窗外" in chapters[0].content
    assert "灯光亮了一下" in chapters[1].content


def test_style_text_splitter_falls_back_to_single_chapter_without_heading():
    chunks = StyleTextSplitter().split("sample-1", "第一段。\n\n第二段。")

    chapters = [chunk for chunk in chunks if chunk.chunk_type == "chapter"]

    assert len(chapters) == 1
    assert chapters[0].chapter_number == 1
    assert chapters[0].title == "全文"
    assert chapters[0].content == "第一段。\n\n第二段。"


def test_style_text_splitter_splits_paragraphs_by_blank_lines():
    chunks = StyleTextSplitter().split("sample-1", "第1章 开端\n\n第一段。\n\n第二段。\n第三行。")
    paragraphs = [chunk for chunk in chunks if chunk.chunk_type == "paragraph"]

    assert [paragraph.content for paragraph in paragraphs] == ["第一段。", "第二段。\n第三行。"]
    assert [paragraph.sequence for paragraph in paragraphs] == [2, 3]


def test_style_text_splitter_preserves_order_and_scene_groups():
    text = "\n\n".join([f"第{i}段，林晚推门看见灯光。" for i in range(1, 9)])

    chunks = StyleTextSplitter(scene_min_chars=30, scene_max_chars=80).split(
        "sample-1",
        text,
    )
    sequences = [chunk.sequence for chunk in chunks]
    scenes = [chunk for chunk in chunks if chunk.chunk_type == "scene"]

    assert sequences == sorted(sequences)
    assert len(scenes) >= 2
    assert all(scene.content for scene in scenes)
    assert chunks[0].chunk_type == "chapter"
