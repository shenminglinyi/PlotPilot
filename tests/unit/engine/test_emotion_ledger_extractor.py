"""EmotionLedger 提取与持久化测试"""
import json
import sqlite3
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.ai.services.llm_service import GenerationResult
from domain.ai.value_objects.token_usage import TokenUsage
from engine.core.entities.story import StoryId
from engine.core.value_objects.emotion_ledger import (
    EmotionLedger,
    EmotionalWound,
    OpenLoop,
)
from engine.infrastructure.memory.emotion_ledger_extractor import EmotionLedgerExtractor
from engine.infrastructure.memory.memory_orchestrator_impl import MemoryOrchestratorImpl


def test_emotion_ledger_from_dict_roundtrip():
    ledger = (
        EmotionLedger.create_empty()
        .add_wound(EmotionalWound(description="失去师父", impact="多疑", chapter_number=3))
        .add_open_loop(OpenLoop(description="身世之谜", hint="血脉", planted_chapter=1, urgency=0.8))
    )
    restored = EmotionLedger.from_dict(ledger.to_dict())
    assert len(restored.wounds) == 1
    assert restored.wounds[0].chapter_number == 3
    assert restored.open_loops[0].planted_chapter == 1
    assert restored.open_loops[0].urgency == 0.8


def test_merge_ledger_appends_and_closes_loops():
    extractor = EmotionLedgerExtractor()
    current = EmotionLedger.create_empty().add_open_loop(
        OpenLoop(description="密信下落", hint="师父遗物", planted_chapter=2)
    )
    deltas = {
        "wounds": [{"description": "同伴牺牲", "impact": "自责"}],
        "boons": [{"description": "获得传承", "value": "实力突破"}],
        "power_shifts": [{"from_state": "被动", "to_state": "主动", "trigger": "觉醒"}],
        "open_loops": [{"description": "幕后黑手", "hint": "组织名", "urgency": 0.9}],
        "resolved_loops": ["密信下落"],
    }
    updated = extractor.merge_ledger(current, deltas, chapter_number=5)
    assert len(updated.wounds) == 1
    assert len(updated.boons) == 1
    assert len(updated.power_shifts) == 1
    assert len(updated.open_loops) == 1
    assert updated.open_loops[0].description == "幕后黑手"
    assert updated.wounds[0].chapter_number == 5


@pytest.mark.asyncio
async def test_extract_deltas_parses_llm_json():
    llm = AsyncMock()
    llm.generate.return_value = GenerationResult(
        content=json.dumps({
            "wounds": [{"description": "失去信任", "impact": "多疑"}],
            "boons": [],
            "power_shifts": [],
            "open_loops": [],
            "resolved_loops": [],
        }),
        token_usage=TokenUsage(input_tokens=10, output_tokens=20),
    )
    extractor = EmotionLedgerExtractor(llm_service=llm)
    deltas = await extractor.extract_deltas(
        chapter_content="林羽站在雨里，师父的背叛像刀一样扎进心里。" * 10,
        chapter_number=4,
        current_ledger=EmotionLedger.create_empty(),
    )
    assert len(deltas["wounds"]) == 1
    assert deltas["wounds"][0]["description"] == "失去信任"


@pytest.mark.asyncio
async def test_extract_deltas_returns_empty_without_llm():
    extractor = EmotionLedgerExtractor(llm_service=None)
    deltas = await extractor.extract_deltas(
        chapter_content="x" * 200,
        chapter_number=1,
        current_ledger=EmotionLedger.create_empty(),
    )
    assert deltas["wounds"] == []


@pytest.mark.asyncio
async def test_update_emotion_ledger_persists_to_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE checkpoints (
            id TEXT PRIMARY KEY,
            story_id TEXT NOT NULL,
            emotion_ledger TEXT NOT NULL DEFAULT '{}',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        """CREATE TABLE checkpoint_heads (
            story_id TEXT PRIMARY KEY,
            checkpoint_id TEXT NOT NULL
        )"""
    )
    conn.execute(
        "INSERT INTO checkpoints (id, story_id, emotion_ledger) VALUES ('cp-1', 'novel-1', '{}')"
    )
    conn.execute(
        "INSERT INTO checkpoint_heads (story_id, checkpoint_id) VALUES ('novel-1', 'cp-1')"
    )
    conn.commit()

    db_pool = MagicMock()
    db_pool.get_connection.return_value = conn

    llm = AsyncMock()
    llm.generate.return_value = GenerationResult(
        content=json.dumps({
            "wounds": [{"description": "师父失踪", "impact": "焦虑"}],
            "boons": [],
            "power_shifts": [],
            "open_loops": [{"description": "密信", "hint": "藏宝图", "urgency": 0.6}],
            "resolved_loops": [],
        }),
        token_usage=TokenUsage(input_tokens=10, output_tokens=20),
    )

    orchestrator = MemoryOrchestratorImpl(db_pool=db_pool, llm_service=llm)
    updated = await orchestrator.update_emotion_ledger(
        story_id=StoryId("novel-1"),
        chapter_number=7,
        chapter_content="师父失踪后，林羽彻夜难眠，翻遍了师父留下的所有遗物。" * 10,
    )

    assert len(updated.wounds) == 1
    assert len(updated.open_loops) == 1

    row = conn.execute(
        "SELECT emotion_ledger FROM checkpoints WHERE id = 'cp-1'"
    ).fetchone()
    stored = json.loads(row["emotion_ledger"])
    assert len(stored["wounds"]) == 1
    assert stored["wounds"][0]["chapter"] == 7
