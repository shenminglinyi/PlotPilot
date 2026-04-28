from domain.knowledge.chapter_summary import ChapterSummary
from domain.knowledge.knowledge_triple import KnowledgeTriple
from domain.knowledge.story_knowledge import StoryKnowledge
from application.engine.services.chapter_aftermath_pipeline import ChapterAftermathPipeline
from application.world.services.obsidian_memory_service import ObsidianMemoryService
import pytest


class FakeKnowledgeService:
    def __init__(self, knowledge):
        self.knowledge = knowledge

    def get_knowledge(self, novel_id: str):
        assert novel_id == self.knowledge.novel_id
        return self.knowledge


def test_sync_chapter_writes_obsidian_long_term_memory(tmp_path):
    knowledge = StoryKnowledge(
        novel_id="novel-obsidian",
        premise_lock="主角必须为每次越级胜利付出代价。",
        chapters=[
            ChapterSummary(
                chapter_id=3,
                summary="林夜击败黄金 Boss，但灵脉受损。",
                key_events="林夜越级战斗；灵脉受损",
                open_threads="灵脉损伤如何恢复",
                consistency_note="战力提升需要代价",
                beat_sections=["遭遇 Boss", "付出代价获胜"],
                sync_status="synced",
            )
        ],
        facts=[
            KnowledgeTriple(
                id="fact-001",
                subject="林夜",
                predicate="战力代价",
                object="灵脉受损",
                chapter_id=3,
                note="避免无代价越级。",
                tags=["战力", "长期记忆"],
            )
        ],
    )
    service = ObsidianMemoryService(tmp_path, FakeKnowledgeService(knowledge))

    result = service.sync_chapter("novel-obsidian", 3)

    assert result["synced"] is True
    assert (tmp_path / "novel-obsidian" / "00_Index.md").exists()
    chapter_note = tmp_path / "novel-obsidian" / "02_Chapters" / "Chapter_0003.md"
    fact_note = tmp_path / "novel-obsidian" / "01_Fact_Locks.md"
    assert chapter_note.exists()
    assert fact_note.exists()

    chapter_text = chapter_note.read_text(encoding="utf-8")
    assert "林夜击败黄金 Boss" in chapter_text
    assert "[[01_Fact_Locks]]" in chapter_text
    assert "sync_status: synced" in chapter_text

    fact_text = fact_note.read_text(encoding="utf-8")
    assert "主角必须为每次越级胜利付出代价" in fact_text
    assert "| 林夜 | 战力代价 | 灵脉受损 |" in fact_text


@pytest.mark.asyncio
async def test_aftermath_pipeline_syncs_obsidian_after_narrative_sync(monkeypatch):
    calls = []

    async def fake_sync(*args, **kwargs):
        calls.append("narrative")
        return {
            "vector_stored": True,
            "foreshadow_stored": True,
            "triples_extracted": True,
        }

    async def fake_infer(novel_id: str, chapter_number: int):
        calls.append("kg")

    class FakeObsidianMemory:
        def sync_chapter(self, novel_id: str, chapter_number: int):
            calls.append(("obsidian", novel_id, chapter_number))
            return {
                "synced": True,
                "chapter_note": "/tmp/vault/novel/02_Chapters/Chapter_0003.md",
            }

    import application.world.services.chapter_narrative_sync as narrative_sync
    import application.engine.services.chapter_aftermath_pipeline as pipeline_module

    monkeypatch.setattr(narrative_sync, "sync_chapter_narrative_after_save", fake_sync)
    monkeypatch.setattr(pipeline_module, "infer_kg_from_chapter", fake_infer)

    pipeline = ChapterAftermathPipeline(
        knowledge_service=object(),
        chapter_indexing_service=None,
        llm_service=object(),
        obsidian_memory_service=FakeObsidianMemory(),
    )

    result = await pipeline.run_after_chapter_saved("novel-obsidian", 3, "正文")

    assert result["narrative_sync_ok"] is True
    assert result["obsidian_memory_synced"] is True
    assert result["obsidian_memory_path"].endswith("Chapter_0003.md")
    assert calls == ["narrative", "kg", ("obsidian", "novel-obsidian", 3)]
